from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Protocol

from .email_importer import extract_csv_attachments
from .gmail_fetcher import GmailService, iter_gmail_messages
from .parser import CsvImportResult, parse_csv_content
from .state_store import ImportStateStore

ImportStatus = Literal["imported", "already_imported", "no_records", "invalid_data_date"]


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
    progress: Callable[[str], None] | None = None,
) -> list[ImportOutcome]:
    """Stream messages, persist attachments, then checkpoint each completed message."""
    outcomes: list[ImportOutcome] = []

    messages = iter_gmail_messages(
        service,
        label_name,
        progress=progress,
        is_message_processed=state_store.message_processed,
    )
    for message_number, message in enumerate(messages, start=1):
        attachments = extract_csv_attachments([message])
        if progress is not None:
            progress(
                f"Message {message_number}: {len(attachments)} CSV attachment(s)"
            )

        for attachment_number, attachment in enumerate(attachments, start=1):
            if progress is not None:
                progress(
                    f"Parsing attachment {attachment_number}/{len(attachments)}: "
                    f"{attachment.filename}"
                )
            result = parse_csv_content(attachment.content, attachment.filename)
            if not result.records:
                outcomes.append(
                    ImportOutcome(
                        source_name=attachment.filename,
                        data_date=None,
                        record_count=0,
                        status="no_records",
                    )
                )
                continue

            data_date = _get_data_date(result)
            if data_date is None:
                outcomes.append(
                    ImportOutcome(
                        source_name=attachment.filename,
                        data_date=None,
                        record_count=len(result.records),
                        status="invalid_data_date",
                    )
                )
                continue

            if state_store.already_imported(attachment.filename, data_date):
                if progress is not None:
                    progress(
                        f"Skipping already imported {attachment.filename} for {data_date}"
                    )
                outcomes.append(
                    ImportOutcome(
                        source_name=attachment.filename,
                        data_date=data_date,
                        record_count=len(result.records),
                        status="already_imported",
                    )
                )
                continue

            if progress is not None:
                progress(
                    f"Writing {len(result.records)} records from {attachment.filename} "
                    f"for {data_date} to SQLite"
                )
            writer.write(attachment.filename, data_date, result)
            state_store.record_import(attachment.filename, data_date)
            if progress is not None:
                progress(f"Stored {attachment.filename} for {data_date}")
            outcomes.append(
                ImportOutcome(
                    source_name=attachment.filename,
                    data_date=data_date,
                    record_count=len(result.records),
                    status="imported",
                )
            )

        if message.id is not None:
            state_store.record_message_processed(message.id, label_name)
        if progress is not None:
            progress(f"Checkpointed Gmail message {message.id or '(no id)'}")

    return outcomes


def _get_data_date(result: CsvImportResult) -> str | None:
    for record in result.records:
        timestamp = record.get("timestamp")
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y%m%d")
    return None