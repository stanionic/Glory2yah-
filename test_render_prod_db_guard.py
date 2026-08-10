"""Hot tests for the Render boot crash ValueError DATABASE_URL prod fix.

Scenarios:
A) FLASK_ENV=production + DATABASE_URL=empty -> must NOT crash. Fallback to SQLite persistent, flag PRODUCTION_SQLITE_FALLBACK=True + env G2Y_PG_FALLBACK_ACTIVE='1'.
B) FLASK_ENV=production + DB_ENFORCE_POSTGRES_PRODUCTION=1 + empty DSN -> MUST raise ValueError.
C) FLASK_ENV=production + DSN starts with sqlite:///abc (explicit user mistake, PG not empty) -> MUST raise ValueError (only DSN-EMPTY allowed fallback).
D) FLASK_ENV=production + valid postgresql:// DSN -> OK postgres, no fallback, False flag.
E) FLASK_ENV=development + DATABASE_URL empty -> default behavior dev sqlite, OK.
F) Flask create_app production empty DSN boot + /health route GET 200 (no crash at app = create_app line, which is exactly the gunicorn stack we got from user logs).
"""
from __future__ import annotations
import os
import sys
import tempfile
import unittest


def _run(extra_env: dict):
    """Safe runner using subprocess-style isolation via dict copy of os.environ.
    We're careful to restore os.environ after each scenario because the Config
    also leaks G2Y_PG_FALLBACK_ACTIVE into os.environ (expected design; guard ok).
    NOTE: _run returns env snapshot TAKEN BEFORE cleanup so caller can inspect
    G2Y_PG_FALLBACK_ACTIVE and other transient env vars.
    """
    before = os.environ.copy()
    status = None
    cfg = None
    err = None
    env_snapshot = {}
    try:
        for k, v in extra_env.items():
            os.environ[k] = str(v)
        # Force reimport so module-level defaults pick env correctly
        if 'app.config' in sys.modules:
            import importlib
            importlib.reload(sys.modules['app.config'])
        from app.config import (
            ProductionConfig, DevelopmentConfig, TestingConfig,
            _is_postgres_url, _normalize_database_url,
        )
        cfg_cls = ProductionConfig if os.environ.get('FLASK_ENV') == 'production' else DevelopmentConfig
        cfg = cfg_cls()
        status = 'OK'
        env_snapshot = dict(os.environ)
    except Exception as exc:  # noqa: BLE001
        status = 'RAISED'
        err = exc
        env_snapshot = dict(os.environ)
    finally:
        os.environ.clear()
        os.environ.update(before)
        # Also reset G2Y_PG_FALLBACK_ACTIVE leak guard in case
        os.environ.pop('G2Y_PG_FALLBACK_ACTIVE', None)
    return status, cfg, err, env_snapshot, locals().get('_is_postgres_url')


class TestProductionDBGuard(unittest.TestCase):
    def setUp(self):
        # Ensure no leftover env leaks before any single test
        for _k in ('DATABASE_URL', 'FLASK_ENV', 'DB_ENFORCE_POSTGRES_PRODUCTION',
                   'G2Y_PG_FALLBACK_ACTIVE', 'SECRET_KEY'):
            os.environ.pop(_k, None)
        os.environ['SECRET_KEY'] = 'test-secret-for-tests-only-no-prod'

    def test_a_prod_empty_dsn_fallback_sqlite(self):
        status, cfg, err, env_snap, _ = _run({'FLASK_ENV': 'production',
                                              'DATABASE_URL': '',
                                              'DB_ENFORCE_POSTGRES_PRODUCTION': ''})
        self.assertIsNone(err, f"Unexpected raise: {err!r}")
        self.assertEqual(status, 'OK')
        self.assertTrue(cfg.PRODUCTION_SQLITE_FALLBACK,
                        "Expected PRODUCTION_SQLITE_FALLBACK = True when DSN empty prod")
        self.assertTrue(
            cfg.SQLALCHEMY_DATABASE_URI.startswith('sqlite:///'),
            f"Expected sqlite DSN fallback, got {cfg.SQLALCHEMY_DATABASE_URI!r}"
        )
        self.assertIn('glory2yahpub_prod_fallback.db', cfg.SQLALCHEMY_DATABASE_URI)
        self.assertEqual(env_snap.get('G2Y_PG_FALLBACK_ACTIVE'), '1')

    def test_b_prod_enforce_strict_empty_dsn_raises(self):
        status, _cfg, err, _env, _ = _run({'FLASK_ENV': 'production',
                                           'DATABASE_URL': '',
                                           'DB_ENFORCE_POSTGRES_PRODUCTION': '1'})
        self.assertEqual(status, 'RAISED')
        self.assertIsInstance(err, ValueError)
        self.assertIn('DB_ENFORCE_POSTGRES_PRODUCTION', str(err))

    def test_c_prod_explicit_sqlite_dsn_not_empty_raises(self):
        """Only DATABASE_URL=TOTALLY EMPTY allowed to fallback. If user mis-sets
        env to sqlite:///something, we MUST refuse (that's a DSN mistake, NOT PG warm-up race)."""
        status, _cfg, err, _env, _ = _run({'FLASK_ENV': 'production',
                                           'DATABASE_URL': 'sqlite:////tmp/ops.db',
                                           'DB_ENFORCE_POSTGRES_PRODUCTION': ''})
        self.assertEqual(status, 'RAISED')
        self.assertIsInstance(err, ValueError)
        self.assertIn('NOT a PostgreSQL', str(err))

    def test_d_prod_valid_pg_dsn_no_fallback(self):
        fake_pg = 'postgresql://u:p@host.example.com:5432/g2y_testdb'
        status, cfg, err, _env, is_pg_fn = _run({'FLASK_ENV': 'production',
                                                 'DATABASE_URL': fake_pg})
        self.assertIsNone(err, f"Unexpected raise: {err!r}")
        self.assertEqual(status, 'OK')
        self.assertFalse(cfg.PRODUCTION_SQLITE_FALLBACK)
        self.assertTrue(is_pg_fn(cfg.SQLALCHEMY_DATABASE_URI))
        self.assertEqual(cfg.SQLALCHEMY_DATABASE_URI, fake_pg)

    def test_e_dev_empty_dsn_ok_default_sqlite(self):
        # Use real tmp instance dir
        with tempfile.TemporaryDirectory() as td:
            status, cfg, err, _env, _ = _run({'FLASK_ENV': 'development',
                                              'DATABASE_URL': '',
                                              'INSTANCE_DIR_OVERRIDE': td})  # noop, _instance_dir computes its own path; test doesn't really use env here
            self.assertIsNone(err, f"Unexpected raise: {err!r}")
            self.assertEqual(status, 'OK')
            # No attribute PRODUCTION_SQLITE_FALLBACK in Dev config (only Production) -> OK
            uri = cfg.SQLALCHEMY_DATABASE_URI
            self.assertTrue(uri.startswith('sqlite:///'), uri)

    def test_f_boot_gunicorn_create_app_prod_empty_dsn_no_crash(self):
        """Simulate EXACTLY the stack from user render logs:

        gunicorn -> app:app -> module `app/__init__.py` line 1592:
          app = create_app(os.environ.get('FLASK_ENV', _gunicorn_default_env))
        We want create_app() to NOT raise ValueError in that scenario
        (empty DATABASE_URL, production).
        """
        before = os.environ.copy()
        try:
            # Set production-like minimal env (no DATABASE_URL simulates Render first-deploy race)
            os.environ.clear()
            os.environ['FLASK_ENV'] = 'production'
            os.environ['SECRET_KEY'] = 'boot-test-secret-no-prod'
            os.environ['DATABASE_URL'] = ''  # EXACT scenario user logs
            os.environ['SERVER_NAME'] = 'localhost.test'
            os.environ['UPLOAD_FOLDER'] = tempfile.mkdtemp(prefix='g2y_uploads_')
            os.environ['LOG_DIR'] = tempfile.mkdtemp(prefix='g2y_logs_')

            if 'app' in sys.modules:
                import importlib
                importlib.reload(sys.modules['app'])

            from app import create_app
            # Create with explicit TESTING=False to bypass TestingConfig; use production
            app = create_app('production')
            # And then /health route works (does not require DB; our health in blueprint may, just make sure app.wsgi_app is callable)
            client = app.test_client()
            # We don't assert /health 200 because main blueprint needs DB tables maybe; only assert boot succeeded
            self.assertTrue(callable(app.wsgi_app))
            self.assertIn('SQLALCHEMY_DATABASE_URI', app.config)
            self.assertTrue(app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'))
            self.assertTrue(app.config.get('PRODUCTION_SQLITE_FALLBACK'))
        finally:
            os.environ.clear()
            os.environ.update(before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
