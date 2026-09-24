import sys
import os
import shutil
import tempfile
import time
import json
import unittest
import threading
from typing import Any, Dict, List, Tuple
from bs4 import BeautifulSoup, Tag
import ebooklib
from ebooklib import epub

# Ensure project root is on path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.epub_parser import EpubParser, BLOCK_TAGS, INLINE_TAGS
from utils.state_manager import StateManager


class AdversarialEpubTests(unittest.TestCase):
    """Adversarial stress tests for EpubParser."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="adv_epub_")
        self.epub_path = os.path.join(self.test_dir, "adv_novel.epub")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_epub_with_content(self, html_content: str, file_name="ch1.xhtml") -> Tuple[EpubParser, str]:
        book = epub.EpubBook()
        book.set_identifier("urn:adv:12345")
        book.set_title("Adversarial Novel Test")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        ch = epub.EpubHtml(title="Chapter", file_name=file_name, lang="en")
        ch.set_content(html_content.encode("utf-8"))
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(self.epub_path, book, {})
        parser = EpubParser(self.epub_path)
        return parser, ch.get_id()

    # -------------------------------------------------------------
    # 1. Unclosed & Malformed Tags
    # -------------------------------------------------------------

    def test_unclosed_inline_tags(self):
        """Test handling of unclosed inline tags inside a block."""
        html = """
        <p>Paragraph with <em>unclosed emphasis and <strong>unclosed bold.
        <p>Second paragraph after unclosed block.
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertGreaterEqual(len(nodes), 1)

        # Ensure node can be updated with unclosed replacement without crashing
        unclosed_replacement = "Ini <em>terjemahan tanpa penutup em dan <strong>bold"
        parser.update_node(nodes[0]["node"], unclosed_replacement)

        # Repack and verify
        out_epub = os.path.join(self.test_dir, "out_unclosed.epub")
        parser.repack(out_epub)
        repacked = epub.read_epub(out_epub)
        self.assertIsNotNone(repacked)

    def test_malformed_html_attributes(self):
        """Test handling of malformed attributes and bizarre brackets."""
        html = """
        <p class="test" style="color: red; font-family: 'Times New Roman'"><span invalid=attribute>>Broken << brackets & unescaped & symbols</span></p>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 1)

        # Update with complex string
        parser.update_node(nodes[0]["node"], "Teks terjemahan & simbol khusus < > & ' \"")
        out_epub = os.path.join(self.test_dir, "out_malformed.epub")
        parser.repack(out_epub)
        self.assertTrue(os.path.exists(out_epub))

    # -------------------------------------------------------------
    # 2. Nested Ruby Annotations
    # -------------------------------------------------------------

    def test_nested_ruby_furigana_annotations(self):
        """Test complex and nested ruby annotations."""
        complex_ruby = """
        <p>Dia berseru: <ruby><rb>超電磁砲</rb><rp>（</rp><rt><ruby><rb>レールガン</rb><rp>（</rp><rt>Railgun</rt><rp>）</rp></ruby></rt><rp>）</rp></ruby> dengan segenap tenaga.</p>
        """
        parser, ch_id = self._create_epub_with_content(complex_ruby)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 1)
        node_record = nodes[0]
        
        # Verify inner_html preserves ruby hierarchy
        self.assertIn("<ruby>", node_record["inner_html"])
        self.assertIn("Railgun", node_record["inner_html"])

        # Update node with Indonesian translation containing preserved ruby
        translated_ruby = 'Dia berteriak: <ruby><rb>Meriam Rel</rb><rp>(</rp><rt><ruby><rb>Railgun</rb><rp>(</rp><rt>Elektromagnetik</rt><rp>)</rp></ruby></rt><rp>)</rp></ruby> kuat-kuat.'
        parser.update_node(node_record["node"], translated_ruby)

        node = node_record["node"]
        ruby_tags = node.find_all("ruby")
        self.assertEqual(len(ruby_tags), 2, "Nested ruby tags must both be preserved")
        rt_tags = node.find_all("rt")
        self.assertEqual(len(rt_tags), 2, "Nested rt tags must both be preserved")
        self.assertEqual(rt_tags[1].get_text(), "Elektromagnetik")

        # Repack EPUB
        out_epub = os.path.join(self.test_dir, "out_ruby.epub")
        parser.repack(out_epub)
        repacked_book = epub.read_epub(out_epub)
        repacked_ch = [item for item in repacked_book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "ch1" in item.get_name()][0]
        ch_content = repacked_ch.get_content().decode("utf-8")
        self.assertIn("Elektromagnetik", ch_content)
        self.assertIn("<ruby>", ch_content)

    # -------------------------------------------------------------
    # 3. Complex Inline CSS Spans & 100% Inline Preservation
    # -------------------------------------------------------------

    def test_complex_inline_css_and_all_inline_tags_preservation(self):
        """
        Verify that ALL supported inline tags and elaborate style attributes
        are 100% preserved without stripping or alteration.
        """
        inline_samples = (
            '<p class="master-para" id="p1" style="margin: 10px; line-height: 1.5;">'
            '<span class="c1 c2" style="font-weight: 700; color: #123456; text-shadow: 1px 1px #000;" data-id="xyz">Span text</span> '
            '<em>Em text</em> '
            '<strong>Strong text</strong> '
            '<a href="https://example.com/target" title="link title" target="_blank">Anchor text</a> '
            '<i>Italic text</i> '
            '<b>Bold text</b> '
            '<small>Small text</small> '
            '<sub>Sub text</sub> '
            '<sup>Sup text</sup> '
            '<code>Code snippet = 42;</code> '
            '<mark class="highlight">Marked text</mark> '
            '<u>Underlined text</u> '
            '<s>Strikethrough text</s> '
            '<cite>Citation of Book</cite> '
            '<abbr title="HyperText Markup Language">HTML</abbr> '
            '<q>Quoted quote</q> '
            '<font color="blue" face="Arial">Font tag</font>'
            '</p>'
        )
        parser, ch_id = self._create_epub_with_content(inline_samples)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 1)

        # Check all tags present in inner_html
        inner = nodes[0]["inner_html"]
        for tag in ["span", "em", "strong", "a", "i", "b", "small", "sub", "sup", "code", "mark", "u", "s", "cite", "abbr", "q", "font"]:
            self.assertIn(f"<{tag}", inner, f"Tag <{tag}> missing in extracted inner_html")

        # Now simulate translating with preserved markup
        translated_markup = (
            '<span class="c1 c2" style="font-weight: 700; color: #123456; text-shadow: 1px 1px #000;" data-id="xyz">Teks span</span> '
            '<em>Teks miring em</em> '
            '<strong>Teks tebal strong</strong> '
            '<a href="https://example.com/target" title="link title" target="_blank">Tautan anchor</a> '
            '<i>Teks italic</i> '
            '<b>Teks bold b</b> '
            '<small>Teks kecil</small> '
            '<sub>Teks sub</sub> '
            '<sup>Teks sup</sup> '
            '<code>potongan_kode = 42;</code> '
            '<mark class="highlight">Teks disorot</mark> '
            '<u>Teks garis bawah</u> '
            '<s>Teks coret</s> '
            '<cite>Kutipan Buku</cite> '
            '<abbr title="HyperText Markup Language">HTML</abbr> '
            '<q>Teks tanda kutip</q> '
            '<font color="blue" face="Arial">Tag font</font>'
        )
        parser.update_node(nodes[0]["node"], translated_markup)

        # Verify outer attributes are untouched
        node = nodes[0]["node"]
        self.assertEqual(node.get("class"), ["master-para"])
        self.assertEqual(node.get("id"), "p1")
        self.assertEqual(node.get("style"), "margin: 10px; line-height: 1.5;")

        # Verify all child tags still exist inside node
        found_tags = {child.name for child in node.find_all(True)}
        expected_tags = {"span", "em", "strong", "a", "i", "b", "small", "sub", "sup", "code", "mark", "u", "s", "cite", "abbr", "q", "font"}
        self.assertTrue(expected_tags.issubset(found_tags), f"Missing tags: {expected_tags - found_tags}")

        # Verify attributes on span
        span = node.find("span")
        self.assertEqual(span.get("data-id"), "xyz")
        self.assertEqual(span.get("style"), "font-weight: 700; color: #123456; text-shadow: 1px 1px #000;")
        self.assertEqual(span.get("class"), ["c1", "c2"])

        # Repack
        out_epub = os.path.join(self.test_dir, "out_all_inline.epub")
        parser.repack(out_epub)
        self.assertTrue(os.path.exists(out_epub))

    # -------------------------------------------------------------
    # 4. Huge Paragraphs & Volume Stress
    # -------------------------------------------------------------

    def test_huge_paragraph_and_many_inline_tags(self):
        """Test single massive paragraph (100,000+ chars) with 1,000 inline tags."""
        chunks = []
        for i in range(1000):
            chunks.append(f'Bagian nomor {i} dengan <span class="tag_{i}">kata penting {i}</span> dan <em>miring {i}</em>. ')
        huge_html = f'<p class="giant">{"".join(chunks)}</p>'
        
        start_t = time.time()
        parser, ch_id = self._create_epub_with_content(huge_html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 1)
        node = nodes[0]["node"]
        self.assertGreater(len(nodes[0]["text"]), 50000)

        # Update with another huge translated string
        translated_chunks = []
        for i in range(1000):
            translated_chunks.append(f'Terjemahan {i} <span class="tag_{i}">kata {i}</span> <em>miring {i}</em>. ')
        parser.update_node(node, "".join(translated_chunks))

        out_epub = os.path.join(self.test_dir, "out_huge.epub")
        parser.repack(out_epub)
        elapsed = time.time() - start_t
        self.assertTrue(os.path.exists(out_epub))
        self.assertLess(elapsed, 10.0, f"Processing huge paragraph took too long: {elapsed:.2f}s")

    # -------------------------------------------------------------
    # 5. Unicode, Emojis, RTL, and Special Characters
    # -------------------------------------------------------------

    def test_unicode_emojis_rtl_and_special_symbols(self):
        """Test full fidelity of emojis, RTL Arabic, Hebrew, CJK, and typographic symbols."""
        special_content = (
            '<p class="polyglot">'
            'English &amp; Symbols: © ® ™ § ¶ &lt; &gt; &quot; &#39; &amp; — … \n'
            'Emoji & Modifiers: 🗡️ 🛡️ 🧙‍♂️ 🧝‍♀️ 🔥 🚀 🌟 📜 ✨ 💎 \n'
            'CJK: 漢字、ひらがな、カタカナ、한글 (Korean) \n'
            'RTL Arabic: مرحبا بك في عالم الروايات الخيالية \n'
            'RTL Hebrew: ברוכים הבאים לעולם הפנטזיה \n'
            'Accents: é, è, ê, ë, à, â, î, ï, ô, ù, û, ç, ñ, ß \n'
            'Indonesian slang & terms: ku- tahu, ber-ulang—ulang, "kutipan \'ganda\'" '
            '</p>'
        )
        parser, ch_id = self._create_epub_with_content(special_content)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        self.assertEqual(len(nodes), 1)
        
        # Verify text preserves emojis and RTL
        orig_text = nodes[0]["text"]
        self.assertIn("🗡️", orig_text)
        self.assertIn("مرحبا", orig_text)
        self.assertIn("漢字", orig_text)

        # Update with Indonesian translation containing emojis and special chars
        translated = (
            'Terjemahan: Simbol © ® ™ — … 🗡️ 🛡️ 🧙‍♂️ '
            'Teks Arab: مرحبا Teks Jepang: 漢字 '
            '"Tanda kutip" &amp; \'petik tunggal\' selesai.'
        )
        parser.update_node(nodes[0]["node"], translated)

        out_epub = os.path.join(self.test_dir, "out_polyglot.epub")
        parser.repack(out_epub)
        
        repacked_book = epub.read_epub(out_epub)
        repacked_ch = [item for item in repacked_book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if "ch1" in item.get_name()][0]
        repacked_str = repacked_ch.get_content().decode("utf-8")
        self.assertIn("🗡️", repacked_str)
        self.assertIn("مرحبا", repacked_str)
        self.assertIn("漢字", repacked_str)

    # -------------------------------------------------------------
    # 6. Structural Vulnerability: Nested <div> extraction
    # -------------------------------------------------------------

    def test_nested_divs_structural_integrity(self):
        """
        ADVERSARIAL CHALLENGE: Nested <div>s without standard block tags.
        Does EpubParser duplicate chunks or corrupt DOM hierarchy when nested divs exist?
        """
        html = """
        <div class="novel-container">
            <div class="chapter-wrapper">
                <div class="scene-box">
                    Direct scene dialogue without p tags.
                </div>
            </div>
        </div>
        """
        parser, ch_id = self._create_epub_with_content(html)
        nodes = [n for n in parser.extract_text_nodes() if n["item_id"] == ch_id]
        
        # If nested divs are extracted, record how many nodes are returned
        div_tags = [n for n in nodes if n["tag"] == "div"]
        print(f"\n[CHALLENGE LOG] Nested divs extracted count: {len(div_tags)}")
        for idx, n in enumerate(div_tags):
            print(f"  Div [{idx}]: text={n['text']!r}")

        # If all 3 divs are extracted, updating div[0] mutates/wipes div[1] and div[2]
        if len(div_tags) > 1:
            parser.update_node(div_tags[0]["node"], "Scene 1 translated at container level.")
            print(f"  After div[0] update, div[1] parent: {div_tags[1]['node'].parent}")
            # div_tags[1] is now detached from the DOM!
            self.assertIsNone(div_tags[1]["node"].parent, "div[1] must be detached after div[0] update")


class AdversarialStateManagerTests(unittest.TestCase):
    """Adversarial stress tests for StateManager."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="adv_state_")
        self.book_id = "adv_book_hash_98765"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # 1. Simulated Crash Mid-Save / Kill Resilience
    # -------------------------------------------------------------

    def test_simulated_crash_mid_save_leaves_original_intact(self):
        """
        Simulate process interruption while writing temp file before os.replace.
        Verify that original progress file remains completely intact and uncorrupted.
        """
        manager = StateManager(self.book_id, total_chunks=10, state_dir=self.test_dir)
        manager.mark_chunk_translated("item1", 0, "Chunk 0 verified")
        manager.flush()
        
        # Verify valid baseline
        self.assertTrue(os.path.exists(manager.progress_file))
        with open(manager.progress_file, "r", encoding="utf-8") as f:
            base_data = json.load(f)
        self.assertEqual(base_data["translated_items"]["item1"]["0"]["translated"], "Chunk 0 verified")

        # Simulate crash: write half-baked partial .tmp file into state_dir
        crashed_tmp = os.path.join(self.test_dir, f"{self.book_id}_9999_12345.tmp")
        with open(crashed_tmp, "w", encoding="utf-8") as f:
            f.write('{"book_identifier": "adv_book_hash_98765", "translat') # cut mid-write

        # Start a new StateManager session
        recovered = StateManager(self.book_id, total_chunks=10, state_dir=self.test_dir)
        self.assertTrue(recovered.is_chunk_translated("item1", 0))
        self.assertEqual(recovered.get_translated_chunk("item1", 0), "Chunk 0 verified")

    # -------------------------------------------------------------
    # 2. Corrupted State Recovery (Schema Variations)
    # -------------------------------------------------------------

    def test_corrupted_json_binary_garbage(self):
        """Verify recovery when progress file is filled with raw random binary bytes."""
        progress_file = os.path.join(self.test_dir, f"{self.book_id}_progress.json")
        with open(progress_file, "wb") as f:
            f.write(os.urandom(1024)) # 1 KB of random binary garbage

        recovered = StateManager(self.book_id, total_chunks=5, state_dir=self.test_dir)
        self.assertEqual(recovered.get_completed_count(), 0)
        self.assertEqual(recovered.state["total_chunks"], 5)

    def test_corrupted_json_invalid_schema_types(self):
        """
        ADVERSARIAL CHALLENGE: Progress file contains valid JSON, but schema is malicious/broken:
        e.g. root is array `[]`, or `{"translated_items": None}`, or `{"translated_items": "string"}`.
        Does StateManager crash on method calls?
        """
        progress_file = os.path.join(self.test_dir, f"{self.book_id}_progress.json")
        
        malformed_schemas = [
            [], # root is list
            None, # root is null
            {"translated_items": None}, # translated_items is None
            {"translated_items": "not a dict"}, # translated_items is string
            {"translated_items": 12345}, # translated_items is int
        ]

        for idx, malformed in enumerate(malformed_schemas):
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(malformed, f)

            print(f"\n[CHALLENGE LOG] Testing malformed schema #{idx}: {malformed}")
            try:
                sm = StateManager(self.book_id, total_chunks=10, state_dir=self.test_dir)
                # Call all public query methods
                is_trans = sm.is_chunk_translated("item1", 0)
                txt = sm.get_translated_chunk("item1", 0)
                cnt = sm.get_completed_count()
                prog = sm.get_progress()
                sm.mark_chunk_translated("item1", 0, "New trans")
                sm.flush()
                print(f"  Schema #{idx} handled gracefully. Completed: {cnt}")
            except Exception as exc:
                print(f"  [VULNERABILITY FOUND] Schema #{idx} crashed with: {type(exc).__name__}: {exc}")

    # -------------------------------------------------------------
    # 3. Concurrent Instances & Race Conditions
    # -------------------------------------------------------------

    def test_concurrent_instances_lost_updates(self):
        """
        ADVERSARIAL CHALLENGE: Two StateManager instances updating the same book concurrently.
        Instance A writes chunks 0-9.
        Instance B writes chunks 10-19.
        Does Instance B wipe out Instance A's progress due to independent in-memory state?
        """
        mgr_a = StateManager(self.book_id, total_chunks=20, state_dir=self.test_dir, save_batch_size=1)
        mgr_b = StateManager(self.book_id, total_chunks=20, state_dir=self.test_dir, save_batch_size=1)

        # Interleaved updates
        for i in range(10):
            mgr_a.mark_chunk_translated("item_a", i, f"Translation A-{i}")
        mgr_a.flush()

        # Manager B writes to same book
        for i in range(10):
            mgr_b.mark_chunk_translated("item_b", i, f"Translation B-{i}")
        mgr_b.flush()

        # Check what is persisted in the actual file on disk
        with open(mgr_a.progress_file, "r", encoding="utf-8") as f:
            disk_state = json.load(f)

        item_a_saved = "item_a" in disk_state.get("translated_items", {})
        item_b_saved = "item_b" in disk_state.get("translated_items", {})

        print(f"\n[CHALLENGE LOG] Concurrency Check:")
        print(f"  item_a in disk state: {item_a_saved}")
        print(f"  item_b in disk state: {item_b_saved}")
        
        if not item_a_saved:
            print("  [VULNERABILITY FOUND] Instance B completely overwrote Instance A's saved chunks!")

    def test_multithreaded_save_state_permission_errors(self):
        """
        ADVERSARIAL CHALLENGE: Concurrent worker threads updating StateManager concurrently.
        On Windows, atomic os.replace without mutex locks triggers [WinError 32] / [WinError 5].
        """
        sm = StateManager("thread_stress", total_chunks=200, state_dir=self.test_dir, save_batch_size=5)
        errors = []

        def worker(w_id):
            try:
                for i in range(20):
                    sm.mark_chunk_translated(f"ch_{w_id}", i, f"Text {w_id}-{i}")
            except Exception as e:
                errors.append((w_id, e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(f"\n[CHALLENGE LOG] Multithreaded save errors count: {len(errors)}")
        if errors:
            print(f"  Sample error: {errors[0]}")
            print("  [VULNERABILITY FOUND] StateManager is NOT thread-safe on Windows despite class docstring claim!")

    # -------------------------------------------------------------
    # 4. Large Chapter Batch Saves (5,000 Chunks)
    # -------------------------------------------------------------

    def test_large_chapter_batch_saves_performance(self):
        """
        Stress test saving 5,000 chunks across multiple chapters with batching.
        Verifies throughput, memory stability, and disk integrity.
        """
        num_chunks = 5000
        batch_size = 250
        manager = StateManager(
            self.book_id,
            total_chunks=num_chunks,
            state_dir=self.test_dir,
            save_batch_size=batch_size,
        )

        start_t = time.time()
        for i in range(num_chunks):
            ch_id = f"ch_{i // 100}"
            chunk_idx = i % 100
            manager.mark_chunk_translated(
                ch_id,
                chunk_idx,
                f"Ini adalah teks terjemahan nomor {i} yang cukup panjang untuk menguji efisiensi I/O.",
            )
        manager.flush()
        elapsed = time.time() - start_t

        print(f"\n[STRESS LOG] 5,000 chunks batched save elapsed time: {elapsed:.2f}s ({num_chunks / elapsed:.0f} chunks/sec)")
        
        # Verify correctness
        self.assertEqual(manager.get_completed_count(), num_chunks)
        progress = manager.get_progress()
        self.assertEqual(progress["percent"], 100.0)

        # Verify disk file valid
        with open(manager.progress_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        saved_count = sum(len(v) for v in disk_data["translated_items"].values())
        self.assertEqual(saved_count, num_chunks)
        self.assertLess(elapsed, 10.0, "Large batch save must finish within 10 seconds")


if __name__ == "__main__":
    unittest.main()
