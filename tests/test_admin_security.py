import os

from app.config import Config


def test_admin_credentials_are_not_hardcoded_public_defaults(monkeypatch):
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('ADMIN_PSEUDO', raising=False)
    monkeypatch.delenv('ADMIN_WHATSAPP', raising=False)
    monkeypatch.delenv('ADMIN_NAME', raising=False)

    cfg = Config()

    assert cfg.ADMIN_PASSWORD in (None, '')
    assert cfg.ADMIN_PASSWORD != 'StanGlory2YahPub1986'
    assert cfg.ADMIN_PASSWORD != 'Admin509'
    assert cfg.ADMIN_WHATSAPP in (None, '')
    assert cfg.ADMIN_PSEUDO in (None, '')
    assert cfg.ADMIN_NAME in (None, '')
