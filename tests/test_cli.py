import os
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from okofen_importer.cli import main
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
            progress=progress,
        )
        self.assertEqual(progress.call_args_list[0].args[0], "Authenticating with Gmail; first-time OAuth may require browser approval.")
        output.assert_called_once_with("imported: touch.csv (20231202, 10 records)")


if __name__ == "__main__":
    unittest.main()