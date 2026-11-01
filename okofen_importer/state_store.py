from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class ImportStateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS imported_files (
                    source_name TEXT NOT NULL,
                    data_date TEXT NOT NULL,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_name, data_date)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    label_name TEXT NOT NULL,
                    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def record_import(self, source_name: str, data_date: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO imported_files (source_name, data_date) VALUES (?, ?)",
                (source_name, data_date),
            )
            return cursor.rowcount == 1

    def already_imported(self, source_name: str, data_date: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM imported_files WHERE source_name = ? AND data_date = ? LIMIT 1",
                (source_name, data_date),
            ).fetchone()
            return row is not None

    def message_processed(self, message_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ? LIMIT 1",
                (message_id,),
            ).fetchone()
            return row is not None

    def record_message_processed(self, message_id: str, label_name: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, label_name) "
                "VALUES (?, ?)",
                (message_id, label_name),
            )
            return cursor.rowcount == 1
