import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from okofen_importer.parser import CsvImportResult
from okofen_importer.sqlite_writer import SQLiteRecordWriter


class SQLiteRecordWriterTests(unittest.TestCase):
    def test_persists_timestamped_numeric_and_text_readings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            writer = SQLiteRecordWriter(db_path)
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

            writer.write("daily.csv", "20231202", result)

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
            writer = SQLiteRecordWriter(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[
                    {"timestamp": datetime(2023, 12, 2), "AT [°C]": 8.5}
                ],
            )

            writer.write("daily.csv", "20231202", result)
            writer.write("daily.csv", "20231202", result)

            with closing(sqlite3.connect(db_path)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

            self.assertEqual(count, 1)

    def test_rejects_rows_without_timestamps_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            writer = SQLiteRecordWriter(db_path)
            result = CsvImportResult(
                source_name="daily.csv",
                records=[{"AT [°C]": 8.5}],
            )

            with self.assertRaisesRegex(ValueError, "Record 0 has no valid timestamp"):
                writer.write("daily.csv", "20231202", result)

            with closing(sqlite3.connect(db_path)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()