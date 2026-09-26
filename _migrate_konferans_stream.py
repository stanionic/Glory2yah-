"""
Idempotent migration for Konferans live-streaming features.

Adds:
  - konferans_recordings.title             (WhatsApp audio-save / title frame)
  - table konferans_stream_sessions        (social-media live sessions)

Compatible SQLite + PostgreSQL, safe to run multiple times.
Usage:  .venv/Scripts/python.exe _migrate_konferans_stream.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import inspect, text


def _table_exists(conn, name):
    insp = inspect(conn)
    return insp.has_table(name)


def _column_exists(conn, table, column):
    insp = inspect(conn)
    if not insp.has_table(table):
        return False
    return column in [c['name'] for c in insp.get_columns(table)]


def migrate():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        changed = []

        # 1) Missing columns on konferans_recordings (title is new; expires_at
        #    backfilled for databases created before it existed)
        for col, ddl in (
            ('title', 'VARCHAR(255)'),
            ('expires_at', 'DATETIME'),
        ):
            if not _column_exists(conn, 'konferans_recordings', col):
                conn.execute(text(f'ALTER TABLE konferans_recordings ADD COLUMN {col} {ddl}'))
                conn.commit()
                changed.append(f'konferans_recordings.{col} (added)')
            else:
                changed.append(f'konferans_recordings.{col} (already present)')

        # 2) New table: konferans_stream_sessions (via db.create_all on the model)
        db.create_all()
        if _table_exists(conn, 'konferans_stream_sessions'):
            changed.append('konferans_stream_sessions (ready)')
        else:
            changed.append('konferans_stream_sessions (MISSING — check model import!)')

        conn.close()
        print('\n'.join(f'  - {c}' for c in changed))
        print('Migration done.')


if __name__ == '__main__':
    migrate()
