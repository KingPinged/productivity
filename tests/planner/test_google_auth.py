import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.planner.ingestion.google_auth import GoogleAuthManager

FAKE_CLIENT_CONFIG = {
    "web": {
        "client_id": "fake-client-id.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8321/auth/callback"],
    }
}

@pytest.fixture
def auth_manager():
    with patch("src.planner.ingestion.google_auth.keyring") as mock_kr:
        mock_kr.get_password.return_value = None
        mgr = GoogleAuthManager(
            client_config=FAKE_CLIENT_CONFIG,
            redirect_uri="http://localhost:8321/auth/callback",
            scopes=["https://www.googleapis.com/auth/gmail.readonly",
                     "https://www.googleapis.com/auth/calendar.readonly"],
        )
        yield mgr, mock_kr

class TestGoogleAuthManager:
    def test_generate_auth_url_returns_url_and_state(self, auth_manager):
        mgr, _ = auth_manager
        url, state = mgr.generate_auth_url()
        assert "accounts.google.com" in url
        assert "state=" in url
        assert len(state) > 10

    def test_generate_auth_url_includes_scopes(self, auth_manager):
        mgr, _ = auth_manager
        url, _ = mgr.generate_auth_url()
        assert "gmail.readonly" in url
        assert "calendar.readonly" in url

    def test_store_tokens_uses_keyring(self, auth_manager):
        mgr, mock_kr = auth_manager
        mgr.store_tokens("user@gmail.com", {
            "token": "access-token-123",
            "refresh_token": "refresh-token-456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id",
            "client_secret": "fake-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        })
        mock_kr.set_password.assert_called_once()
        call_args = mock_kr.set_password.call_args[0]
        assert call_args[0] == "productivity-planner"
        assert call_args[1] == "user@gmail.com"
        stored = json.loads(call_args[2])
        assert stored["token"] == "access-token-123"
        assert stored["refresh_token"] == "refresh-token-456"

    def test_get_credentials_returns_none_when_no_tokens(self, auth_manager):
        mgr, mock_kr = auth_manager
        mock_kr.get_password.return_value = None
        creds = mgr.get_credentials("user@gmail.com")
        assert creds is None

    def test_get_credentials_returns_credentials_when_stored(self, auth_manager):
        mgr, mock_kr = auth_manager
        mock_kr.get_password.return_value = json.dumps({
            "token": "access-token",
            "refresh_token": "refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id",
            "client_secret": "fake-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        })
        creds = mgr.get_credentials("user@gmail.com")
        assert creds is not None
        assert creds.token == "access-token"

    def test_remove_tokens(self, auth_manager):
        mgr, mock_kr = auth_manager
        mgr.remove_tokens("user@gmail.com")
        mock_kr.delete_password.assert_called_once_with(
            "productivity-planner", "user@gmail.com"
        )
