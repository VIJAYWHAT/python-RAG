from typing import Dict

from memory.chat_memory import ChatMemory


class MemoryManager:

    def __init__(self):

        self._sessions: Dict[str, ChatMemory] = {}

    def get_memory(
        self,
        session_id: str
    ) -> ChatMemory:

        if session_id not in self._sessions:

            self._sessions[session_id] = ChatMemory()

        return self._sessions[session_id]

    def clear_memory(
        self,
        session_id: str
    ) -> None:

        if session_id in self._sessions:

            del self._sessions[session_id]

    def has_session(
        self,
        session_id: str
    ) -> bool:

        return session_id in self._sessions

    def clear_all(self) -> None:

        self._sessions.clear()