import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from okofen_importer.attachment_cache import DEFAULT_ATTACHMENT_CACHE_DIR
from okofen_importer.cli import _ProgressReporter, main
from okofen_importer.driver import ImportOutcome
from okofen_importer.gmail_fetcher import MessageCompleted, Note, PageStarted


class ImportCliTests(unittest.TestCase):
    def test_defaults_to_chaudiere_gmail_label(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("okofen_importer.cli.create_gmail_service", return_value="gmail"),
            patch("okofen_importer.cli.Database"),
            patch("okofen_importer.cli.run_gmail_import", return_value=[]) as run,
            patch("okofen_importer.cli._report_progress"),
            patch("builtins.print"),
        ):
            result = main([])

        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.args[1], "chaudière")

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
            patch("okofen_importer.cli.Database") as db,
            patch("okofen_importer.cli.run_gmail_import", return_value=expected_outcomes) as run,
            patch("okofen_importer.cli._report_progress") as progress,
            patch("builtins.print") as output,
        ):
            result = main([])

        self.assertEqual(result, 0)
        auth.assert_called_once_with(Path("/config/client.json"), Path("/tokens/gmail.json"))
        db.assert_called_once_with(Path("/data/okofen.sqlite3"))
        run.assert_called_once_with(
            "gmail",
            "Okofen daily",
            db.return_value,
            progress=ANY,
            cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
        )
        self.assertIsInstance(run.call_args.kwargs["progress"], _ProgressReporter)
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
                patch("okofen_importer.cli.Database") as db,
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
            db.return_value,
            progress=ANY,
            cache_dir=Path("cache"),
        )
        self.assertIsInstance(replay.call_args.kwargs["progress"], _ProgressReporter)
        output.assert_called_once_with("replayed: touch.csv (20231202, 10 records)")

    def test_replay_cache_requires_an_existing_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "missing.sqlite3"
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("okofen_importer.cli.create_gmail_service") as auth,
                patch("okofen_importer.cli.Database") as db,
                self.assertRaises(SystemExit) as error,
            ):
                main(["--replay-cache", "--database", str(database)])

        self.assertEqual(error.exception.code, 2)
        auth.assert_not_called()
        db.assert_not_called()

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
                patch("okofen_importer.cli.Database") as db,
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
        self.assertIsInstance(download.call_args.kwargs["progress"], _ProgressReporter)
        db.assert_not_called()
        run_gmail.assert_not_called()
        replay_cache.assert_not_called()
        output.assert_called_once_with("Cached 3 Gmail CSV attachment(s).")

    def test_replay_download_defaults_to_chaudiere_gmail_label(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("okofen_importer.cli.create_gmail_service", return_value="gmail"),
            patch(
                "okofen_importer.cli.download_and_cache_gmail_csvs", return_value=0
            ) as download,
            patch("okofen_importer.cli._report_progress"),
            patch("builtins.print"),
        ):
            result = main(["--replay-download"])

        self.assertEqual(result, 0)
        self.assertEqual(download.call_args.args[1], "chaudière")

    def test_progress_bar_updates_one_line_and_finishes_with_newline(self):
        stream = io.StringIO()
        progress = _ProgressReporter(stream)

        progress(PageStarted(page=1, message_count=2, estimated_total_pages=3))
        progress(MessageCompleted(page=1, index=1, total=2))
        progress(MessageCompleted(page=1, index=2, total=2))
        progress.finish()

        self.assertEqual(
            stream.getvalue(),
            "\r[--------------------] Gmail page 1/~3 (0/2)"
            "\r[##########----------] Gmail page 1/~3 (1/2)"
            "\r[####################] Gmail page 1/~3 (2/2)\n",
        )

    def test_progress_note_prints_above_the_bar_and_redraws_it(self):
        stream = io.StringIO()
        progress = _ProgressReporter(stream)

        progress(PageStarted(page=1, message_count=2, estimated_total_pages=None))
        progress(MessageCompleted(page=1, index=1, total=2))
        progress(Note("Writing 10 records from report.csv for 20231202 to SQLite"))
        progress.finish()

        bar = "[##########----------] Gmail page 1 (1/2)"
        self.assertEqual(
            stream.getvalue(),
            "\r[--------------------] Gmail page 1 (0/2)"
            f"\r{bar}"
            f"\r{' ' * len(bar)}\r"
            "Writing 10 records from report.csv for 20231202 to SQLite\n"
            f"{bar}\n",
        )

    def test_progress_notes_alone_print_line_by_line(self):
        stream = io.StringIO()

        with _ProgressReporter(stream) as progress:
            progress(Note("Replaying cached CSV 1/1: report.csv"))
            progress(Note("Stored report.csv for 20231202"))

        self.assertEqual(
            stream.getvalue(),
            "Replaying cached CSV 1/1: report.csv\nStored report.csv for 20231202\n",
        )

    def test_progress_bar_handles_empty_page_without_estimate(self):
        stream = io.StringIO()
        progress = _ProgressReporter(stream)

        progress(PageStarted(page=1, message_count=0, estimated_total_pages=None))
        progress.finish()

        self.assertEqual(
            stream.getvalue(),
            "\r[####################] Gmail page 1 (0/0)\n",
        )


if __name__ == "__main__":
    unittest.main()