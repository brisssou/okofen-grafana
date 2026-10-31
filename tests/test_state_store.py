import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from okofen_importer.state_store import ImportStateStore


class ImportStateStoreTests(unittest.TestCase):
    def test_schema_distinguishes_data_date_from_import_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "okofen.sqlite3"
            ImportStateStore(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(imported_files)")
                }

            self.assertIn("data_date", columns)
            self.assertIn("imported_at", columns)

    def test_record_import_is_idempotent_per_source_and_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "okofen.sqlite3"
            store = ImportStateStore(db_path)

            self.assertTrue(store.record_import("report.csv", "20231202"))
            self.assertFalse(store.record_import("report.csv", "20231202"))
            self.assertTrue(store.already_imported("report.csv", "20231202"))

    def test_record_import_keeps_distinct_sources_and_dates_independent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "okofen.sqlite3"
            store = ImportStateStore(db_path)

            self.assertTrue(store.record_import("report.csv", "20231202"))
            self.assertTrue(store.record_import("report.csv", "20231203"))
            self.assertTrue(store.record_import("other.csv", "20231202"))
            self.assertFalse(store.already_imported("report.csv", "20231204"))


if __name__ == "__main__":
    unittest.main()
