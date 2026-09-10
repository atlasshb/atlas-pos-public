import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFESTS = sorted((ROOT / "addons").glob("*/__manifest__.py"))


def test_at_least_one_manifest():
    assert MANIFESTS, "no addons/*/__manifest__.py found"


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_manifest_is_valid(path):
    data = ast.literal_eval(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    for key in ("name", "version", "license", "depends"):
        assert key in data, f"{path.parent.name} missing {key!r}"
    assert data["license"] == "LGPL-3", f"{path.parent.name} license must be LGPL-3"
    assert isinstance(data["depends"], list) and data["depends"]
    assert "point_of_sale" in data["depends"] or "web" in data["depends"]


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_module_has_license_file(path):
    assert (path.parent / "LICENSE").exists(), f"{path.parent.name} missing LICENSE"
