from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class EmailMessage:
    id: str | None
    attachments: list[EmailAttachment]


@dataclass(frozen=True, slots=True)
class CsvAttachment:
    message_id: str | None
    filename: str
    content: bytes


def extract_csv_attachments(messages: Iterable[EmailMessage]) -> list[CsvAttachment]:
    """Return CSV attachments from typed email-message objects."""
    attachments: list[CsvAttachment] = []

    for message in messages:
        for attachment in message.attachments:
            if not attachment.filename.lower().endswith(".csv"):
                continue

            attachments.append(
                CsvAttachment(
                    message_id=message.id,
                    filename=attachment.filename,
                    content=attachment.content,
                )
            )

    return attachments
