from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager

# Protected routes (bearer token required — applied by server.py)
router = APIRouter(prefix="/auth")

# Unprotected route (Google redirects browser here)
callback_router = APIRouter(prefix="/auth")

# Module-level reference, set by server.py
auth_manager: GoogleAuthManager | None = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/google")
def initiate_google_auth(db: PlannerDB = Depends(get_db)):
    if auth_manager is None:
        return {"error": "Google OAuth not configured. Set client config in settings."}
    auth_url, state = auth_manager.generate_auth_url()
    return {"auth_url": auth_url, "state": state}


@callback_router.get("/callback")
def oauth_callback(code: str, state: str, db: PlannerDB = Depends(get_db)):
    if auth_manager is None:
        return {"error": "Google OAuth not configured"}
    try:
        credentials, email = auth_manager.handle_callback(code, state)
        auth_manager.store_tokens(email, auth_manager.credentials_to_dict(credentials))
        scopes = " ".join(credentials.scopes) if credentials.scopes else ""
        db.add_account(email, "google", scopes)

        # Issue a JWT and redirect to app (handles both login and account linking)
        from src.planner.api.login import _make_jwt, ALLOWED_EMAIL
        import os
        allowed = os.environ.get("ALLOWED_EMAIL", ALLOWED_EMAIL)

        if email.lower() == allowed.lower():
            token = _make_jwt(email)
            from fastapi.responses import HTMLResponse
            return HTMLResponse(f"""<!DOCTYPE html><html><body>
<script>
localStorage.setItem('planner_token', '{token}');
window.location.href = '/';
</script>
<p>Logging in as {email}...</p>
</body></html>""")
        else:
            # Not the owner — just connecting an account for syncing
            from fastapi.responses import HTMLResponse
            return HTMLResponse(f"""<!DOCTYPE html><html><body>
<script>window.close();</script>
<p>Account {email} connected. You can close this tab.</p>
</body></html>""")
    except ValueError as e:
        return {"error": str(e)}


@router.get("/accounts")
def list_accounts(db: PlannerDB = Depends(get_db)):
    return db.list_accounts()


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: PlannerDB = Depends(get_db)):
    account = db.get_account(account_id)
    if account and auth_manager:
        try:
            auth_manager.remove_tokens(account["email"])
        except Exception:
            pass
    db.delete_events_for_account(account_id)
    db.soft_delete_account(account_id)
    return {"status": "deleted"}
