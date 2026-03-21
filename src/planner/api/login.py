import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/auth")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30
ALLOWED_EMAIL = "kingsinland@gmail.com"


def _make_jwt(email: str) -> str:
    jwt_secret = os.environ.get("JWT_SECRET", "change-me-in-production")
    payload = {
        "sub": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


@router.post("/login")
def login(body: dict):
    """Fallback: authenticate with password, returns JWT."""
    jwt_secret = os.environ.get("JWT_SECRET", "change-me-in-production")
    planner_password = os.environ.get("PLANNER_PASSWORD", "")

    password = body.get("password", "")
    if not planner_password or password != planner_password:
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"token": _make_jwt("planner-user")}


@router.get("/login/google")
def login_with_google():
    """Initiate Google OAuth for app login. Reuses the same auth flow."""
    from src.planner.api.auth import auth_manager
    if auth_manager is None:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    auth_url, state = auth_manager.generate_auth_url()
    return {"auth_url": auth_url, "state": state}
