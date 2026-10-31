import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from okofen_importer.gmail_auth import GMAIL_READONLY_SCOPE, create_gmail_service


class _FakeCredentials:
    loaded_from = None
    loaded_credentials = None

    def __init__(self, *, valid, expired=False, refresh_token=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refresh_calls = 0

    @classmethod
    def from_authorized_user_file(cls, token_file, scopes):
        cls.loaded_from = (token_file, scopes)
        return cls.loaded_credentials

    def refresh(self, request):
        self.refresh_calls += 1
        self.valid = True

    def to_json(self):
        return "serialized-token"


class _FakeFlow:
    created_from = None
    flow = None

    @classmethod
    def from_client_secrets_file(cls, secrets_file, scopes):
        cls.created_from = (secrets_file, scopes)
        return cls.flow

    def run_local_server(self, *, port):
        self.port = port
        return self.credentials


def _google_modules(build):
    google = types.ModuleType("google")
    google.__path__ = []
    google_auth = types.ModuleType("google.auth")
    google_auth.__path__ = []
    google_transport = types.ModuleType("google.auth.transport")
    google_transport.__path__ = []
    google_requests = types.ModuleType("google.auth.transport.requests")
    google_requests.Request = Mock(name="Request")
    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2.__path__ = []
    google_credentials = types.ModuleType("google.oauth2.credentials")
    google_credentials.Credentials = _FakeCredentials
    google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
    google_auth_oauthlib.__path__ = []
    google_flow = types.ModuleType("google_auth_oauthlib.flow")
    google_flow.InstalledAppFlow = _FakeFlow
    googleapiclient = types.ModuleType("googleapiclient")
    googleapiclient.__path__ = []
    google_discovery = types.ModuleType("googleapiclient.discovery")
    google_discovery.build = build

    modules = {
        "google": google,
        "google.auth": google_auth,
        "google.auth.transport": google_transport,
        "google.auth.transport.requests": google_requests,
        "google.oauth2": google_oauth2,
        "google.oauth2.credentials": google_credentials,
        "google_auth_oauthlib": google_auth_oauthlib,
        "google_auth_oauthlib.flow": google_flow,
        "googleapiclient": googleapiclient,
        "googleapiclient.discovery": google_discovery,
    }
    google.auth = google_auth
    google_auth.transport = google_transport
    google_transport.requests = google_requests
    google.oauth2 = google_oauth2
    google_oauth2.credentials = google_credentials
    google_auth_oauthlib.flow = google_flow
    googleapiclient.discovery = google_discovery
    return modules, google_requests.Request


class CreateGmailServiceTests(unittest.TestCase):
    def setUp(self):
        _FakeCredentials.loaded_from = None
        _FakeCredentials.loaded_credentials = None
        _FakeFlow.created_from = None
        _FakeFlow.flow = None

    def test_runs_installed_app_flow_and_saves_token(self):
        credentials = _FakeCredentials(valid=True)
        flow = _FakeFlow()
        flow.credentials = credentials
        _FakeFlow.flow = flow
        service = object()
        build = Mock(return_value=service)
        modules, _ = _google_modules(build)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            secrets_file = root / "client-secret.json"
            token_file = root / ".credentials" / "gmail-token.json"
            with patch.dict(sys.modules, modules):
                result = create_gmail_service(secrets_file, token_file)

            self.assertIs(result, service)
            self.assertEqual(_FakeFlow.created_from, (str(secrets_file), [GMAIL_READONLY_SCOPE]))
            self.assertEqual(flow.port, 0)
            self.assertEqual(token_file.read_text(encoding="utf-8"), "serialized-token")
            build.assert_called_once_with(
                "gmail", "v1", credentials=credentials, cache_discovery=False
            )

    def test_refreshes_expired_token_without_starting_browser_flow(self):
        credentials = _FakeCredentials(
            valid=False, expired=True, refresh_token="refresh-token"
        )
        _FakeCredentials.loaded_credentials = credentials
        build = Mock(return_value=object())
        modules, request_factory = _google_modules(build)

        with tempfile.TemporaryDirectory() as temporary_directory:
            token_file = Path(temporary_directory) / "gmail-token.json"
            token_file.write_text("existing-token", encoding="utf-8")
            with patch.dict(sys.modules, modules):
                create_gmail_service("client-secret.json", token_file)

            self.assertEqual(
                _FakeCredentials.loaded_from,
                (str(token_file), [GMAIL_READONLY_SCOPE]),
            )
            self.assertEqual(credentials.refresh_calls, 1)
            self.assertEqual(request_factory.call_count, 1)
            self.assertIsNone(_FakeFlow.created_from)
            self.assertEqual(token_file.read_text(encoding="utf-8"), "serialized-token")

    def test_default_token_path_is_outside_the_repository(self):
        credentials = _FakeCredentials(valid=True)
        flow = _FakeFlow()
        flow.credentials = credentials
        _FakeFlow.flow = flow
        build = Mock(return_value=object())
        modules, _ = _google_modules(build)

        with tempfile.TemporaryDirectory() as temporary_directory:
            home_directory = Path(temporary_directory)
            token_file = (
                home_directory / ".config" / "okofen-grafana" / "gmail-token.json"
            )
            with (
                patch("okofen_importer.gmail_auth.Path.home", return_value=home_directory),
                patch.dict(sys.modules, modules),
            ):
                create_gmail_service("client-secret.json")

            self.assertTrue(token_file.exists())


if __name__ == "__main__":
    unittest.main()