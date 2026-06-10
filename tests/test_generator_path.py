"""Path-confinement guard for the maintainer-only collection generator (CWE-23)."""

import importlib.util
from pathlib import Path

import pytest

# scripts/ is not an installed package, so load the module directly by file path.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_from_collection.py"
_spec = importlib.util.spec_from_file_location("generate_from_collection", _SCRIPT)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_path_within_cwd_is_accepted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "sub" / "collection.json"
    target.parent.mkdir()
    target.write_text("{}")
    resolved = gen._resolve_collection_path("sub/collection.json")
    assert resolved == target.resolve()


def test_traversal_outside_cwd_is_rejected(tmp_path, monkeypatch):
    base = tmp_path / "repo"
    base.mkdir()
    monkeypatch.chdir(base)
    # A relative path that climbs out of the working tree must be refused.
    with pytest.raises(ValueError, match="must stay within"):
        gen._resolve_collection_path("../secret.json")


def test_absolute_path_outside_cwd_is_rejected(tmp_path, monkeypatch):
    base = tmp_path / "repo"
    base.mkdir()
    monkeypatch.chdir(base)
    with pytest.raises(ValueError, match="must stay within"):
        gen._resolve_collection_path("/etc/passwd")
