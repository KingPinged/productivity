import json
import os
import secrets
from typing import Any

# Suppress oauthlib scope change warning — Google always adds 'openid' to returned scopes
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

import keyring
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

KEYRING_SERVICE = "productivity-planner"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
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
        # Normalize config: handle both "installed" and "web" client types
        config = self._client_config
        if "installed" in config and "web" not in config:
            # Convert installed config to work with our redirect URI
            installed = config["installed"]
            config = {
                "web": {
                    "client_id": installed["client_id"],
                    "client_secret": installed["client_secret"],
                    "auth_uri": installed.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": installed.get("token_uri", "https://oauth2.googleapis.com/token"),
                    "redirect_uris": [self._redirect_uri],
                }
            }
        flow = Flow.from_client_config(
            config,
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

        # Get user email — try ID token first (no extra API call), fall back to userinfo
        email = None

        # Method 1: Extract from ID token if available
        if hasattr(credentials, 'id_token') and credentials.id_token:
            try:
                from google.auth.transport.requests import Request
                from google.oauth2 import id_token as id_token_module
                id_info = id_token_module.verify_oauth2_token(
                    credentials.id_token, Request(),
                    audience=credentials.client_id,
                    clock_skew_in_seconds=10,
                )
                email = id_info.get("email")
            except Exception:
                pass

        # Method 2: Use userinfo API
        if not email:
            try:
                from googleapiclient.discovery import build
                service = build("oauth2", "v2", credentials=credentials)
                user_info = service.userinfo().get().execute()
                email = user_info.get("email")
            except Exception:
                pass

        # Method 3: Use token info endpoint directly
        if not email:
            import urllib.request
            token = credentials.token
            url = f"https://www.googleapis.com/oauth2/v3/userinfo"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    import json as _json
                    data = _json.loads(resp.read().decode())
                    email = data.get("email")
            except Exception:
                pass

        if not email:
            raise ValueError("Could not determine email from OAuth credentials")

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
