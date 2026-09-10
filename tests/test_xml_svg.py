import pathlib
import xml.dom.minidom

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = sorted(
    p
    for p in list(ROOT.rglob("*.xml")) + list(ROOT.rglob("*.svg"))
    if ".git" not in p.parts and "node_modules" not in p.parts
)


def test_files_found():
    assert FILES, "no xml/svg files found"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_xml_svg_parses(path):
    xml.dom.minidom.parse(str(path))
