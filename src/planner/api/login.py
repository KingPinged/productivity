import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/auth")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30


@router.post("/login")
def login(body: dict):
    """Authenticate with password, returns JWT."""
    jwt_secret = os.environ.get("JWT_SECRET", "change-me-in-production")
    planner_password = os.environ.get("PLANNER_PASSWORD", "")

    password = body.get("password", "")
    if not planner_password or password != planner_password:
        raise HTTPException(status_code=401, detail="Invalid password")

    payload = {
        "sub": "planner-user",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    token = jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)
    return {"token": token}
