from fastmcp import FastMCP

from greymatter_mcp import config
from greymatter_mcp.server import build_server


def test_build_server(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "k")
    config.reset_config_cache()
    mcp = build_server()
    assert isinstance(mcp, FastMCP)
    config.reset_config_cache()
