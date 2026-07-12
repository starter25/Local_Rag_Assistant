import unittest

from app.rag.index_profile import get_current_index_profile, get_reindex_reasons, needs_reindex


class IndexProfileTests(unittest.TestCase):
    def test_current_profile_has_expected_fields(self):
        profile = get_current_index_profile()

        self.assertIn("loader_version", profile)
        self.assertIn("embedding_model", profile)
        self.assertIn("chunk_size", profile)
        self.assertIn("chunk_overlap", profile)
        self.assertIn("ocr_enabled", profile)

    def test_matching_profile_has_no_reindex_reasons(self):
        profile = get_current_index_profile()

        self.assertEqual(get_reindex_reasons(profile), [])
        self.assertFalse(needs_reindex(profile))

    def test_legacy_profile_needs_reindex(self):
        self.assertEqual(get_reindex_reasons({}), ["legacy index metadata"])
        self.assertTrue(needs_reindex({}))

    def test_changed_profile_reports_human_reason(self):
        current = get_current_index_profile()
        stored = {
            **current,
            "chunk_size": current["chunk_size"] + 100,
            "ocr_languages": "eng",
        }

        reasons = get_reindex_reasons(stored, current_profile=current)

        self.assertIn("chunk size changed", reasons)
        self.assertIn("OCR language setting changed", reasons)


if __name__ == "__main__":
    unittest.main()
