import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from okofen_importer.attachment_cache import DEFAULT_ATTACHMENT_CACHE_DIR
from okofen_importer.cli import _GmailProgressReporter, main
from okofen_importer.driver import ImportOutcome


class ImportCliTests(unittest.TestCase):
    def test_requires_a_gmail_label(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as error:
                main([])

        self.assertEqual(error.exception.code, 2)

    def test_wires_gmail_to_sqlite_using_configured_paths(self):
        expected_outcomes = [
            ImportOutcome("touch.csv", "20231202", 10, "imported")
        ]
        with (
            patch.dict(
                os.environ,
                {
                    "OKOFEN_GMAIL_LABEL": "Okofen daily",
                    "GOOGLE_CLIENT_SECRETS": "/config/client.json",
                    "GOOGLE_TOKEN_PATH": "/tokens/gmail.json",
                    "OKOFEN_DATABASE": "/data/okofen.sqlite3",
                },
                clear=True,
            ),
            patch("okofen_importer.cli.create_gmail_service", return_value="gmail") as auth,
            patch("okofen_importer.cli.ImportStateStore") as state_store,
            patch("okofen_importer.cli.SQLiteRecordWriter") as writer,
            patch("okofen_importer.cli.run_gmail_import", return_value=expected_outcomes) as run,
            patch("okofen_importer.cli._report_progress") as progress,
            patch("builtins.print") as output,
        ):
            result = main([])

        self.assertEqual(result, 0)
        auth.assert_called_once_with(Path("/config/client.json"), Path("/tokens/gmail.json"))
        state_store.assert_called_once_with(Path("/data/okofen.sqlite3"))
        writer.assert_called_once_with(Path("/data/okofen.sqlite3"))
        run.assert_called_once_with(
            "gmail",
            "Okofen daily",
            state_store.return_value,
            writer.return_value,
            progress=ANY,
            cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
        )
        self.assertIsInstance(run.call_args.kwargs["progress"], _GmailProgressReporter)
        self.assertEqual(progress.call_args_list[0].args[0], "Authenticating with Gmail; first-time OAuth may require browser approval.")
        output.assert_called_once_with("imported: touch.csv (20231202, 10 records)")

    def test_replay_cache_needs_no_label_and_does_not_authenticate_or_fetch(self):
        expected_outcomes = [
            ImportOutcome("touch.csv", "20231202", 10, "replayed")
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "okofen.sqlite3"
            database.touch()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("okofen_importer.cli.create_gmail_service") as auth,
                patch("okofen_importer.cli.run_gmail_import") as run_gmail,
                patch(
                    "okofen_importer.cli.replay_cached_csvs",
                    return_value=expected_outcomes,
                ) as replay,
                patch("okofen_importer.cli.DEFAULT_ATTACHMENT_CACHE_DIR", Path("cache")),
                patch("okofen_importer.cli.ImportStateStore") as state_store,
                patch("okofen_importer.cli.SQLiteRecordWriter") as writer,
                patch("okofen_importer.cli._report_progress"),
                patch("builtins.print") as output,
            ):
                result = main(
                    ["--replay-cache", "--database", str(database)]
                )

        self.assertEqual(result, 0)
        auth.assert_not_called()
        run_gmail.assert_not_called()
        replay.assert_called_once_with(
            state_store.return_value,
            writer.return_value,
            progress=ANY,
            cache_dir=Path("cache"),
        )
        output.assert_called_once_with("replayed: touch.csv (20231202, 10 records)")

    def test_replay_cache_requires_an_existing_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "missing.sqlite3"
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("okofen_importer.cli.create_gmail_service") as auth,
                patch("okofen_importer.cli.ImportStateStore") as state_store,
                self.assertRaises(SystemExit) as error,
            ):
                main(["--replay-cache", "--database", str(database)])

        self.assertEqual(error.exception.code, 2)
        auth.assert_not_called()
        state_store.assert_not_called()

    def test_replay_download_authenticates_and_only_caches_messages(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "must-not-be-opened.sqlite3"
            with (
                patch.dict(
                    os.environ,
                    {"OKOFEN_GMAIL_LABEL": "Historical"},
                    clear=True,
                ),
                patch("okofen_importer.cli.create_gmail_service", return_value="gmail") as auth,
                patch("okofen_importer.cli.ImportStateStore") as state_store,
                patch("okofen_importer.cli.SQLiteRecordWriter") as writer,
                patch("okofen_importer.cli.run_gmail_import") as run_gmail,
                patch("okofen_importer.cli.replay_cached_csvs") as replay_cache,
                patch(
                    "okofen_importer.cli.download_and_cache_gmail_csvs",
                    return_value=3,
                ) as download,
                patch("okofen_importer.cli.DEFAULT_ATTACHMENT_CACHE_DIR", Path("cache")),
                patch("okofen_importer.cli._report_progress"),
                patch("builtins.print") as output,
            ):
                result = main(
                    [
                        "--replay-download",
                        "--client-secrets",
                        "/config/client.json",
                        "--token",
                        "/tokens/gmail.json",
                        "--database",
                        str(database),
                    ]
                )

        self.assertEqual(result, 0)
        auth.assert_called_once_with(Path("/config/client.json"), Path("/tokens/gmail.json"))
        download.assert_called_once_with(
            "gmail",
            "Historical",
            progress=ANY,
            cache_dir=Path("cache"),
        )
        self.assertIsInstance(download.call_args.kwargs["progress"], _GmailProgressReporter)
        state_store.assert_not_called()
        writer.assert_not_called()
        run_gmail.assert_not_called()
        replay_cache.assert_not_called()
        output.assert_called_once_with("Cached 3 Gmail CSV attachment(s).")

    def test_replay_download_requires_a_gmail_label(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("okofen_importer.cli.create_gmail_service") as auth,
            self.assertRaises(SystemExit) as error,
        ):
            main(["--replay-download"])

        self.assertEqual(error.exception.code, 2)
        auth.assert_not_called()

    def test_gmail_progress_updates_one_line_and_finishes_with_newline(self):
        stream = io.StringIO()
        progress = _GmailProgressReporter(stream)

        progress(
            "Gmail page 1: 2 message(s); 0 retrieved, 0 checkpointed so far; "
            "estimated total pages: ~3"
        )
        progress("Fetching message 1/2 from Gmail page 1")
        progress("Completed message 1/2 on Gmail page 1")
        progress("Writing 10 records from report.csv for 20231202 to SQLite")
        progress("Completed message 2/2 on Gmail page 1")
        progress.finish()

        rendered = stream.getvalue()
        self.assertEqual(rendered.count("\r"), 3)
        self.assertTrue(rendered.endswith("\n"))
        self.assertIn("Gmail page 1/~3", rendered)
        self.assertIn("(2/2)", rendered)
        self.assertNotIn("Writing 10 records", rendered)

    def test_gmail_progress_handles_empty_page_without_estimate(self):
        stream = io.StringIO()
        progress = _GmailProgressReporter(stream)

        progress("Gmail page 1: 0 message(s); 0 retrieved, 0 checkpointed so far")
        progress.finish()

        self.assertEqual(
            stream.getvalue(),
            "\r[####################] Gmail page 1 (0/0)\n",
        )


if __name__ == "__main__":
    unittest.main()