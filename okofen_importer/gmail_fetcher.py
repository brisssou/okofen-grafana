from __future__ import annotations

import base64
from typing import Protocol

from .email_importer import EmailAttachment, EmailMessage


class _GmailRequest(Protocol):
    def execute(self) -> dict[str, object]: ...


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
        pageToken: str | None = None,
    ) -> _GmailRequest: ...

    def get(self, *, userId: str, id: str, format: str) -> _GmailRequest: ...

    def attachments(self) -> _GmailAttachments: ...


class _GmailUsers(Protocol):
    def labels(self) -> _GmailLabels: ...

    def messages(self) -> _GmailMessages: ...


class GmailService(Protocol):
    def users(self) -> _GmailUsers: ...


def fetch_gmail_messages(service: GmailService, label_name: str) -> list[EmailMessage]:
    """Fetch messages with the named Gmail label and decode their attachments."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label_id = _find_label_id(labels, label_name)
    messages_api = service.users().messages()
    fetched_messages: list[EmailMessage] = []
    page_token: str | None = None

    while True:
        if page_token is None:
            page = messages_api.list(userId="me", labelIds=[label_id]).execute()
        else:
            page = messages_api.list(
                userId="me", labelIds=[label_id], pageToken=page_token
            ).execute()

        listed_messages = page.get("messages", [])
        if isinstance(listed_messages, list):
            for listed_message in listed_messages:
                if not isinstance(listed_message, dict):
                    continue
                message_id = listed_message.get("id")
                if not isinstance(message_id, str):
                    continue

                message = messages_api.get(
                    userId="me", id=message_id, format="full"
                ).execute()
                payload = message.get("payload")
                attachments = _decode_named_attachments(
                    messages_api, message_id, payload
                )
                fetched_messages.append(
                    EmailMessage(id=message_id, attachments=attachments)
                )

        next_page_token = page.get("nextPageToken")
        if not isinstance(next_page_token, str) or not next_page_token:
            break
        page_token = next_page_token

    return fetched_messages


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


def _decode_named_attachments(
    messages_api: _GmailMessages, message_id: str, payload: object
) -> list[EmailAttachment]:
    attachments: list[EmailAttachment] = []
    for part in _iter_parts(payload):
        filename = part.get("filename")
        body = part.get("body")
        if not isinstance(filename, str) or not filename or not isinstance(body, dict):
            continue

        data = body.get("data")
        if isinstance(data, str):
            content = _decode_base64url(data)
        else:
            attachment_id = body.get("attachmentId")
            if not isinstance(attachment_id, str):
                continue
            attachment = messages_api.attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute()
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