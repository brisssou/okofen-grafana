import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from okofen_importer.attachment_cache import cache_attachment, iter_cached_csv_files
from okofen_importer.driver import (
    ImportOutcome,
    download_and_cache_gmail_csvs,
    replay_cached_csvs,
    run_gmail_import,
)
from okofen_importer.email_importer import CsvAttachment, EmailAttachment, EmailMessage
from okofen_importer.gmail_fetcher import Note
from okofen_importer.parser import parse_csv_content, parse_csv_file
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

    def test_download_replay_caches_only_csv_without_touching_import_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            store.record_message_processed("already-processed", "Okofen daily")
            store.record_import("existing.csv", "20231202")
            cache_dir = Path(temporary_directory) / "gmail-attachments"
            messages = [
                EmailMessage(
                    id="already-processed",
                    attachments=[
                        EmailAttachment("touch.csv", FIXTURE_PATH.read_bytes()),
                        EmailAttachment("notes.txt", b"not a CSV"),
                    ],
                ),
                EmailMessage(
                    id="not-processed",
                    attachments=[
                        EmailAttachment("other.CSV", FIXTURE_PATH.read_bytes())
                    ],
                ),
            ]
            progress_messages = []
            service = object()
            with (
                patch(
                    "okofen_importer.driver.iter_gmail_messages",
                    return_value=iter(messages),
                ) as fetch,
                patch("okofen_importer.driver.parse_csv_content") as parse,
            ):
                cached_count = download_and_cache_gmail_csvs(
                    service,
                    "Okofen daily",
                    progress=progress_messages.append,
                    cache_dir=cache_dir,
                )

            fetch.assert_called_once_with(
                service,
                "Okofen daily",
                progress=progress_messages.append,
            )
            self.assertNotIn("is_message_processed", fetch.call_args.kwargs)
            parse.assert_not_called()
            cached = list(iter_cached_csv_files(cache_dir))
            self.assertEqual(cached_count, 2)
            self.assertEqual(
                {source_name for _, source_name in cached},
                {"touch.csv", "other.CSV"},
            )
            self.assertTrue(
                all(
                    path.read_bytes() == FIXTURE_PATH.read_bytes()
                    for path, _ in cached
                )
            )
            self.assertTrue(store.message_processed("already-processed"))
            self.assertFalse(store.message_processed("not-processed"))
            self.assertTrue(store.already_imported("existing.csv", "20231202"))
            self.assertFalse(store.already_imported("touch.csv", "20231202"))
            self.assertIn(Note("Message 2: 1 CSV attachment(s)"), progress_messages)
            self.assertIn(Note("Cached CSV attachment: other.CSV"), progress_messages)

    def test_writes_then_records_parsed_csv_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            cache_dir = Path(temporary_directory) / "gmail-attachments"
            writer = _Writer()
            progress_messages = []
            raw_bytes = FIXTURE_PATH.read_bytes()

            def parse_after_cache(content, source_name):
                cached_files = list(cache_dir.glob("*.csv"))
                self.assertEqual(len(cached_files), 1)
                self.assertEqual(cached_files[0].read_bytes(), raw_bytes)
                return parse_csv_content(content, source_name)

            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                return_value=iter(self._messages()),
            ), patch(
                "okofen_importer.driver.parse_csv_content",
                side_effect=parse_after_cache,
            ):
                outcomes = run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    progress=progress_messages.append,
                    cache_dir=cache_dir,
                )

            self.assertEqual(
                outcomes,
                [ImportOutcome(FIXTURE_PATH.name, "20231202", 1438, "imported")],
            )
            self.assertEqual(len(writer.calls), 1)
            self.assertTrue(store.already_imported(FIXTURE_PATH.name, "20231202"))
            self.assertEqual(
                progress_messages,
                [
                    Note("Message 1: 1 CSV attachment(s)"),
                    Note("Parsing attachment 1/1: touch_20231202.csv"),
                    Note(
                        "Writing 1438 records from touch_20231202.csv "
                        "for 20231202 to SQLite"
                    ),
                    Note("Stored touch_20231202.csv for 20231202"),
                    Note("Checkpointed Gmail message message-1"),
                ],
            )
            self.assertTrue(store.message_processed("message-1"))

    def test_cache_failure_stops_parse_and_does_not_checkpoint_message(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            with (
                patch(
                    "okofen_importer.driver.iter_gmail_messages",
                    return_value=iter(self._messages()),
                ),
                patch(
                    "okofen_importer.driver.cache_attachment",
                    side_effect=OSError("cache unavailable"),
                ),
                patch("okofen_importer.driver.parse_csv_content") as parse,
                self.assertRaisesRegex(OSError, "cache unavailable"),
            ):
                run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    _Writer(),
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

            parse.assert_not_called()
            self.assertFalse(store.message_processed("message-1"))
            self.assertFalse(store.already_imported(FIXTURE_PATH.name, "20231202"))

    def test_skips_csv_after_successful_import(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            store.record_import(FIXTURE_PATH.name, "20231202")
            writer = _Writer()
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                return_value=iter(self._messages()),
            ):
                outcomes = run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

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
                run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

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
                outcomes = run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

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
                run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

            self.assertTrue(store.message_processed("message-1"))
            self.assertFalse(store.message_processed("message-2"))

            writer.should_fail = False
            with patch(
                "okofen_importer.driver.iter_gmail_messages",
                side_effect=stream_unprocessed_messages,
            ):
                outcomes = run_gmail_import(
                    object(),
                    "Okofen daily",
                    store,
                    writer,
                    cache_dir=Path(temporary_directory) / "gmail-attachments",
                )

            self.assertEqual(skipped_ids, ["message-1"])
            self.assertEqual([outcome.source_name for outcome in outcomes], ["second.csv"])
            self.assertEqual(outcomes[0].status, "imported")
            self.assertTrue(store.message_processed("message-2"))

    def test_replays_cached_csv_even_when_imported_and_inserts_new_fields(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_path = Path(temporary_directory) / "imports.sqlite3"
            store = ImportStateStore(db_path)
            writer = SQLiteRecordWriter(db_path)
            source_name = "touch.csv"
            original = (
                "Datum;Zeit;KT Ist [°C]\n"
                "02.12.2023;00:00:00;50,0\n"
            ).encode("cp1252")
            updated = (
                "Datum;Zeit;KT Ist [°C];BR\n"
                "02.12.2023;00:00:00;50,0;1\n"
            ).encode("cp1252")
            writer.write(
                source_name, "20231202", parse_csv_content(original, source_name)
            )
            store.record_import(source_name, "20231202")
            store.record_message_processed("message-1", "Okofen daily")
            cache_dir = Path(temporary_directory) / "gmail-attachments"
            cache_attachment(
                CsvAttachment("message-1", source_name, updated),
                cache_dir,
            )

            outcomes = replay_cached_csvs(store, writer, cache_dir=cache_dir)

            self.assertEqual(
                outcomes,
                [ImportOutcome(source_name, "20231202", 1, "replayed")],
            )
            self.assertTrue(store.already_imported(source_name, "20231202"))
            self.assertTrue(store.message_processed("message-1"))
            with closing(sqlite3.connect(db_path)) as connection:
                persisted = connection.execute(
                    "SELECT field_name, numeric_value FROM readings "
                    "ORDER BY field_name"
                ).fetchall()
            self.assertEqual(persisted, [("BR", 1.0), ("KT Ist [°C]", 50.0)])

    def test_cache_replay_failure_does_not_record_import_or_message(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            cache_dir = Path(temporary_directory) / "gmail-attachments"
            cache_attachment(
                CsvAttachment(
                    "message-1",
                    "touch.csv",
                    "Datum;Zeit;KT Ist [°C]\n02.12.2023;00:00:00;50,0\n".encode(
                        "cp1252"
                    ),
                ),
                cache_dir,
            )

            with self.assertRaisesRegex(RuntimeError, "write failed"):
                replay_cached_csvs(
                    store,
                    _Writer(error=RuntimeError("write failed")),
                    cache_dir=cache_dir,
                )

            self.assertFalse(store.already_imported("touch.csv", "20231202"))
            self.assertFalse(store.message_processed("message-1"))

    def test_cache_replay_ignores_unrecognized_and_temporary_csvs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ImportStateStore(Path(temporary_directory) / "imports.sqlite3")
            cache_dir = Path(temporary_directory) / "gmail-attachments"
            cache_dir.mkdir()
            (cache_dir / "unrelated.csv").write_bytes(FIXTURE_PATH.read_bytes())
            (cache_dir / ".attachment-temporary.csv").write_bytes(
                FIXTURE_PATH.read_bytes()
            )
            writer = _Writer()

            outcomes = replay_cached_csvs(store, writer, cache_dir=cache_dir)

            self.assertEqual(outcomes, [])
            self.assertEqual(writer.calls, [])


if __name__ == "__main__":
    unittest.main()