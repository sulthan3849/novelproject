import hashlib
import os
import re
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Tag

from core.agentic_translator import AgenticTranslator, TranslationResult
from utils.epub_parser import EpubParser
from utils.state_manager import StateManager


class MockChoice:
    def __init__(self, content: str):
        self.message = MagicMock(content=content)


class MockUsage:
    def __init__(self, total_tokens: int = 45):
        self.total_tokens = total_tokens


class MockCompletionResponse:
    def __init__(self, content: str, total_tokens: int = 45):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(total_tokens)


def build_synthetic_novel(
    file_path: str,
    title: str = "The Sovereign of Shadows",
    author: str = "Jin-Woo Sung",
) -> str:
    """Builds a realistic, publication-grade multi-chapter EPUB novel for simulation."""
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:novel-synthetic-test-uuid-98765")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # CSS Stylesheet
    style_css = epub.EpubItem(
        uid="main_css",
        file_name="style/main.css",
        media_type="text/css",
        content=b"""
        body { font-family: 'Newsreader', serif; line-height: 1.7; color: #111; }
        h1, h2 { font-family: sans-serif; font-weight: 700; color: #000; }
        .thought { font-style: italic; color: #444; }
        .system-alert { border: 1px solid #333; padding: 8px; font-family: monospace; }
        .character { font-weight: bold; }
        """,
    )
    book.add_item(style_css)

    chapters = [
        (
            "chapter1.xhtml",
            "Chapter 1: The Gate Awakening",
            """<?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Chapter 1</title><link rel="stylesheet" href="style/main.css" type="text/css"/></head>
            <body>
                <h1>Chapter 1: The Gate Awakening</h1>
                <p class="narrative">A cold tremor resonated through the cavern as the <em>blue dungeon gate</em> flared violently.</p>
                <p class="thought">"Is this the end?" he whispered silently.</p>
                <p class="dialogue">"Do not retreat!" shouted <span class="character">Hunter Song</span>, gripping his <strong>steel sword</strong>.</p>
            </body>
            </html>""",
        ),
        (
            "chapter2.xhtml",
            "Chapter 2: The Shadow Monarch",
            """<?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Chapter 2</title><link rel="stylesheet" href="style/main.css" type="text/css"/></head>
            <body>
                <h2>Chapter 2: The Shadow Monarch</h2>
                <p class="system-alert">A quest has arrived: <a href="quest.xhtml">Defeat the Monarch</a>.</p>
                <p>The ancient blade was engraved with <ruby>Dark Magic<rt>Kurayami</rt></ruby>.</p>
                <blockquote cite="lore">From death, the sovereign commands the eternal army.</blockquote>
            </body>
            </html>""",
        ),
        (
            "chapter3.xhtml",
            "Chapter 3: The Climax",
            """<?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Chapter 3</title><link rel="stylesheet" href="style/main.css" type="text/css"/></head>
            <body>
                <h2>Chapter 3: The Climax</h2>
                <p>Darkness swallowed the horizon as thousands of shadow soldiers knelt in silent fealty.</p>
            </body>
            </html>""",
        ),
    ]

    spine = ["nav"]
    for file_name, ch_title, ch_html in chapters:
        c = epub.EpubHtml(title=ch_title, file_name=file_name, lang="en")
        c.set_content(ch_html.encode("utf-8"))
        book.add_item(c)
        spine.append(c)

    book.spine = spine
    epub.write_epub(file_path, book, {})
    return file_path


def run_translation_pipeline(
    parser: EpubParser,
    state_manager: StateManager,
    translator: AgenticTranslator,
    source_lang: str = "English",
    target_lang: str = "Indonesian (Gramedia Standard)",
    glossary: dict = None,
) -> str:
    """End-to-end execution pipeline simulating the application loop."""
    html_items = [it for it in parser.get_html_items() if not it.get_name().startswith("nav")]
    
    for item in html_items:
        item_id = item.get_id()
        soup, nodes = parser.extract_chunks(item)
        for idx, node in enumerate(nodes):
            orig_inner = "".join(str(c) for c in node.contents).strip()
            if not orig_inner:
                continue

            if state_manager.is_chunk_translated(item_id, idx):
                translated_text = state_manager.get_translated_chunk(item_id, idx)
                parser.update_node(node, translated_text or "")
                continue

            result = translator.translate_chunk(
                text=orig_inner,
                source_lang=source_lang,
                target_lang=target_lang,
                glossary=glossary,
            )
            trans_str = str(result)
            state_manager.mark_chunk_translated(item_id, idx, trans_str, orig_inner)
            parser.update_node(node, trans_str)

        state_manager.flush()

    output_path = os.path.join(tempfile.gettempdir(), f"{parser.book_name}_translated.epub")
    parser.repack(output_path)
    return output_path


class TestE2EIntegration(unittest.TestCase):
    """Tier 3 (Cross-Feature) and Tier 4 (Real-World Scenarios) E2E integration test suite."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_e2e_")
        self.epub_path = os.path.join(self.test_dir, "synthetic_novel.epub")
        build_synthetic_novel(self.epub_path)
        self.book_hash = EpubParser.compute_hash(self.epub_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # Tier 3: Cross-Feature Combinations (Resume Interrupted Workflow)
    # -------------------------------------------------------------

    @patch("core.agentic_translator.litellm.completion")
    def test_e2e_interrupted_resume_workflow(self, mock_completion):
        """
        Simulate an interrupted translation session and subsequent resumption:
        1. Initialize Session 1: Parse EPUB, compute SHA-256, translate Chapter 1.
        2. Simulate crash / browser disconnect after Chapter 1.
        3. Initialize Session 2: Fresh EpubParser and StateManager with same book SHA-256.
        4. Assert Chapter 1 chunks are skipped as already translated (0 LLM calls for Ch 1).
        5. Translate remaining chapters.
        6. Repack and verify final EPUB validity and HTML structure.
        """
        # Session 1: Translate Chapter 1 chunks (h1, p.narrative, p.thought, p.dialogue -> 4 chunks)
        mock_completion.side_effect = [
            # Ch1 - Chunk 0: h1 (Fast path)
            MockCompletionResponse("Bab 1: Kebangkitan Gerbang", 20),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch1 - Chunk 1: p.narrative (3-step)
            MockCompletionResponse("Draf: Getaran dingin bergema...", 30),
            MockCompletionResponse("Kritik: Perbaiki pilihan kata.", 20),
            MockCompletionResponse("Getaran dingin merayap melalui gua saat <em>gerbang bawah tanah biru</em> itu menyala dengan ganas.", 40),
            # Ch1 - Chunk 2: p.thought (Fast path)
            MockCompletionResponse('"Apakah ini akhir?" bisiknya lirih.', 25),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch1 - Chunk 3: p.dialogue (3-step)
            MockCompletionResponse("Draf: Jangan mundur!", 25),
            MockCompletionResponse("Kritik: Pastikan tag dipertahankan.", 20),
            MockCompletionResponse('"Jangan mundur!" seru <span class="character">Pemburu Song</span>, menggenggam <strong>pedang bajanya</strong>.', 40),
        ]

        parser_s1 = EpubParser(self.epub_path, book_hash=self.book_hash)
        state_s1 = StateManager(self.book_hash, total_chunks=9, state_dir=self.test_dir)
        translator_s1 = AgenticTranslator(api_key="sk-mock", model_name="gpt-4o-mini")

        # Process only Chapter 1 items in Session 1
        items = [it for it in parser_s1.get_html_items() if not it.get_name().startswith("nav")]
        ch1_item = items[0]
        soup, nodes = parser_s1.extract_chunks(ch1_item)

        for idx, node in enumerate(nodes):
            orig_text = "".join(str(c) for c in node.contents).strip()
            res = translator_s1.translate_chunk(orig_text)
            state_s1.mark_chunk_translated(ch1_item.get_id(), idx, str(res), orig_text)
            parser_s1.update_node(node, str(res))

        state_s1.flush()
        self.assertEqual(state_s1.get_completed_count(), 4)

        # -------------------------------------------------------------
        # Session 2: Resumption after simulated interruption
        # -------------------------------------------------------------
        # Reset mock completion to track new calls only
        mock_completion.reset_mock()
        mock_completion.side_effect = [
            # Ch2 - Chunk 0 (Fast path)
            MockCompletionResponse("Bab 2: Sang Raja Bayangan", 20),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch2 - Chunk 1 (Fast path)
            MockCompletionResponse('Pencarian telah tiba: <a href="quest.xhtml">Kalahkan sang Raja</a>.', 30),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch2 - Chunk 2 (Fast path)
            MockCompletionResponse('Bilah kuno itu diukir dengan <ruby>Sihir Kegelapan<rt>Kurayami</rt></ruby>.', 30),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch2 - Chunk 3 (Fast path)
            MockCompletionResponse('Dari kematian, sang penguasa memerintah pasukan abadi.', 25),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch3 - Chunk 0: h2 (Fast path)
            MockCompletionResponse("Bab 3: Puncak Pertarungan", 20),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
            # Ch3 - Chunk 1: p (Fast path)
            MockCompletionResponse("Kegelapan menelan cakrawala saat ribuan prajurit bayangan berlutut dalam kesetiaan hening.", 35),
            MockCompletionResponse("[STATUS: PERFECT]", 10),
        ]

        parser_s2 = EpubParser(self.epub_path, book_hash=self.book_hash)
        state_s2 = StateManager(self.book_hash, total_chunks=9, state_dir=self.test_dir)
        translator_s2 = AgenticTranslator(api_key="sk-mock", model_name="gpt-4o-mini")

        # Resume translation for all items
        story_items_s2 = [it for it in parser_s2.get_html_items() if not it.get_name().startswith("nav")]

        for item in story_items_s2:
            s, n_list = parser_s2.extract_chunks(item)
            for idx, node in enumerate(n_list):
                orig_text = "".join(str(c) for c in node.contents).strip()
                if state_s2.is_chunk_translated(item.get_id(), idx):
                    # Already translated: reuse state, do NOT call LLM
                    trans_text = state_s2.get_translated_chunk(item.get_id(), idx)
                    parser_s2.update_node(node, trans_text or "")
                else:
                    res = translator_s2.translate_chunk(orig_text)
                    state_s2.mark_chunk_translated(item.get_id(), idx, str(res), orig_text)
                    parser_s2.update_node(node, str(res))

        state_s2.flush()

        # Verify all 10 story chunks completed across the 3 chapters (4 in Ch1, 4 in Ch2, 2 in Ch3)
        self.assertEqual(state_s2.get_completed_count(), 10)

        # Repack to new EPUB
        output_epub = os.path.join(self.test_dir, "resumed_output.epub")
        parser_s2.repack(output_epub)
        self.assertTrue(os.path.exists(output_epub))

        # Inspect repacked EPUB
        repacked = epub.read_epub(output_epub)
        doc_items = [it for it in repacked.get_items_of_type(ebooklib.ITEM_DOCUMENT) if not it.get_name().startswith("nav")]
        
        # Verify Chapter 1 translation retained intact
        ch1_repacked_html = doc_items[0].get_content().decode("utf-8")
        self.assertIn("Kebangkitan Gerbang", ch1_repacked_html)
        self.assertIn("<em>gerbang bawah tanah biru</em>", ch1_repacked_html)
        self.assertIn('<span class="character">Pemburu Song</span>', ch1_repacked_html)
        self.assertIn("<strong>pedang bajanya</strong>", ch1_repacked_html)

        # Verify Chapter 2 translation succeeded
        ch2_repacked_html = doc_items[1].get_content().decode("utf-8")
        self.assertIn("Sang Raja Bayangan", ch2_repacked_html)
        self.assertIn('<ruby>Sihir Kegelapan<rt>Kurayami</rt></ruby>', ch2_repacked_html)

    # -------------------------------------------------------------
    # Tier 4: Real-World Scenario (Synthetic Multi-Chapter End-to-End)
    # -------------------------------------------------------------

    @patch("core.agentic_translator.litellm.completion")
    def test_synthetic_multi_chapter_novel_translation_simulation(self, mock_completion):
        """
        Execute a full real-world translation simulation:
        - Multi-chapter EPUB with styles, ruby markup, and formatting tags
        - User-defined glossary mapping
        - Full execution through pipeline harness
        - Verified repacked EPUB output
        """
        # Setup mock responses for all 10 chunks in the 3 chapters
        # Fast path for some, 3-step for others
        mock_responses = []
        for i in range(10):
            # Step 1: Draft
            mock_responses.append(MockCompletionResponse(f"Draf Terjemahan Paragraf {i}", 40))
            if i % 2 == 0:
                # Fast path bypass
                mock_responses.append(MockCompletionResponse("[STATUS: PERFECT] Terjemahan memuaskan.", 15))
            else:
                # Full 3-step cycle
                mock_responses.append(MockCompletionResponse("Kritik: Sesuaikan diksi sastra.", 20))
                mock_responses.append(MockCompletionResponse(f"Final Terjemahan Paragraf {i} berstandar Gramedia.", 45))

        mock_completion.side_effect = mock_responses

        glossary_dict = {
            "Hunter Song": "Pemburu Song",
            "Shadow Monarch": "Raja Bayangan",
        }

        parser = EpubParser(self.epub_path, book_hash=self.book_hash)
        story_nodes = [
            n for n in parser.extract_text_nodes()
            if not n["item_id"].startswith("nav") and not n["item"].get_name().startswith("nav")
        ]
        total_chunks = len(story_nodes)
        state_mgr = StateManager(self.book_hash, total_chunks=total_chunks, state_dir=self.test_dir)
        translator = AgenticTranslator(api_key="sk-valid", model_name="gpt-4o-mini", glossary=glossary_dict)

        output_path = run_translation_pipeline(
            parser=parser,
            state_manager=state_mgr,
            translator=translator,
            source_lang="English",
            target_lang="Indonesian (Gramedia Standard)",
            glossary=glossary_dict,
        )

        # Assert output was produced and exists
        self.assertIsNotNone(output_path)
        self.assertTrue(os.path.exists(output_path))

        # Assert StateManager recorded 100% completion
        progress = state_mgr.get_progress()
        self.assertEqual(progress["completed"], total_chunks)
        self.assertEqual(progress["percent"], 100.0)

        # Assert Telemetry
        self.assertGreater(translator.total_tokens_used, 0)
        self.assertGreater(translator.fast_path_count, 0)

        # Verify Repacked EPUB integrity
        repacked = epub.read_epub(output_path)
        self.assertEqual(repacked.get_metadata("DC", "title")[0][0], "The Sovereign of Shadows")

        # Verify stylesheet is preserved in repacked EPUB
        css_items = list(repacked.get_items_of_type(ebooklib.ITEM_STYLE))
        self.assertEqual(len(css_items), 1)
        self.assertIn(b"Newsreader", css_items[0].get_content())

    # -------------------------------------------------------------
    # Taste-Skill CSS Verification (AC-4 Compliance from Disk)
    # -------------------------------------------------------------

    def test_taste_skill_css_compliance_in_app_source(self):
        """Verify app.py source code contains bespoke Taste-Skill CSS adhering to minimalist-ui design standards."""
        app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
        self.assertTrue(os.path.exists(app_path), f"app.py not found at {app_path}")

        with open(app_path, "r", encoding="utf-8") as f:
            app_code = f.read()

        # AC-4: Custom CSS injection via st.markdown
        self.assertIn("st.markdown(", app_code)
        self.assertIn("<style>", app_code)
        self.assertIn("</style>", app_code)

        # Warm/Dark Obsidian Palette
        self.assertIn("#0D0F12", app_code, "Missing #0D0F12 canvas background")
        self.assertIn("#16191F", app_code, "Missing #16191F container/card background")
        self.assertIn("#E6E8EC", app_code, "Missing #E6E8EC typography color")

        # Editorial Typography Hierarchy
        self.assertIn("Geist", app_code)
        self.assertIn("SF Pro Display", app_code)
        self.assertIn("monospace", app_code)

        # Bento Telemetry Grid
        self.assertIn("bento-grid", app_code)
        self.assertIn("bento-card", app_code)
        self.assertIn("bento-value", app_code)

        # Monospace Live Terminal
        self.assertIn("terminal-window", app_code)
        self.assertIn("terminal-header", app_code)

        # Split-pane Inspection Container
        self.assertIn("inspection-container", app_code)
        self.assertIn("inspection-pane", app_code)


if __name__ == "__main__":
    unittest.main()
