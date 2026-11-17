"""Local SQLite store: metadata + durable outgoing event queue."""
import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

PENDING, SYNCED, REJECTED = 'pending', 'synced', 'rejected'


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


class Store:
    def __init__(self, path):
        self._lock = threading.RLock()      # re-entrant: enqueue() may run inside tx()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')      # survive power loss on routers
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                synced_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_events_status ON events(status, seq);
        ''')

    @contextlib.contextmanager
    def tx(self):
        """One atomic, serialised SQLite transaction (BEGIN IMMEDIATE)."""
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            else:
                self.db.execute('COMMIT')

    # ---- metadata
    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self._lock:
            self.db.execute('INSERT INTO meta(key,value) VALUES(?,?) '
                            'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            (key, json.dumps(value)))

    # ---- events
    def enqueue(self, type_, payload):
        """Durable before returning: the event survives a crash right after."""
        eid = str(uuid.uuid4())
        with self._lock:
            cur = self.db.execute(
                'INSERT INTO events(event_id,type,payload,created_at) VALUES(?,?,?,?)',
                (eid, type_, json.dumps(payload, separators=(',', ':')), _now()))
        return eid

    def pending(self, limit=100):
        rows = self.db.execute(
            'SELECT seq,event_id,type,payload,created_at FROM events '
            'WHERE status=? ORDER BY seq LIMIT ?', (PENDING, limit)).fetchall()
        return [{'seq': r[0], 'event_id': r[1], 'type': r[2],
                 'payload': json.loads(r[3]), 'created_at': r[4]} for r in rows]

    def count(self, status=PENDING):
        return self.db.execute('SELECT COUNT(*) FROM events WHERE status=?',
                               (status,)).fetchone()[0]

    def mark(self, event_ids, status, error=None):
        if not event_ids:
            return
        with self._lock:
            self.db.executemany(
                'UPDATE events SET status=?, last_error=?, synced_at=? WHERE event_id=?',
                [(status, error, _now() if status == SYNCED else None, e) for e in event_ids])

    def bump_attempts(self, event_ids, error):
        with self._lock:
            self.db.executemany(
                'UPDATE events SET attempts=attempts+1, last_error=? WHERE event_id=?',
                [(error[:200], e) for e in event_ids])

    def purge_synced(self, keep=1000):
        """Bound disk use on small devices; never touches pending events."""
        with self._lock:
            self.db.execute(
                'DELETE FROM events WHERE status=? AND seq NOT IN '
                '(SELECT seq FROM events WHERE status=? ORDER BY seq DESC LIMIT ?)',
                (SYNCED, SYNCED, keep))
