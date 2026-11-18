"""Offline voucher / entitlement engine (SQLite).

Atomicity: every redemption is ONE ``BEGIN IMMEDIATE`` transaction, so a voucher
can never be spent twice, even with concurrent requests. Brute force is limited
per device AND globally (an attacker can rotate MAC addresses for free).

Time: uses the device clock via ``now_fn``. Secure time validation and clock
rollback detection arrive in Phase 8; until then a gateway clock can be abused.
Data quotas are stored but enforced in Phase 7 (usage accounting).
"""
import hashlib
import hmac
import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..routers.validation import norm_mac
from ..routers.base import ValidationFailed

ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'      # must match the cloud (tested)
CODE_LEN = 12
DEVICE_FAIL_LIMIT, DEVICE_WINDOW = 5, 300
GLOBAL_FAIL_LIMIT, GLOBAL_WINDOW, GLOBAL_LOCK = 60, 600, 60


def normalize_code(raw):
    s = re.sub(r'[\s\-]', '', str(raw or '')).upper()
    if len(s) != CODE_LEN or any(c not in ALPHABET for c in s):
        return None
    return s


def hash_code(key_b64, norm):
    return hmac.new(base64.b64decode(key_b64), b'v1:' + norm.encode(), hashlib.sha256).hexdigest()


def _b64u_decode(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def device_tag(key_b64, mac):
    """Opaque per-device tag the cloud binds into a ticket. Only this gateway (and the
    cloud, which never needs to compute it) can derive it from a MAC."""
    return hmac.new(base64.b64decode(key_b64), b'dev:' + mac.encode(),
                    hashlib.sha256).hexdigest()[:32]


_TID = re.compile(r'^tk_[0-9a-f]{16}$')
_TAG = re.compile(r'^[0-9a-f]{32}$')


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _epoch(iso):
    return datetime.fromisoformat(str(iso).replace('Z', '+00:00')).timestamp()


@dataclass
class Result:
    ok: bool
    reason: str                 # ok|invalid|locked|device_limit|unavailable|not_ready|bad_device|cooldown|disabled
    grant: Optional[dict] = None
    retry_after: Optional[int] = None


SCHEMA = '''
CREATE TABLE IF NOT EXISTS packages(id INTEGER PRIMARY KEY, name TEXT, duration_minutes INTEGER,
    data_mb INTEGER, down_kbps INTEGER, up_kbps INTEGER, max_devices INTEGER, price_gkach INTEGER);
CREATE TABLE IF NOT EXISTS vouchers(uid TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL,
    package_id INTEGER NOT NULL, status TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS entitlements(id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
    voucher_uid TEXT, package_name TEXT, started_at REAL NOT NULL, ends_at REAL NOT NULL,
    max_devices INTEGER NOT NULL, data_mb INTEGER, down_kbps INTEGER, up_kbps INTEGER,
    status TEXT NOT NULL DEFAULT 'active', ticket_id TEXT,
    used_down INTEGER NOT NULL DEFAULT 0, used_up INTEGER NOT NULL DEFAULT 0,
    rep_down INTEGER NOT NULL DEFAULT 0, rep_up INTEGER NOT NULL DEFAULT 0,
    last_report REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_ent_voucher ON entitlements(voucher_uid);
CREATE INDEX IF NOT EXISTS idx_ent_active ON entitlements(status, ends_at);
CREATE TABLE IF NOT EXISTS ent_devices(entitlement_id INTEGER NOT NULL, device TEXT NOT NULL,
    first_seen REAL NOT NULL, PRIMARY KEY(entitlement_id, device));
CREATE TABLE IF NOT EXISTS attempts(device TEXT NOT NULL, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_attempts_at ON attempts(at);
CREATE TABLE IF NOT EXISTS free_grants(device TEXT PRIMARY KEY, last_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(tid TEXT PRIMARY KEY, device TEXT NOT NULL, redeemed_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS counters(device TEXT PRIMARY KEY, last_down INTEGER NOT NULL,
    last_up INTEGER NOT NULL);
'''


class VoucherEngine:
    def __init__(self, store, now_fn=time.time):
        self.store, self.now_fn = store, now_fn
        self.license = None            # set by the agent (LicenseManager); None = legacy cloud-only mode
        store.db.executescript(SCHEMA)

    def now(self):
        return float(self.now_fn())

    # ------------------------------------------------------------ cloud sync
    def sync_from_cloud(self, policy):
        db = self.store.db
        with self.store.tx():
            for k, m in (('voucher_key', 'voucher_key'), ('portal', 'portal'),
                         ('access', 'access'), ('vendor', 'vendor')):
                if k in policy:
                    self.store.set(m, policy[k])
            self.store.set('policy_synced_epoch', int(self.now()))
            db.execute('DELETE FROM packages')
            for p in policy.get('packages', []):
                db.execute('INSERT INTO packages VALUES(?,?,?,?,?,?,?,?)',
                           (p['id'], p['name'], p['duration_minutes'], p.get('data_mb'),
                            p.get('down_kbps'), p.get('up_kbps'), p['max_devices'],
                            p.get('price_gkach', 0)))
            for v in policy.get('vouchers', []):
                exp = _epoch(v['expires_at'])
                if v['status'] == 'UNUSED':
                    db.execute('INSERT OR IGNORE INTO vouchers VALUES(?,?,?,?,?)',
                               (v['uid'], v['hash'], v['package_id'], 'unused', exp))
                    db.execute("UPDATE vouchers SET hash=?, package_id=?, expires_at=? "
                               "WHERE uid=? AND status='unused'",
                               (v['hash'], v['package_id'], exp, v['uid']))
                elif v['status'] == 'REVOKED':
                    db.execute('INSERT OR IGNORE INTO vouchers VALUES(?,?,?,?,?)',
                               (v['uid'], v['hash'], v['package_id'], 'revoked', exp))
                    db.execute("UPDATE vouchers SET status='revoked' WHERE uid=? AND status='unused'",
                               (v['uid'],))

    def packages(self):
        rows = self.store.db.execute(
            'SELECT id,name,duration_minutes,data_mb,down_kbps,up_kbps,max_devices,price_gkach '
            'FROM packages ORDER BY price_gkach,duration_minutes').fetchall()
        keys = ('id', 'name', 'duration_minutes', 'data_mb', 'down_kbps', 'up_kbps',
                'max_devices', 'price_gkach')
        return [dict(zip(keys, r)) for r in rows]

    # -------------------------------------------------------------- helpers
    def can_sell(self):
        """May NEW activations be sold right now? (existing prepaid sessions are never affected)

        * clock rolled back since the last cloud sync -> NO (fail closed);
        * cloud heard from recently -> the cloud's current answer (most up to date);
        * otherwise -> the signed offline license evaluated with TRUSTED time;
        * no license yet -> the last cloud answer (legacy behaviour).
        Returns None when nothing is known yet (not ready).
        """
        cloud = self.store.get('access')
        lic = self.license.state() if self.license is not None else None
        if lic is not None and lic['state'] == 'UNTRUSTED_CLOCK':
            return False
        synced = self.store.get('last_cloud_ok_epoch')
        if cloud is not None and synced is not None and self.now() - synced <= 900:
            return bool(cloud.get('can_sell'))
        if lic is not None and lic['state'] != 'NONE':
            return bool(lic['can_sell'])
        return None if cloud is None else bool(cloud.get('can_sell'))

    _can_sell = can_sell

    def _lock_remaining(self, device, now):
        db = self.store.db
        rows = [r[0] for r in db.execute(
            'SELECT at FROM attempts WHERE device=? AND at>? ORDER BY at',
            (device, now - DEVICE_WINDOW))]
        if len(rows) >= DEVICE_FAIL_LIMIT:
            return max(1, math.ceil(rows[len(rows) - DEVICE_FAIL_LIMIT] + DEVICE_WINDOW - now))
        g = [r[0] for r in db.execute('SELECT at FROM attempts WHERE at>? ORDER BY at',
                                      (now - GLOBAL_WINDOW,))]
        if len(g) >= GLOBAL_FAIL_LIMIT:
            until = g[-1] + GLOBAL_LOCK
            if until > now:
                return max(1, math.ceil(until - now))
        return 0

    def _fail(self, device, now):
        self.store.db.execute('INSERT INTO attempts VALUES(?,?)', (device, now))
        self.store.db.execute('DELETE FROM attempts WHERE at<?', (now - 3600,))

    def _grant(self, ent_row, now, reconnect):
        (eid, source, vuid, pname, started, ends, maxd, data, down, up) = ent_row
        return {'entitlement_id': eid, 'source': source, 'package': pname, 'ends_at': ends,
                'seconds_remaining': max(0, int(ends - now)), 'duration_s': int(ends - started),
                'down_kbps': down, 'up_kbps': up, 'data_mb': data, 'max_devices': maxd,
                'reconnect': reconnect}

    _ENT = ('SELECT id,source,voucher_uid,package_name,started_at,ends_at,max_devices,data_mb,'
            'down_kbps,up_kbps FROM entitlements ')

    def _new_entitlement(self, source, vuid, pkg, now):
        (_pid, name, dur, data, down, up, maxd, _price) = pkg
        cur = self.store.db.execute(
            'INSERT INTO entitlements(source,voucher_uid,package_name,started_at,ends_at,'
            'max_devices,data_mb,down_kbps,up_kbps) VALUES(?,?,?,?,?,?,?,?,?)',
            (source, vuid, name, now, now + dur * 60, maxd, data, down, up))
        return cur.lastrowid

    def _attach(self, eid, device, now):
        self.store.db.execute('INSERT OR IGNORE INTO ent_devices VALUES(?,?,?)', (eid, device, now))

    # ---------------------------------------------------------------- redeem
    def redeem(self, code, device):
        try:
            dev = norm_mac(device)
        except ValidationFailed:
            return Result(False, 'bad_device')
        now = self.now()
        db = self.store.db
        with self.store.tx():
            wait = self._lock_remaining(dev, now)
            if wait:                                    # checked BEFORE looking at the code
                return Result(False, 'locked', retry_after=wait)
            key = self.store.get('voucher_key')
            can_sell = self._can_sell()
            if key is None or can_sell is None:
                return Result(False, 'not_ready')
            norm = normalize_code(code)
            if norm is None:
                self._fail(dev, now)
                return Result(False, 'invalid')
            row = db.execute('SELECT uid,package_id,status,expires_at FROM vouchers WHERE hash=?',
                             (hash_code(key, norm),)).fetchone()
            if row is None or row[2] == 'revoked':
                self._fail(dev, now)
                return Result(False, 'invalid')
            uid, pid, status, exp = row
            if status == 'unused':
                if exp <= now:
                    self._fail(dev, now)
                    return Result(False, 'invalid')
                if not can_sell:                        # new activations stopped by policy
                    return Result(False, 'unavailable')
                pkg = db.execute('SELECT * FROM packages WHERE id=?', (pid,)).fetchone()
                if pkg is None:
                    return Result(False, 'not_ready')
                cur = db.execute("UPDATE vouchers SET status='redeemed' WHERE uid=? AND status='unused'",
                                 (uid,))
                if cur.rowcount != 1:                   # lost a race: treat as already used
                    self._fail(dev, now)
                    return Result(False, 'invalid')
                eid = self._new_entitlement('voucher', uid, pkg, now)
                self._attach(eid, dev, now)
                ent = db.execute(self._ENT + 'WHERE id=?', (eid,)).fetchone()
                self.store.enqueue('voucher.redeemed', {
                    'voucher_uid': uid, 'device': dev, 'redeemed_at': _iso(now),
                    'ends_at': _iso(ent[5])})
                db.execute('DELETE FROM attempts WHERE device=?', (dev,))
                return Result(True, 'ok', self._grant(ent, now, False))
            # status == 'redeemed': only the active entitlement's devices may (re)use it
            ent = db.execute(self._ENT + "WHERE voucher_uid=? AND status='active' AND ends_at>?",
                             (uid, now)).fetchone()
            if ent is None:
                self._fail(dev, now)
                return Result(False, 'invalid')          # used up / expired: same answer as unknown
            eid = ent[0]
            attached = db.execute('SELECT 1 FROM ent_devices WHERE entitlement_id=? AND device=?',
                                  (eid, dev)).fetchone()
            if attached:
                return Result(True, 'ok', self._grant(ent, now, True))
            n = db.execute('SELECT COUNT(*) FROM ent_devices WHERE entitlement_id=?', (eid,)).fetchone()[0]
            if n >= ent[6]:
                return Result(False, 'device_limit')
            self._attach(eid, dev, now)
            self.store.enqueue('voucher.redeemed', {
                'voucher_uid': uid, 'device': dev, 'redeemed_at': _iso(now), 'ends_at': _iso(ent[5])})
            return Result(True, 'ok', self._grant(ent, now, False))

    # ------------------------------------------------------------- free access
    def free_access(self, device):
        try:
            dev = norm_mac(device)
        except ValidationFailed:
            return Result(False, 'bad_device')
        now = self.now()
        db = self.store.db
        portal = self.store.get('portal') or {}
        with self.store.tx():
            if not (portal.get('free_access_enabled') and portal.get('free_package_id')):
                return Result(False, 'disabled')
            active = db.execute(
                self._ENT + "WHERE source='free' AND status='active' AND ends_at>? AND id IN "
                "(SELECT entitlement_id FROM ent_devices WHERE device=?)", (now, dev)).fetchone()
            if active:
                return Result(True, 'ok', self._grant(active, now, True))
            can_sell = self._can_sell()
            if can_sell is None:
                return Result(False, 'not_ready')
            if not can_sell:
                return Result(False, 'unavailable')
            last = db.execute('SELECT last_at FROM free_grants WHERE device=?', (dev,)).fetchone()
            cool = int(portal.get('free_cooldown_hours', 24)) * 3600
            if last and last[0] + cool > now:
                return Result(False, 'cooldown', retry_after=math.ceil(last[0] + cool - now))
            pkg = db.execute('SELECT * FROM packages WHERE id=?', (portal['free_package_id'],)).fetchone()
            if pkg is None or pkg[7] != 0:
                return Result(False, 'not_ready')
            eid = self._new_entitlement('free', None, pkg, now)
            self._attach(eid, dev, now)
            db.execute('INSERT INTO free_grants VALUES(?,?) ON CONFLICT(device) DO UPDATE SET last_at=?',
                       (dev, now, now))
            ent = db.execute(self._ENT + 'WHERE id=?', (eid,)).fetchone()
            self.store.enqueue('session.started', {
                'source': 'free', 'device': dev, 'package_id': pkg[0], 'ends_at': _iso(ent[5])})
            return Result(True, 'ok', self._grant(ent, now, False))


    # ------------------------------------------------------------- tickets
    def _verify_ticket(self, ticket, cloud_pub_b64):
        """Return the payload of a validly SIGNED ticket, else None (no detail leaked)."""
        try:
            if not isinstance(ticket, str) or len(ticket) > 2048 or ticket.count('.') != 1:
                return None
            body, sig = ticket.split('.')
            Ed25519PublicKey.from_public_bytes(base64.b64decode(cloud_pub_b64)).verify(
                _b64u_decode(sig), body.encode())
            payload = json.loads(_b64u_decode(body))
            return payload if isinstance(payload, dict) else None
        except (InvalidSignature, ValueError, TypeError, KeyError, Exception):
            return None

    def redeem_ticket(self, ticket, device):
        """Deliver a package the customer ALREADY PAID FOR on the cloud.

        Verified fully offline: Ed25519 signature (cloud public key), this gateway,
        this device (tag derived from the connection's MAC), not expired, single use.
        Works even if the subscription lapsed since the customer has already paid.
        """
        try:
            dev = norm_mac(device)
        except ValidationFailed:
            return Result(False, 'bad_device')
        now = self.now()
        db = self.store.db
        with self.store.tx():
            wait = self._lock_remaining(dev, now)
            if wait:
                return Result(False, 'locked', retry_after=wait)
            key, cpk, gw_uid = (self.store.get('voucher_key'), self.store.get('cloud_public_key'),
                                self.store.get('gateway_uid'))
            if not (key and cpk and gw_uid):
                return Result(False, 'not_ready')
            pl = self._verify_ticket(ticket, cpk)
            pk = (pl or {}).get('pk') if isinstance((pl or {}).get('pk'), dict) else {}
            good = (pl is not None and pl.get('v') == 1 and pl.get('gw') == gw_uid
                    and isinstance(pl.get('tid'), str) and _TID.match(pl['tid'])
                    and isinstance(pl.get('dt'), str) and _TAG.match(pl['dt'])
                    and hmac.compare_digest(pl['dt'], device_tag(key, dev))
                    and isinstance(pl.get('exp'), int) and not isinstance(pl.get('exp'), bool)
                    and isinstance(pk.get('dur'), int) and 1 <= pk['dur'] <= 525600
                    and all(pk.get(k) is None or (isinstance(pk[k], int) and pk[k] > 0)
                            for k in ('mb', 'dn', 'up')))
            if not good:
                self._fail(dev, now)
                return Result(False, 'invalid')
            tid = pl['tid']
            row = db.execute('SELECT device FROM tickets WHERE tid=?', (tid,)).fetchone()
            if row is not None:                                   # already redeemed
                ent = db.execute(self._ENT + "WHERE ticket_id=? AND status='active' AND ends_at>?",
                                 (tid, now)).fetchone()
                attached = ent and db.execute(
                    'SELECT 1 FROM ent_devices WHERE entitlement_id=? AND device=?',
                    (ent[0], dev)).fetchone()
                if attached:
                    return Result(True, 'ok', self._grant(ent, now, True))   # reconnect, same device
                self._fail(dev, now)
                return Result(False, 'invalid')
            if pl['exp'] <= now:                                   # unredeemed AND expired
                self._fail(dev, now)
                return Result(False, 'invalid')
            cur = db.execute(
                'INSERT INTO entitlements(source,voucher_uid,package_name,started_at,ends_at,'
                'max_devices,data_mb,down_kbps,up_kbps,ticket_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('purchase', None, str(pk.get('n', 'Package'))[:40], now, now + pk['dur'] * 60,
                 1, pk.get('mb'), pk.get('dn'), pk.get('up'), tid))
            eid = cur.lastrowid
            db.execute('INSERT INTO tickets VALUES(?,?,?)', (tid, dev, now))
            self._attach(eid, dev, now)
            ent = db.execute(self._ENT + 'WHERE id=?', (eid,)).fetchone()
            self.store.enqueue('ticket.redeemed', {
                'ticket_id': tid, 'device': dev, 'redeemed_at': _iso(now), 'ends_at': _iso(ent[5])})
            db.execute('DELETE FROM attempts WHERE device=?', (dev,))
            return Result(True, 'ok', self._grant(ent, now, False))

    def tag_for(self, mac):
        key = self.store.get('voucher_key')
        try:
            return device_tag(key, norm_mac(mac)) if key else None
        except ValidationFailed:
            return None

    # --------------------------------------------------- usage / data quota
    def record_usage(self, samples):
        """samples: {mac: (down_bytes_total, up_bytes_total)} as seen by the firewall
        (client's perspective). Counter resets are handled. Returns the devices whose
        data quota is now exhausted (their access must be removed)."""
        now = self.now()
        db = self.store.db
        out = []
        with self.store.tx():
            for mac, pair in (samples or {}).items():
                try:
                    dev = norm_mac(mac)
                    dn, up = int(pair[0]), int(pair[1])
                except (ValidationFailed, TypeError, ValueError, IndexError):
                    continue
                if dn < 0 or up < 0:
                    continue
                last = db.execute('SELECT last_down,last_up FROM counters WHERE device=?',
                                  (dev,)).fetchone()
                d_dn = dn if last is None or dn < last[0] else dn - last[0]
                d_up = up if last is None or up < last[1] else up - last[1]
                db.execute('INSERT INTO counters VALUES(?,?,?) ON CONFLICT(device) DO UPDATE '
                           'SET last_down=excluded.last_down, last_up=excluded.last_up', (dev, dn, up))
                if d_dn == 0 and d_up == 0:
                    continue
                ent = db.execute(
                    "SELECT e.id, e.data_mb, e.voucher_uid, e.ticket_id, e.source FROM entitlements e "
                    "JOIN ent_devices d ON d.entitlement_id=e.id WHERE d.device=? AND e.status='active' "
                    "AND e.ends_at>? ORDER BY e.ends_at DESC LIMIT 1", (dev, now)).fetchone()
                if ent is None:
                    continue
                eid, quota_mb = ent[0], ent[1]
                db.execute('UPDATE entitlements SET used_down=used_down+?, used_up=used_up+? WHERE id=?',
                           (d_dn, d_up, eid))
                if quota_mb is not None:
                    used = db.execute('SELECT used_down+used_up FROM entitlements WHERE id=?',
                                      (eid,)).fetchone()[0]
                    if used >= quota_mb * 1024 * 1024:
                        devs = [r[0] for r in db.execute(
                            'SELECT device FROM ent_devices WHERE entitlement_id=?', (eid,))]
                        db.execute("UPDATE entitlements SET status='exhausted' WHERE id=?", (eid,))
                        self.store.enqueue('session.ended', {
                            'source': ent[4], 'voucher_uid': ent[2], 'devices': devs,
                            'reason': 'data_exhausted'})
                        out.extend(devs)
        return out

    def flush_usage(self, force=False, min_interval=3600):
        """Queue 'usage.recorded' events for unreported bytes. Ended sessions are flushed
        immediately so nothing is lost; active ones at most once per ``min_interval``."""
        now = self.now()
        db = self.store.db
        n = 0
        with self.store.tx():
            for (eid, src, vuid, tid, ud, uu, rd, ru, last, status, started) in db.execute(
                    'SELECT id,source,voucher_uid,ticket_id,used_down,used_up,rep_down,rep_up,'
                    'last_report,status,started_at FROM entitlements '
                    'WHERE used_down>rep_down OR used_up>rep_up').fetchall():
                # the first interval is measured from the session START, not from epoch 0
                if status == 'active' and not force and now - (last or started) < min_interval:
                    continue
                ref = vuid or tid or f'free:{eid}'
                self.store.enqueue('usage.recorded', {
                    'source': src, 'ref': ref[:40], 'bytes_down': ud - rd, 'bytes_up': uu - ru,
                    'period_end': _iso(now)})
                db.execute('UPDATE entitlements SET rep_down=?, rep_up=?, last_report=? WHERE id=?',
                           (ud, uu, now, eid))
                n += 1
        return n

    # ------------------------------------------------------------ maintenance
    def status(self, device):
        try:
            dev = norm_mac(device)
        except ValidationFailed:
            return None
        now = self.now()
        ent = self.store.db.execute(
            self._ENT + "WHERE status='active' AND ends_at>? AND id IN "
            "(SELECT entitlement_id FROM ent_devices WHERE device=?) ORDER BY ends_at DESC LIMIT 1",
            (now, dev)).fetchone()
        return self._grant(ent, now, True) if ent else None

    def expire_due(self):
        """Mark finished entitlements; return devices whose access must be removed."""
        now = self.now()
        db = self.store.db
        out = []
        with self.store.tx():
            for (eid, source, vuid) in db.execute(
                    "SELECT id,source,voucher_uid FROM entitlements WHERE status='active' AND ends_at<=?",
                    (now,)).fetchall():
                devs = [r[0] for r in db.execute(
                    'SELECT device FROM ent_devices WHERE entitlement_id=?', (eid,))]
                db.execute("UPDATE entitlements SET status='expired' WHERE id=?", (eid,))
                self.store.enqueue('session.ended', {
                    'source': source, 'voucher_uid': vuid, 'devices': devs, 'reason': 'time_expired'})
                out.extend(devs)
        return out

    def active_devices(self):
        """For re-authorising clients after a gateway restart."""
        now = self.now()
        rows = self.store.db.execute(
            "SELECT d.device, e.id,e.source,e.voucher_uid,e.package_name,e.started_at,e.ends_at,"
            "e.max_devices,e.data_mb,e.down_kbps,e.up_kbps FROM ent_devices d JOIN entitlements e "
            "ON e.id=d.entitlement_id WHERE e.status='active' AND e.ends_at>?", (now,)).fetchall()
        return [(r[0], self._grant(r[1:], now, True)) for r in rows]
