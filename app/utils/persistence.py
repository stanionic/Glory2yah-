"""Durable-storage canary + SQLite inventory.

WHY THIS EXISTS
===============
On Render the container filesystem is rebuilt from the build image on every
deploy, and a free instance that spins down can come back on a fresh one. Only a
mounted *persistent disk* keeps its files. The app used to "verify" persistence
by writing a marker file and reading it back immediately — a test that passes on
a completely ephemeral filesystem too. Meanwhile real users were losing their
accounts (they log out, then the identifier "does not exist" anymore, so they
register again). That check therefore told everyone the opposite of the truth.

The only honest test is *across boots*: record a boot entry in the instance
folder, and on the next boot look for the previous entry.
  - previous entry found   -> storage really is durable           (persisted=True)
  - previous entry missing -> either the very first boot ever, or the folder was
                              reset. Not distinguishable from one copy alone, so
                              a second copy (the "mirror") is written OUTSIDE the
                              instance folder, i.e. on the container filesystem
                              that Render rebuilds at every deploy:
                                mirror present + journal gone  -> instance/ was
                                  wiped between two boots => persisted=False.
                                neither present                -> first boot, no
                                  evidence yet => persisted=None.
The journal also keeps the users/ads counters and the SECRET_KEY fingerprint, so
one glance at /health shows whether accounts or signing keys are being lost.

Everything here is read-only apart from appending to the journal, never raises,
and exposes no secret material (the key fingerprint is a truncated hash).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sqlite3
import time
import uuid

JOURNAL_NAME = '.boot_journal.jsonl'
MIRROR_NAME = '.g2y_boot_mirror.json'
_MAX_ENTRIES_KEPT = 40


def _journal_path(inst_dir):
    return os.path.join(inst_dir, JOURNAL_NAME)


def _mirror_path(root_dir):
    """Pointer that lives on the (always ephemeral) code filesystem.

    It proves "this machine has booted the app before" independently of the
    instance folder, which is what turns an absent journal from 'unknown' into
    a proven wipe.
    """
    if not root_dir:
        return None
    return os.path.join(root_dir, MIRROR_NAME)


def read_previous_boots(inst_dir, limit: int = 5):
    """Most-recent-first list of previous boot records. Empty list = none yet."""
    path = _journal_path(inst_dir)
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return list(reversed(out[-limit:]))


def count_rows(db_path, table='users'):
    """Row count of one table in a SQLite file; 0 when unavailable. Read-only."""
    try:
        if not (db_path and os.path.isfile(db_path)):
            return 0
        # 'file:...?mode=ro' keeps SQLite from creating/altering anything.
        con = sqlite3.connect(f'file:{db_path.replace(os.sep, "/")}?mode=ro', uri=True)
        try:
            cur = con.cursor()
            cur.execute(f'SELECT COUNT(1) FROM "{table}"')
            return int(cur.fetchone()[0] or 0)
        finally:
            con.close()
    except Exception:
        return 0


def sqlite_inventory(inst_dir, current_db_path=None, limit: int = 8):
    """Every *.db in the instance folder with its users count, newest first.

    Used to spot the "accounts are alive but in another file" failure mode,
    which is what a filename switch (dev -> prod fallback) produces.
    """
    out = []
    try:
        paths = glob.glob(os.path.join(inst_dir, '*.db'))
    except Exception:
        paths = []
    cur_norm = None
    if current_db_path:
        try:
            cur_norm = os.path.normcase(os.path.abspath(current_db_path))
        except Exception:
            cur_norm = None
    for p in paths:
        try:
            st = os.stat(p)
        except Exception:
            continue
        out.append({
            'file': os.path.basename(p),
            'bytes': int(st.st_size),
            'mtime': int(st.st_mtime),
            'users': count_rows(p, 'users'),
            'ads': count_rows(p, 'ads'),
            # normcase+abspath: the SQLAlchemy URI arrives with forward slashes
            # (sqlite:////a/b.db) while glob() gives the platform separators, and
            # a raw string compare made 'is_current' always false — which hid the
            # fact that the app was reading a different file than the one holding
            # the accounts.
            'is_current': bool(cur_norm and os.path.normcase(os.path.abspath(p)) == cur_norm),
        })
    out.sort(key=lambda d: d['mtime'], reverse=True)
    return out[:limit]


def _sqlite_file_from_uri(uri):
    uri = str(uri or '')
    if not uri.startswith('sqlite'):
        return None
    tail = uri[len('sqlite:'):]
    while tail.startswith('/'):
        tail = tail[1:]
    return tail or None


def devices(inst_dir, project_root):
    """st_dev of the instance folder vs the code folder.

    Different devices => instance/ is a separate mount (the persistent disk).
    Same device => it is part of the container filesystem, i.e. ephemeral.
    None => could not tell (Windows dev box, permission error, ...).
    """
    try:
        inst_dev = os.stat(inst_dir).st_dev
        root_dev = os.stat(project_root).st_dev
        return {'instance_dev': inst_dev, 'root_dev': root_dev,
                'separate_mount': bool(inst_dev != root_dev)}
    except Exception:
        return {'instance_dev': None, 'root_dev': None, 'separate_mount': None}


def secret_fingerprint(secret_key):
    """Short, non-reversible fingerprint used to detect a key rotation.

    A changed fingerprint invalidates every session + remember-me cookie, so
    users are logged out even when their accounts are intact.
    """
    try:
        if not secret_key:
            return None
        return hashlib.sha256(str(secret_key).encode('utf-8')).hexdigest()[:10]
    except Exception:
        return None


def record_boot(inst_dir, info, root_dir=None):
    """Append this boot to the journal and return the persistence verdict.

    `info` is whatever is worth remembering (db scheme, counters, key fp).
    `root_dir` is the project root, used for the ephemeral mirror pointer. If it
    is omitted it is guessed as the parent of inst_dir.
    Returns a dict safe to expose in /health (no DSN, no secrets).
    """
    previous = read_previous_boots(inst_dir, limit=1)
    prev = previous[0] if previous else None

    if not root_dir:
        try:
            root_dir = os.path.dirname(os.path.abspath(inst_dir))
        except Exception:
            root_dir = None
    mirror = _mirror_path(root_dir)
    mirror_seen = bool(mirror and os.path.exists(mirror))
    prev_from_mirror = None
    if mirror_seen and prev is None:
        # Journal unreadable/wiped but we HAVE booted here before: recover the
        # previous record from the mirror so counters/keys stay comparable.
        try:
            with open(mirror, 'r', encoding='utf-8') as fh:
                prev_from_mirror = json.load(fh)
        except Exception:
            prev_from_mirror = None

    entry = dict(info or {})
    entry['boot_id'] = uuid.uuid4().hex[:12]
    entry['boot_ts'] = int(time.time())
    entry['boot_utc'] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())

    # storage_persisted: True  = the journal survived into this boot, the folder
    # is really durable. False = we have booted here before (mirror proves it)
    # and the journal is gone => instance/ was reset. None = no evidence yet
    # (first boot ever, so nothing has been tested across a restart).
    ref = prev if prev is not None else prev_from_mirror
    boots_seen = 1
    if prev is not None:
        verdict = True
        try:
            boots_seen = int(prev.get('boots_seen') or 1) + 1
        except Exception:
            boots_seen = 2
    elif mirror_seen:
        verdict = False
        try:
            boots_seen = int((prev_from_mirror or {}).get('boots_seen') or 1) + 1
        except Exception:
            boots_seen = 2
    else:
        verdict = None
        boots_seen = 1

    entry['boots_seen'] = boots_seen
    entry['storage_persisted'] = verdict

    key_fp = entry.get('secret_key_fp')
    prev_fp = (ref or {}).get('secret_key_fp')
    key_rotated = None
    if ref is not None and key_fp and prev_fp:
        key_rotated = (key_fp != prev_fp)
    entry['secret_key_rotated_since_previous_boot'] = key_rotated

    try:
        os.makedirs(inst_dir, exist_ok=True)
        path = _journal_path(inst_dir)
        lines = []
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as fh:
                lines = [l.strip() for l in fh if l.strip()]
        lines = lines[-(_MAX_ENTRIES_KEPT - 1):] + [json.dumps(entry, default=str)]
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
    except Exception as e:  # never break a boot over diagnostics
        entry['journal_write_error'] = repr(e)

    try:
        if mirror:
            with open(mirror, 'w', encoding='utf-8') as fh:
                json.dump(entry, fh, default=str)
    except Exception:
        pass

    return {
        'this_boot': entry,
        'previous_boot': prev if prev is not None else prev_from_mirror,
        'storage_persisted': verdict,
        'boots_seen': boots_seen,
        'secret_key_rotated': key_rotated,
        'journal_found': prev is not None,
        'mirror_seen': mirror_seen,
    }


def health_summary(state):
    """Reduce the recorded boot state to a small public-safe dict."""
    if not state:
        return None
    prev = state.get('previous_boot') or {}
    this = state.get('this_boot') or {}
    return {
        'storage_persisted': state.get('storage_persisted'),
        'boots_seen': state.get('boots_seen'),
        'evidence': ('journal_survived' if state.get('journal_found')
                     else ('instance_reset' if state.get('mirror_seen')
                           else 'first_boot_no_evidence_yet')),
        'previous_boot_utc': prev.get('boot_utc'),
        'users_previous_boot': prev.get('users'),
        'users_now': this.get('users'),
        'ads_now': this.get('ads'),
        'db_file': this.get('db_file'),
        'secret_key_source': this.get('secret_key_source'),
        'secret_key_fp': this.get('secret_key_fp'),
        'secret_key_rotated': state.get('secret_key_rotated'),
        'db_scheme': this.get('db_scheme'),
        'disk_separate_mount': (this.get('disk') or {}).get('separate_mount'),
        'sqlite_files': this.get('sqlite_files'),
    }
