"""
Migrate an existing SQLite database to PostgreSQL (idempotent, safe).

Reads every table/row from a source SQLite DB and copies it into a PostgreSQL
target DB, preserving integer PRIMARY KEY ids and all foreign keys.

Approach
========
  - Source + target are accessed through SQLAlchemy reflection (no ORM models),
    so it works even for legacy tables no longer defined in the app models.
  - Per table only the columns present in BOTH databases are copied.
  - Tables are inserted first-parents-then-children (topological order of the
    foreign-key graph) to maximise FK success on PostgreSQL.
  - PostgreSQL gets INSERT ... ON CONFLICT DO NOTHING, so re-runs are safe.
  - SERIAL sequences are re-synced afterwards so new rows won't collide.
  - '\\x00' bytes (legal in SQLite, illegal in Postgres text) are stripped.
  - Batch failures are retried row-by-row and reported instead of aborting.

Usage
=====
  1) Prepare the target schema first:
       python setup_postgres.py --create-db
     (or boot the app once with DATABASE_URL set — db.create_all() + the
      idempotent startup migration patches build the same tables.)
  2) Copy the data:
       python migrate_sqlite_to_postgres.py --target "postgresql://user:pass@host/db"
       python migrate_sqlite_to_postgres.py --target "$DATABASE_URL" --dry-run
       python migrate_sqlite_to_postgres.py --target "$DATABASE_URL" --truncate
       python migrate_sqlite_to_postgres.py --tables users,ads,user_gkach ...

Source resolution (first match wins):  --source flag,
SOURCE_DATABASE_URL env, then the first existing non-empty *.db among
instance/glory2yahpub_dev.db, glory2yahpub_dev.db, instance/glory2yahpub.db,
glory2yahpub.db.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import (
    MetaData,
    Table,
    create_engine,
    insert,
    inspect,
    select,
    text,
)
from sqlalchemy.schema import CreateIndex, CreateTable

_SQLITE_CANDIDATES = (
    'instance/glory2yahpub_dev.db',
    'glory2yahpub_dev.db',
    'instance/glory2yahpub.db',
    'glory2yahpub.db',
)
_SKIP_PREFIXES = ('sqlite_', 'alembic_')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def _normalize_url(url):
    """Render legacy postgres:// -> postgresql:// (SQLAlchemy 1.4+)."""
    if not url:
        return url
    url = url.strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


def _quote(ident):
    """Double-quote an identifier for DDL (injection-safe)."""
    return '"' + str(ident).replace('"', '""') + '"'


def _find_source_db():
    """Pick the first existing, non-empty SQLite database file."""
    base = os.path.dirname(os.path.abspath(__file__))
    for rel in _SQLITE_CANDIDATES:
        path = os.path.join(base, rel)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return 'sqlite:///' + path.replace('\\', '/')
    for rel in _SQLITE_CANDIDATES:
        path = os.path.join(base, rel)
        if os.path.isfile(path):
            return 'sqlite:///' + path.replace('\\', '/')
    return None


def _order_tables(tables, fk_map):
    """First-parents-then-children topological sort (Kahn) over the FK graph."""
    indeg = {t: 0 for t in tables}
    children = {t: [] for t in tables}
    for t in tables:
        for ref in fk_map.get(t, ()):
            if ref in tables:
                children[ref].append(t)
                indeg[t] += 1
    ready = [t for t in tables if indeg[t] == 0]
    ordered = []
    while ready:
        t = ready.pop()
        ordered.append(t)
        for child in children.get(t, ()):
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)
    # cycle leftovers (should never happen) appended at the end
    ordered += [t for t in tables if t not in ordered]
    return ordered


def _sanitize_value(value, pytype):
    """Coerce a source value to something PostgreSQL accepts happily."""
    if isinstance(value, str):
        return value.replace('\x00', '')
    if pytype is bool and isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, bytes):
        return value  # BYTEA target columns accept bytes as-is
    return value


# ---------------------------------------------------------------------------
# core migration
# ---------------------------------------------------------------------------

def migrate_urls(
    source_url,
    target_url=None,
    tables=None,
    batch_size=1000,
    dry_run=False,
    truncate=False,
    auto_create_tables=False,
    sync_sequences=True,
    verbose=True,
):
    """Migrate all (or a subset of) tables from source_url into target_url."""
    source_url = _normalize_url(source_url)
    target_url = _normalize_url(target_url)
    if not source_url:
        raise ValueError('No SQLite source database found.')

    _src = create_engine(source_url)
    src_insp = inspect(_src)
    all_src_tables = [
        t for t in src_insp.get_table_names()
        if not t.startswith(_SKIP_PREFIXES)
    ]
    selected = set(tables) if tables else set(all_src_tables)
    missing_requested = sorted(selected - set(all_src_tables))
    table_names = _order_tables(
        [t for t in all_src_tables if t in selected],
        {t: [c['referred_table'] for c in src_insp.get_foreign_keys(t)]
         for t in all_src_tables},
    )
    if not table_names:
        raise ValueError('No tables to migrate.')

    if verbose:
        print('SRC :', source_url)
        print('TGT :', target_url if target_url else '(none — dry-run)')
    if missing_requested:
        print(f'  [WARN] requested tables missing on source: {missing_requested}')

    if dry_run:
        if verbose:
            print('DRY-RUN: table inventory only (nothing will be written).')
        stats = {'tables': {}, 'skipped': [], 'total_source_rows': 0,
                 'total_inserted': 0, 'total_errors': 0}
        with _src.connect() as c:
            for t in table_names:
                n = c.execute(text(f'SELECT COUNT(*) FROM {_quote(t)}')).scalar()
                stats['tables'][t] = {'source_rows': n}
                stats['total_source_rows'] += n
        if verbose:
            for t in table_names:
                print(f'  {t:<32} {stats["tables"][t]["source_rows"]:>6} rows')
            print(f'  TOTAL {stats["total_source_rows"]} rows across '
                  f'{len(table_names)} tables.')
        return stats

    if not target_url:
        raise ValueError('target must be provided unless --dry-run is used.')

    dst = create_engine(target_url)
    tgt_insp = inspect(dst)
    target_tables = set(tgt_insp.get_table_names())

    # ----- create missing target tables (reflected DDL, target dialect) -----
    if auto_create_tables:
        _meta = MetaData()
        for t in table_names:
            if t in target_tables:
                continue
            src_tbl = Table(t, _meta, autoload_with=_src)
            with dst.begin() as cc:
                cc.execute(CreateTable(src_tbl))
                for idx in src_insp.get_indexes(t):
                    if idx.get('name', '').startswith('sqlite_auto'):
                        continue
                    try:
                        col_objs = [src_tbl.c[c] for c in idx['column_names']]
                        cc.execute(CreateIndex(idx['name'], src_tbl, col_objs))
                    except Exception as e:
                        print(f'  [WARN] index {idx.get("name")} skipped: {e}')
            if dst.dialect.name == 'postgresql':
                _ensure_pg_serial(dst, t, src_insp)
            target_tables.add(t)
            print(f'  [CREATED] target table {t}')
        tgt_insp = inspect(dst)  # refresh columns/types after DDL

    # ----- truncate requested -----
    to_copy = [t for t in table_names if t in target_tables]
    skipped = sorted(t for t in table_names if t not in target_tables)
    if skipped:
        print(f'  [WARN] tables missing on TARGET (skipped): {skipped}')
    if truncate and to_copy:
        if dst.dialect.name == 'postgresql':
            with dst.begin() as cc:
                cc.execute(text(
                    'TRUNCATE TABLE ' + ', '.join(_quote(t) for t in to_copy)
                    + ' CASCADE'))
            print('  [OK] target tables truncated (CASCADE).')
        else:
            with dst.begin() as cc:
                for t in to_copy:
                    cc.execute(text(f'DELETE FROM {_quote(t)}'))
            print('  [OK] target tables emptied (DELETE).')
# ----- copy each table -----
    stats = {'tables': {}, 'skipped': skipped, 'total_source_rows': 0,
             'total_inserted': 0, 'total_errors': 0}
    src_conn = _src.connect()
    dst_conn = dst.connect()
    try:
        for t in to_copy:
            src_cols = [c['name'] for c in src_insp.get_columns(t)]
            tgt_cols = [c['name'] for c in tgt_insp.get_columns(t)]
            common = [c for c in src_cols if c in tgt_cols]
            if not common:
                stats['skipped'].append(t)
                print(f'  [SKIP] {t}: no common columns '
                      f'(src={len(src_cols)}, tgt={len(tgt_cols)})')
                continue
            type_map = {}
            for c in tgt_insp.get_columns(t):
                try:
                    type_map[c['name']] = c['type'].python_type
                except Exception:
                    type_map[c['name']] = None

            dst_tbl = Table(t, MetaData(), autoload_with=dst)
            if dst.dialect.name == 'postgresql':
                stmt = insert(dst_tbl).on_conflict_do_nothing()
            else:
                stmt = insert(dst_tbl)
            src_tbl = Table(t, MetaData(), autoload_with=_src)
            rows_it = src_conn.execute(
                select(*[src_tbl.c[c] for c in common]).select_from(src_tbl)
            ).mappings()

            t_stats = {'source_rows': 0, 'inserted': 0, 'errors': 0}
            stats['tables'][t] = t_stats
            batch = []
            errors = []

            def flush(buf):
                if not buf:
                    return 0
                try:
                    with dst_conn.begin():
                        dst_conn.execute(stmt, buf)
                    return 0
                except Exception:
                    fails = 0
                    for row in buf:
                        try:
                            with dst_conn.begin():
                                dst_conn.execute(stmt, row)
                        except Exception as e2:
                            fails += 1
                            key = row.get('id') if row else '?'
                            if key is None:
                                key = row.get(list(row.keys())[0]) if row else '?'
                            errors.append((str(key), str(e2)[:160]))
                    return fails

            processed = 0
            for mapped in rows_it:
                row = {k: _sanitize_value(v, type_map.get(k))
                       for k, v in dict(mapped).items()}
                batch.append(row)
                processed += 1
                if len(batch) >= batch_size:
                    t_stats['errors'] += flush(batch)
                    batch = []
            if batch:
                t_stats['errors'] += flush(batch)

            inserted = processed - t_stats['errors']
            t_stats['source_rows'] = processed
            t_stats['inserted'] = inserted
            stats['total_source_rows'] += processed
            stats['total_inserted'] += inserted
            stats['total_errors'] += t_stats['errors']
            flag = 'OK' if t_stats['errors'] == 0 else '!!!'
            print(f'  [{flag}] {t:<32} src={processed:>6} '
                  f'inserted={inserted:>6} errors={t_stats["errors"]}')
            for key, why in errors[:10]:
                print(f'        - row id={key}: {why}')
    finally:
        src_conn.close()
        dst_conn.close()

    # ----- re-sync PostgreSQL SERIAL sequences -----
    if sync_sequences and not dry_run and dst.dialect.name == 'postgresql':
        _sync_pg_sequences(dst, to_copy, tgt_insp)

    if stats['total_errors']:
        print(f'\n  [WARN] {stats["total_errors"]} row(s) failed (orphan FK / dup / '
              f'typing). Inspect the messages above before switching traffic.')
    else:
        print(f'\n  [OK] {stats["total_inserted"]} rows copied into '
              f'{len(to_copy)} tables.')
    return stats


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def _ensure_pg_serial(engine, table, src_insp):
    """Best-effort SERIAL default for a single integer PK on a created table."""
    pk_cols = (src_insp.get_pk_constraint(table).get('constrained_columns') or [])
    if len(pk_cols) != 1:
        return
    col = pk_cols[0]
    try:
        pt = next(c['type'].python_type for c in src_insp.get_columns(table)
                  if c['name'] == col)
    except Exception:
        return
    if pt is not int:
        return
    try:
        seq = f'{table}_{col}_seq'
        with engine.begin() as cc:
            cc.execute(text(f'CREATE SEQUENCE IF NOT EXISTS {seq}'))
            cc.execute(text(f'ALTER TABLE {_quote(table)} ALTER COLUMN '
                            f'{_quote(col)} SET DEFAULT nextval(\'{seq}\')'))
    except Exception as e:
        print(f'  [WARN] {table}: serial default skipped: {e}')


def _sync_pg_sequences(engine, tables, tgt_insp):
    """setval() every SERIAL sequence so future inserts don't collide."""
    synced = []
    with engine.connect() as cc:
        for t in tables:
            pk = tgt_insp.get_pk_constraint(t).get('constrained_columns') or []
            if len(pk) != 1:
                continue
            col = pk[0]
            try:
                seq = cc.execute(
                    text('SELECT pg_get_serial_sequence(:t, :c)'),
                    {'t': t, 'c': col},
                ).scalar()
            except Exception:
                continue
            if not seq:
                continue
            try:
                cc.execute(text(
                    'SELECT setval(:seq::regclass, '
                    'GREATEST(COALESCE((SELECT MAX({c}) FROM {t}), 0), 1), '
                    'EXISTS (SELECT 1 FROM {t} WHERE {c} IS NOT NULL))'
                ).format(t=_quote(t), c=_quote(col)), {'seq': seq})
                synced.append(t)
            except Exception as e:
                print(f'  [WARN] {t}.{col} sequence sync failed: {e}')
    if synced:
        print(f'  [OK] sequences re-synced: {", ".join(synced)}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(description='SQLite -> PostgreSQL data migration.')
    ap.add_argument('--source', help='Source SQLite URL (sqlite:///...). Defaults '
                                     'to the first existing dev .db file found.')
    ap.add_argument('--target', help='Target PostgreSQL URL (postgresql://...). '
                                     'Defaults to $DATABASE_URL / $STAGING_DATABASE_URL.')
    ap.add_argument('--tables', help='Comma-separated subset of tables to copy.')
    ap.add_argument('--batch-size', type=int, default=1000)
    ap.add_argument('--dry-run', action='store_true',
                    help='Only report the table/row inventory, write nothing.')
    ap.add_argument('--truncate', action='store_true',
                    help='Empty the target tables (CASCADE) before copying.')
    ap.add_argument('--auto-create-tables', action='store_true',
                    help='Create on the target any source table that is missing '
                         '(reflected DDL compiled for the target dialect).')
    ap.add_argument('--no-sync-sequences', action='store_true',
                    help='Skip PostgreSQL SERIAL sequence re-sync.')
    args = ap.parse_args(argv)

    source = args.source or os.environ.get('SOURCE_DATABASE_URL') or _find_source_db()
    target = (args.target
              or os.environ.get('DATABASE_URL')
              or os.environ.get('STAGING_DATABASE_URL'))
    if not source:
        print('[ERROR] No source database found. Pass --source "sqlite:///...".')
        sys.exit(1)
    if not target and not args.dry_run:
        print('[ERROR] No target database. Pass --target or set DATABASE_URL.')
        sys.exit(1)

    stats = migrate_urls(
        source_url=source,
        target_url=(target if not args.dry_run else None),
        tables=set(args.tables.split(',')) if args.tables else None,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        truncate=args.truncate,
        auto_create_tables=args.auto_create_tables,
        sync_sequences=not args.no_sync_sequences,
    )

    sys.exit(2 if stats.get('total_errors') else 0)


if __name__ == '__main__':
    main()