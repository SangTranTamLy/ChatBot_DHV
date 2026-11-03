"""Persistence and failure handling for account-scoped chat history."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest import TestCase

from src.chat_history import ChatHistoryStorageError, ChatHistoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = PROJECT_ROOT / ".qa_tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class ChatHistoryStoreTests(TestCase):
    def test_conversations_survive_store_recreation_and_stay_account_scoped(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "history.json"
            first_store = ChatHistoryStore(path)
            first_store.save_conversation(
                "auth-user-a",
                2,
                {
                    "title": "Học phí ngành CNTT",
                    "messages": [
                        {"role": "user", "content": "Học phí ngành CNTT?"},
                        {"role": "assistant", "content": "Dữ liệu năm 2026."},
                    ],
                    "conversation_state": {"previous_intent": "HOI_HOC_PHI"},
                    "updated_at": "2026-11-03T10:00:00",
                },
                next_chat=2,
            )
            first_store.save_conversation(
                "auth-user-b",
                0,
                {
                    "title": "Ngành học",
                    "messages": [{"role": "user", "content": "DHV có ngành nào?"}],
                    "conversation_state": {},
                    "updated_at": "2026-11-03T10:01:00",
                },
                next_chat=0,
            )

            restarted_store = ChatHistoryStore(path)
            account_a, next_chat_a = restarted_store.load_user("auth-user-a")
            account_b, next_chat_b = restarted_store.load_user("auth-user-b")

            self.assertEqual(account_a[2]["messages"][0]["content"], "Học phí ngành CNTT?")
            self.assertEqual(account_a[2]["conversation_state"]["previous_intent"], "HOI_HOC_PHI")
            self.assertEqual(next_chat_a, 2)
            self.assertEqual(set(account_b), {0})
            self.assertEqual(next_chat_b, 0)
            self.assertNotIn("auth-user-b", account_a)

            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(document["users"]), {"auth-user-a", "auth-user-b"})
            serialized = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("access_token", serialized)
            self.assertNotIn("refresh_token", serialized)
            self.assertNotIn("password", serialized)

    def test_malformed_history_is_reported_and_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            path = Path(directory) / "history.json"
            malformed = b'{"version": 1, "users": '
            path.write_bytes(malformed)
            store = ChatHistoryStore(path)

            with self.assertRaises(ChatHistoryStorageError):
                store.load_user("auth-user-a")
            with self.assertRaises(ChatHistoryStorageError):
                store.save_conversation("auth-user-a", 0, {"messages": []}, 0)

            self.assertEqual(path.read_bytes(), malformed)

    def test_write_failure_is_reported_without_overwriting_existing_parent_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            blocker = Path(directory) / "not-a-folder"
            sentinel = b"preserve this unrelated file"
            blocker.write_bytes(sentinel)
            store = ChatHistoryStore(blocker / "history.json")

            with self.assertRaises(ChatHistoryStorageError):
                store.save_conversation("auth-user-a", 0, {"messages": []}, 0)

            self.assertEqual(blocker.read_bytes(), sentinel)


if __name__ == "__main__":
    import unittest

    unittest.main()
