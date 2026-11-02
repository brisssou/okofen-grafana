from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .attachment_cache import DEFAULT_ATTACHMENT_CACHE_DIR
from .database import Database
from .driver import (
    ImportOutcome,
    download_and_cache_gmail_csvs,
    replay_cached_csvs,
    run_gmail_import,
)
from .gmail_auth import create_gmail_service
from .gmail_fetcher import MessageCompleted, Note, PageStarted, ProgressEvent


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Okofen CSV attachments from Gmail.")
    parser.add_argument(
        "--label",
        default=os.environ.get("OKOFEN_GMAIL_LABEL", "chaudière"),
        help="Gmail label to import (default: chaudière; override with OKOFEN_GMAIL_LABEL)",
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
    replay_modes = parser.add_mutually_exclusive_group()
    replay_modes.add_argument(
        "--replay-cache",
        action="store_true",
        help="re-import cached Gmail CSVs without contacting Gmail",
    )
    replay_modes.add_argument(
        "--replay-download",
        action="store_true",
        help="download and cache labeled Gmail CSVs without importing them",
    )
    args = parser.parse_args(argv)

    if not args.replay_cache and not args.label:
        parser.error("--label or OKOFEN_GMAIL_LABEL is required")

    if args.replay_cache:
        if not args.database.is_file():
            parser.error(f"cache replay database does not exist: {args.database}")
        database = _open_database(args.database)
        _report_progress(f"Replaying cached Gmail CSVs from {DEFAULT_ATTACHMENT_CACHE_DIR}.")
        with _ProgressReporter() as progress:
            outcomes = replay_cached_csvs(
                database,
                progress=progress,
                cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
            )
        _print_outcomes(outcomes, empty_message="No cached Gmail CSVs found.")
        return 0

    _report_progress("Authenticating with Gmail; first-time OAuth may require browser approval.")
    service = create_gmail_service(args.client_secrets, args.token)
    if args.replay_download:
        with _ProgressReporter() as progress:
            cached_count = download_and_cache_gmail_csvs(
                service,
                args.label,
                progress=progress,
                cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
            )
        print(f"Cached {cached_count} Gmail CSV attachment(s).")
        return 0

    database = _open_database(args.database)
    with _ProgressReporter() as progress:
        outcomes = run_gmail_import(
            service,
            args.label,
            database,
            progress=progress,
            cache_dir=DEFAULT_ATTACHMENT_CACHE_DIR,
        )
    _print_outcomes(outcomes)
    return 0


def _report_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _open_database(path: Path) -> Database:
    _report_progress(f"Preparing SQLite database: {path}")
    return Database(path)


class _ProgressReporter:
    """Render progress events on stderr: notes line by line, Gmail pages as a bar.

    The bar stays on the last line; a note arriving while it is shown is
    printed above it and the bar is redrawn, so replay-cache (notes only)
    and the Gmail modes (notes and bar) share one reporter.
    """

    _BAR_WIDTH = 20

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = sys.stderr if stream is None else stream
        self._page: PageStarted | None = None
        self._completed = 0
        self._bar_line = ""

    def __enter__(self) -> _ProgressReporter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.finish()

    def __call__(self, event: ProgressEvent) -> None:
        if isinstance(event, PageStarted):
            self._page = event
            self._completed = 0
            self._draw_bar()
        elif isinstance(event, MessageCompleted):
            self._completed = event.index
            self._draw_bar()
        else:
            self._write_note(event)

    def _write_note(self, note: Note) -> None:
        if self._bar_line:
            self._stream.write("\r" + " " * len(self._bar_line) + "\r")
        self._stream.write(note.text + "\n")
        if self._bar_line:
            self._stream.write(self._bar_line)
        self._stream.flush()

    def _draw_bar(self) -> None:
        if self._page is None:
            return
        total = self._page.message_count
        completed = min(self._completed, total)
        fraction = 1.0 if total == 0 else completed / total
        filled = round(self._BAR_WIDTH * fraction)
        bar = "#" * filled + "-" * (self._BAR_WIDTH - filled)
        page_total = (
            f"/~{self._page.estimated_total_pages}"
            if self._page.estimated_total_pages is not None
            else ""
        )
        line = f"[{bar}] Gmail page {self._page.page}{page_total} ({completed}/{total})"
        self._stream.write("\r" + line + " " * max(0, len(self._bar_line) - len(line)))
        self._stream.flush()
        self._bar_line = line

    def finish(self) -> None:
        if self._bar_line:
            self._stream.write("\n")
            self._stream.flush()
            self._bar_line = ""


def _print_outcomes(
    outcomes: Sequence[ImportOutcome],
    empty_message: str = "No CSV attachments found.",
) -> None:
    if not outcomes:
        print(empty_message)
        return

    for outcome in outcomes:
        date_text = outcome.data_date or "no data date"
        print(
            f"{outcome.status}: {outcome.source_name} "
            f"({date_text}, {outcome.record_count} records)"
        )