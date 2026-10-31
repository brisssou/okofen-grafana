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
    from google_auth_oauthlib.flow import InstalledAppFlow
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
        credentials = flow.run_local_server(port=0)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")

    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return cast(GmailService, service)