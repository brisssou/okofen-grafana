from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .parser import CsvImportResult
from .sqlite_store import SQLiteStore


class SQLiteRecordWriter(SQLiteStore):
    def _initialize(self, connection: sqlite3.Connection) -> None:
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

    def write(self, source_name: str, data_date: str, result: CsvImportResult) -> None:
        """Persist normalized readings, retaining each row's source timestamp."""
        values = _serialize_records(source_name, data_date, result.records)
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO readings (
                    source_name, data_date, row_index, timestamp,
                    field_name, numeric_value, text_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )


def _serialize_records(
    source_name: str, data_date: str, records: list[dict[str, Any]]
) -> list[tuple[str, str, int, str, str, float | None, str | None]]:
    values = []
    for row_index, record in enumerate(records):
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, datetime):
            raise ValueError(f"Record {row_index} has no valid timestamp")

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
                    timestamp.isoformat(sep=" "),
                    field_name,
                    numeric_value,
                    text_value,
                )
            )
    return values