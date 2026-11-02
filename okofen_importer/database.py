from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .parser import CsvImportResult


class Database:
    """The importer's SQLite file: readings plus import checkpoints.

    One connection lives for the object's lifetime. Every method runs inside
    ``transaction()``, and nested uses join the outermost transaction, so a
    caller can commit a readings write and its checkpoint atomically.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Autocommit mode: transaction() issues BEGIN and COMMIT itself.
        self._connection = sqlite3.connect(self.db_path, isolation_level=None)
        self._transaction_depth = 0
        with self.transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    source_name TEXT NOT NULL,
                    data_date TEXT NOT NULL,
                    row_index INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    numeric_value REAL,
                    text_value TEXT,
                    PRIMARY KEY (source_name, data_date, row_index, field_name),
                    CHECK (
                        (numeric_value IS NOT NULL AND text_value IS NULL)
                        OR (numeric_value IS NULL AND text_value IS NOT NULL)
                    )
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS readings_by_timestamp "
                "ON readings (timestamp, field_name)"
            )
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

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run the block in one transaction; nested uses join the outer one."""
        if self._transaction_depth == 0:
            self._connection.execute("BEGIN")
        self._transaction_depth += 1
        try:
            yield self._connection
        except BaseException:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                self._connection.execute("ROLLBACK")
            raise
        self._transaction_depth -= 1
        if self._transaction_depth == 0:
            self._connection.execute("COMMIT")

    def write(self, source_name: str, data_date: str, result: CsvImportResult) -> None:
        """Persist normalized readings, retaining each row's source timestamp."""
        values = _serialize_records(source_name, data_date, result.records)
        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO readings (
                    source_name, data_date, row_index, timestamp,
                    field_name, numeric_value, text_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def record_import(self, source_name: str, data_date: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO imported_files (source_name, data_date) VALUES (?, ?)",
                (source_name, data_date),
            )
            return cursor.rowcount == 1

    def already_imported(self, source_name: str, data_date: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM imported_files WHERE source_name = ? AND data_date = ? LIMIT 1",
            (source_name, data_date),
        ).fetchone()
        return row is not None

    def message_processed(self, message_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ? LIMIT 1",
            (message_id,),
        ).fetchone()
        return row is not None

    def record_message_processed(self, message_id: str, label_name: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id, label_name) "
                "VALUES (?, ?)",
                (message_id, label_name),
            )
            return cursor.rowcount == 1


def _serialize_records(
    source_name: str, data_date: str, records: list[dict[str, Any]]
) -> list[tuple[str, str, int, str, str, float | None, str | None]]:
    values = []
    for row_index, record in enumerate(records):
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, datetime):
            raise ValueError(f"Record {row_index} has no valid timestamp")
        timestamp_text = timestamp.isoformat(sep=" ")

        for field_name, value in record.items():
            if field_name == "timestamp" or value is None:
                continue

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_value = float(value)
                text_value = None
            else:
                numeric_value = None
                text_value = str(value)

            values.append(
                (
                    source_name,
                    data_date,
                    row_index,
                    timestamp_text,
                    field_name,
                    numeric_value,
                    text_value,
                )
            )
    return values
