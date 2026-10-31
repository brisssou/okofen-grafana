# Gmail Import

The importer reads CSV attachments from one Gmail label and stores the parsed readings in SQLite. Run it once per import cycle with Python 3.12.8.

## Google OAuth Setup

1. In Google Cloud Console, create or select a project and enable the Gmail API.
2. Configure the OAuth consent screen and add the Gmail account as a test user if the app is in testing mode.
3. Create an OAuth client ID for a **Desktop app** and download its client-secrets JSON file.
4. Store the file outside this repository, for example at `~/.config/okofen-grafana/client_secret.json`.
5. Create a Gmail label for the Okofen messages and apply it to the messages whose CSV attachments should be imported.

The first run opens a browser for consent to the read-only Gmail scope. The refresh token is saved outside the repository at `~/.config/okofen-grafana/gmail-token.json` by default. Override that path with `GOOGLE_TOKEN_PATH` if needed. Do not commit OAuth client secrets or tokens.

## Install Dependencies

With Python 3.12.8 and `uv` installed, run from the repository root:

```sh
uv sync --no-install-project
```

## Run

Set the Gmail label. The client-secrets file and database path can also be overridden:

```sh
export OKOFEN_GMAIL_LABEL='Okofen daily'
export GOOGLE_CLIENT_SECRETS="$HOME/.config/okofen-grafana/client_secret.json"
export OKOFEN_DATABASE="$PWD/data/okofen.sqlite3"
uv run --no-sync python -m okofen_importer
```

Alternatively, pass options directly:

```sh
uv run --no-sync python -m okofen_importer \
  --label 'Okofen daily' \
  --client-secrets "$HOME/.config/okofen-grafana/client_secret.json" \
  --database data/okofen.sqlite3
```

The command reports each attachment as imported, already imported, empty, or invalid. Import identity is the attachment filename plus the date of its first valid CSV timestamp. The SQLite database is runtime data under the ignored `data/` directory; Grafana reads it through the provisioned SQLite datasource.
