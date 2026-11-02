# Project Context

## What this repository does

This project imports Ökofen heating-system CSV readings from Gmail into a local
SQLite database, which Grafana reads through its SQLite datasource. Runtime
database files, cached attachments, and container data live under `data/` and
are ignored by Git.

## Architecture

- `okofen_importer/gmail_auth.py` handles local OAuth credentials.
- `okofen_importer/gmail_fetcher.py` resolves the configured Gmail label,
  paginates messages, retries transient API failures, and downloads CSV
  attachments only. The default label is `chaudière`; `--label` and
  `OKOFEN_GMAIL_LABEL` override it.
- `okofen_importer/attachment_cache.py` preserves raw CSV bytes under
  `data/gmail-attachments/` before parsing.
- `okofen_importer/driver.py` coordinates cache, parse, write, and checkpoints.
- `okofen_importer/parser.py` normalizes CSV rows, tracks recognized columns,
  skips repeated headers and invalid-timestamp rows, and supports the known
  headerless legacy CSV layout.
- `okofen_importer/database.py` owns the SQLite file: it stores readings and
  tracks imported files and completed Gmail messages over one connection, and
  its `transaction()` lets a readings write and its checkpoint commit together.
- `okofen_importer/cli.py` exposes the command and compact stderr progress.
- `--replay-download` backfills cached CSV attachments from Gmail without
  importing them. `--replay-cache` reparses cached CSVs without contacting
  Gmail; replay deliberately bypasses message and imported-file checkpoints.
- `grafana/` contains the Podman configuration, provisioning, and dashboards.
  Dashboard time filters should remain compatible with the SQLite timestamp
  index. `docs/gmail-import.md` and `docs/grafana.md` document setup and
  operations; `README.md` is the project entry point.

Message checkpoints prevent fetching completed messages again. Imported-file
state separately identifies files by attachment filename and data date. Keep
these mechanisms consistent when changing import or replay behavior. Do not
delete, recreate, or otherwise rewrite the user's SQLite database to work
around import state; it contains substantial user data.

## Development

- Python version: 3.12.8 (`.python-version`); dependencies are managed by `uv`.
- Run tests: `uv run python -m unittest discover -s tests`
- Run the importer: `uv run python -m okofen_importer`
- Override the default label: `uv run python -m okofen_importer --label "LABEL"`
- See `docs/gmail-import.md` for OAuth setup, replay modes, command options, and
  operational guidance. See `docs/grafana.md` for starting Grafana.

Tests use `unittest` and local fixtures/mocks; do not contact Gmail or run a
real import for validation. Prefer focused test modules during iteration.
Preserve unrelated worktree changes and runtime data. Only stage or commit
changes when explicitly requested, and follow the user's requested scope.
