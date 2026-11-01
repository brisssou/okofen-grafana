from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from typing import Protocol

from .email_importer import EmailAttachment, EmailMessage

_GMAIL_PAGE_SIZE = 100


class _GmailRequest(Protocol):
    def execute(self, *, num_retries: int = 0) -> dict[str, object]: ...


class _GmailAttachments(Protocol):
    def get(self, *, userId: str, messageId: str, id: str) -> _GmailRequest: ...


class _GmailLabels(Protocol):
    def list(self, *, userId: str) -> _GmailRequest: ...


class _GmailMessages(Protocol):
    def list(
        self,
        *,
        userId: str,
        labelIds: list[str],
        maxResults: int,
        pageToken: str | None = None,
    ) -> _GmailRequest: ...

    def get(self, *, userId: str, id: str, format: str) -> _GmailRequest: ...

    def attachments(self) -> _GmailAttachments: ...


class _GmailUsers(Protocol):
    def labels(self) -> _GmailLabels: ...

    def messages(self) -> _GmailMessages: ...


class GmailService(Protocol):
    def users(self) -> _GmailUsers: ...


def fetch_gmail_messages(
    service: GmailService,
    label_name: str,
    progress: Callable[[str], None] | None = None,
) -> list[EmailMessage]:
    """Fetch all messages with the named Gmail label into memory."""
    return list(iter_gmail_messages(service, label_name, progress=progress))


def iter_gmail_messages(
    service: GmailService,
    label_name: str,
    progress: Callable[[str], None] | None = None,
    is_message_processed: Callable[[str], bool] | None = None,
) -> Iterator[EmailMessage]:
    """Fetch matching messages one at a time, optionally skipping checkpoints."""
    if progress is not None:
        progress(f"Looking up Gmail label: {label_name}")
    labels = (
        service.users()
        .labels()
        .list(userId="me")
        .execute(num_retries=5)
        .get("labels", [])
    )
    label_id = _find_label_id(labels, label_name)
    messages_api = service.users().messages()
    fetched_count = 0
    skipped_count = 0
    page_token: str | None = None
    page_number = 0
    estimated_total_pages: int | None = None

    while True:
        if page_token is None:
            page = messages_api.list(
                userId="me", labelIds=[label_id], maxResults=_GMAIL_PAGE_SIZE
            ).execute(num_retries=5)
        else:
            page = messages_api.list(
                userId="me",
                labelIds=[label_id],
                maxResults=_GMAIL_PAGE_SIZE,
                pageToken=page_token,
            ).execute(num_retries=5)

        page_number += 1
        if estimated_total_pages is None:
            estimated_total_pages = _estimated_total_pages(
                page.get("resultSizeEstimate")
            )
        listed_messages = page.get("messages", [])
        page_messages = listed_messages if isinstance(listed_messages, list) else []
        if progress is not None:
            page_progress = (
                f"Gmail page {page_number}: {len(page_messages)} message(s); "
                f"{fetched_count} retrieved, {skipped_count} checkpointed so far"
            )
            if estimated_total_pages is not None:
                page_progress += (
                    f"; estimated total pages: ~{estimated_total_pages}"
                )
            progress(page_progress)
        if isinstance(listed_messages, list):
            for message_number, listed_message in enumerate(listed_messages, start=1):
                if not isinstance(listed_message, dict):
                    if progress is not None:
                        progress(
                            f"Completed message {message_number}/{len(listed_messages)} "
                            f"on Gmail page {page_number}"
                        )
                    continue
                message_id = listed_message.get("id")
                if not isinstance(message_id, str):
                    if progress is not None:
                        progress(
                            f"Completed message {message_number}/{len(listed_messages)} "
                            f"on Gmail page {page_number}"
                        )
                    continue

                if is_message_processed is not None and is_message_processed(message_id):
                    skipped_count += 1
                    if progress is not None:
                        progress(
                            f"Skipping checkpointed message {message_number}/"
                            f"{len(listed_messages)} on page {page_number}"
                        )
                        progress(
                            f"Completed message {message_number}/{len(listed_messages)} "
                            f"on Gmail page {page_number}"
                        )
                    continue

                if progress is not None:
                    progress(
                        f"Fetching message {message_number}/{len(listed_messages)} "
                        f"from Gmail page {page_number}"
                    )
                message = messages_api.get(
                    userId="me", id=message_id, format="full"
                ).execute(num_retries=5)
                payload = message.get("payload")
                attachments = _decode_named_attachments(
                    messages_api, message_id, payload, progress
                )
                yield EmailMessage(id=message_id, attachments=attachments)
                fetched_count += 1
                if progress is not None:
                    progress(
                        f"Completed message {message_number}/{len(listed_messages)} "
                        f"on Gmail page {page_number}"
                    )
                if progress is not None and fetched_count % 10 == 0:
                    progress(f"Retrieved {fetched_count} Gmail messages...")

        next_page_token = page.get("nextPageToken")
        if not isinstance(next_page_token, str) or not next_page_token:
            break
        page_token = next_page_token

    if progress is not None:
        progress(
            f"Finished Gmail fetch: {fetched_count} message(s) retrieved; "
            f"{skipped_count} skipped from checkpoint"
        )


def _find_label_id(labels: object, label_name: str) -> str:
    if isinstance(labels, list):
        for label in labels:
            if not isinstance(label, dict):
                continue
            if label.get("name") == label_name:
                label_id = label.get("id")
                if isinstance(label_id, str):
                    return label_id
                break
    raise ValueError(f"Gmail label not found: {label_name}")


def _estimated_total_pages(result_size_estimate: object) -> int | None:
    if (
        not isinstance(result_size_estimate, int)
        or isinstance(result_size_estimate, bool)
        or result_size_estimate < 0
    ):
        return None
    return max(1, (result_size_estimate + _GMAIL_PAGE_SIZE - 1) // _GMAIL_PAGE_SIZE)


def _decode_named_attachments(
    messages_api: _GmailMessages,
    message_id: str,
    payload: object,
    progress: Callable[[str], None] | None = None,
) -> list[EmailAttachment]:
    attachments: list[EmailAttachment] = []
    for part in _iter_parts(payload):
        filename = part.get("filename")
        body = part.get("body")
        if (
            not isinstance(filename, str)
            or not filename.lower().endswith(".csv")
            or not isinstance(body, dict)
        ):
            continue

        data = body.get("data")
        if isinstance(data, str):
            content = _decode_base64url(data)
        else:
            attachment_id = body.get("attachmentId")
            if not isinstance(attachment_id, str):
                continue
            if progress is not None:
                progress(f"Downloading attachment {filename}")
            attachment = messages_api.attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute(num_retries=5)
            encoded_content = attachment.get("data")
            if not isinstance(encoded_content, str):
                continue
            content = _decode_base64url(encoded_content)

        attachments.append(EmailAttachment(filename=filename, content=content))

    return attachments


def _iter_parts(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []

    parts = [payload]
    nested_parts = payload.get("parts")
    if isinstance(nested_parts, list):
        for nested_part in nested_parts:
            parts.extend(_iter_parts(nested_part))
    return parts


def _decode_base64url(data: str) -> bytes:
    padded_data = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded_data)