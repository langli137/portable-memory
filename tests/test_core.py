"""Core tests using unittest (stdlib only)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from portable_memory.config import Config
from portable_memory.db import Store, content_hash, redact
from portable_memory.pipeline import Retriever, tokenize


class TestGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")
        self.config = Config(
            data_dir=Path(self.tmp.name),
            db_path=Path(self.tmp.name) / "test.sqlite3",
            host="127.0.0.1", port=0, token="",
            decay_half_life_days=30.0, default_limit=8, max_limit=50,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_hash_normalizes_whitespace_and_case(self):
        self.assertEqual(content_hash("  Hello   World "), content_hash("hello world"))

    def test_redact_secret(self):
        clean, changed = redact("key ghp_abcdefghijklmnopqrstuvwxyz1234567890 end")
        self.assertTrue(changed)
        self.assertIn("[REDACTED]", clean)
        self.assertNotIn("ghp_", clean)

    def test_tokenize_cjk_bigrams(self):
        tokens = tokenize("分页默认十条")
        self.assertIn("分页", tokens)
        self.assertIn("页默", tokens)

    def test_add_and_dedup(self):
        m1, s1 = self.store.add("分页默认 10 条")
        m2, s2 = self.store.add("分页默认 10 条")
        self.assertEqual(s1, "added")
        self.assertEqual(s2, "duplicate")
        self.assertEqual(m1.id, m2.id)

    def test_recall_ranks_relevant_first(self):
        self.store.add("分页默认 10 条，不开特例", tags=["分页"])
        self.store.add("curl 必须 noproxy")
        r = Retriever(self.store, self.config)
        results = r.recall("分页", limit=2)
        self.assertIn("分页", results[0].memory.content)
        self.assertGreater(results[0].bm25, results[1].bm25)

    def test_soft_delete(self):
        m, _ = self.store.add("to be removed")
        self.assertTrue(self.store.delete(m.id))
        self.assertIsNone(self.store.get(m.id))
        self.assertEqual(len(self.store.all()), 0)

    def test_export_markdown(self):
        self.store.add("first fact")
        path = Path(self.tmp.name) / "out.md"
        count = self.store.export_markdown(path)
        self.assertEqual(count, 1)
        self.assertIn("first fact", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
