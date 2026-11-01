from __future__ import annotations

import csv
from io import BytesIO, TextIOWrapper
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

LOGGER = logging.getLogger(__name__)

KNOWN_COLUMNS = {
    "Datum",
    "Zeit",
    "AT [°C]",
    "ATakt [°C]",
    "KT Ist [°C]",
    "KT Soll [°C]",
    "BR",
    "Sperrzeit",
    "PE1_BR1",
    "HK1 VL Ist[°C]",
    "HK1 VL Soll[°C]",
    "HK1 RT Ist[°C]",
    "HK1 RT Soll[°C]",
    "HK1 Pumpe",
    "HK1 Mischer",
    "HK1 Fernb[°C]",
    "HK1 Status",
    "HK2 VL Ist[°C]",
    "HK2 VL Soll[°C]",
    "HK2 RT Ist[°C]",
    "HK2 RT Soll[°C]",
    "HK2 Pumpe",
    "HK2 Mischer",
    "HK2 Fernb[°C]",
    "HK2 Status",
    "Zubrp1 Pumpe",
    "Radio 16499 Temp[°C]",
    "Radio 16499 Hum[%]",
    "Radio 16499 Batt[%]",
    "Radio 16499 Rssi[dBm]",
    "PE1 KT[°C]",
    "PE1 KT_SOLL[°C]",
    "PE1 UW Freigabe[°C]",
    "PE1 Modulation[%]",
    "PE1 FRT Ist[°C]",
    "PE1 FRT Soll[°C]",
    "PE1 FRT End[°C]",
    "PE1 Einschublaufzeit[zs]",
    "PE1 Pausenzeit[zs]",
    "PE1 Luefterdrehzahl[%]",
    "PE1 Saugzugdrehzahl[%]",
    "PE1 Unterdruck Ist[EH]",
    "PE1 Unterdruck Soll[EH]",
    "PE1 Fuellstand[kg]",
    "PE1 Fuellstand ZWB[kg]",
    "PE1 Status",
    "PE1 Statusbit",
    "PE1 Motor ES",
    "PE1 Motor RA",
    "PE1 Motor RES1",
    "PE1 Motor TURBINE",
    "PE1 Motor ZUEND",
    "PE1 Motor UW[%]",
    "PE1 Motor AV",
    "PE1 Motor RES2",
    "PE1 Motor MA",
    "PE1 Motor RM",
    "PE1 Motor SM",
    "PE1 CAP RA",
    "PE1 CAP ZB",
    "PE1 AK",
    "PE1 Saug-Int[min]",
    "PE1 DigIn1",
    "PE1 DigIn2",
    "PE1 CntDig1",
    "PE1 Ashfill[kg]",
    "PE1 Starts[h]",
    "PE1 Runtime[h]",
    "Fehler1",
    "Fehler2",
    "Fehler3",
}

LEGACY_COLUMNS = (
    "Datum",
    "Zeit",
    "AT [°C]",
    "ATakt [°C]",
    "KT Ist [°C]",
    "KT Soll [°C]",
    "BR",
    "Sperrzeit",
    "PE1_BR1",
    "HK1 VL Ist[°C]",
    "HK1 VL Soll[°C]",
    "HK1 RT Ist[°C]",
    "HK1 RT Soll[°C]",
    "HK1 Pumpe",
    "HK1 Mischer",
    "HK1 Fernb[°C]",
    "HK1 Status",
    "HK2 VL Ist[°C]",
    "HK2 VL Soll[°C]",
    "HK2 RT Ist[°C]",
    "HK2 RT Soll[°C]",
    "HK2 Pumpe",
    "HK2 Mischer",
    "HK2 Fernb[°C]",
    "HK2 Status",
    "Zubrp1 Pumpe",
    "Radio 16499 Temp[°C]",
    "Radio 16499 Hum[%]",
    "PE1 KT[°C]",
    "PE1 KT_SOLL[°C]",
    "PE1 UW Freigabe[°C]",
    "PE1 Modulation[%]",
    "PE1 FRT Ist[°C]",
    "PE1 FRT Soll[°C]",
    "PE1 FRT End[°C]",
    "PE1 Einschublaufzeit[zs]",
    "PE1 Pausenzeit[zs]",
    "PE1 Luefterdrehzahl[%]",
    "PE1 Saugzugdrehzahl[%]",
    "PE1 Unterdruck Ist[EH]",
    "PE1 Unterdruck Soll[EH]",
    "PE1 Fuellstand[kg]",
    "PE1 Fuellstand ZWB[kg]",
    "PE1 Status",
    "PE1 Statusbit",
    "PE1 Motor ES",
    "PE1 Motor RA",
    "PE1 Motor RES1",
    "PE1 Motor TURBINE",
    "PE1 Motor ZUEND",
    "PE1 Motor UW[%]",
    "PE1 Motor AV",
    "PE1 Motor RES2",
    "PE1 Motor MA",
    "PE1 Motor RM",
    "PE1 Motor SM",
    "PE1 CAP RA",
    "PE1 CAP ZB",
    "PE1 AK",
    "PE1 Saug-Int[min]",
    "PE1 DigIn1",
    "PE1 DigIn2",
    "PE1 CntDig1",
    "PE1 Ashfill[kg]",
    "PE1 Runtime[h]",
    "Fehler1",
    "Fehler2",
    "Fehler3",
)


@dataclass(slots=True)
class CsvImportResult:
    source_name: str
    records: list[dict[str, Any]] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)


def _coerce_float(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        LOGGER.warning("Skipping malformed numeric value: %r", raw)
        return None


def _parse_timestamp(date_raw: str | None, time_raw: str | None) -> datetime | None:
    if date_raw is None or time_raw is None:
        return None
    date_text = date_raw.strip()
    time_text = time_raw.strip()
    if not date_text or not time_text:
        return None
    try:
        return datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        LOGGER.warning(
            "Skipping malformed timestamp: date=%r, time=%r",
            date_text,
            time_text,
        )
        return None


def _normalize_row(raw_row: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    canonical_row = {key.strip(): value for key, value in raw_row.items() if key is not None}
    timestamp = _parse_timestamp(canonical_row.get("Datum"), canonical_row.get("Zeit"))
    if timestamp is not None:
        normalized["timestamp"] = timestamp

    for key, value in canonical_row.items():
        if key not in KNOWN_COLUMNS:
            continue
        if key in {"Datum", "Zeit"}:
            continue
        if value is None:
            normalized[key] = None
            continue
        numeric = _coerce_float(value)
        normalized[key] = numeric if numeric is not None else value.strip()

    return normalized


def parse_csv_file(path: str | Path) -> CsvImportResult:
    csv_path = Path(path)
    with csv_path.open("r", encoding="cp1252", newline="") as handle:
        return _parse_csv(handle, csv_path.name)


def parse_csv_content(content: bytes, source_name: str) -> CsvImportResult:
    with TextIOWrapper(BytesIO(content), encoding="cp1252", newline="") as handle:
        return _parse_csv(handle, source_name)


def _parse_csv(handle: TextIO, source_name: str) -> CsvImportResult:
    reader = csv.DictReader(handle, delimiter=";")
    if reader.fieldnames is None:
        return CsvImportResult(source_name=source_name, records=[], unknown_columns=[])

    header = [field.strip() for field in reader.fieldnames]
    if _is_legacy_headerless_row(header):
        LOGGER.warning(
            "Missing CSV header in %s; using legacy column order", source_name
        )
        handle.seek(0)
        reader = csv.DictReader(handle, fieldnames=LEGACY_COLUMNS, delimiter=";")
        header = list(LEGACY_COLUMNS)

    unknown_columns = [field for field in header if field and field not in KNOWN_COLUMNS]
    if unknown_columns:
        LOGGER.warning("Unknown columns in %s: %s", source_name, ", ".join(unknown_columns))

    records: list[dict[str, Any]] = []
    for raw_row in reader:
        if not raw_row:
            continue
        canonical_row = {
            key.strip(): value for key, value in raw_row.items() if key is not None
        }
        date_value = canonical_row.get("Datum")
        time_value = canonical_row.get("Zeit")
        if (
            date_value is not None
            and time_value is not None
            and date_value.strip() == "Datum"
            and time_value.strip() == "Zeit"
        ):
            LOGGER.warning("Skipping repeated header row in %s", source_name)
            continue

        normalized = _normalize_row(canonical_row)
        if normalized:
            if "timestamp" not in normalized:
                LOGGER.warning(
                    "Skipping CSV row without a valid timestamp in %s", source_name
                )
                continue
            records.append(normalized)

    return CsvImportResult(source_name=source_name, records=records, unknown_columns=unknown_columns)


def _is_legacy_headerless_row(fields: list[str]) -> bool:
    if len(fields) not in {len(LEGACY_COLUMNS), len(LEGACY_COLUMNS) + 1}:
        return False
    if len(fields) == len(LEGACY_COLUMNS) + 1 and fields[-1]:
        return False
    try:
        datetime.strptime(f"{fields[0]} {fields[1]}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        return False
    return True
