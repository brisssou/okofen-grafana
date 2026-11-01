import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from okofen_importer.driver import ImportOutcome, run_gmail_import
from okofen_importer.email_importer import EmailAttachment, EmailMessage
from okofen_importer.parser import parse_csv_file
from okofen_importer.sqlite_writer import SQLiteRecordWriter
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
            progress_messages = []
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                return_value=iter(self._messages()),
            ):
                outcomes = run_gmail_import(
                    object(), "Okofen daily", store, writer, progress=progress_messages.append
                )

            self.assertEqual(
                outcomes,
                [ImportOutcome(FIXTURE_PATH.name, "20231202", 1438, "imported")],
            )
            self.assertEqual(len(writer.calls), 1)
            self.assertTrue(store.already_imported(FIXTURE_PATH.name, "20231202"))
            self.assertTrue(any("Message 1: 1 CSV attachment" in message for message in progress_messages))
            self.assertTrue(any("Parsing attachment 1/1" in message for message in progress_messages))
            self.assertTrue(any("Writing 1438 records" in message for message in progress_messages))
            self.assertTrue(any("Stored touch_20231202.csv" in message for message in progress_messages))
            self.assertTrue(store.message_processed("message-1"))

    def test_skips_csv_after_successful_import(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            store.record_import(FIXTURE_PATH.name, "20231202")
            writer = _Writer()
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                return_value=iter(self._messages()),
            ):
                outcomes = run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertEqual(outcomes[0].status, "already_imported")
            self.assertEqual(writer.calls, [])

    def test_does_not_record_csv_when_writer_fails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            writer = _Writer(error=RuntimeError("write failed"))
            with (
                patch(
                    "okofen_importer.driver.iter_gmail_messages",
                    return_value=iter(self._messages()),
                ),
                self.assertRaisesRegex(RuntimeError, "write failed"),
            ):
                run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertFalse(store.already_imported(FIXTURE_PATH.name, "20231202"))

    def test_driver_persists_timestamped_rows_before_recording_import(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            store = ImportStateStore(db_path)
            writer = SQLiteRecordWriter(db_path)
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                return_value=iter(self._messages()),
            ):
                outcomes = run_gmail_import(object(), "Okofen daily", store, writer)

            with closing(sqlite3.connect(db_path)) as connection:
                persisted = connection.execute(
                    "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM readings"
                ).fetchone()
            expected_readings = sum(
                sum(
                    field_name != "timestamp" and value is not None
                    for field_name, value in record.items()
                )
                for record in parse_csv_file(FIXTURE_PATH).records
            )

            self.assertEqual(outcomes[0].status, "imported")
            self.assertEqual(outcomes[0].data_date, "20231202")
            self.assertEqual(persisted[0], expected_readings)
            self.assertEqual(persisted[1], "2023-12-02 00:03:36")
            self.assertEqual(persisted[2], "2023-12-03 00:00:36")
            self.assertTrue(store.already_imported(FIXTURE_PATH.name, "20231202"))
            self.assertTrue(store.message_processed("message-1"))

    def test_rerun_skips_completed_messages_and_resumes_after_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            messages = [
                EmailMessage(
                    id="message-1",
                    attachments=[
                        EmailAttachment("first.csv", FIXTURE_PATH.read_bytes())
                    ],
                ),
                EmailMessage(
                    id="message-2",
                    attachments=[
                        EmailAttachment("second.csv", FIXTURE_PATH.read_bytes())
                    ],
                ),
            ]
            skipped_ids = []

            def stream_unprocessed_messages(
                service, label_name, *, progress, is_message_processed
            ):
                for message in messages:
                    if is_message_processed(message.id):
                        skipped_ids.append(message.id)
                        continue
                    yield message

            class FailSecondWriter(_Writer):
                should_fail = True

                def write(self, source_name, data_date, result):
                    if source_name == "second.csv" and self.should_fail:
                        raise RuntimeError("simulated interruption")
                    self.calls.append((source_name, data_date, result))

            writer = FailSecondWriter()
            with (
                patch(
                    "okofen_importer.driver.iter_gmail_messages",
                    side_effect=stream_unprocessed_messages,
                ),
                self.assertRaisesRegex(RuntimeError, "simulated interruption"),
            ):
                run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertTrue(store.message_processed("message-1"))
            self.assertFalse(store.message_processed("message-2"))

            writer.should_fail = False
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                side_effect=stream_unprocessed_messages,
            ):
                outcomes = run_gmail_import(object(), "Okofen daily", store, writer)

            self.assertEqual(skipped_ids, ["message-1"])
            self.assertEqual([outcome.source_name for outcome in outcomes], ["second.csv"])
            self.assertEqual(outcomes[0].status, "imported")
            self.assertTrue(store.message_processed("message-2"))


if __name__ == "__main__":
    unittest.main()