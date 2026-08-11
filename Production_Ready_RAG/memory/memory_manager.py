import sqlite3
from datetime import datetime
from typing import List, Dict


class MemoryManager:

    def __init__(
        self,
        database_path: str = "data/chat_memory.db"
    ):

        self.database_path = database_path

        self._create_tables()

    # --------------------------------
    # Database Connection
    # --------------------------------

    def _get_connection(self):

        return sqlite3.connect(
            self.database_path
        )

    # --------------------------------
    # Create Tables
    # --------------------------------

    def _create_tables(self):

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id TEXT NOT NULL,

                session_id TEXT NOT NULL,

                role TEXT NOT NULL,

                content TEXT NOT NULL,

                language TEXT,

                created_at TEXT NOT NULL

            )
            """
        )

        connection.commit()

        connection.close()

    # --------------------------------
    # Add User Message
    # --------------------------------

    def add_user_message(
        self,
        user_id: str,
        session_id: str,
        content: str,
        language: str = "English"
    ):

        self._add_message(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=content,
            language=language
        )

    # --------------------------------
    # Add Assistant Message
    # --------------------------------

    def add_assistant_message(
        self,
        user_id: str,
        session_id: str,
        content: str,
        language: str = "English"
    ):

        self._add_message(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=content,
            language=language
        )

    # --------------------------------
    # Internal Add Message
    # --------------------------------

    def _add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        language: str
    ):

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO chat_messages (
                user_id,
                session_id,
                role,
                content,
                language,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                role,
                content,
                language,
                datetime.utcnow().isoformat()
            )
        )

        connection.commit()

        connection.close()

    # --------------------------------
    # Get Conversation History
    # --------------------------------

    def get_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 20
    ) -> List[Dict]:

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                role,
                content

            FROM chat_messages

            WHERE user_id = ?
              AND session_id = ?

            ORDER BY id ASC

            LIMIT ?
            """,
            (
                user_id,
                session_id,
                limit
            )
        )

        rows = cursor.fetchall()

        connection.close()

        messages = []

        for row in rows:

            messages.append(
                {
                    "role": row[0],
                    "content": row[1]
                }
            )

        return messages

    # --------------------------------
    # Get Full Conversation History
    # --------------------------------
    #
    # This method is useful when we need
    # metadata such as language or timestamp.
    #

    def get_messages_with_metadata(
        self,
        user_id: str,
        session_id: str,
        limit: int = 20
    ) -> List[Dict]:

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                role,
                content,
                language,
                created_at

            FROM chat_messages

            WHERE user_id = ?
              AND session_id = ?

            ORDER BY id ASC

            LIMIT ?
            """,
            (
                user_id,
                session_id,
                limit
            )
        )

        rows = cursor.fetchall()

        connection.close()

        messages = []

        for row in rows:

            messages.append(
                {
                    "role": row[0],
                    "content": row[1],
                    "language": row[2],
                    "created_at": row[3]
                }
            )

        return messages

    # --------------------------------
    # Clear Session
    # --------------------------------

    def clear_session(
        self,
        user_id: str,
        session_id: str
    ):

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM chat_messages

            WHERE user_id = ?
              AND session_id = ?
            """,
            (
                user_id,
                session_id
            )
        )

        connection.commit()

        connection.close()