from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .attachment_cache import DEFAULT_ATTACHMENT_CACHE_DIR
from .driver import ImportOutcome, run_gmail_import
from .gmail_auth import create_gmail_service
from .sqlite_writer import SQLiteRecordWriter
from .state_store import ImportStateStore

_PAGE_PROGRESS = re.compile(
    r"^Gmail page (\d+): (\d+) message\(s\)"
    r"(?:;.*; estimated total pages: ~(\d+))?"
)
_MESSAGE_PROGRESS = re.compile(
    r"^Completed message (\d+)/(\d+) on Gmail page (\d+)$"
)


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
    progress = _GmailProgressReporter()
    try:
        outcomes = run_gmail_import(
            service,
            args.label,
            state_store,
            writer,
            progress=progress,
            cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
        )
    finally:
        progress.finish()
    _print_outcomes(outcomes)
    return 0


def _report_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class _GmailProgressReporter:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = sys.stderr if stream is None else stream
        self._page_number = 0
        self._message_count = 0
        self._estimated_total_pages: int | None = None
        self._line_length = 0
        self._active = False

    def __call__(self, message: str) -> None:
        page_progress = _PAGE_PROGRESS.match(message)
        if page_progress is not None:
            self._page_number = int(page_progress.group(1))
            self._message_count = int(page_progress.group(2))
            if page_progress.group(3) is not None:
                self._estimated_total_pages = int(page_progress.group(3))
            self._render(0 if self._message_count else self._message_count)
            return

        message_progress = _MESSAGE_PROGRESS.match(message)
        if message_progress is not None:
            completed = int(message_progress.group(1))
            self._message_count = int(message_progress.group(2))
            self._page_number = int(message_progress.group(3))
            self._render(completed)

    def _render(self, completed: int) -> None:
        total = self._message_count
        fraction = 1.0 if total == 0 else min(max(completed / total, 0), 1)
        width = 20
        filled = round(width * fraction)
        bar = "#" * filled + "-" * (width - filled)
        page_total = (
            f"/~{self._estimated_total_pages}"
            if self._estimated_total_pages is not None
            else ""
        )
        line = (
            f"[{bar}] Gmail page {self._page_number}{page_total} "
            f"({min(completed, total)}/{total})"
        )
        self._stream.write(
            "\r" + line + " " * max(0, self._line_length - len(line))
        )
        self._stream.flush()
        self._line_length = len(line)
        self._active = True

    def finish(self) -> None:
        if self._active:
            self._stream.write("\n")
            self._stream.flush()
            self._active = False


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