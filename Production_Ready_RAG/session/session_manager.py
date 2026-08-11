class SessionManager:

    @staticmethod
    def get_scoped_session_id(
        user_id: str,
        session_id: str
    ) -> str:

        return f"{user_id}:{session_id}"