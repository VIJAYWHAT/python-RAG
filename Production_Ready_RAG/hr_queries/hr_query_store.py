import sqlite3
import os
from datetime import datetime


class HRQueryStore:

    def __init__(
        self,
        db_path: str = "./database/hr_queries.db"
    ):

        directory = os.path.dirname(db_path)

        if directory:
            os.makedirs(
                directory,
                exist_ok=True
            )

        self.db_path = db_path

        self._create_table()

    def _get_connection(self):

        return sqlite3.connect(
            self.db_path
        )

    def _create_table(self):

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hr_queries (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                question TEXT NOT NULL,

                session_id TEXT,

                created_at TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'NEW'

            )
        """)

        connection.commit()
        connection.close()

    def save_query(
        self,
        question: str,
        session_id: str = None
    ):

        connection = self._get_connection()

        cursor = connection.cursor()

        created_at = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO hr_queries (
                question,
                session_id,
                created_at,
                status
            )
            VALUES (?, ?, ?, ?)
        """, (
            question,
            session_id,
            created_at,
            "NEW"
        ))

        connection.commit()

        query_id = cursor.lastrowid

        connection.close()

        return query_id

    def get_all_queries(self):

        connection = self._get_connection()

        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                question,
                session_id,
                created_at,
                status
            FROM hr_queries
            ORDER BY id DESC
        """)

        rows = cursor.fetchall()

        connection.close()

        return rows