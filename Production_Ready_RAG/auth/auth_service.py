import hashlib
import hmac
import secrets

from fastapi import HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()


class AuthService:
    """
    Demo authentication.

    Employees log in with their EMPLOYEE ID and a password.
    A successful login returns an opaque session token which the
    Socket.IO handshake and the REST endpoints both accept.

    NOTE FOR PRODUCTION:
    Replace CREDENTIALS with a real user store and replace the
    plain-text passwords with salted hashes (bcrypt / argon2).
    Replace the in-memory token map with signed JWTs so that the
    API can scale beyond a single process.
    """

    # ------------------------------------------------------------
    # Demo credentials
    # employee_id -> password
    # ------------------------------------------------------------

    CREDENTIALS = {
        "employee-001": "Test@123",
        "employee-002": "Test@123",
    }

    # ------------------------------------------------------------
    # Long-lived demo tokens (kept so existing tests and the
    # Swagger examples keep working)
    # ------------------------------------------------------------

    DEMO_USERS = {
        "demo-token-001": "employee-001",
        "demo-token-002": "employee-002",
    }

    # ------------------------------------------------------------
    # Tokens issued at runtime by login()
    # token -> employee_id
    # ------------------------------------------------------------

    ACTIVE_TOKENS = {}

    # ============================================================
    # Login
    # ============================================================

    @classmethod
    def login(cls, employee_id: str, password: str) -> str:
        """
        Validates the credentials and returns a session token.

        Raises ValueError when the credentials are invalid.
        """

        employee_id = (employee_id or "").strip()
        password = password or ""

        expected = cls.CREDENTIALS.get(employee_id)

        # Constant-time comparison, and we still run it when the
        # employee does not exist so that a wrong ID and a wrong
        # password take the same amount of time.
        reference = expected if expected is not None else "\x00" * 16

        password_ok = hmac.compare_digest(
            cls._digest(password),
            cls._digest(reference)
        )

        if expected is None or not password_ok:

            print(
                f"[AUTH] Failed login attempt for "
                f"'{employee_id or '(empty)'}'"
            )

            raise ValueError("Invalid employee ID or password")

        token = f"sess-{secrets.token_urlsafe(24)}"

        cls.ACTIVE_TOKENS[token] = employee_id

        print(f"[AUTH] Login successful: {employee_id}")

        return token

    # ============================================================
    # Logout
    # ============================================================

    @classmethod
    def logout(cls, token: str) -> bool:

        removed = cls.ACTIVE_TOKENS.pop(token, None)

        if removed:
            print(f"[AUTH] Logged out: {removed}")

        return removed is not None

    # ============================================================
    # Token validation
    # ============================================================

    @classmethod
    def authenticate_token(cls, token: str) -> str:

        token = (token or "").strip()

        if not token:
            raise ValueError("Missing authentication token")

        # Tokens issued by login()
        user_id = cls.ACTIVE_TOKENS.get(token)

        if user_id:
            return user_id

        # Static demo tokens
        user_id = cls.DEMO_USERS.get(token)

        if user_id:
            return user_id

        raise ValueError("Invalid authentication token")

    @classmethod
    def authenticate(cls, credentials: HTTPAuthorizationCredentials) -> str:

        if not credentials:

            raise HTTPException(
                status_code=401,
                detail="Missing authorization header"
            )

        try:

            return cls.authenticate_token(credentials.credentials)

        except ValueError as error:

            raise HTTPException(
                status_code=401,
                detail=str(error)
            )

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _digest(value: str) -> bytes:

        return hashlib.sha256(value.encode("utf-8")).digest()
