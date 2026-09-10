"""Helpers for loading repo modules by path (the components are not packages)."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(rel_path: str):
    path = ROOT / rel_path
    name = path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
