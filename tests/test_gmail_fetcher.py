import base64
import unittest

from okofen_importer.email_importer import EmailAttachment, EmailMessage
from okofen_importer.gmail_fetcher import fetch_gmail_messages, iter_gmail_messages


class _Request:
    requests = []

    def __init__(self, response):
        self.response = response
        self.__class__.requests.append(self)

    def execute(self, *, num_retries=0):
        self.num_retries = num_retries
        return self.response


class _Attachments:
    def __init__(self):
        self.requests = []

    def get(self, *, userId, messageId, id):
        self.request = (userId, messageId, id)
        self.requests.append(self.request)
        return _Request({"data": base64.urlsafe_b64encode(b"attachment bytes").decode()})


class _Labels:
    def __init__(self, definitions):
        self.definitions = definitions

    def list(self, *, userId):
        return _Request({"labels": self.definitions})


class _Messages:
    def __init__(self):
        self.pages = {
            None: {"messages": [{"id": "message-1"}], "nextPageToken": "next"},
            "next": {"messages": [{"id": "message-2"}]},
        }
        self.message_payloads = {
            "message-1": {
                "payload": {
                    "parts": [
                        {
                            "filename": "nested.csv",
                            "body": {"data": base64.urlsafe_b64encode(b"csv bytes").decode()},
                        }
                    ]
                }
            },
            "message-2": {
                "payload": {
                    "parts": [
                        {
                            "filename": "notes.txt",
                            "body": {"attachmentId": "attachment-2"},
                        },
                        {
                            "filename": "report.csv",
                            "body": {"attachmentId": "attachment-1"},
                        }
                    ]
                }
            },
        }
        self.attachments_api = _Attachments()
        self.list_requests = []
        self.get_requests = []

    def list(self, *, userId, labelIds, pageToken=None):
        self.list_requests.append((userId, labelIds, pageToken))
        return _Request(self.pages[pageToken])

    def get(self, *, userId, id, format):
        self.get_requests.append((userId, id, format))
        return _Request(self.message_payloads[id])

    def attachments(self):
        return self.attachments_api


class _Users:
    def __init__(self, label_definitions):
        self.labels_api = _Labels(label_definitions)
        self.messages_api = _Messages()

    def labels(self):
        return self.labels_api

    def messages(self):
        return self.messages_api


class _Service:
    def __init__(self, label_definitions=None):
        if label_definitions is None:
            label_definitions = [{"id": "Label_123", "name": "Okofen daily"}]
        self.users_api = _Users(label_definitions)

    def users(self):
        return self.users_api


class FetchGmailMessagesTests(unittest.TestCase):
    def test_fetches_labelled_pages_and_decodes_nested_attachments(self):
        _Request.requests = []
        service = _Service()
        progress_messages = []

        messages = fetch_gmail_messages(
            service, "Okofen daily", progress=progress_messages.append
        )

        self.assertEqual(
            messages,
            [
                EmailMessage(
                    id="message-1",
                    attachments=[EmailAttachment("nested.csv", b"csv bytes")],
                ),
                EmailMessage(
                    id="message-2",
                    attachments=[EmailAttachment("report.csv", b"attachment bytes")],
                ),
            ],
        )
        self.assertEqual(
            service.users_api.messages_api.list_requests,
            [
                ("me", ["Label_123"], None),
                ("me", ["Label_123"], "next"),
            ],
        )
        self.assertEqual(
            service.users_api.messages_api.attachments_api.requests,
            [("me", "message-2", "attachment-1")],
        )
        self.assertIn("Looking up Gmail label: Okofen daily", progress_messages)
        self.assertIn(
            "Gmail page 1: 1 message(s); 0 retrieved, 0 checkpointed so far",
            progress_messages,
        )
        self.assertIn("Fetching message 1/1 from Gmail page 1", progress_messages)
        self.assertIn("Downloading attachment report.csv", progress_messages)
        self.assertIn(
            "Finished Gmail fetch: 2 message(s) retrieved; 0 skipped from checkpoint",
            progress_messages,
        )
        self.assertTrue(all(request.num_retries == 5 for request in _Request.requests))

    def test_raises_for_unknown_label(self):
        service = _Service(label_definitions=[])

        with self.assertRaisesRegex(ValueError, "Gmail label not found: Missing"):
            fetch_gmail_messages(service, "Missing")

    def test_skips_checkpointed_message_before_fetching_its_payload(self):
        service = _Service()

        messages = list(
            iter_gmail_messages(
                service,
                "Okofen daily",
                is_message_processed=lambda message_id: message_id == "message-1",
            )
        )

        self.assertEqual([message.id for message in messages], ["message-2"])
        self.assertEqual(
            service.users_api.messages_api.get_requests,
            [("me", "message-2", "full")],
        )


if __name__ == "__main__":
    unittest.main()