import pytest

import app.config as app_config


def test_production_refuses_to_start_without_database_url_when_enforced(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(app_config, '_instance_dir', lambda: str(tmp_path))
    monkeypatch.setattr(
        app_config, '_load_secret_key', lambda: ('test-secret', 'test')
    )
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DB_ENFORCE_POSTGRES_PRODUCTION', '1')

    with pytest.raises(ValueError, match='DATABASE_URL not set'):
        app_config.ProductionConfig()
