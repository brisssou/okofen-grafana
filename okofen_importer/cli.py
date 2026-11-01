from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .driver import ImportOutcome, run_gmail_import
from .gmail_auth import create_gmail_service
from .sqlite_writer import SQLiteRecordWriter
from .state_store import ImportStateStore


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Okofen CSV attachments from Gmail.")
    parser.add_argument(
        "--label",
        default=os.environ.get("OKOFEN_GMAIL_LABEL"),
        help="Gmail label to import (or set OKOFEN_GMAIL_LABEL)",
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=Path(os.environ.get("GOOGLE_CLIENT_SECRETS", "client_secret.json")),
        help="Google OAuth client secrets JSON file",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=Path(os.environ["GOOGLE_TOKEN_PATH"])
        if os.environ.get("GOOGLE_TOKEN_PATH")
        else None,
        help="OAuth token path (default: ~/.config/okofen-grafana/gmail-token.json)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("OKOFEN_DATABASE", "data/okofen.sqlite3")),
        help="SQLite database path (or set OKOFEN_DATABASE)",
    )
    args = parser.parse_args(argv)

    if not args.label:
        parser.error("--label or OKOFEN_GMAIL_LABEL is required")

    _report_progress("Authenticating with Gmail; first-time OAuth may require browser approval.")
    service = create_gmail_service(args.client_secrets, args.token)
    _report_progress(f"Preparing SQLite database: {args.database}")
    state_store = ImportStateStore(args.database)
    writer = SQLiteRecordWriter(args.database)
    outcomes = run_gmail_import(
        service, args.label, state_store, writer, progress=_report_progress
    )
    _print_outcomes(outcomes)
    return 0


def _report_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _print_outcomes(outcomes: Sequence[ImportOutcome]) -> None:
    if not outcomes:
        print("No CSV attachments found.")
        return

    for outcome in outcomes:
        date_text = outcome.data_date or "no data date"
        print(
            f"{outcome.status}: {outcome.source_name} "
            f"({date_text}, {outcome.record_count} records)"
        )