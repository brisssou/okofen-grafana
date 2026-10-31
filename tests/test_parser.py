import datetime as dt
import unittest

from okofen_importer.parser import _coerce_float, _parse_timestamp, parse_csv_file


class ParseCsvFileTests(unittest.TestCase):
    def test_parses_historical_rows_and_detects_metadata(self):
        # These fixtures live under tests/fixtures so the parser validates explicit test input, not repo runtime data.
        result = parse_csv_file("tests/fixtures/touch_20231202.csv")

        self.assertGreaterEqual(len(result.records), 3)
        self.assertEqual(result.records[0]["timestamp"], dt.datetime(2023, 12, 2, 0, 3, 36))
        self.assertAlmostEqual(result.records[0]["AT [°C]"], 8.0)
        self.assertAlmostEqual(result.records[0]["KT Ist [°C]"], 51.9)
        self.assertEqual(result.source_name, "touch_20231202.csv")
        self.assertEqual(result.unknown_columns, [])

    def test_logs_unknown_columns_without_breaking_known_fields(self):
        result = parse_csv_file("tests/fixtures/touch_20261030.csv")

        self.assertIn("timestamp", result.records[0])
        self.assertAlmostEqual(result.records[0]["AT [°C]"], 12.3)
        self.assertIn("Radio 16499 Batt[%]", result.unknown_columns)
        self.assertIn("PE1 Starts[h]", result.unknown_columns)

    def test_coerce_float_handles_invalid_values_without_raising(self):
        with self.assertLogs("okofen_importer.parser", level="WARNING") as captured:
            value = _coerce_float("not-a-number")

        self.assertIsNone(value)
        self.assertIn("Skipping malformed numeric value", "\n".join(captured.output))

    def test_parse_timestamp_handles_invalid_values_without_raising(self):
        with self.assertLogs("okofen_importer.parser", level="WARNING") as captured:
            value = _parse_timestamp("99.99.9999", "not-a-time")

        self.assertIsNone(value)
        self.assertIn("Skipping malformed timestamp", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
