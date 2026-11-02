import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from okofen_importer.database import Database
from okofen_importer.parser import CsvImportResult


def _count_readings(db_path):
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]


class DatabaseReadingsTests(unittest.TestCase):
    def test_persists_timestamped_numeric_and_text_readings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            database = Database(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[
                    {
                        "timestamp": datetime(2023, 12, 2, 0, 3, 36),
                        "AT [°C]": 8.5,
                        "HK1 Status": "heating",
                        "empty_metric": None,
                    }
                ],
            )

            database.write("daily.csv", "20231202", result)

            with closing(sqlite3.connect(db_path)) as connection:
                readings = connection.execute(
                    """
                    SELECT timestamp, field_name, numeric_value, text_value
                    FROM readings
                    ORDER BY field_name
                    """
                ).fetchall()

            self.assertEqual(
                readings,
                [
                    ("2023-12-02 00:03:36", "AT [°C]", 8.5, None),
                    ("2023-12-02 00:03:36", "HK1 Status", None, "heating"),
                ],
            )

    def test_rewriting_same_file_rows_does_not_duplicate_them(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            database = Database(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[
                    {"timestamp": datetime(2023, 12, 2), "AT [°C]": 8.5}
                ],
            )

            database.write("daily.csv", "20231202", result)
            database.write("daily.csv", "20231202", result)

            self.assertEqual(_count_readings(db_path), 1)

    def test_rejects_rows_without_timestamps_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            database = Database(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[{"AT [°C]": 8.5}],
            )

            with self.assertRaisesRegex(ValueError, "Record 0 has no valid timestamp"):
                database.write("daily.csv", "20231202", result)

            self.assertEqual(_count_readings(db_path), 0)


class DatabaseCheckpointTests(unittest.TestCase):
    def test_schema_distinguishes_data_date_from_import_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "okofen.sqlite3"
            Database(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(imported_files)")
                }

            self.assertIn("data_date", columns)
            self.assertIn("imported_at", columns)

    def test_record_import_is_idempotent_per_source_and_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "okofen.sqlite3")

            self.assertTrue(database.record_import("report.csv", "20231202"))
            self.assertFalse(database.record_import("report.csv", "20231202"))
            self.assertTrue(database.already_imported("report.csv", "20231202"))

    def test_record_import_keeps_distinct_sources_and_dates_independent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "okofen.sqlite3")

            self.assertTrue(database.record_import("report.csv", "20231202"))
            self.assertTrue(database.record_import("report.csv", "20231203"))
            self.assertTrue(database.record_import("other.csv", "20231202"))
            self.assertFalse(database.already_imported("report.csv", "20231204"))

    def test_message_checkpoints_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "okofen.sqlite3")

            self.assertFalse(database.message_processed("gmail-message-1"))
            self.assertTrue(
                database.record_message_processed("gmail-message-1", "Okofen daily")
            )
            self.assertTrue(database.message_processed("gmail-message-1"))
            self.assertFalse(
                database.record_message_processed("gmail-message-1", "Okofen daily")
            )

    def test_processed_message_ids_lists_every_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Database(Path(tmpdir) / "okofen.sqlite3")

            self.assertEqual(database.processed_message_ids(), set())
            database.record_message_processed("gmail-message-1", "Okofen daily")
            database.record_message_processed("gmail-message-2", "Okofen daily")

            self.assertEqual(
                database.processed_message_ids(),
                {"gmail-message-1", "gmail-message-2"},
            )


class DatabaseTransactionTests(unittest.TestCase):
    def test_nested_calls_commit_together_and_roll_back_together(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "okofen.sqlite3"
            database = Database(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[{"timestamp": datetime(2023, 12, 2), "AT [°C]": 8.5}],
            )

            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                with database.transaction():
                    database.write("daily.csv", "20231202", result)
                    database.record_import("daily.csv", "20231202")
                    raise RuntimeError("interrupted")

            self.assertEqual(_count_readings(db_path), 0)
            self.assertFalse(database.already_imported("daily.csv", "20231202"))

            with database.transaction():
                database.write("daily.csv", "20231202", result)
                database.record_import("daily.csv", "20231202")

            self.assertEqual(_count_readings(db_path), 1)
            self.assertTrue(database.already_imported("daily.csv", "20231202"))


if __name__ == "__main__":
    unittest.main()
