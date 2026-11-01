import tempfile
import unittest
from pathlib import Path

from okofen_importer.attachment_cache import cache_attachment
from okofen_importer.email_importer import CsvAttachment


class AttachmentCacheTests(unittest.TestCase):
    def test_repeated_saves_are_idempotent_and_same_filenames_do_not_collide(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory)
            first = CsvAttachment("message-1", "report.csv", b"first attachment")
            second = CsvAttachment("message-2", "report.csv", b"second attachment")

            first_path = cache_attachment(first, cache_dir)
            repeated_path = cache_attachment(first, cache_dir)
            second_path = cache_attachment(second, cache_dir)

            self.assertEqual(first_path, repeated_path)
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), first.content)
            self.assertEqual(second_path.read_bytes(), second.content)
            self.assertEqual(len(list(cache_dir.glob("*.csv"))), 2)

    def test_distinguishes_same_message_attachments_with_same_filename(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory)
            first = CsvAttachment("message-1", "report.csv", b"first")
            second = CsvAttachment("message-1", "report.csv", b"second")

            first_path = cache_attachment(first, cache_dir, attachment_number=1)
            second_path = cache_attachment(second, cache_dir, attachment_number=2)

            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), first.content)
            self.assertEqual(second_path.read_bytes(), second.content)

    def test_sanitizes_attachment_filename(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = cache_attachment(
                CsvAttachment("message-1", "..\\outside.csv", b"raw"),
                temporary_directory,
            )

            self.assertEqual(path.parent, Path(temporary_directory))
            self.assertTrue(path.name.endswith("outside.csv"))

    def test_long_attachment_filename_keeps_csv_extension(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = cache_attachment(
                CsvAttachment("message-1", "a" * 200 + ".csv", b"raw"),
                temporary_directory,
            )

            self.assertTrue(path.name.endswith(".csv"))
            self.assertLessEqual(len(path.name), 255)


if __name__ == "__main__":
    unittest.main()
