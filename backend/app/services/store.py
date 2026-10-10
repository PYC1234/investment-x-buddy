import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id),
            goal TEXT NOT NULL, status TEXT NOT NULL, plan_version INTEGER NOT NULL,
            planner_mode TEXT NOT NULL, plan_json TEXT, approval_json TEXT,
            report_json TEXT, error TEXT, prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            started_at TEXT, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
            plan_version INTEGER NOT NULL, position INTEGER NOT NULL, title TEXT NOT NULL,
            tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL, rationale TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            evidence_id TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(run_id, plan_version, position)
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
            task_id TEXT NOT NULL REFERENCES tasks(id), tool_name TEXT NOT NULL,
            title TEXT NOT NULL, data_json TEXT NOT NULL, is_demo INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tool_calls (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL,
            tool_name TEXT NOT NULL, attempt INTEGER NOT NULL, status TEXT NOT NULL,
            duration_ms REAL NOT NULL, result_json TEXT, error TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            event_type TEXT NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            state_json TEXT NOT NULL, context_summary TEXT NOT NULL,
            before_chars INTEGER NOT NULL, after_chars INTEGER NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(run_id, sequence)
        );
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, memory_key TEXT NOT NULL,
            value_json TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(thread_id, memory_key)
        );
        """
        with self.connection() as connection:
            connection.executescript(schema)

    @staticmethod
    def decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for key in (
            "plan_json", "approval_json", "report_json", "arguments_json",
            "data_json", "result_json", "state_json", "value_json",
        ):
            if key in result and result[key] is not None:
                result[key.removesuffix("_json")] = json.loads(result.pop(key))
        if "is_demo" in result:
            result["is_demo"] = bool(result["is_demo"])
        return result

    def fetch_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection() as connection:
            return self.decode_row(connection.execute(sql, parameters).fetchone())

    def fetch_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [self.decode_row(row) for row in connection.execute(sql, parameters).fetchall()]  # type: ignore[misc]

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with self.connection() as connection:
            connection.execute(sql, parameters)

