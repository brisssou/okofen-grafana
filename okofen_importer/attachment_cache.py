from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from .email_importer import CsvAttachment

DEFAULT_ATTACHMENT_CACHE_DIR = Path("data") / "gmail-attachments"
_CACHED_CSV_NAME = re.compile(
    r"^[0-9a-f]{64}-\d+-[0-9a-f]{64}-(?P<filename>.+\.csv)$",
    re.IGNORECASE,
)


def iter_cached_csv_files(
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
) -> Iterator[tuple[Path, str]]:
    """Yield recognized cached CSVs with their sanitized source filenames."""
    directory = Path(cache_dir)
    if not directory.is_dir():
        return

    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        match = _CACHED_CSV_NAME.fullmatch(path.name)
        if match is not None:
            yield path, match.group("filename")


def cache_attachment(
    attachment: CsvAttachment,
    cache_dir: str | Path = DEFAULT_ATTACHMENT_CACHE_DIR,
    attachment_number: int = 1,
) -> Path:
    """Persist an attachment's original bytes under a stable, collision-safe name."""
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)

    content_hash = hashlib.sha256(attachment.content).hexdigest()
    message_key = (
        hashlib.sha256(attachment.message_id.encode("utf-8")).hexdigest()
        if attachment.message_id is not None
        else content_hash
    )
    filename = _safe_filename(attachment.filename)
    name = f"{message_key}-{attachment_number:04d}-{content_hash}-{filename}"
    destination = directory / name

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".attachment-", dir=directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(attachment.content)
            temporary.flush()
            os.fsync(temporary.fileno())

        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            if destination.read_bytes() == attachment.content:
                return destination
            destination = _next_available_path(destination)
            os.link(temporary_path, destination)
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", basename).strip("._")
    safe_name = safe_name or "attachment.csv"
    if len(safe_name) > 120:
        safe_name = (
            safe_name[:116] + safe_name[-4:]
            if safe_name.lower().endswith(".csv")
            else safe_name[:120]
        )
    return safe_name


def _next_available_path(path: Path) -> Path:
    suffix = 1
    while True:
        candidate = path.with_name(f"{path.stem}-{suffix}{path.suffix}")
        if not candidate.exists():
            return candidate
        suffix += 1
