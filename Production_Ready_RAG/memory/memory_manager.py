import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List


class MemoryManager:
    """
    Conversation history.

    Two things to know about the storage model:

    * Rows are keyed by (user_id, session_id) where `session_id` is
      the EMPLOYEE-SCOPED key produced by
      session.SessionManager.scope(). Both halves are written, so a
      lookup can never cross employees even if two clients pick the
      same raw session id.

    * Messages are personal data. `purge_older_than` enforces the
      retention window and is called at startup; point a scheduled
      job at /api/admin/purge-memory to run it during the day too.
    """

    def __init__(
        self,
        database_path: str = "data/chat_memory.db"
    ):

        self.database_path = database_path

        directory = os.path.dirname(database_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        # SQLite serialises writers anyway; the lock keeps our own
        # short transactions from tripping over each other when the
        # socket server handles several employees at once.
        self._write_lock = threading.Lock()

        self._create_tables()

    # --------------------------------
    # Database Connection
    # --------------------------------

    def _get_connection(self):

        connection = sqlite3.connect(
            self.database_path,
            timeout=10.0
        )

        # WAL lets a reader and a writer work at the same time,
        # which matters once several employees are chatting.
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")

        except sqlite3.DatabaseError:
            pass

        return connection

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

        # Every read filters on (user_id, session_id) and orders by
        # id, so this covers the hot path.
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_lookup
                ON chat_messages (user_id, session_id, id)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_created
                ON chat_messages (created_at)
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

        with self._write_lock:

            connection = self._get_connection()

            try:

                connection.execute(
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
                        datetime.now(timezone.utc).isoformat()
                    )
                )

                connection.commit()

            finally:
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
        #
        # IMPORTANT:
        # We need the MOST RECENT `limit` messages, returned in
        # chronological order.
        #
        # "ORDER BY id ASC LIMIT 20" returned the OLDEST 20, so
        # once a session passed 20 messages the history froze at
        # the start of the conversation and follow-up questions
        # stopped resolving correctly.
        #

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                role,
                content

            FROM (

                SELECT
                    id,
                    role,
                    content

                FROM chat_messages

                WHERE user_id = ?
                  AND session_id = ?

                ORDER BY id DESC

                LIMIT ?
            )

            ORDER BY id ASC
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
    ) -> int:

        with self._write_lock:

            connection = self._get_connection()

            try:

                cursor = connection.execute(
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

                return cursor.rowcount or 0

            finally:
                connection.close()

    # --------------------------------
    # Clear every session for one employee
    # --------------------------------

    def clear_user(self, user_id: str) -> int:
        """
        Called when the employee signs out, so nothing of theirs is
        left on the server for the next person to use the device.
        """

        with self._write_lock:

            connection = self._get_connection()

            try:

                cursor = connection.execute(
                    "DELETE FROM chat_messages WHERE user_id = ?",
                    (user_id,)
                )

                connection.commit()

                return cursor.rowcount or 0

            finally:
                connection.close()

    # --------------------------------
    # Transcript for one session
    # --------------------------------

    def get_transcript(
        self,
        user_id: str,
        session_id: str,
        limit: int = 200
    ) -> List[Dict]:
        """
        Oldest-first, with timestamps - what the app needs to
        rebuild a conversation after a reinstall.
        """

        connection = self._get_connection()

        try:

            rows = connection.execute(
                """
                SELECT role, content, language, created_at

                FROM chat_messages

                WHERE user_id = ?
                  AND session_id = ?

                ORDER BY id ASC

                LIMIT ?
                """,
                (user_id, session_id, limit)
            ).fetchall()

        finally:
            connection.close()

        return [
            {
                "role": row[0],
                "content": row[1],
                "language": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]

    # --------------------------------
    # Sessions belonging to one employee
    # --------------------------------

    def list_sessions(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict]:

        connection = self._get_connection()

        try:

            rows = connection.execute(
                """
                SELECT
                    session_id,
                    COUNT(*)          AS message_count,
                    MIN(created_at)   AS started_at,
                    MAX(created_at)   AS last_message_at

                FROM chat_messages

                WHERE user_id = ?

                GROUP BY session_id

                ORDER BY MAX(id) DESC

                LIMIT ?
                """,
                (user_id, limit)
            ).fetchall()

        finally:
            connection.close()

        return [
            {
                "session_id": row[0],
                "message_count": row[1],
                "started_at": row[2],
                "last_message_at": row[3],
            }
            for row in rows
        ]

    # --------------------------------
    # Retention
    # --------------------------------

    def purge_older_than(self, days: int) -> int:
        """
        Deletes messages older than `days`. Returns the row count.

        Chat transcripts hold employees' HR questions, so they are
        not kept forever. `days <= 0` disables the purge.
        """

        if days is None or days <= 0:
            return 0

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()

        with self._write_lock:

            connection = self._get_connection()

            try:

                cursor = connection.execute(
                    "DELETE FROM chat_messages WHERE created_at < ?",
                    (cutoff,)
                )

                connection.commit()

                deleted = cursor.rowcount or 0

            finally:
                connection.close()

        return deleted

    # --------------------------------
    # Health
    # --------------------------------

    def ping(self) -> bool:

        try:
            connection = self._get_connection()

            try:
                connection.execute("SELECT 1").fetchone()

            finally:
                connection.close()

            return True

        except Exception:
            return False