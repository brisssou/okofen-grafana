from __future__ import annotations

from pathlib import Path
from typing import cast

from .gmail_fetcher import GmailService

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def create_gmail_service(
    client_secrets_path: str | Path, token_path: str | Path | None = None
) -> GmailService:
    """Authorize Gmail read access and return an API service for the fetcher."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError
    from googleapiclient.discovery import build

    client_secrets_file = Path(client_secrets_path)
    token_file = (
        Path(token_path)
        if token_path is not None
        else Path.home() / ".config" / "okofen-grafana" / "gmail-token.json"
    )
    credentials = None

    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_file), [GMAIL_READONLY_SCOPE]
        )

    if credentials is not None and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif credentials is None or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets_file), [GMAIL_READONLY_SCOPE]
        )
        try:
            credentials = flow.run_local_server(
                port=0, open_browser=False, timeout_seconds=300
            )
        except WSGITimeoutError as error:
            raise RuntimeError(
                "Gmail OAuth callback was not received within 5 minutes. "
                "Open the printed authorization URL in your Windows browser and "
                "keep this importer process running until the browser returns to localhost."
            ) from error

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")

    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return cast(GmailService, service)