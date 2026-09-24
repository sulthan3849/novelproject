import sys
import os
import shutil
import tempfile
import json
import unittest
import threading
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.epub_parser import EpubParser
from utils.state_manager import StateManager


class TestEmpiricalReproductions(unittest.TestCase):
    """Targeted empirical reproduction scripts for confirmed bugs."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="repro_")
        self.epub_path = os.path.join(self.test_dir, "repro.epub")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_reproduce_nested_div_duplication_and_detachment(self):
        """
        REPRODUCTION 1:
        Nested divs without standard block tags are duplicated and subsequently detached.
        """
        book = epub.EpubBook()
        book.set_identifier("urn:repro:1")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        ch = epub.EpubHtml(title="Div Repro", file_name="ch.xhtml", lang="en")
        ch.set_content(b'<div class="outer"><div class="inner">Novel scene text</div></div>')
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(self.epub_path, book, {})

        parser = EpubParser(self.epub_path)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch.get_id()]
        
        # BUG: Both outer and inner divs are extracted
        self.assertEqual(len(nodes), 2, "Expected outer and inner div both extracted")
        self.assertEqual(nodes[0]["tag"], "div")
        self.assertEqual(nodes[1]["tag"], "div")

        # When outer div is updated, inner div is detached
        parser.update_node(nodes[0]["node"], "Outer translated")
        self.assertIsNone(nodes[1]["node"].parent, "Inner div parent must be None (detached from DOM)")

    def test_reproduce_table_text_completely_omitted(self):
        """
        REPRODUCTION 2:
        Table cells (td, th) are completely omitted from extract_text_nodes.
        """
        book = epub.EpubBook()
        book.set_identifier("urn:repro:2")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        ch = epub.EpubHtml(title="Table Repro", file_name="table.xhtml", lang="en")
        ch.set_content(b'<table><tr><th>Character</th></tr><tr><td>Protagonist</td></tr></table>')
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(self.epub_path, book, {})

        parser = EpubParser(self.epub_path)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch.get_id()]
        
        # BUG: 0 nodes extracted from table!
        self.assertEqual(len(nodes), 0, "Table contents are silently skipped")

    def test_reproduce_state_manager_crash_on_null_translated_items(self):
        """
        REPRODUCTION 3:
        StateManager crashes when translated_items is null in JSON.
        """
        state_file = os.path.join(self.test_dir, "book1_progress.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"book_identifier": "book1", "translated_items": None}, f)

        sm = StateManager("book1", total_chunks=5, state_dir=self.test_dir)
        with self.assertRaises(AttributeError):
            sm.is_chunk_translated("item1", 0)

    def test_reproduce_state_manager_crash_on_list_schema(self):
        """
        REPRODUCTION 4:
        StateManager crashes on initialization if JSON root is a list with 'translated_items'.
        """
        state_file = os.path.join(self.test_dir, "book2_progress.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(["translated_items"], f)

        with self.assertRaises(AttributeError):
            StateManager("book2", total_chunks=5, state_dir=self.test_dir)

    def test_reproduce_state_manager_lost_updates_concurrent_instances(self):
        """
        REPRODUCTION 5:
        Two concurrent StateManager instances cause silent lost updates.
        """
        mgr_a = StateManager("book3", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)
        mgr_b = StateManager("book3", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)

        mgr_a.mark_chunk_translated("ch1", 0, "Trans A")
        mgr_a.flush()

        mgr_b.mark_chunk_translated("ch2", 0, "Trans B")
        mgr_b.flush()

        with open(mgr_a.progress_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        # BUG: ch1 is wiped out by mgr_b!
        self.assertNotIn("ch1", disk_data["translated_items"], "ch1 from mgr_a was completely overwritten by mgr_b")


if __name__ == "__main__":
    unittest.main()
