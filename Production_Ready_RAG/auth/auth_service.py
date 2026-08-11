from fastapi import HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()


class AuthService:

    DEMO_TOKENS = {
        "demo-token-001": "employee-001",
        "demo-token-002": "employee-002"
    }

    @classmethod
    def authenticate(
        cls,
        credentials: HTTPAuthorizationCredentials
    ) -> str:

        token = credentials.credentials

        user_id = cls.DEMO_TOKENS.get(token)

        if not user_id:

            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )

        return user_id