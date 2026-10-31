import unittest
from pathlib import Path

from okofen_importer.email_importer import CsvAttachment, EmailAttachment, EmailMessage, extract_csv_attachments

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "email_sample.csv"


class EmailImporterTests(unittest.TestCase):
    def test_extract_csv_attachments_filters_non_csv_and_returns_payloads(self):
        csv_payload = FIXTURE_CSV.read_bytes()
        messages = [
            EmailMessage(
                id="a",
                attachments=[
                    EmailAttachment(filename="report.csv", content=csv_payload),
                    EmailAttachment(filename="notes.txt", content=b"ignore me"),
                ],
            ),
            EmailMessage(
                id="b",
                attachments=[
                    EmailAttachment(filename="other.csv", content=csv_payload),
                ],
            ),
        ]

        attachments = extract_csv_attachments(messages)

        self.assertEqual(len(attachments), 2)
        self.assertIsInstance(attachments[0], CsvAttachment)
        self.assertEqual(attachments[0].filename, "report.csv")
        self.assertIn(b"Datum;Zeit;AT", attachments[0].content)
        self.assertEqual(attachments[1].filename, "other.csv")

    def test_extract_csv_attachments_ignores_messages_without_attachments(self):
        messages = [
            EmailMessage(id="c", attachments=[]),
            EmailMessage(id="d", attachments=[]),
        ]

        self.assertEqual(extract_csv_attachments(messages), [])


if __name__ == "__main__":
    unittest.main()
