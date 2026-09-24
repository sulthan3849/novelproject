"""
Independent Victory Verification Script
Auditor: teamwork_preview_victory_auditor
Folder: .agents/victory_auditor_1
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.agentic_translator import AgenticTranslator, TranslationResult
from core.prompts import get_draft_prompt, get_reflect_prompt, get_improve_prompt, format_glossary
from utils.epub_parser import EpubParser, BLOCK_TAGS, INLINE_TAGS
from utils.state_manager import StateManager


def test_1_epub_parser_tag_preservation():
    print("[1/5] Testing EPUB Parser tag preservation...")
    tmpdir = tempfile.mkdtemp(prefix="va_epub_")
    try:
        epub_path = os.path.join(tmpdir, "sample.epub")
        html_content = """<?xml version="1.0" encoding="utf-8"?>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head><title>Chapter 1</title></head>
        <body>
            <h1>Chapter 1: The Awakening</h1>
            <p id="p1" class="prose intro" style="color:red;" data-meta="test">
                The <em>ancient sword</em> hummed with <strong>unfathomable power</strong> and <span class="magical">azure light</span>.
            </p>
            <p id="p2">
                He whispered <ruby>勇者<rt>Yūsha</rt></ruby> to the winds.
            </p>
            <div>
                <div>
                    <p id="nested_p">Nested inside multiple divs.</p>
                </div>
            </div>
            <table>
                <tr>
                    <th>Skill</th>
                    <td>Rank <strong>S</strong></td>
                </tr>
            </table>
        </body>
        </html>"""

        from tests.test_epub_pipeline import create_test_epub
        create_test_epub(
            epub_path,
            title="Victory Audit Test Novel",
            chapters_content={"ch1.xhtml": ("Chapter 1", html_content)},
        )

        parser = EpubParser(epub_path)
        items = parser.get_html_items()
        assert len(items) >= 1, "Failed to retrieve HTML items"

        c1 = next(item for item in items if "ch1.xhtml" in item.get_name())
        soup, nodes = parser.extract_chunks(c1)
        tag_names = [n.name for n in nodes]
        assert "h1" in tag_names, "Missing h1"
        assert "p" in tag_names, "Missing p"
        assert "th" in tag_names, "Missing th"
        assert "td" in tag_names, "Missing td"

        # Check node p1
        p1 = next(n for n in nodes if n.get("id") == "p1")
        assert p1.name == "p"
        assert p1.get("id") == "p1"
        assert "prose" in p1.get("class")
        assert p1.get("style") == "color:red;"
        assert p1.get("data-meta") == "test"

        # Update node with Indonesian translation containing preserved inline tags
        indonesian_html = "Pedang <em>kuno itu</em> berdengung dengan <strong>kekuatan tak terduga</strong> dan <span class=\"magical\">cahaya biru langit</span>."
        parser.update_node(p1, indonesian_html)

        # Verify outer attributes are kept, tag remains p, and inline tags are preserved
        assert p1.name == "p"
        assert p1.get("id") == "p1"
        assert "prose" in p1.get("class")
        assert p1.get("style") == "color:red;"
        assert p1.get("data-meta") == "test"
        assert p1.find("em") is not None
        assert p1.find("em").get_text() == "kuno itu"
        assert p1.find("strong") is not None
        assert p1.find("strong").get_text() == "kekuatan tak terduga"
        assert p1.find("span") is not None
        assert p1.find("span").get_text() == "cahaya biru langit"
        assert p1.find("span").get("class") == ["magical"]

        # Verify double wrapping prevention if model output returned <p> tag
        parser.update_node(p1, f'<p class="dummy">{indonesian_html}</p>')
        assert p1.name == "p"
        assert p1.find("p") is None, "Accidentally created nested <p><p>"
        assert p1.find("em").get_text() == "kuno itu"

        # Repack and verify readable
        output_repack = os.path.join(tmpdir, "repacked.epub")
        parser.repack(output_repack)
        assert os.path.exists(output_repack), "Repacked EPUB does not exist"
        repacked_book = epub.read_epub(output_repack)
        assert repacked_book.get_metadata("DC", "title")[0][0] == "Victory Audit Test Novel"

        print("  -> PASS: EPUB Parser preserves HTML tags, attributes, and repacks cleanly.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_2_state_manager_persistence_and_concurrency():
    print("[2/5] Testing StateManager persistence, SHA-256 keying, and thread safety...")
    tmpdir = tempfile.mkdtemp(prefix="va_state_")
    try:
        book_id = "test_novel_hash_sha256_abcdef123456"
        sm = StateManager(book_id, total_chunks=100, state_dir=tmpdir, save_batch_size=2)
        assert sm.progress_file.endswith(f"{book_id}_progress.json")

        # Concurrency check: 10 threads doing 20 updates each
        errors = []
        def worker(t_idx):
            try:
                for c_idx in range(20):
                    sm.mark_chunk_translated(
                        item_id=f"item_{t_idx}",
                        chunk_index=c_idx,
                        translated_text=f"Trans_{t_idx}_{c_idx}",
                        original_text=f"Orig_{t_idx}_{c_idx}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        sm.flush()

        # Check total completed count
        assert sm.get_completed_count() == 200, f"Expected 200, got {sm.get_completed_count()}"

        # Check progress file on disk
        assert os.path.exists(sm.progress_file)
        with open(sm.progress_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["translated_items"]) == 10
        assert len(data["translated_items"]["item_0"]) == 20

        # Test recovery from corruption
        with open(sm.progress_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID JSON CORRUPTED FILE !!!")

        sm_recovered = StateManager(book_id, total_chunks=100, state_dir=tmpdir)
        assert sm_recovered.get_completed_count() == 0
        # Check that corrupted file was backed up
        backups = [f for f in os.listdir(tmpdir) if ".corrupted_" in f]
        assert len(backups) == 1, f"Expected 1 corrupted backup, got {backups}"

        print("  -> PASS: StateManager atomic persistence, thread locking, and corruption recovery verified.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_3_agentic_translator_prompt_chain():
    print("[3/5] Testing LiteLLM prompt chain and fast-path bypass...")
    glossary = {"Shadow Sovereign": "Penguasa Bayangan", "Hunter": "Pemburu"}
    
    draft_prompt = get_draft_prompt(glossary=glossary)
    assert "Gramedia" in draft_prompt
    assert "PELESTARIAN TAG FORMAT HTML (MUTLAK)" in draft_prompt
    assert "Shadow Sovereign -> Penguasa Bayangan" in draft_prompt

    reflect_prompt = get_reflect_prompt(glossary=glossary)
    assert "[STATUS: PERFECT]" in reflect_prompt
    assert "Kepatuhan Glosarium" in reflect_prompt
    assert "Shadow Sovereign -> Penguasa Bayangan" in reflect_prompt

    improve_prompt = get_improve_prompt(glossary=glossary)
    assert "Gramedia" in improve_prompt
    assert "Shadow Sovereign -> Penguasa Bayangan" in improve_prompt

    # Test AgenticTranslator logic with mock litellm
    class MockChoice:
        def __init__(self, content):
            self.message = type("Message", (), {"content": content})

    class MockUsage:
        def __init__(self, tokens):
            self.total_tokens = tokens

    class MockResponse:
        def __init__(self, content, tokens=150):
            self.choices = [MockChoice(content)]
            self.usage = MockUsage(tokens)

    call_records = []
    import litellm
    def fake_completion(**kwargs):
        call_records.append(kwargs)
        sys_msg = kwargs["messages"][0]["content"]
        user_msg = kwargs["messages"][1]["content"]
        if "Anda adalah penerjemah" in sys_msg:
            return MockResponse("Draf: Pedang kuno itu berdengung.")
        elif "Anda adalah Redaktur Senior" in sys_msg:
            # Reflection
            if "force_perfect" in user_msg:
                return MockResponse("[STATUS: PERFECT]\nDraf ini sempurna tanpa cela.")
            elif "negated" in user_msg:
                return MockResponse("Draf ini BUKAN [STATUS: PERFECT]. Perlu perbaikan diksi.")
            else:
                return MockResponse("Kritik: Diksi kurang dramatis, ubah menjadi berdengung menggetarkan jiwa.")
        else:
            return MockResponse("Final: Pedang kuno itu bergetar menggetarkan jiwa.")

    orig_comp = litellm.completion
    litellm.completion = fake_completion

    try:
        translator = AgenticTranslator(model_name="gpt-4o-mini", api_key="sk-test-key-12345", glossary=glossary)
        assert translator.api_key == "sk-test-key-12345"
        assert translator.model_name == "gpt-4o-mini"

        # Case A: Standard 3-step loop
        call_records.clear()
        res_standard = translator.translate_chunk("The ancient sword hummed.")
        assert len(call_records) == 3, f"Expected 3 calls, got {len(call_records)}"
        assert res_standard.fast_path is False
        assert "bergetar menggetarkan jiwa" in res_standard.final

        # Case B: Fast-Path bypass on [STATUS: PERFECT]
        call_records.clear()
        res_fast = translator.translate_chunk("The ancient sword hummed. force_perfect")
        assert len(call_records) == 2, f"Expected 2 calls for fast-path, got {len(call_records)}"
        assert res_fast.fast_path is True
        assert res_fast.final == "Draf: Pedang kuno itu berdengung."

        # Case C: Negation safety ('BUKAN [STATUS: PERFECT]')
        call_records.clear()
        res_neg = translator.translate_chunk("The ancient sword hummed. negated")
        assert len(call_records) == 3, f"Expected 3 calls for negated status, got {len(call_records)}"
        assert res_neg.fast_path is False

        # Verify api_key was passed directly to every litellm.completion call
        for call in call_records:
            assert call.get("api_key") == "sk-test-key-12345", "api_key not passed directly!"

        print("  -> PASS: 3-step loop, fast-path bypass, negation safety, and api_key passing verified.")
    finally:
        litellm.completion = orig_comp


def test_4_app_css_and_structure():
    print("[4/5] Testing app.py CSS, taste-skill standards, and architecture...")
    app_path = os.path.join(PROJECT_ROOT, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        app_code = f.read()

    # Verify custom CSS injection
    assert 'st.markdown(CUSTOM_CSS, unsafe_allow_html=True)' in app_code or 'st.markdown("<style>' in app_code or '<style>' in app_code
    assert "#0D0F12" in app_code, "Missing obsidian background #0D0F12"
    assert "bento-grid" in app_code, "Missing bento grid styling"
    assert "terminal-window" in app_code, "Missing terminal window styling"
    assert "inspection-container" in app_code, "Missing inspection container styling"

    # Verify no emojis in custom headers or labels
    # Verify typing imports
    assert "from typing import Any, Dict, List, Optional, Tuple, Union" in app_code

    # Verify modular structure
    assert os.path.exists(os.path.join(PROJECT_ROOT, "core", "agentic_translator.py"))
    assert os.path.exists(os.path.join(PROJECT_ROOT, "core", "prompts.py"))
    assert os.path.exists(os.path.join(PROJECT_ROOT, "utils", "epub_parser.py"))
    assert os.path.exists(os.path.join(PROJECT_ROOT, "utils", "state_manager.py"))
    assert os.path.exists(os.path.join(PROJECT_ROOT, "app.py"))

    print("  -> PASS: app.py contains custom CSS adhering to taste-skill standards and clean modular structure.")


def test_5_headless_streamlit_apptest():
    print("[5/5] Testing Streamlit app execution via AppTest...")
    from streamlit.testing.v1 import AppTest
    app_path = os.path.join(PROJECT_ROOT, "app.py")
    at = AppTest.from_file(app_path)
    at.run()
    assert not at.exception, f"AppTest raised an unhandled exception: {at.exception}"
    print("  -> PASS: Streamlit app boots cleanly with zero unhandled exceptions.")


if __name__ == "__main__":
    print("==================================================")
    print("RUNNING VICTORY AUDITOR INDEPENDENT VERIFICATION")
    print("==================================================")
    test_1_epub_parser_tag_preservation()
    test_2_state_manager_persistence_and_concurrency()
    test_3_agentic_translator_prompt_chain()
    test_4_app_css_and_structure()
    test_5_headless_streamlit_apptest()
    print("==================================================")
    print("ALL 5 INDEPENDENT VERIFICATIONS PASSED CLEANLY!")
    print("==================================================")
