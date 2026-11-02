from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from .attachment_cache import (
    DEFAULT_ATTACHMENT_CACHE_DIR,
    cache_attachment,
    iter_cached_csv_files,
)
from .email_importer import CsvAttachment, EmailMessage, extract_csv_attachments
from .gmail_fetcher import GmailService, ProgressCallback, iter_gmail_messages, no_progress
from .parser import CsvImportResult, parse_csv_content
from .state_store import ImportStateStore

ImportStatus = Literal["imported", "replayed", "already_imported", "no_records"]


class ImportWriter(Protocol):
    def write(self, source_name: str, data_date: str, result: CsvImportResult) -> None: ...


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    source_name: str
    data_date: str | None
    record_count: int
    status: ImportStatus


def run_gmail_import(
    service: GmailService,
    label_name: str,
    state_store: ImportStateStore,
    writer: ImportWriter,
    progress: ProgressCallback = no_progress,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> list[ImportOutcome]:
    """Cache raw attachments, import them, then checkpoint each completed message."""
    outcomes: list[ImportOutcome] = []

    messages = iter_gmail_messages(
        service,
        label_name,
        progress=progress,
        is_message_processed=state_store.message_processed,
    )
    for message_number, message in enumerate(messages, start=1):
        attachments = _message_attachments(message, message_number, progress)
        for attachment_number, attachment in enumerate(attachments, start=1):
            cache_attachment(attachment, cache_dir, attachment_number)
            progress(
                f"Parsing attachment {attachment_number}/{len(attachments)}: "
                f"{attachment.filename}"
            )
            result = parse_csv_content(attachment.content, attachment.filename)
            outcomes.append(
                _store_result(
                    attachment.filename,
                    result,
                    state_store,
                    writer,
                    "imported",
                    skip_imported=True,
                    progress=progress,
                )
            )

        if message.id is not None:
            state_store.record_message_processed(message.id, label_name)
        progress(f"Checkpointed Gmail message {message.id or '(no id)'}")

    return outcomes


def download_and_cache_gmail_csvs(
    service: GmailService,
    label_name: str,
    progress: ProgressCallback = no_progress,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> int:
    """Download and cache CSV attachments without reading or changing import state."""
    cached_count = 0
    messages = iter_gmail_messages(service, label_name, progress=progress)
    for message_number, message in enumerate(messages, start=1):
        attachments = _message_attachments(message, message_number, progress)
        for attachment_number, attachment in enumerate(attachments, start=1):
            cache_attachment(attachment, cache_dir, attachment_number)
            cached_count += 1
            progress(f"Cached CSV attachment: {attachment.filename}")

    return cached_count


def replay_cached_csvs(
    state_store: ImportStateStore,
    writer: ImportWriter,
    progress: ProgressCallback = no_progress,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> list[ImportOutcome]:
    """Reparse recognized cached CSVs without consulting Gmail or import checkpoints."""
    cached_files = list(iter_cached_csv_files(cache_dir))
    outcomes: list[ImportOutcome] = []

    for file_number, (path, source_name) in enumerate(cached_files, start=1):
        progress(
            f"Replaying cached CSV {file_number}/{len(cached_files)}: {source_name}"
        )
        result = parse_csv_content(path.read_bytes(), source_name)
        outcomes.append(
            _store_result(
                source_name,
                result,
                state_store,
                writer,
                "replayed",
                skip_imported=False,
                progress=progress,
            )
        )

    return outcomes


def _message_attachments(
    message: EmailMessage, message_number: int, progress: ProgressCallback
) -> list[CsvAttachment]:
    attachments = extract_csv_attachments([message])
    progress(f"Message {message_number}: {len(attachments)} CSV attachment(s)")
    return attachments


def _store_result(
    source_name: str,
    result: CsvImportResult,
    state_store: ImportStateStore,
    writer: ImportWriter,
    status: ImportStatus,
    *,
    skip_imported: bool,
    progress: ProgressCallback,
) -> ImportOutcome:
    """Write a parsed CSV and record it, returning how it was classified."""
    if not result.records:
        return ImportOutcome(source_name, None, 0, "no_records")

    record_count = len(result.records)
    # The parser drops every row without a valid timestamp, so the first
    # record always carries one.
    data_date = result.records[0]["timestamp"].strftime("%Y%m%d")
    if skip_imported and state_store.already_imported(source_name, data_date):
        progress(f"Skipping already imported {source_name} for {data_date}")
        return ImportOutcome(source_name, data_date, record_count, "already_imported")

    progress(
        f"Writing {record_count} records from {source_name} for {data_date} to SQLite"
    )
    writer.write(source_name, data_date, result)
    state_store.record_import(source_name, data_date)
    progress(f"Stored {source_name} for {data_date}")
    return ImportOutcome(source_name, data_date, record_count, status)
