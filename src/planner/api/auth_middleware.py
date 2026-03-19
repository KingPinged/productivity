from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer(auto_error=False)


def create_token_dependency(expected_token: str):
    def verify_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    ) -> str:
        if credentials is None or credentials.credentials != expected_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token",
            )
        return credentials.credentials

    return Depends(verify_token)
