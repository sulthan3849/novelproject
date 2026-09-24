"""
Auditor 2 Forensic Verification Script
Exhaustively tests all remediation changes introduced in Iteration 2 by worker_3.
"""
import os
import sys
import tempfile
import time
import shutil
import json
import threading
from unittest.mock import patch, MagicMock
from ebooklib import epub
from bs4 import BeautifulSoup

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.state_manager import StateManager
from utils.epub_parser import EpubParser, BLOCK_TAGS
from core.prompts import get_draft_prompt, get_reflect_prompt, get_improve_prompt, format_glossary
from core.agentic_translator import AgenticTranslator, TranslationResult


class MockChoice:
    def __init__(self, content: str):
        self.message = MagicMock(content=content)


class MockUsage:
    def __init__(self, total_tokens: int = 50):
        self.total_tokens = total_tokens


class MockResponse:
    def __init__(self, content: str, tokens: int = 50):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(tokens)


def test_state_manager_concurrency():
    print("[1/8] Testing StateManager threading concurrency...")
    temp_dir = tempfile.mkdtemp()
    try:
        sm = StateManager("test_concurrency", total_chunks=200, state_dir=temp_dir, save_batch_size=2)
        num_threads = 10
        chunks_per_thread = 20
        errors = []

        def worker(thread_idx):
            try:
                for c_idx in range(chunks_per_thread):
                    sm.mark_chunk_translated(
                        item_id=f"chapter_{thread_idx}",
                        chunk_index=c_idx,
                        translated_text=f"Trans {thread_idx}:{c_idx}",
                        original_text=f"Orig {thread_idx}:{c_idx}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        sm.flush()
        completed = sm.get_completed_count()
        assert len(errors) == 0, f"Encountered thread errors: {errors}"
        assert completed == num_threads * chunks_per_thread, f"Expected {num_threads * chunks_per_thread}, got {completed}"
        print(f"  -> Concurrency PASS: Successfully saved {completed} chunks across {num_threads} concurrent threads.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_state_manager_multi_instance_merge():
    print("[2/8] Testing StateManager multi-instance merge logic...")
    temp_dir = tempfile.mkdtemp()
    try:
        # Instance A writes chapter 1
        sm_a = StateManager("novel_merge", total_chunks=10, state_dir=temp_dir, save_batch_size=1)
        sm_a.mark_chunk_translated("chap1", 0, "Ch1 Trans 0", "Ch1 Orig 0")
        sm_a.mark_chunk_translated("chap1", 1, "Ch1 Trans 1", "Ch1 Orig 1")
        sm_a.flush()

        # Instance B (simulating another worker/tab on the same book) writes chapter 2
        sm_b = StateManager("novel_merge", total_chunks=10, state_dir=temp_dir, save_batch_size=1)
        sm_b.mark_chunk_translated("chap2", 0, "Ch2 Trans 0", "Ch2 Orig 0")
        sm_b.flush()

        # Instance A writes chapter 1 chunk 2 (should merge chapter 2 from disk without clobbering)
        sm_a.mark_chunk_translated("chap1", 2, "Ch1 Trans 2", "Ch1 Orig 2")
        sm_a.flush()

        # Check final state on disk
        progress_file = os.path.join(temp_dir, "novel_merge_progress.json")
        with open(progress_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "chap1" in data["translated_items"], "chap1 missing from merged disk state"
        assert "chap2" in data["translated_items"], "chap2 missing from merged disk state"
        assert len(data["translated_items"]["chap1"]) == 3, "chap1 chunk count mismatch"
        assert len(data["translated_items"]["chap2"]) == 1, "chap2 chunk count mismatch"
        print("  -> Multi-instance merge PASS: Both instances merged non-destructively.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_state_manager_schema_validation_and_backup():
    print("[3/8] Testing StateManager schema validation and corrupted backup...")
    temp_dir = tempfile.mkdtemp()
    try:
        progress_file = os.path.join(temp_dir, "corrupt_test_progress.json")

        # Scenario 1: Malformed JSON syntax
        with open(progress_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json syntax !!!")

        sm1 = StateManager("corrupt_test", state_dir=temp_dir)
        assert sm1.get_completed_count() == 0
        # Check backup file exists
        backup_files = [f for f in os.listdir(temp_dir) if "corrupted_" in f]
        assert len(backup_files) == 1, f"Expected 1 corrupted backup file, found {backup_files}"

        time.sleep(1.1)
        # Scenario 2: Valid JSON but invalid schema (translated_items is not a dict)
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump({"book_identifier": "corrupt_test", "translated_items": ["not", "a", "dict"]}, f)

        sm2 = StateManager("corrupt_test", state_dir=temp_dir)
        assert sm2.get_completed_count() == 0
        backup_files = [f for f in os.listdir(temp_dir) if "corrupted_" in f]
        assert len(backup_files) == 2, f"Expected 2 corrupted backup files, found {backup_files}"

        print("  -> Schema validation & corrupted backup PASS: Handled gracefully and backed up.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_epub_parser_nested_divs_and_block_tags():
    print("[4/8] Testing EpubParser nested <div> extraction and BLOCK_TAGS...")
    temp_dir = tempfile.mkdtemp()
    try:
        # Check BLOCK_TAGS additions
        for tag in ["td", "th", "aside", "caption", "section"]:
            assert tag in BLOCK_TAGS, f"Expected {tag} in BLOCK_TAGS"

        # Build synthetic EPUB with nested divs, tables, aside, section
        book_path = os.path.join(temp_dir, "nested.epub")
        book = epub.EpubBook()
        book.set_identifier("epub_nested_test")
        book.set_title("Nested Test")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        html_content = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <div class="outer-container">
                <div class="middle-wrapper">
                    <div class="inner-leaf" id="leaf_div">
                        Direct leaf text inside nested div.
                    </div>
                </div>
            </div>
            <table>
                <caption>Tabel Ringkasan</caption>
                <tr><th>Header Kolom</th></tr>
                <tr><td>Data Sel</td></tr>
            </table>
            <aside>Catatan Samping Penulis</aside>
            <section><p>Paragraf dalam section</p></section>
        </body>
        </html>
        """
        ch = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
        ch.set_content(html_content.encode("utf-8"))
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(book_path, book, {})

        parser = EpubParser(book_path)
        nodes = parser.extract_text_nodes()

        extracted_texts = [n["text"] for n in nodes]
        extracted_tags = [n["tag"] for n in nodes]

        # Verify leaf div was extracted
        assert "Direct leaf text inside nested div." in extracted_texts
        # Verify outer containers were NOT extracted as separate nodes
        assert len([t for t in extracted_tags if t == "div"]) == 1, f"Expected exactly 1 leaf div, got {extracted_tags}"

        # Verify expanded BLOCK_TAGS extracted
        assert "caption" in extracted_tags
        assert "th" in extracted_tags
        assert "td" in extracted_tags
        assert "aside" in extracted_tags
        assert "p" in extracted_tags

        # Verify updating node preserves DOM tree structure (parent is not None)
        leaf_div_node = next(n["node"] for n in nodes if n["tag"] == "div")
        parser.update_node(leaf_div_node, "Teks terjemahan daun div.")
        assert leaf_div_node.parent is not None, "Leaf div node was unexpectedly detached from parent DOM!"
        assert "Teks terjemahan daun div." in str(leaf_div_node)

        print(f"  -> EpubParser nested div & BLOCK_TAGS PASS: Extracted tags: {extracted_tags}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_prompts_and_agentic_translator_glossary_forwarding():
    print("[5/8] Testing Glossary forwarding to reflect prompt...")
    glossary = {"Mana": "Tenaga Batin", "Dungeon": "Ruang Bawah Tanah"}
    reflect_prompt = get_reflect_prompt("English", "Indonesian", glossary)

    assert "GLOSARIUM ISTILAH" in reflect_prompt
    assert "Mana -> Tenaga Batin" in reflect_prompt
    assert "Dungeon -> Ruang Bawah Tanah" in reflect_prompt
    assert "Kepatuhan Glosarium" in reflect_prompt

    translator = AgenticTranslator(api_key="sk-test", glossary=glossary)
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf awal dengan Tenaga Batin."),
            MockResponse("Kritik: Diksi sudah baik."),
            MockResponse("Draf akhir dengan Tenaga Batin."),
        ]
        res = translator.translate_chunk("The dungeon was filled with Mana.")

        # Check call 1 (reflect) received glossary in system prompt
        reflect_call_sys = mock_comp.call_args_list[1].kwargs["messages"][0]["content"]
        assert "Tenaga Batin" in reflect_call_sys, "Glossary was not forwarded to reflection call!"
        assert "Ruang Bawah Tanah" in reflect_call_sys, "Glossary was not forwarded to reflection call!"
        print("  -> Glossary forwarding PASS: Verified in prompts and litellm reflection call.")


def test_robust_status_perfect_detection():
    print("[6/8] Testing robust [STATUS: PERFECT] parsing and negation filtering...")
    translator = AgenticTranslator(api_key="sk-test")

    # Case A: Positive exact line
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf sempurna."),
            MockResponse("[STATUS: PERFECT]\nTerjemahan luar biasa indah."),
        ]
        res = translator.translate_chunk("Test sentence.")
        assert res.fast_path is True
        assert mock_comp.call_count == 2
        print("    - Positive exact line: fast_path=True (2 calls)")

    # Case B: Positive line prefix
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf sempurna."),
            MockResponse("STATUS: PERFECT: Sangat memuaskan dan indah."),
        ]
        res = translator.translate_chunk("Test sentence.")
        assert res.fast_path is True
        assert mock_comp.call_count == 2
        print("    - Positive line prefix: fast_path=True (2 calls)")

    # Case C: Positive 'TIDAK ADA REVISI'
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf sempurna."),
            MockResponse("Draf ini sangat baik. TIDAK ADA REVISI yang diperlukan."),
        ]
        res = translator.translate_chunk("Test sentence.")
        assert res.fast_path is True
        assert mock_comp.call_count == 2
        print("    - Positive 'TIDAK ADA REVISI': fast_path=True (2 calls)")

    # Case D: NEGATIVE: 'BUKAN [STATUS: PERFECT]'
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf buruk."),
            MockResponse("Draf ini BUKAN [STATUS: PERFECT] karena tata bahasa masih kaku."),
            MockResponse("Draf revisi final."),
        ]
        res = translator.translate_chunk("Test sentence.")
        assert res.fast_path is False, "Negated STATUS: PERFECT incorrectly triggered fast_path!"
        assert mock_comp.call_count == 3
        print("    - Negated 'BUKAN [STATUS: PERFECT]': fast_path=False (3 calls)")

    # Case E: NEGATIVE: 'BELUM TIDAK ADA REVISI'
    with patch("core.agentic_translator.litellm.completion") as mock_comp:
        mock_comp.side_effect = [
            MockResponse("Draf buruk."),
            MockResponse("Draf ini belum tidak ada revisi, masih banyak yang harus diganti."),
            MockResponse("Draf revisi final."),
        ]
        res = translator.translate_chunk("Test sentence.")
        assert res.fast_path is False, "Negated 'belum tidak ada revisi' incorrectly triggered fast_path!"
        assert mock_comp.call_count == 3
        print("    - Negated 'belum tidak ada revisi': fast_path=False (3 calls)")

    print("  -> Robust fast-path parsing PASS: All negation and positive cases verified.")


def test_app_flush_in_finally():
    print("[7/8] Testing app.py execute_translation_loop try...finally state_manager.flush()...")
    import app
    temp_dir = tempfile.mkdtemp()
    try:
        # Build mini EPUB
        book_path = os.path.join(temp_dir, "test_app.epub")
        book = epub.EpubBook()
        book.set_identifier("app_test_book")
        book.set_title("App Test")
        book.set_language("en")
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        ch = epub.EpubHtml(title="Chap 1", file_name="c1.xhtml", lang="en")
        ch.set_content(b"<p>Paragraf 1</p><p>Paragraf 2</p><p>Paragraf 3</p>")
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(book_path, book, {})

        parser = EpubParser(book_path)
        sm = StateManager("app_test_book", total_chunks=3, state_dir=temp_dir, save_batch_size=10)

        # Mock translator that throws error on chunk 2
        call_count = [0]
        def mock_translate(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated API failure on chunk 2!")
            return TranslationResult("Terjemahan sukses", fast_path=True)

        mock_trans = MagicMock()
        mock_trans.translate_chunk.side_effect = mock_translate
        mock_trans.total_tokens_used = 100
        mock_trans.fast_path_count = 1

        mock_metric = MagicMock()
        mock_bar = MagicMock()
        mock_inspect = MagicMock()
        mock_term = MagicMock()

        with patch("streamlit.error") as mock_st_error:
            ret = app.execute_translation_loop(
                parser=parser,
                state_manager=sm,
                translator=mock_trans,
                source_lang="English",
                target_lang="Indonesian",
                glossary_dict={},
                metric_placeholder=mock_metric,
                progress_bar=mock_bar,
                inspection_placeholder=mock_inspect,
                terminal_placeholder=mock_term,
            )
            assert ret is None, "Expected pipeline to return None on error"
            assert mock_st_error.called, "st.error should have been called"

        # Check that state_manager flushed chunk 1 to disk even though pipeline failed on chunk 2!
        sm_check = StateManager("app_test_book", state_dir=temp_dir)
        completed = sm_check.get_completed_count()
        assert completed == 1, f"Expected 1 chunk flushed to disk via finally block, got {completed}"
        print("  -> app.py try...finally flush PASS: State was flushed to disk on simulated crash.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_app_test_boot_and_cliche_check():
    print("[8/8] Testing app.py AppTest clean boot and cliché removal...")
    from streamlit.testing.v1 import AppTest

    app_path = os.path.join(PROJECT_ROOT, "app.py")
    at = AppTest.from_file(app_path)
    at.run()
    assert not at.exception, f"AppTest raised unexpected exception: {at.exception}"

    with open(app_path, "r", encoding="utf-8") as f:
        app_source = f.read()

    assert "seamlessly" not in app_source.lower(), "Cliché 'seamlessly' found in app.py!"
    assert "seamless" not in app_source.lower(), "Cliché 'seamless' found in app.py!"
    print("  -> AppTest clean boot and zero clichés PASS.")


if __name__ == "__main__":
    test_state_manager_concurrency()
    test_state_manager_multi_instance_merge()
    test_state_manager_schema_validation_and_backup()
    test_epub_parser_nested_divs_and_block_tags()
    test_prompts_and_agentic_translator_glossary_forwarding()
    test_robust_status_perfect_detection()
    test_app_flush_in_finally()
    test_app_test_boot_and_cliche_check()
    print("\n==================================================")
    print("ALL 8 FORENSIC REMEDIATION INTEGRITY TESTS PASSED!")
    print("==================================================")
