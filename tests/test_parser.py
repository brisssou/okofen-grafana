import datetime as dt
import unittest

from okofen_importer.parser import (
    _coerce_float,
    _parse_timestamp,
    parse_csv_content,
    parse_csv_file,
)


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

    def test_parses_recent_columns_without_reporting_them_as_unknown(self):
        result = parse_csv_file("tests/fixtures/touch_20261030.csv")

        self.assertIn("timestamp", result.records[0])
        self.assertAlmostEqual(result.records[0]["AT [°C]"], 12.3)
        self.assertAlmostEqual(result.records[0]["Radio 16499 Batt[%]"], 10.0)
        self.assertAlmostEqual(result.records[0]["Radio 16499 Rssi[dBm]"], -8.5)
        self.assertAlmostEqual(result.records[0]["PE1 Starts[h]"], 5383)
        self.assertEqual(result.unknown_columns, [])

    def test_skips_repeated_headers_and_rows_without_valid_timestamps(self):
        content = (
            "Datum;Zeit;KT Ist [°C]\n"
            "02.12.2023;00:03:36;51,9\n"
            "Datum;Zeit;KT Ist [°C]\n"
            "not-a-date;not-a-time;52,0\n"
            "02.12.2023;00:04:36;52,1\n"
        ).encode("cp1252")

        with self.assertLogs("okofen_importer.parser", level="WARNING") as captured:
            result = parse_csv_content(content, "repeated-header.csv")

        self.assertEqual(len(result.records), 2)
        self.assertTrue(all("timestamp" in row for row in result.records))
        self.assertAlmostEqual(result.records[0]["KT Ist [°C]"], 51.9)
        self.assertAlmostEqual(result.records[1]["KT Ist [°C]"], 52.1)
        warnings = "\n".join(captured.output)
        self.assertIn("Skipping repeated header row", warnings)
        self.assertIn("Skipping CSV row without a valid timestamp", warnings)

    def test_parses_legacy_csv_without_a_header(self):
        fields = ["0"] * 68
        fields[0] = "23.09.2024"
        fields[1] = "07:19:11"
        fields[2] = "19,7"
        fields[4] = "0,0"
        content = (";".join(fields) + ";\n" + ";".join(fields) + ";\n").encode(
            "cp1252"
        )

        with self.assertLogs("okofen_importer.parser", level="WARNING") as captured:
            result = parse_csv_content(content, "headerless.csv")

        self.assertEqual(len(result.records), 2)
        self.assertEqual(
            result.records[0]["timestamp"], dt.datetime(2024, 9, 23, 7, 19, 11)
        )
        self.assertAlmostEqual(result.records[0]["AT [°C]"], 19.7)
        self.assertEqual(result.unknown_columns, [])
        self.assertIn("Missing CSV header", "\n".join(captured.output))

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
