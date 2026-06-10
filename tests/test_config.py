import pytest

from greymatter_mcp.config import Config, ConfigError


def _base_env(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "secret-key")


def test_minimal_config(monkeypatch):
    _base_env(monkeypatch)
    cfg = Config.from_env()
    assert cfg.api_key == "secret-key"
    assert cfg.base_url == "https://greymatter.myreliaquest.com/graphql"
    assert cfg.customer_slug is None
    assert cfg.read_only is False
    assert cfg.timeout == 60.0


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GREYMATTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_read_only_truthy_parsing(monkeypatch):
    _base_env(monkeypatch)
    for val in ("true", "1", "yes", "TRUE"):
        monkeypatch.setenv("GREYMATTER_READ_ONLY", val)
        assert Config.from_env().read_only is True
    for val in ("false", "0", "no", ""):
        monkeypatch.setenv("GREYMATTER_READ_ONLY", val)
        assert Config.from_env().read_only is False


def test_base_url_must_be_http(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GREYMATTER_BASE_URL", "ftp://nope")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_timeout_must_be_number(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("GREYMATTER_TIMEOUT", "abc")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_invalid_log_level_raises(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ConfigError):
        Config.from_env()
