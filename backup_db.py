"""
backup_db.py — Consistent snapshot backup of the SQLite database.

Uses the sqlite3 online-backup API (safe even while the app holds the file),
writes a timestamped copy into instance/backups/, verifies integrity + row
counts, and keeps only the newest N=10 backups.

Usage:
  python backup_db.py [path/to/app.db]
  # without an argument: first existing non-empty dev database is used.
"""
import datetime
import os
import sqlite3
import sys

_DEFAULT_CANDIDATES = (
    'instance/glory2yahpub_dev.db',
    'glory2yahpub.db',
    'instance/glory2yahpub.db',
)
_KEEP = 10


def find_source():
    base = os.path.dirname(os.path.abspath(__file__))
    for rel in _DEFAULT_CANDIDATES:
        p = os.path.join(base, rel)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            return p
    raise SystemExit('[ERROR] no non-empty SQLite database found.')


def _counts(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return tables, {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    for t in tables}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else find_source()
    if not os.path.isfile(src):
        raise SystemExit(f'[ERROR] not a file: {src}')
    src = os.path.abspath(src)

    back_dir = os.path.join(os.path.dirname(src), 'backups')
    os.makedirs(back_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(
        back_dir,
        f'{os.path.splitext(os.path.basename(src))[0]}_backup_{ts}.db')

    print(f'SRC : {src}')
    print(f'DST : {dst}')

    src_conn = sqlite3.connect(src)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    # verify integrity + identical row counts
    a = sqlite3.connect(src)
    b = sqlite3.connect(dst)
    fails = False
    try:
        a_ok = a.execute('PRAGMA integrity_check').fetchone()[0]
        b_ok = b.execute('PRAGMA integrity_check').fetchone()[0]
        tables, counts_src = _counts(a)
        _, counts_dst = _counts(b)
        mismatch = [t for t in tables if counts_src.get(t) != counts_dst.get(t)]
        total = sum(counts_src.values())
        print(f'integrity : src={a_ok} dst={b_ok}')
        print(f'tables    : {len(tables)} | rows={total}')
        print(f'mismatch  : {mismatch or "none"}')
        if a_ok != 'ok' or b_ok != 'ok' or mismatch:
            fails = True
    finally:
        b.close()
        a.close()

    if fails:
        print('[ERROR] backup verification FAILED — do NOT migrate yet!')
        sys.exit(2)

    # prune old backups (keep newest N)
    backups = sorted(os.path.join(back_dir, f)
                     for f in os.listdir(back_dir) if f.endswith('.db'))
    for old in backups[:-_KEEP]:
        try:
            os.remove(old)
            print(f'pruned old backup: {os.path.basename(old)}')
        except OSError:
            pass

    size = os.path.getsize(dst)
    print(f'[OK] backup ready: {dst} ({size:,} bytes, {total:,} rows).')
    print('You can now run the migration safely.')


if __name__ == '__main__':
    main()