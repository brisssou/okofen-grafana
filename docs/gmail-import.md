# Gmail Import

The importer reads CSV attachments from one Gmail label and stores the parsed readings in SQLite. Run it once per import cycle with Python 3.12.8.

## Google OAuth Setup

Use a Google account that can access the Okofen messages. The importer uses the Gmail API with the read-only scope `https://www.googleapis.com/auth/gmail.readonly`; it does not send, modify, or delete mail.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, or select an existing one. Note the project name so you can select the same project in each following page.
2. Enable the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) for that project. Click **Enable** if it is not already enabled.
3. Open [Google Auth Platform > Branding](https://console.cloud.google.com/auth/branding). If Google Auth Platform setup has not started, click **Get started**. Enter an app name such as `Okofen CSV Importer`, choose your email as the user support email, enter a developer contact email, accept the policy acknowledgement, and save.
4. Open [Google Auth Platform > Audience](https://console.cloud.google.com/auth/audience). Choose **Internal** only if the Gmail account is in your Google Workspace organization and Internal is available. Otherwise choose **External**. If External is in **Testing** status, add the Gmail account you will import from under **Test users** and save. This is a personal/local importer; do not publish it just to use it yourself.
5. Open [Google Auth Platform > Data Access](https://console.cloud.google.com/auth/scopes). Click **Add or remove scopes**, add `https://www.googleapis.com/auth/gmail.readonly`, and save. This must match the scope requested by the importer.
6. Open [Google Auth Platform > Clients](https://console.cloud.google.com/auth/clients). Click **Create client**, select **Desktop app**, give it a recognizable name such as `Okofen importer on this computer`, and create it. Download the JSON file for that client.
7. Create the private config directory and move the downloaded JSON there. Do not put it in the repository:

  ```sh
  mkdir -p "$HOME/.config/okofen-grafana"
  mv "$HOME/Downloads/client_secret_*.json" "$HOME/.config/okofen-grafana/client_secret.json"
  chmod 600 "$HOME/.config/okofen-grafana/client_secret.json"
  ```

  If the downloaded file has a different name or is not in `Downloads`, adjust the source path in the `mv` command. The importer defaults to `~/.config/okofen-grafana/client_secret.json`; alternatively, set `GOOGLE_CLIENT_SECRETS` to its actual path.

Google may show an unverified-app warning because this is a locally configured app requesting a sensitive Gmail scope. For a personal importer, continue only if the consent screen and OAuth client belong to the Google Cloud project you just configured.

## Gmail Label

The importer fetches messages by their Gmail label's name, including messages added to the label later. Use the same exact spelling and capitalization for `OKOFEN_GMAIL_LABEL` or `--label`.

To create and apply the label in Gmail:

1. In Gmail, use the left sidebar's **Create new label** action. If it is hidden, expand **More** first.
2. Enter a name, for example `Okofen daily`, and create it.
3. Select the messages that have Okofen CSV attachments, open the toolbar's **Labels** action, select the new label, and apply it. You can also create a Gmail filter to apply the label automatically to future matching messages.
4. Set the importer label to the exact name you created, for example `OKOFEN_GMAIL_LABEL='Okofen daily'`.

On the first run, the importer prints a Google authorization URL and waits up to five minutes for the callback. Open that URL in your Windows browser when running under WSL; the importer intentionally does not try to launch a Linux desktop browser. Sign into the Gmail account that has the label, review the requested read-only access, and approve it. The browser should then redirect to a `http://localhost:<port>/` callback and show that authorization completed. Keep the importer process running until it prints the import results. If the callback page does not load, verify WSL localhost forwarding as described below. The refresh token is saved outside the repository at `~/.config/okofen-grafana/gmail-token.json` by default. Override that path with `GOOGLE_TOKEN_PATH` if needed. Do not commit OAuth client secrets or tokens. If Google shows the app is in testing, refresh tokens for external test users can expire; rerun the importer and consent again if token refresh stops working.

If the browser remains on a loading page after account selection, check the browser address: it should return to `http://localhost:<port>/`. If it cannot connect to localhost, WSL localhost forwarding may be disabled; enable `localhostForwarding=true` under `[wsl2]` in `%UserProfile%\.wslconfig`, then restart WSL with `wsl --shutdown` and retry. If Google displays an error instead, verify that the signed-in account is listed as a test user when the OAuth app audience is External and in Testing status.

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
uv run python -m okofen_importer
```

Alternatively, pass options directly:

```sh
uv run python -m okofen_importer \
  --label 'Okofen daily' \
  --client-secrets "$HOME/.config/okofen-grafana/client_secret.json" \
  --database data/okofen.sqlite3
```

`uv run` synchronizes the project dependencies before running the command. Do not add `--no-sync` when the virtual environment may have been recreated; that option skips installing dependencies. If you see `ModuleNotFoundError: No module named 'google'`, restore the project environment with:

```sh
uv sync --no-install-project
```

Then rerun the importer with `uv run python -m okofen_importer`.

Progress updates are written to stderr during Gmail authentication, message fetching, attachment parsing, and SQLite writes. Final per-attachment results are written to stdout. Gmail requests use up to five randomized exponential-backoff retries for rate-limit responses and transient server errors. If a run still stops on a quota error, wait before rerunning; attachments already written to SQLite are recognized and skipped. The command reports each attachment as imported, already imported, empty, or invalid. Import identity is the attachment filename plus the date of its first valid CSV timestamp. The SQLite database is runtime data under the ignored `data/` directory; Grafana reads it through the provisioned SQLite datasource.

Before parsing, each downloaded CSV's original bytes are saved under the ignored `data/gmail-attachments/` directory for future parser fixes or manual reprocessing. Cache filenames include a hashed message identifier, attachment position, content digest, and sanitized attachment filename, so repeated fetches reuse the same file while attachments with matching Gmail filenames remain distinct. A cache write failure stops the import before parsing or checkpointing that Gmail message, allowing a later run to retry. Already-checkpointed messages are still skipped; this cache does not backfill messages imported before caching was added.

To backfill raw cache files for previously checkpointed messages, run the download-only replay first, then replay the cache into SQLite:

```sh
uv run python -m okofen_importer --replay-download \
  --label 'Okofen daily' \
  --client-secrets "$HOME/.config/okofen-grafana/client_secret.json" \
  --token "$HOME/.config/okofen-grafana/gmail-token.json"

uv run python -m okofen_importer --replay-cache \
  --database data/okofen.sqlite3
```

`--replay-download` authenticates with Gmail and fetches every message under the label, including messages already recorded in `processed_messages`. It caches CSV attachment bodies only; it does not parse CSVs, access or modify SQLite, or write message checkpoints. It requires `--label` or `OKOFEN_GMAIL_LABEL` and accepts the usual OAuth options. This fetch may consume substantial Gmail API quota, especially for a large label. The subsequent `--replay-cache` step parses the downloaded files and imports them into the existing database.

To re-import the CSVs already present in the cache after changing the parser, run:

```sh
uv run python -m okofen_importer --replay-cache \
  --database data/okofen.sqlite3
```

Cache replay does not require a Gmail label or OAuth credentials and does not authenticate with or fetch from Gmail. It processes only files matching the importer's cache filename format, skips temporary and unrelated files, and writes to the configured existing database. Replay deliberately ignores Gmail message checkpoints and `imported_files` status so updated CSV fields can be added; SQLite's `INSERT OR IGNORE` preserves existing readings while inserting new fields. Import state is recorded only after a successful write. Replay does not delete or replace the database. It can only reprocess files that are actually present in `data/gmail-attachments/`; it cannot recover attachments that were never cached.
