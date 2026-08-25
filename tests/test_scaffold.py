"""task 001 冒烟测试：包结构可导入、版本可读。"""

import importlib

import battlefrontier


def test_version_exposed() -> None:
    assert battlefrontier.__version__


def test_subpackages_importable() -> None:
    for name in ("engine", "dsl", "agent", "runner", "report"):
        importlib.import_module(f"battlefrontier.{name}")


def test_cli_entrypoint_returns_zero() -> None:
    from battlefrontier.cli import main

    assert main() == 0


def test_ptcgdb_sdk_importable() -> None:
    import ptcgdb.sdk

    assert hasattr(ptcgdb.sdk, "open_db")
