import tempfile
import unittest
from pathlib import Path

import app.chat_store as chat_store


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_chat_dir = chat_store.CHAT_DIR
        self.original_store_file = chat_store.CHAT_STORE_FILE
        chat_store.CHAT_DIR = Path(self.temp_dir.name)
        chat_store.CHAT_STORE_FILE = Path(self.temp_dir.name) / "chats.json"

    def tearDown(self):
        chat_store.CHAT_DIR = self.original_chat_dir
        chat_store.CHAT_STORE_FILE = self.original_store_file
        self.temp_dir.cleanup()

    def test_create_update_list_and_delete_chat(self):
        chat = chat_store.create_chat("Test chat")

        self.assertEqual(chat["title"], "Test chat")
        self.assertEqual(chat["messages"], [])

        updated = chat_store.update_chat(
            chat["id"],
            title="Updated chat",
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                    "sources": [],
                }
            ],
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "Updated chat")
        self.assertEqual(updated["messages"][0]["content"], "hello")

        chats = chat_store.list_chats()
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["id"], chat["id"])

        self.assertTrue(chat_store.delete_chat(chat["id"]))
        self.assertEqual(chat_store.list_chats(), [])
        self.assertFalse(chat_store.delete_chat(chat["id"]))

    def test_update_missing_chat_returns_none(self):
        self.assertIsNone(chat_store.update_chat("missing", title="Nope"))

    def test_custom_store_file_keeps_project_chats_separate(self):
        first_store = Path(self.temp_dir.name) / "project-a" / "chats.json"
        second_store = Path(self.temp_dir.name) / "project-b" / "chats.json"

        first_chat = chat_store.create_chat("Project A", store_file=first_store)
        second_chat = chat_store.create_chat("Project B", store_file=second_store)

        first_chats = chat_store.list_chats(store_file=first_store)
        second_chats = chat_store.list_chats(store_file=second_store)

        self.assertEqual([chat["id"] for chat in first_chats], [first_chat["id"]])
        self.assertEqual([chat["id"] for chat in second_chats], [second_chat["id"]])

        updated = chat_store.update_chat(
            first_chat["id"],
            messages=[{"role": "user", "content": "hello"}],
            store_file=first_store,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(chat_store.list_chats(store_file=second_store)[0]["messages"], [])
        self.assertTrue(chat_store.delete_chat(first_chat["id"], store_file=first_store))
        self.assertFalse(chat_store.delete_chat(first_chat["id"], store_file=second_store))


if __name__ == "__main__":
    unittest.main()
