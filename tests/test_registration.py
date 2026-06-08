import pytest
from fastmcp import FastMCP

from greymatter_mcp import config
from greymatter_mcp.tools import register_all


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GREYMATTER_API_KEY", "k")
    config.reset_config_cache()
    yield
    config.reset_config_cache()


async def _tool_names(mcp) -> set[str]:
    tools = await mcp.get_tools()
    return set(tools.keys())


async def test_read_write_registers_mutations(monkeypatch):
    monkeypatch.setenv("GREYMATTER_READ_ONLY", "false")
    config.reset_config_cache()
    mcp = FastMCP(name="t")
    register_all(mcp)
    names = await _tool_names(mcp)
    assert "incidents" in names
    assert "acknowledge_incident" in names
    assert "graphql_query" in names


async def test_read_only_hides_mutations(monkeypatch):
    monkeypatch.setenv("GREYMATTER_READ_ONLY", "true")
    config.reset_config_cache()
    mcp = FastMCP(name="t")
    register_all(mcp)
    names = await _tool_names(mcp)
    assert "incidents" in names
    assert "acknowledge_incident" not in names
    assert "graphql_query" in names
