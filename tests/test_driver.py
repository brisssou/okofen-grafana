import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from okofen_importer.driver import ImportOutcome, run_gmail_import
from okofen_importer.email_importer import EmailAttachment, EmailMessage
from okofen_importer.state_store import ImportStateStore


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "touch_20231202.csv"


class _Writer:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def write(self, source_name, data_date, result):
        if self.error is not None:
            raise self.error
        self.calls.append((source_name, data_date, result))


class GmailImportDriverTests(unittest.TestCase):
    def _messages(self):
        return [
            EmailMessage(
                id="message-1",
                attachments=[
                    EmailAttachment(FIXTURE_PATH.name, FIXTURE_PATH.read_bytes())
                ],
            )
        ]

    def test_writes_then_records_parsed_csv_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            writer = _Writer()
            with patch("okofen_importer.driver.fetch_gmail_messages", return_value=self._messages()):
                outcomes = run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertEqual(
                outcomes,
                [ImportOutcome(FIXTURE_PATH.name, "20231202", 1438, "imported")],
            )
            self.assertEqual(len(writer.calls), 1)
            self.assertTrue(store.already_imported(FIXTURE_PATH.name, "20231202"))

    def test_skips_csv_after_successful_import(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            store.record_import(FIXTURE_PATH.name, "20231202")
            writer = _Writer()
            with patch("okofen_importer.driver.fetch_gmail_messages", return_value=self._messages()):
                outcomes = run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertEqual(outcomes[0].status, "already_imported")
            self.assertEqual(writer.calls, [])

    def test_does_not_record_csv_when_writer_fails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            writer = _Writer(error=RuntimeError("write failed"))
            with (
                patch("okofen_importer.driver.fetch_gmail_messages", return_value=self._messages()),
                self.assertRaisesRegex(RuntimeError, "write failed"),
            ):
                run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertFalse(store.already_imported(FIXTURE_PATH.name, "20231202"))


if __name__ == "__main__":
    unittest.main()