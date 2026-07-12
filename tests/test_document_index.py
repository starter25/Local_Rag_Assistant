import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.rag import document_index
from app.rag.index_profile import get_current_index_profile


class FakeCollection:
    def __init__(self, metadatas=None):
        self.metadatas = metadatas or []

    def get(self, include=None):
        return {"metadatas": self.metadatas}

    def count(self):
        return len(self.metadatas)


class DocumentIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.document_dir = self.root / "documents"
        self.index_file = self.root / "document_index.json"
        self.document_dir.mkdir()
        self.patches = [
            patch.object(document_index, "DOCUMENT_DIR", self.document_dir),
            patch.object(document_index, "DOCUMENT_INDEX_FILE", self.index_file),
        ]

        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

        self.temp_dir.cleanup()

    def test_indexed_document_state_includes_health_metadata(self):
        path = self.document_dir / "guide.txt"
        path.write_text("hello local rag", encoding="utf-8")
        document_index.mark_document_indexed(
            path,
            {
                "chunks": 2,
                "pages": 1,
                "characters": 15,
                "file_hash": "hash-1",
                "ocr_used": True,
                "ocr_engine": "tesseract",
                "ocr_pages": 1,
                "index_profile": get_current_index_profile(),
            },
        )
        collection = FakeCollection(
            [
                {
                    "source": "guide.txt",
                    "file_hash": "hash-1",
                },
                {
                    "source": "guide.txt",
                    "file_hash": "hash-1",
                },
            ]
        )

        state = document_index.build_document_state(collection)
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "indexed")
        self.assertEqual(doc["chunks"], 2)
        self.assertEqual(doc["pages"], 1)
        self.assertEqual(doc["characters"], 15)
        self.assertTrue(doc["ocr_used"])
        self.assertEqual(doc["ocr_engine"], "tesseract")
        self.assertEqual(doc["ocr_pages"], 1)
        self.assertFalse(doc["needs_sync"])

    def test_empty_document_keeps_empty_status_without_db_chunks(self):
        path = self.document_dir / "scan.pdf"
        path.write_bytes(b"%PDF empty")
        document_index.mark_document_empty(
            path,
            {
                "chunks": 0,
                "pages": 0,
                "characters": 0,
                "file_hash": "hash-empty",
                "index_profile": get_current_index_profile(),
            },
        )

        state = document_index.build_document_state(FakeCollection())
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "empty")
        self.assertIn("warnings", doc)

    def test_changed_file_is_marked_needs_sync(self):
        path = self.document_dir / "guide.txt"
        path.write_text("old text", encoding="utf-8")
        document_index.mark_document_indexed(
            path,
            {
                "chunks": 1,
                "pages": 1,
                "characters": 8,
                "file_hash": "old-hash",
                "index_profile": get_current_index_profile(),
            },
        )
        path.write_text("new text with more data", encoding="utf-8")
        os.utime(path, (path.stat().st_atime + 5, path.stat().st_mtime + 5))
        collection = FakeCollection(
            [
                {
                    "source": "guide.txt",
                    "file_hash": "old-hash",
                }
            ]
        )

        state = document_index.build_document_state(collection)
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "needs_sync")
        self.assertTrue(doc["needs_sync"])

    def test_legacy_index_profile_is_marked_needs_sync(self):
        path = self.document_dir / "legacy.txt"
        path.write_text("old index", encoding="utf-8")
        document_index.mark_document_indexed(
            path,
            {
                "chunks": 1,
                "pages": 1,
                "characters": 9,
                "file_hash": "legacy-hash",
            },
        )
        collection = FakeCollection(
            [
                {
                    "source": "legacy.txt",
                    "file_hash": "legacy-hash",
                }
            ]
        )

        state = document_index.build_document_state(collection)
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "needs_sync")
        self.assertTrue(doc["needs_reindex"])
        self.assertEqual(doc["reindex_reasons"], ["legacy index metadata"])

    def test_changed_index_profile_is_marked_needs_sync(self):
        current_profile = get_current_index_profile()
        old_profile = {
            **current_profile,
            "chunk_size": current_profile["chunk_size"] + 100,
        }
        path = self.document_dir / "guide.txt"
        path.write_text("hello local rag", encoding="utf-8")
        document_index.mark_document_indexed(
            path,
            {
                "chunks": 1,
                "pages": 1,
                "characters": 15,
                "file_hash": "hash-1",
                "index_profile": old_profile,
            },
        )
        collection = FakeCollection(
            [
                {
                    "source": "guide.txt",
                    "file_hash": "hash-1",
                }
            ]
        )

        state = document_index.build_document_state(collection)
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "needs_sync")
        self.assertTrue(doc["needs_reindex"])
        self.assertIn("chunk size changed", doc["reindex_reasons"])

    def test_unsupported_file_is_visible(self):
        path = self.document_dir / "legacy.hwp"
        path.write_text("unsupported", encoding="utf-8")

        state = document_index.build_document_state(FakeCollection())
        doc = state["documents"][0]

        self.assertEqual(doc["status"], "unsupported")
        self.assertEqual(doc["chunks"], 0)


if __name__ == "__main__":
    unittest.main()
