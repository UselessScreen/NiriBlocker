"""Tests for daemon.migrations SQL flow and branch handling."""

from __future__ import annotations

import asyncio

from daemon import migrations


class FakeResult:
    def __init__(self, first_row=None, rows=None):
        self._first_row = first_row
        self._rows = list(rows or [])

    def fetchone(self):
        return self._first_row

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.executed = []
        self.committed = False

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if self._responses:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return FakeResult()

    async def commit(self):
        self.committed = True


def test_migrate_schedules_to_blocks_returns_when_old_table_missing():
    session = FakeSession([FakeResult(first_row=None)])

    asyncio.run(migrations.migrate_schedules_to_blocks(session))

    assert len(session.executed) == 1
    assert "name='schedules'" in session.executed[0][0]
    assert session.committed is False


def test_migrate_schedules_to_blocks_returns_when_new_table_exists():
    session = FakeSession([
        FakeResult(first_row=("schedules",)),
        FakeResult(first_row=("blocks",)),
    ])

    asyncio.run(migrations.migrate_schedules_to_blocks(session))

    assert len(session.executed) == 2
    assert "name='blocks'" in session.executed[1][0]
    assert session.committed is False


def test_migrate_schedules_to_blocks_runs_full_migration():
    session = FakeSession([
        FakeResult(first_row=("schedules",)),
        FakeResult(first_row=None),
    ])

    asyncio.run(migrations.migrate_schedules_to_blocks(session))

    sql = "\n".join(stmt for stmt, _ in session.executed)
    assert "CREATE TABLE blocks" in sql
    assert "INSERT INTO blocks" in sql
    assert "CREATE TABLE block_rule_associations" in sql
    assert "ALTER TABLE schedule_rules RENAME TO schedule_rules_backup" in sql
    assert "ALTER TABLE schedules RENAME TO schedules_backup" in sql
    assert session.committed is True


def test_migrate_rules_to_text_fields_returns_when_already_migrated():
    session = FakeSession([FakeResult(first_row=None)])

    asyncio.run(migrations.migrate_rules_to_text_fields(session))

    assert len(session.executed) == 1
    assert "name='block_rules'" in session.executed[0][0]
    assert session.committed is False


def test_migrate_rules_to_text_fields_migrates_rows_and_handles_existing_columns():
    session = FakeSession([
        FakeResult(first_row=("block_rules",)),
        FakeResult(),
        RuntimeError("duplicate column"),
        FakeResult(),
        FakeResult(),
        FakeResult(
            rows=[
                (1, "website", "a.com"),
                (1, "website", "b.com"),
                (1, "application", "code"),
                (2, "application", "steam"),
            ]
        ),
    ])

    asyncio.run(migrations.migrate_rules_to_text_fields(session))

    updates = [params for stmt, params in session.executed if "UPDATE blocks" in stmt]
    assert {u["id"] for u in updates} == {1, 2}
    update_by_id = {u["id"]: u for u in updates}
    assert update_by_id[1]["websites"] == "a.com\nb.com"
    assert update_by_id[1]["apps"] == "code"
    assert update_by_id[2]["websites"] is None
    assert update_by_id[2]["apps"] == "steam"

    sql = "\n".join(stmt for stmt, _ in session.executed)
    assert "DROP TABLE IF EXISTS block_rule_associations" in sql
    assert "DROP TABLE IF EXISTS block_rules" in sql
    assert session.committed is True


def test_migrate_rules_to_text_fields_survives_block_event_rebuild_errors():
    session = FakeSession([
        FakeResult(first_row=("block_rules",)),
        FakeResult(),
        FakeResult(),
        FakeResult(),
        FakeResult(),
        FakeResult(rows=[]),
        RuntimeError("block_events missing"),
    ])

    asyncio.run(migrations.migrate_rules_to_text_fields(session))

    sql = "\n".join(stmt for stmt, _ in session.executed)
    assert "DROP TABLE IF EXISTS block_rule_associations" in sql
    assert "DROP TABLE IF EXISTS block_rules" in sql
    assert session.committed is True
