"""One-shot, admin-guarded SQLite -> production PostgreSQL migration.

Runs INSIDE the deployed web service, so it reaches the managed Render
Postgres over the private network through DATABASE_URL — no External
Database URL is required.

Flow
====
  1. GET  /admin/db-migration          status + upload/run forms
  2. POST /admin/db-migration/upload   store an uploaded .db snapshot on the
                                       persistent disk (never in git)
  3. POST /admin/db-migration/run      dry-run inventory, or the real
                                       idempotent (safe-fusion) copy

The copy is INSERT ... ON CONFLICT DO NOTHING (see
migrate_sqlite_to_postgres.migrate_urls), so re-running it never overwrites or
duplicates rows already online. Nothing is truncated unless explicitly asked.

Once the data has landed, remove this module, the template
templates/admin_db_migration.html and the blueprint registration in
app/__init__.py.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import time

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.utils.security import admin_required

admin_db_bp = Blueprint('admin_db', __name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SQLITE_MAGIC = b'SQLite format 3\x00'
_CONFIRM_WORD = 'MIGRATE'


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _snapshot_dir():
    """Persistent folder holding the uploaded .db snapshots."""
    base = current_app.config.get('INSTANCE_DIR') or os.path.join(_REPO_ROOT, 'instance')
    path = os.path.join(base, 'db_migration')
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _snapshots():
    """Existing snapshots, newest first."""
    folder = _snapshot_dir()
    out = []
    try:
        for name in os.listdir(folder):
            if not name.lower().endswith('.db'):
                continue
            full = os.path.join(folder, name)
            if os.path.isfile(full):
                out.append({
                    'name': name,
                    'size': os.path.getsize(full),
                    'mtime': os.path.getmtime(full),
                })
    except Exception:
        pass
    return sorted(out, key=lambda d: d['mtime'], reverse=True)


def _snapshot_path(name):
    """Resolve a snapshot name to a path, rejecting any traversal attempt."""
    if not name or not re.fullmatch(r'[A-Za-z0-9._-]+', name):
        return None
    full = os.path.join(_snapshot_dir(), name)
    return full if os.path.isfile(full) else None


def _mask_dsn(url):
    """Never echo credentials back to the browser."""
    if not url:
        return ''
    if '@' not in url:
        return url
    scheme, rest = url.split('://', 1) if '://' in url else ('', url)
    host = rest.split('@', 1)[1]
    return f'{scheme}://***@{host}' if scheme else '***@' + host


def _target_summary():
    """What we are migrating INTO, and whether it is safely PostgreSQL."""
    uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    return {
        'uri_masked': _mask_dsn(uri),
        'is_postgres': uri.startswith('postgresql://') or uri.startswith('postgres://'),
        'dialect': 'postgresql' if uri.startswith('postgres') else 'sqlite',
    }


def _run_migration(source_path, dry_run, auto_create_tables, truncate=False):
    """Invoke the CLI helper, capturing its report for the admin page."""
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from migrate_sqlite_to_postgres import migrate_urls

    target = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    source_url = 'sqlite:///' + source_path.replace('\\', '/')

    buf = io.StringIO()
    started = time.time()
    with contextlib.redirect_stdout(buf):
        stats = migrate_urls(
            source_url=source_url,
            target_url=(None if dry_run else target),
            dry_run=dry_run,
            truncate=truncate,
            auto_create_tables=auto_create_tables,
            sync_sequences=True,
            verbose=True,
        )
    return {
        'log': buf.getvalue(),
        'stats': stats,
        'seconds': round(time.time() - started, 1),
    }


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@admin_db_bp.route('', methods=['GET'])
@admin_db_bp.route('/', methods=['GET'])
@login_required
@admin_required
def index():
    """Status page: target database, available snapshots, upload + run forms."""
    return render_template(
        'admin_db_migration.html',
        target=_target_summary(),
        snapshots=_snapshots(),
        confirm_word=_CONFIRM_WORD,
        result=None,
    )


@admin_db_bp.route('/upload', methods=['POST'])
@login_required
@admin_required
def upload():
    """Persist an uploaded SQLite snapshot on the persistent disk."""
    file = request.files.get('snapshot')
    if not file or not file.filename:
        flash('Pa gen fichye ki chwazi.', 'error')
        return redirect(url_for('admin_db.index'))

    head = file.stream.read(16)
    file.stream.seek(0)
    if not head.startswith(_SQLITE_MAGIC):
        flash('Fichye sa a pa yon baz SQLite valab (.db).', 'error')
        return redirect(url_for('admin_db.index'))

    safe = re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(file.filename))
    stamp = time.strftime('%Y%m%d_%H%M%S')
    name = f'{stamp}_{safe}'
    full = os.path.join(_snapshot_dir(), name)
    try:
        file.save(full)
    except Exception as e:
        current_app.logger.error(f'db-migration upload failed: {e}')
        flash(f"Erè pandan sovgad fichye a: {e}", 'error')
        return redirect(url_for('admin_db.index'))

    size = os.path.getsize(full)
    flash(
        f'SNAPSHOT RESEVWA: {name} ({size:,} bytes) — li sou disk pèsistan an. '
        f'Kounye a ou ka lanse yon dry-run.',
        'success',
    )
    return redirect(url_for('admin_db.index'))


@admin_db_bp.route('/run', methods=['POST'])
@login_required
@admin_required
def run():
    """Dry-run inventory, or the real idempotent copy into PostgreSQL."""
    name = (request.form.get('snapshot') or '').strip()
    source_path = _snapshot_path(name)
    if not source_path:
        flash('Chwazi yon snapshot valab anvan ou lanse migrasyon an.', 'error')
        return redirect(url_for('admin_db.index'))

    dry_run = request.form.get('dry_run') == '1'
    auto_create = request.form.get('auto_create_tables') == '1'
    confirm = (request.form.get('confirm') or '').strip().upper()
    target = _target_summary()

    if not dry_run:
        if not target['is_postgres']:
            flash(
                'BLOKE: sib la pa yon baz PostgreSQL (DATABASE_URL pa konfigire). '
                'Migrasyon ekri sèlman nan PostgreSQL.',
                'error',
            )
            return redirect(url_for('admin_db.index'))
        if confirm != _CONFIRM_WORD:
            flash(
                f'BLOKE: pou ekri tout bon, tape {_CONFIRM_WORD} nan chan konfimasyon an.',
                'error',
            )
            return redirect(url_for('admin_db.index'))

    try:
        result = _run_migration(
            source_path=source_path,
            dry_run=dry_run,
            auto_create_tables=auto_create,
        )
    except Exception as e:
        current_app.logger.error(f'db-migration run failed: {e}')
        flash(f'Erè pandan migrasyon an: {e}', 'error')
        return redirect(url_for('admin_db.index'))

    stats = result['stats'] or {}
    if dry_run:
        flash(
            f"DRY-RUN: {stats.get('total_source_rows', 0)} liy nan "
            f"{len(stats.get('tables') or {})} tab. Anyen pa ekri.",
            'success',
        )
    elif stats.get('total_errors'):
        flash(
            f"{stats.get('total_errors')} liy echwe — gade rapò a anba a.",
            'warning',
        )
    else:
        flash(
            f"OK: {stats.get('total_inserted', 0)} liy fusionnen nan baz anliy lan "
            f"({result['seconds']}s).",
            'success',
        )

    return render_template(
        'admin_db_migration.html',
        target=target,
        snapshots=_snapshots(),
        confirm_word=_CONFIRM_WORD,
        result=result,
        ran_snapshot=name,
        ran_dry_run=dry_run,
        actor=(current_user.pseudo or current_user.whatsapp or 'Admin'),
    )
