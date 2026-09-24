import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from typing import Any, Dict, List, Tuple
from bs4 import BeautifulSoup, Tag
import ebooklib
from ebooklib import epub

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.epub_parser import EpubParser, BLOCK_TAGS, INLINE_TAGS
from utils.state_manager import StateManager


class TestAdversarialReVerification(unittest.TestCase):
    """
    Challenger 3 Adversarial Re-Verification Suite.
    Rigorous stress testing across 5 core dimensions:
    1. Multithreading stress & zero lost updates on Windows.
    2. Corrupted schema inputs, warnings, backups, and clean fallback.
    3. Multi-instance merge without progress clobbering.
    4. Nested <div> leaf extraction and DOM integrity.
    5. Table, caption, aside, and section content extraction.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="adv_c3_")
        self.epub_path = os.path.join(self.test_dir, "test_book.epub")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_epub_with_content(self, html_content: str, file_name="content.xhtml") -> Tuple[EpubParser, str]:
        """Helper to create an EPUB with specified HTML content and return (parser, item_id)."""
        book = epub.EpubBook()
        book.set_identifier("urn:adv:c3:test")
        book.set_title("Challenger 3 Re-Verification")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        ch = epub.EpubHtml(title="Section", file_name=file_name, lang="en")
        ch.set_content(html_content.encode("utf-8"))
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(self.epub_path, book, {})
        parser = EpubParser(self.epub_path)
        return parser, ch.get_id()

    # =========================================================================
    # 1. Multithreading Stress & Concurrency (Windows)
    # =========================================================================

    def test_multithreading_stress_high_concurrency_zero_exceptions_zero_lost_updates(self):
        """
        Stress test: 20 concurrent threads rapidly updating StateManager with save_batch_size=1.
        Every single mark_chunk_translated call triggers an immediate disk write.
        Verifies:
        - 0 unhandled exceptions (0 PermissionError / WinError 32 / WinError 5).
        - Exactly 1,000 updates made across threads.
        - In-memory state and on-disk JSON both reflect 1,000 updates without data loss.
        """
        num_threads = 20
        chunks_per_thread = 50
        total_expected_chunks = num_threads * chunks_per_thread

        sm = StateManager(
            book_identifier="mt_stress_c3",
            total_chunks=total_expected_chunks,
            state_dir=self.test_dir,
            save_batch_size=1,  # Every update flushes to disk!
        )

        errors = []

        def worker(thread_idx: int):
            try:
                for chunk_idx in range(chunks_per_thread):
                    sm.mark_chunk_translated(
                        item_id=f"thread_{thread_idx}",
                        chunk_index=chunk_idx,
                        translated_text=f"Terjemahan T{thread_idx}-C{chunk_idx}",
                        original_text=f"Original T{thread_idx}-C{chunk_idx}",
                    )
            except Exception as e:
                errors.append((thread_idx, e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check for exceptions
        self.assertEqual(len(errors), 0, f"Encountered {len(errors)} thread errors: {errors}")

        # Check in-memory count
        completed_mem = sm.get_completed_count()
        self.assertEqual(
            completed_mem,
            total_expected_chunks,
            f"Expected {total_expected_chunks} chunks in memory, got {completed_mem}",
        )

        # Force flush and verify disk state
        sm.flush()
        self.assertTrue(os.path.exists(sm.progress_file), "Progress file must exist on disk")

        with open(sm.progress_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        disk_items = disk_data.get("translated_items", {})
        total_disk_chunks = sum(len(chunks) for chunks in disk_items.values())
        self.assertEqual(
            total_disk_chunks,
            total_expected_chunks,
            f"Expected {total_expected_chunks} chunks on disk, got {total_disk_chunks}",
        )

        # Verify exact chunks for every thread
        for t_idx in range(num_threads):
            item_key = f"thread_{t_idx}"
            self.assertIn(item_key, disk_items, f"Item {item_key} missing from disk state")
            for c_idx in range(chunks_per_thread):
                c_str = str(c_idx)
                self.assertIn(c_str, disk_items[item_key], f"Chunk {c_str} missing in {item_key}")
                rec = disk_items[item_key][c_str]
                self.assertEqual(rec["translated"], f"Terjemahan T{t_idx}-C{c_idx}")

    def test_multithreading_concurrent_mark_and_explicit_save_state(self):
        """
        Stress test: Concurrent threads executing mark_chunk_translated while other threads
        concurrently call save_state(force=True), flush(), and get_progress().
        Verifies 0 deadlock, 0 race condition exceptions.
        """
        sm = StateManager(
            book_identifier="race_stress_c3",
            total_chunks=300,
            state_dir=self.test_dir,
            save_batch_size=3,
        )

        stop_event = threading.Event()
        errors = []

        def writer(w_id):
            try:
                for i in range(50):
                    sm.mark_chunk_translated(f"doc_{w_id}", i, f"Trans {w_id}-{i}", f"Orig {w_id}-{i}")
            except Exception as e:
                errors.append(("writer", w_id, e))

        def flusher():
            try:
                while not stop_event.is_set():
                    sm.save_state(force=True)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(("flusher", 0, e))

        def reader():
            try:
                while not stop_event.is_set():
                    _ = sm.get_progress()
                    _ = sm.get_completed_count()
                    time.sleep(0.005)
            except Exception as e:
                errors.append(("reader", 0, e))

        flusher_threads = [threading.Thread(target=flusher) for _ in range(2)]
        reader_threads = [threading.Thread(target=reader) for _ in range(2)]
        writer_threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]

        for t in flusher_threads + reader_threads + writer_threads:
            t.start()

        for t in writer_threads:
            t.join()

        stop_event.set()
        for t in flusher_threads + reader_threads:
            t.join()

        sm.flush()
        self.assertEqual(len(errors), 0, f"Concurrent flusher/reader/writer errors: {errors}")
        self.assertEqual(sm.get_completed_count(), 300)

    # =========================================================================
    # 2. Corrupted Schema Inputs, Warning, Backup, and Clean Fallback
    # =========================================================================

    def test_corrupted_schema_null_translated_items_backed_up_and_clean_state(self):
        """
        Verify load_state handles translated_items=null by:
        1. Logging a warning.
        2. Backing up the corrupted file to .corrupted_{timestamp}.
        3. Returning a clean default state without crashing.
        4. Successfully accepting new translation chunks.
        """
        state_file = os.path.join(self.test_dir, "null_schema_progress.json")
        corrupted_payload = {"book_identifier": "null_schema", "total_chunks": 50, "translated_items": None}
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(corrupted_payload, f)

        sm = StateManager("null_schema", total_chunks=50, state_dir=self.test_dir)

        # 1. Clean default state
        self.assertEqual(sm.get_completed_count(), 0)
        self.assertFalse(sm.is_chunk_translated("item1", 0))
        self.assertIsNone(sm.get_translated_chunk("item1", 0))
        self.assertEqual(sm.get_progress()["completed"], 0)

        # 2. Corrupted file was backed up and unlinked
        backup_files = [f for f in os.listdir(self.test_dir) if "corrupted_" in f]
        self.assertGreaterEqual(len(backup_files), 1, "Backup corrupted file must be created")
        backup_path = os.path.join(self.test_dir, backup_files[0])
        with open(backup_path, "r", encoding="utf-8") as bf:
            backup_content = json.load(bf)
        self.assertIsNone(backup_content["translated_items"], "Backup file must retain original corrupted payload")

        # 3. New writes succeed normally
        sm.mark_chunk_translated("item1", 0, "Clean translation", "Original")
        sm.flush()
        self.assertEqual(sm.get_completed_count(), 1)
        self.assertTrue(sm.is_chunk_translated("item1", 0))
        self.assertEqual(sm.get_translated_chunk("item1", 0), "Clean translation")

    def test_corrupted_schema_list_data_backed_up_and_clean_state(self):
        """
        Verify load_state handles root array schema [ ... ] by backing up and starting clean.
        """
        state_file = os.path.join(self.test_dir, "list_schema_progress.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(["corrupted", "list", 12345], f)

        sm = StateManager("list_schema", total_chunks=10, state_dir=self.test_dir)
        self.assertEqual(sm.get_completed_count(), 0)

        backup_files = [f for f in os.listdir(self.test_dir) if "corrupted_" in f]
        self.assertGreaterEqual(len(backup_files), 1, "Corrupted file must be backed up")

        # Verify writing after list corruption works
        sm.mark_chunk_translated("ch_1", 0, "Bekerja")
        sm.flush()
        self.assertEqual(sm.get_completed_count(), 1)

    def test_corrupted_malformed_json_syntax_backed_up_and_clean_state(self):
        """
        Verify load_state handles truncated/malformed JSON syntax by backing up and starting clean.
        """
        state_file = os.path.join(self.test_dir, "syntax_error_progress.json")
        with open(state_file, "w", encoding="utf-8") as f:
            f.write('{"book_identifier": "syntax_error", "translated_items": { "ch1": ')  # syntax error

        sm = StateManager("syntax_error", total_chunks=10, state_dir=self.test_dir)
        self.assertEqual(sm.get_completed_count(), 0)

        backup_files = [f for f in os.listdir(self.test_dir) if "corrupted_" in f]
        self.assertGreaterEqual(len(backup_files), 1, "Malformed syntax file must be backed up")

    def test_corrupted_schema_primitive_types_handled(self):
        """
        Verify string, int, boolean root types in JSON do not crash StateManager.
        """
        for val in ["just a string", 12345, True, False]:
            sub_dir = tempfile.mkdtemp(prefix="adv_prim_", dir=self.test_dir)
            p_file = os.path.join(sub_dir, "prim_progress.json")
            with open(p_file, "w", encoding="utf-8") as f:
                json.dump(val, f)

            sm = StateManager("prim", total_chunks=5, state_dir=sub_dir)
            self.assertEqual(sm.get_completed_count(), 0)
            self.assertEqual(sm.get_progress()["completed"], 0)

    # =========================================================================
    # 3. Multi-Instance Merge (No Overwriting / Lost Updates)
    # =========================================================================

    def test_multi_instance_merge_different_items_preserves_both(self):
        """
        Verify two StateManager instances on the same book merge different document items
        without clobbering each other.
        """
        mgr_a = StateManager("novel_merge", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)
        mgr_b = StateManager("novel_merge", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)

        # Instance A translates Chapter 1
        mgr_a.mark_chunk_translated("item_chap1", 0, "Bab 1 Paragraf 1")
        mgr_a.mark_chunk_translated("item_chap1", 1, "Bab 1 Paragraf 2")
        mgr_a.flush()

        # Instance B translates Chapter 2
        mgr_b.mark_chunk_translated("item_chap2", 0, "Bab 2 Paragraf 1")
        mgr_b.mark_chunk_translated("item_chap2", 1, "Bab 2 Paragraf 2")
        mgr_b.flush()

        # Read disk state
        with open(mgr_a.progress_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        translated = disk_data.get("translated_items", {})
        self.assertIn("item_chap1", translated, "item_chap1 must NOT be overwritten by Instance B")
        self.assertIn("item_chap2", translated, "item_chap2 must be present from Instance B")
        self.assertEqual(len(translated["item_chap1"]), 2)
        self.assertEqual(len(translated["item_chap2"]), 2)

    def test_multi_instance_merge_same_item_different_chunks_preserves_all_chunks(self):
        """
        Verify two StateManager instances writing to the SAME item but different chunks
        merge chunk-level entries without loss.
        """
        mgr_a = StateManager("same_item_book", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)
        mgr_b = StateManager("same_item_book", total_chunks=10, state_dir=self.test_dir, save_batch_size=1)

        # A writes chunks 0 and 1
        mgr_a.mark_chunk_translated("ch_same", 0, "Chunk 0 from A")
        mgr_a.mark_chunk_translated("ch_same", 1, "Chunk 1 from A")
        mgr_a.flush()

        # B writes chunks 2 and 3
        mgr_b.mark_chunk_translated("ch_same", 2, "Chunk 2 from B")
        mgr_b.mark_chunk_translated("ch_same", 3, "Chunk 3 from B")
        mgr_b.flush()

        with open(mgr_a.progress_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        ch_chunks = disk_data["translated_items"]["ch_same"]
        self.assertEqual(len(ch_chunks), 4, f"Expected 4 chunks in ch_same, got {len(ch_chunks)}")
        self.assertEqual(ch_chunks["0"]["translated"], "Chunk 0 from A")
        self.assertEqual(ch_chunks["1"]["translated"], "Chunk 1 from A")
        self.assertEqual(ch_chunks["2"]["translated"], "Chunk 2 from B")
        self.assertEqual(ch_chunks["3"]["translated"], "Chunk 3 from B")

    # =========================================================================
    # 4. Nested <div> Leaf Extraction & DOM Integrity
    # =========================================================================

    def test_nested_divs_extract_only_innermost_leafs_no_duplicates(self):
        """
        Verify nested <div>s extract ONLY innermost leaf divs.
        Parent container divs must NOT be extracted, preventing chunk duplication.
        """
        html = """
        <div class="novel-page" id="page1">
            <div class="column-left">
                <div class="scene-dialogue">
                    Dialogue in leaf 1.
                </div>
            </div>
            <div class="column-right">
                <div class="scene-action">
                    Action in leaf 2.
                </div>
            </div>
        </div>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]

        # Must extract exactly 2 leaf nodes (scene-dialogue and scene-action)
        self.assertEqual(len(nodes), 2, f"Expected exactly 2 leaf div nodes, got {len(nodes)}")
        texts = [n["text"] for n in nodes]
        self.assertIn("Dialogue in leaf 1.", texts)
        self.assertIn("Action in leaf 2.", texts)

        # Neither novel-page nor column-left nor column-right should be in nodes
        node_classes = [n["node"].get("class", []) for n in nodes]
        flattened_classes = [c for classes in node_classes for c in classes]
        self.assertNotIn("novel-page", flattened_classes)
        self.assertNotIn("column-left", flattened_classes)
        self.assertNotIn("column-right", flattened_classes)

    def test_nested_divs_update_does_not_detach_dom_nodes(self):
        """
        Verify updating extracted leaf <div>s does NOT detach sibling or child nodes from the DOM.
        """
        html = """
        <div class="container">
            <div class="leaf-a">First speech.</div>
            <div class="leaf-b">Second speech.</div>
        </div>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 2)

        node_a = nodes[0]["node"]
        node_b = nodes[1]["node"]

        # Initial DOM parents
        self.assertIsNotNone(node_a.parent)
        self.assertIsNotNone(node_b.parent)

        # Update first node
        parser.update_node(node_a, "Ucapan pertama yang diterjemahkan.")

        # Crucial check: node_b must STILL have its parent intact!
        self.assertIsNotNone(node_b.parent, "node_b must NOT be detached after updating node_a")
        self.assertEqual(node_b.parent.get("class"), ["container"])

        # Update second node
        parser.update_node(node_b, "Ucapan kedua yang diterjemahkan.")
        self.assertIsNotNone(node_a.parent, "node_a must NOT be detached after updating node_b")

        # Repack and verify round-trip content
        out_epub = os.path.join(self.test_dir, "repacked_divs.epub")
        parser.repack(out_epub)
        repacked_book = epub.read_epub(out_epub)
        ch_item = [item for item in repacked_book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "content" in item.get_name()][0]
        repacked_html = ch_item.get_content().decode("utf-8")

        self.assertIn("Ucapan pertama yang diterjemahkan.", repacked_html)
        self.assertIn("Ucapan kedua yang diterjemahkan.", repacked_html)
        self.assertIn('class="container"', repacked_html)

    def test_div_containing_p_tags_extracts_only_p_tags_not_div(self):
        """
        When a <div> wraps standard <p> tags, only the <p> tags should be extracted.
        The wrapper <div> must NOT be extracted.
        """
        html = """
        <div class="section-wrapper">
            <p>First paragraph.</p>
            <p>Second paragraph.</p>
        </div>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]

        self.assertEqual(len(nodes), 2)
        tags = [n["tag"] for n in nodes]
        self.assertEqual(tags, ["p", "p"])

    # =========================================================================
    # 5. Table Content: <td>, <th>, <aside>, <caption> Extraction & Translation
    # =========================================================================

    def test_table_content_td_th_caption_extracted_and_translated(self):
        """
        Verify that <td>, <th>, and <caption> elements in tables are extracted and translated.
        """
        html = """
        <table>
            <caption>Daftar Statistik Tokoh</caption>
            <thead>
                <tr>
                    <th scope="col">Nama Karakter</th>
                    <th scope="col">Tingkat Daya</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Rimuru Tempest</td>
                    <td>S-Rank Bencana</td>
                </tr>
                <tr>
                    <td>Veldora</td>
                    <td>Naga Sejati</td>
                </tr>
            </tbody>
        </table>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]

        tags = [n["tag"] for n in nodes]
        # Should have: 1 caption, 2 th, 4 td = 7 nodes total
        self.assertEqual(len(nodes), 7, f"Expected 7 table nodes, got {len(nodes)} (tags: {tags})")
        self.assertIn("caption", tags)
        self.assertEqual(tags.count("th"), 2)
        self.assertEqual(tags.count("td"), 4)

        # Update all nodes with translated text
        translations = [
            "Character Statistics Table",
            "Character Name",
            "Power Level",
            "Rimuru Tempest",
            "S-Rank Disaster",
            "Veldora Tempest",
            "True Dragon",
        ]
        for node_info, trans_text in zip(nodes, translations):
            parser.update_node(node_info["node"], trans_text)

        # Repack and verify
        out_epub = os.path.join(self.test_dir, "repacked_table.epub")
        parser.repack(out_epub)
        repacked = epub.read_epub(out_epub)
        ch_item = [item for item in repacked.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "content" in item.get_name()][0]
        repacked_html = ch_item.get_content().decode("utf-8")

        for trans in translations:
            self.assertIn(trans, repacked_html)

    def test_aside_and_section_elements_extracted_and_translated(self):
        """
        Verify <aside> and <section> literary text elements are extracted and translatable.
        """
        html = """
        <article>
            <section class="prologue">
                <p>Kisah ini bermula di padang tandus.</p>
            </section>
            <aside class="author-note">
                Catatan Pengarang: Jangan lewatkan bagian kedua.
            </aside>
        </article>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]

        tags = [n["tag"] for n in nodes]
        # <section> contains <p>, so <section> is skipped as container, <p> is extracted.
        # <aside> contains direct text (no block children), so <aside> IS extracted.
        self.assertIn("p", tags)
        self.assertIn("aside", tags)
        self.assertEqual(len(nodes), 2)

        # Update aside
        aside_node = [n for n in nodes if n["tag"] == "aside"][0]
        parser.update_node(aside_node["node"], "Author's Note: Do not miss part two.")

        out_epub = os.path.join(self.test_dir, "repacked_aside.epub")
        parser.repack(out_epub)
        repacked = epub.read_epub(out_epub)
        ch_item = [item for item in repacked.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "content" in item.get_name()][0]
        self.assertIn("Author's Note: Do not miss part two.", ch_item.get_content().decode("utf-8"))

    def test_table_cell_with_nested_inline_formatting(self):
        """
        Verify <td> containing inline elements (<em>, <strong>, <span>) preserves formatting.
        """
        html = """
        <table>
            <tr>
                <td><em>Pahlawan</em> <strong>Legendaris</strong></td>
            </tr>
        </table>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]

        self.assertEqual(len(nodes), 1)
        node_info = nodes[0]
        self.assertEqual(node_info["tag"], "td")
        self.assertIn("<em>", node_info["inner_html"])
        self.assertIn("<strong>", node_info["inner_html"])

        # Update preserving inline tags
        parser.update_node(node_info["node"], "<em>Legendary</em> <strong>Hero</strong>")

        out_epub = os.path.join(self.test_dir, "repacked_td_inline.epub")
        parser.repack(out_epub)
        repacked = epub.read_epub(out_epub)
        ch_item = [item for item in repacked.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "content" in item.get_name()][0]
        repacked_html = ch_item.get_content().decode("utf-8")
        self.assertIn("<em>Legendary</em> <strong>Hero</strong>", repacked_html)


if __name__ == "__main__":
    unittest.main()
