import io
import os
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