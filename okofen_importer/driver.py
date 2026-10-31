from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .email_importer import CsvAttachment, extract_csv_attachments
from .gmail_fetcher import GmailService, fetch_gmail_messages
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
) -> list[ImportOutcome]:
    """Fetch, parse, write, and record CSV attachments from one Gmail label."""
    messages = fetch_gmail_messages(service, label_name)
    attachments = extract_csv_attachments(messages)
    outcomes: list[ImportOutcome] = []

    for attachment in attachments:
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
            outcomes.append(
                ImportOutcome(
                    source_name=attachment.filename,
                    data_date=data_date,
                    record_count=len(result.records),
                    status="already_imported",
                )
            )
            continue

        writer.write(attachment.filename, data_date, result)
        state_store.record_import(attachment.filename, data_date)
        outcomes.append(
            ImportOutcome(
                source_name=attachment.filename,
                data_date=data_date,
                record_count=len(result.records),
                status="imported",
            )
        )

    return outcomes


def _get_data_date(result: CsvImportResult) -> str | None:
    for record in result.records:
        timestamp = record.get("timestamp")
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%Y%m%d")
    return None