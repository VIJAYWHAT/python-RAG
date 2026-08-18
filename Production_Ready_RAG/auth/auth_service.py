from fastapi import HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()


class AuthService:

    DEMO_USERS = {
        "demo-token-001": "employee-001",
        "demo-token-002": "employee-002",
    }

    @staticmethod
    def authenticate_token(token: str):

        user_id = AuthService.DEMO_USERS.get(token)

        if not user_id:
            raise ValueError("Invalid authentication token")

        return user_id

    @staticmethod
    def authenticate(credentials):

        token = credentials.credentials

        return AuthService.authenticate_token(token)

        user_id = AuthService.DEMO_USERS.get(token)

        if not user_id:
            raise ValueError(
                "Invalid authentication token"
            )

        return user_id