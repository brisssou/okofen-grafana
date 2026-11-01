# Okofen Grafana

A local monitoring stack for Okofen heating-system data. The importer reads CSV
attachments from a Gmail label, stores timestamped readings in SQLite, and
Grafana provides a provisioned dashboard for exploring temperature, heating
circuits, burner operation, remote sensors, and system status.

This project is designed to run locally. It does not send email or modify Gmail
messages: Gmail access uses the read-only API scope.

This project is vibe-coded from a bootstrap I did a long time ago. So, more like vibe-finished.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)
- [Podman](https://podman.io/) with `podman play kube` support
- A Gmail API OAuth desktop client, if importing from Gmail

## Quick start

Clone the repository and run commands from its root.

### Install Python dependencies

```sh
uv sync --no-install-project
```

### Configure Gmail access

Create a Gmail API OAuth desktop client and save its client-secrets JSON outside
the repository. Set up the Gmail label containing the Okofen CSV attachments.
The default label is `chaudière`.

The complete OAuth, label, and first-run instructions are in
[docs/gmail-import.md](docs/gmail-import.md).

### Import readings

```sh
uv run python -m okofen_importer
```

Override the default label or paths as needed:

```sh
uv run python -m okofen_importer \
  --label 'Okofen daily' \
  --client-secrets "$HOME/.config/okofen-grafana/client_secret.json" \
  --database data/okofen.sqlite3
```

The importer caches original CSV attachments in `data/gmail-attachments/` and
stores readings and import state in `data/okofen.sqlite3`. Both are local
runtime data and are ignored by Git. The database can become large; ensure the
host has sufficient disk space and back up the database and cache if you need
to preserve them.

To re-import cached CSVs after parser changes, without contacting Gmail:

```sh
uv run python -m okofen_importer --replay-cache \
  --database data/okofen.sqlite3
```

For replay options and details, see [docs/gmail-import.md](docs/gmail-import.md).

### Start Grafana

After creating the database, start the local Grafana pod from the repository
root:

```sh
podman play kube okofen.yaml
```

Open [http://localhost:3000](http://localhost:3000). The provisioned dashboard
uses `data/okofen.sqlite3`. Grafana startup, restart, and troubleshooting
instructions are in [docs/grafana.md](docs/grafana.md).

## Tests

Run the test suite with:

```sh
uv run python -m unittest discover -s tests
```

## Security

The checked-in local Grafana configuration enables anonymous access and uses
the default `admin` / `grafana` credentials. Keep this deployment on a trusted
local machine; do not expose it to the internet or an untrusted network without
changing those settings and reviewing the network binding.

Never commit OAuth client secrets, Gmail tokens, imported CSVs, or the SQLite
database.

## License

This project is released under the [WTFPL Version 2](LICENSE).
