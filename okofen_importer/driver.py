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
from .gmail_fetcher import (
    GmailService,
    Note,
    ProgressCallback,
    iter_gmail_messages,
    no_progress,
)
from .database import Database
from .parser import CsvImportResult, parse_csv_content

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
    database: Database,
    writer: ImportWriter | None = None,
    progress: ProgressCallback = no_progress,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> list[ImportOutcome]:
    """Cache raw attachments, import them, then checkpoint each completed message.

    Readings go to ``writer``, which defaults to the database itself.
    """
    outcomes: list[ImportOutcome] = []

    messages = iter_gmail_messages(
        service,
        label_name,
        progress=progress,
        is_message_processed=database.message_processed,
    )
    for message_number, message in enumerate(messages, start=1):
        attachments = _message_attachments(message, message_number, progress)
        for attachment_number, attachment in enumerate(attachments, start=1):
            cache_attachment(attachment, cache_dir, attachment_number)
            progress(
                Note(
                    f"Parsing attachment {attachment_number}/{len(attachments)}: "
                    f"{attachment.filename}"
                )
            )
            result = parse_csv_content(attachment.content, attachment.filename)
            outcomes.append(
                _store_result(
                    attachment.filename,
                    result,
                    database,
                    writer,
                    "imported",
                    skip_imported=True,
                    progress=progress,
                )
            )

        if message.id is not None:
            database.record_message_processed(message.id, label_name)
        progress(Note(f"Checkpointed Gmail message {message.id or '(no id)'}"))

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
            progress(Note(f"Cached CSV attachment: {attachment.filename}"))

    return cached_count


def replay_cached_csvs(
    database: Database,
    writer: ImportWriter | None = None,
    progress: ProgressCallback = no_progress,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> list[ImportOutcome]:
    """Reparse recognized cached CSVs without consulting Gmail or import checkpoints.

    Readings go to ``writer``, which defaults to the database itself.
    """
    cached_files = list(iter_cached_csv_files(cache_dir))
    outcomes: list[ImportOutcome] = []

    for file_number, (path, source_name) in enumerate(cached_files, start=1):
        progress(
            Note(f"Replaying cached CSV {file_number}/{len(cached_files)}: {source_name}")
        )
        result = parse_csv_content(path.read_bytes(), source_name)
        outcomes.append(
            _store_result(
                source_name,
                result,
                database,
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
    progress(Note(f"Message {message_number}: {len(attachments)} CSV attachment(s)"))
    return attachments


def _store_result(
    source_name: str,
    result: CsvImportResult,
    database: Database,
    writer: ImportWriter | None,
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
    if skip_imported and database.already_imported(source_name, data_date):
        progress(Note(f"Skipping already imported {source_name} for {data_date}"))
        return ImportOutcome(source_name, data_date, record_count, "already_imported")

    progress(
        Note(f"Writing {record_count} records from {source_name} for {data_date} to SQLite")
    )
    # One transaction, so readings never land without their checkpoint.
    with database.transaction():
        (database if writer is None else writer).write(source_name, data_date, result)
        database.record_import(source_name, data_date)
    progress(Note(f"Stored {source_name} for {data_date}"))
    return ImportOutcome(source_name, data_date, record_count, status)
