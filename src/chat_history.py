"""File-backed, account-scoped persistence for Streamlit chat history."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "storage" / "chat_history.json"
_STORE_LOCK = RLock()


class ChatHistoryStorageError(RuntimeError):
    """Raised when chat history cannot safely be read or written."""


def _configured_path() -> Path:
    configured = os.getenv("CHAT_HISTORY_PATH", "").strip()
    if not configured:
        return DEFAULT_HISTORY_PATH
    path = Path(configured).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


class ChatHistoryStore:
    """Persist conversations in one JSON file, partitioned by authenticated user ID."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else _configured_path()

    @staticmethod
    def _normalise_user_id(user_id: str) -> str:
        clean_id = str(user_id or "").strip()
        if not clean_id or len(clean_id) > 256:
            raise ChatHistoryStorageError("Không xác định được tài khoản để lưu lịch sử chat.")
        return clean_id

    def _read_document(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"version": 1, "users": {}}
        try:
            with self.storage_path.open("r", encoding="utf-8") as history_file:
                payload = json.load(history_file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ChatHistoryStorageError("Không đọc được file lịch sử chat.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("users"), dict):
            raise ChatHistoryStorageError("File lịch sử chat có cấu trúc không hợp lệ.")
        payload.setdefault("version", 1)
        return payload

    def load_user(self, user_id: str) -> tuple[dict[int, dict[str, Any]], int]:
        """Return one account's conversations and next numeric conversation ID."""
        account_id = self._normalise_user_id(user_id)
        with _STORE_LOCK:
            payload = self._read_document()
            account = payload["users"].get(account_id, {})

        if not isinstance(account, dict):
            return {}, 0
        raw_chats = account.get("chats", {})
        if not isinstance(raw_chats, dict):
            raw_chats = {}

        chats: dict[int, dict[str, Any]] = {}
        for raw_id, raw_chat in raw_chats.items():
            try:
                chat_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if chat_id < 0 or not isinstance(raw_chat, dict):
                continue
            chat = dict(raw_chat)
            chat["id"] = chat_id
            if not isinstance(chat.get("messages"), list):
                chat["messages"] = []
            if not isinstance(chat.get("conversation_state"), dict):
                chat["conversation_state"] = {}
            chats[chat_id] = chat

        try:
            saved_next_chat = max(0, int(account.get("next_chat", 0)))
        except (TypeError, ValueError):
            saved_next_chat = 0
        next_chat = max(saved_next_chat, max(chats, default=0))
        return chats, next_chat

    def save_conversation(
        self,
        user_id: str,
        chat_id: int,
        conversation: Mapping[str, Any],
        next_chat: int,
    ) -> None:
        """Atomically update one conversation without replacing other accounts' data."""
        account_id = self._normalise_user_id(user_id)
        try:
            numeric_chat_id = int(chat_id)
            numeric_next_chat = max(0, int(next_chat))
            serialisable_conversation = json.loads(
                json.dumps(dict(conversation), ensure_ascii=False)
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ChatHistoryStorageError("Nội dung lịch sử chat không thể lưu thành JSON.") from exc
        if numeric_chat_id < 0 or not isinstance(serialisable_conversation, dict):
            raise ChatHistoryStorageError("Cuộc trò chuyện cần lưu không hợp lệ.")

        with _STORE_LOCK:
            payload = self._read_document()
            users = payload["users"]
            account = users.get(account_id)
            if not isinstance(account, dict):
                account = {"next_chat": 0, "chats": {}}
                users[account_id] = account
            chats = account.get("chats")
            if not isinstance(chats, dict):
                chats = {}
                account["chats"] = chats
            serialisable_conversation["id"] = numeric_chat_id
            chats[str(numeric_chat_id)] = serialisable_conversation
            try:
                saved_next_chat = max(0, int(account.get("next_chat", 0) or 0))
            except (TypeError, ValueError):
                saved_next_chat = 0
            account["next_chat"] = max(
                numeric_next_chat,
                saved_next_chat,
                numeric_chat_id,
            )
            self._write_document(payload)

    def _write_document(self, payload: dict[str, Any]) -> None:
        temporary_path: Path | None = None
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.storage_path.parent,
                prefix=f"{self.storage_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as history_file:
                temporary_path = Path(history_file.name)
                json.dump(payload, history_file, ensure_ascii=False, indent=2)
                history_file.flush()
                os.fsync(history_file.fileno())
            os.replace(temporary_path, self.storage_path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ChatHistoryStorageError("Không ghi được file lịch sử chat.") from exc


__all__ = ["ChatHistoryStorageError", "ChatHistoryStore", "DEFAULT_HISTORY_PATH"]
