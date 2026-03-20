import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me-in-production")


def require_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )
    try:
        payload = jwt.decode(
            credentials.credentials, _get_jwt_secret(), algorithms=[JWT_ALGORITHM]
        )
        return payload.get("sub", "")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_token_dependency(legacy_token: str | None = None):
    """Returns a Depends that validates JWT tokens.

    If legacy_token is provided (for backward compatibility with existing tests),
    the dependency will also accept the legacy static token alongside JWT tokens.
    """
    if legacy_token is not None:
        def verify_token_with_legacy(
            credentials: HTTPAuthorizationCredentials | None = Depends(_security),
        ) -> str:
            if credentials is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing token",
                )
            # Accept legacy static token for backward compatibility
            if credentials.credentials == legacy_token:
                return credentials.credentials
            # Otherwise validate as JWT
            try:
                payload = jwt.decode(
                    credentials.credentials, _get_jwt_secret(), algorithms=[JWT_ALGORITHM]
                )
                return payload.get("sub", "")
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token expired")
            except jwt.InvalidTokenError:
                raise HTTPException(status_code=401, detail="Invalid token")

        return Depends(verify_token_with_legacy)

    return Depends(require_jwt)
