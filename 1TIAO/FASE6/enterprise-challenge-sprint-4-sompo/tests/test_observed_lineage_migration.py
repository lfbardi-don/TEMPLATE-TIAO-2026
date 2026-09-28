from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations/versions/0003_observed_only_window_lineage.py"
)


class _Bind:
    def __init__(self, existing_rows: int) -> None:
        self._existing_rows = existing_rows

    def scalar(self, statement) -> int:
        assert "SELECT count(*) FROM scored_windows" in str(statement)
        return self._existing_rows


class _Op:
    def __init__(self, existing_rows: int) -> None:
        self.bind = _Bind(existing_rows)
        self.calls: list[str] = []

    def execute(self, statement: str) -> None:
        self.calls.append(f"execute:{statement}")

    def get_bind(self) -> _Bind:
        return self.bind

    def drop_constraint(self, *args, **kwargs) -> None:
        self.calls.append("drop_constraint")

    def alter_column(self, *args, **kwargs) -> None:
        self.calls.append("alter_column")

    def create_check_constraint(self, *args, **kwargs) -> None:
        self.calls.append("create_check_constraint")


def _migration_module():
    spec = importlib.util.spec_from_file_location("observed_lineage_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observed_lineage_migration_refuses_all_existing_scored_rows() -> None:
    migration = _migration_module()
    op = _Op(existing_rows=3)
    migration.op = op

    with pytest.raises(RuntimeError, match="3 unverified row"):
        migration.upgrade()

    assert op.calls == ["execute:LOCK TABLE scored_windows IN ACCESS EXCLUSIVE MODE"]


def test_observed_lineage_migration_applies_constraints_only_to_an_empty_table() -> None:
    migration = _migration_module()
    op = _Op(existing_rows=0)
    migration.op = op

    migration.upgrade()

    assert op.calls == [
        "execute:LOCK TABLE scored_windows IN ACCESS EXCLUSIVE MODE",
        "drop_constraint",
        "alter_column",
        "alter_column",
        "create_check_constraint",
    ]
    assert len(migration.revision) <= 32
