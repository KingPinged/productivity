import json
import secrets
from typing import Any

import keyring
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

KEYRING_SERVICE = "productivity-planner"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthManager:
    def __init__(
        self,
        client_config: dict[str, Any],
        redirect_uri: str = "http://localhost:8321/auth/callback",
        scopes: list[str] | None = None,
    ):
        self._client_config = client_config
        self._redirect_uri = redirect_uri
        self._scopes = scopes or SCOPES
        self._pending_states: dict[str, Flow] = {}

    def generate_auth_url(self) -> tuple[str, str]:
        flow = Flow.from_client_config(
            self._client_config,
            scopes=self._scopes,
            redirect_uri=self._redirect_uri,
        )
        state = secrets.token_urlsafe(32)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        self._pending_states[state] = flow
        return auth_url, state

    def handle_callback(self, code: str, state: str) -> tuple[Credentials, str]:
        flow = self._pending_states.pop(state, None)
        if flow is None:
            raise ValueError("Invalid or expired OAuth state parameter")
        flow.fetch_token(code=code)
        credentials = flow.credentials
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info["email"]
        return credentials, email

    def store_tokens(self, email: str, token_data: dict) -> None:
        keyring.set_password(KEYRING_SERVICE, email, json.dumps(token_data))

    def get_credentials(self, email: str) -> Credentials | None:
        stored = keyring.get_password(KEYRING_SERVICE, email)
        if not stored:
            return None
        data = json.loads(stored)
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        )

    def refresh_if_expired(self, email: str) -> Credentials | None:
        creds = self.get_credentials(email)
        if creds is None:
            return None
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            self.store_tokens(email, self.credentials_to_dict(creds))
        return creds

    def remove_tokens(self, email: str) -> None:
        keyring.delete_password(KEYRING_SERVICE, email)

    def credentials_to_dict(self, creds: Credentials) -> dict:
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [],
        }
