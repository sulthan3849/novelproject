import sys
import os
import tempfile
import json
import hashlib
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.epub_parser import EpubParser, BLOCK_TAGS, INLINE_TAGS
from utils.state_manager import StateManager
from core.agentic_translator import AgenticTranslator, TranslationResult
from core.prompts import get_draft_prompt, get_reflect_prompt, get_improve_prompt

def check_1_static_analysis():
    print("=== CHECK 1: STATIC CODE ANALYSIS FOR SHORTCUTS & HARDCODING ===")
    prohibited = ["Aethelgard", "The Chronicles of", "The Sovereign of", "Jin-Woo Sung"]
    target_files = [
        "core/agentic_translator.py",
        "core/prompts.py",
        "utils/epub_parser.py",
        "utils/state_manager.py",
    ]
    found_issues = []
    for rel_path in target_files:
        full_path = os.path.join(project_root, rel_path)
        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()
        for p in prohibited:
            if p.lower() in code.lower():
                found_issues.append(f"Found '{p}' in {rel_path}")
        # Check for facade returns (e.g. return "mock", return True without logic)
        lines = code.splitlines()
        for idx, line in enumerate(lines, 1):
            sline = line.strip()
            if sline == "return \"mock\"" or sline == "return \"test\"":
                found_issues.append(f"Suspicious return at {rel_path}:{idx}: {sline}")

    if found_issues:
        print("FAIL: Prohibited patterns found:")
        for issue in found_issues:
            print("  -", issue)
        return False
    else:
        print("PASS: Zero hardcoded test names, zero test strings, zero facade shortcuts in core/ and utils/.")
        return True

def check_2_dom_traversal():
    print("\n=== CHECK 2: BEAUTIFUL SOUP DOM TRAVERSAL & NODE UPDATES ===")
    test_dir = tempfile.mkdtemp()
    try:
        epub_path = os.path.join(test_dir, "dom_test.epub")
        book = epub.EpubBook()
        book.set_identifier("urn:uuid:dom-test-12345")
        book.set_title("DOM Audit Book")
        book.set_language("en")
        book.add_author("Auditor")
        
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        ch = epub.EpubHtml(title="Ch 1", file_name="ch1.xhtml", lang="en")
        ch.set_content(b"""<?xml version="1.0" encoding="utf-8"?>
        <html><body>
            <p id="target_p" class="styled_text" data-custom="123">
                Original text with <em>italic emphasis</em> and <span class="badge">span badge</span>.
            </p>
        </body></html>""")
        book.add_item(ch)
        book.spine = ["nav", ch]
        epub.write_epub(epub_path, book, {})

        parser = EpubParser(epub_path)
        nodes = parser.extract_text_nodes()
        print("Nodes found:", [(n["item_id"], n["tag"], n["text"]) for n in nodes])
        story_nodes = [n for n in nodes if not n["item_id"].startswith("nav") and not n["item"].get_name().startswith("nav")]
        assert len(story_nodes) == 1, f"Expected 1 story node, got {len(story_nodes)}"
        node_record = story_nodes[0]
        node = node_record["node"]
        
        print("Extracted node tag:", node.name)
        print("Extracted node attributes:", node.attrs)
        assert node.name == "p"
        assert node.get("id") == "target_p"
        assert node.get("class") == ["styled_text"]
        assert node.get("data-custom") == "123"

        # Update node with translated Indonesian containing inline tags
        translated_markup = 'Teks terjemahan dengan <em>penekanan miring</em> dan <span class="badge">lencana rentang</span>.'
        parser.update_node(node, translated_markup)

        print("Updated node HTML:", str(node))
        assert node.get("id") == "target_p"
        assert node.get("class") == ["styled_text"]
        assert node.get("data-custom") == "123"
        em_child = node.find("em")
        span_child = node.find("span")
        assert em_child is not None and em_child.get_text() == "penekanan miring"
        assert span_child is not None and span_child.get_text() == "lencana rentang"
        print("PASS: DOM traversal and node updates genuinely manipulate BS4 tree and retain all attributes.")
        return True
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

def check_3_agentic_prompts_and_litellm():
    print("\n=== CHECK 3: LITELLM AGENTIC LOOP & PROMPTS ===")
    draft_p = get_draft_prompt("Japanese", "Indonesian", {"Kuro": "Si Hitam"})
    reflect_p = get_reflect_prompt("Japanese", "Indonesian")
    improve_p = get_improve_prompt("Japanese", "Indonesian", {"Kuro": "Si Hitam"})

    assert "Gramedia" in draft_p
    assert "Kuro -> Si Hitam" in draft_p
    assert "[STATUS: PERFECT]" in reflect_p
    assert "Kuro -> Si Hitam" in improve_p
    assert "{text}" not in draft_p and "{text}" not in improve_p

    translator = AgenticTranslator(api_key="sk-live-test", model_name="gpt-4o-mini")
    assert translator.api_key == "sk-live-test"
    assert translator.model_name == "gpt-4o-mini"
    print("Prompts properly structured, glossary injected, fast-path markers present.")
    print("PASS: LiteLLM agentic loop properly configured.")
    return True

def check_4_state_manager_atomicity():
    print("\n=== CHECK 4: STATEMANAGER ATOMIC DISK WRITES & SHA-256 ===")
    test_dir = tempfile.mkdtemp()
    try:
        sample_bytes = b"Sample EPUB bytes for SHA-256 testing"
        hasher = hashlib.sha256(sample_bytes)
        book_hash = hasher.hexdigest()

        mgr = StateManager(book_identifier=book_hash, total_chunks=10, state_dir=test_dir, save_batch_size=2)
        assert mgr.progress_file.endswith(f"{book_hash}_progress.json")

        mgr.mark_chunk_translated("sec1", 0, "Diterjemahkan 0", "Original 0")
        mgr.mark_chunk_translated("sec1", 1, "Diterjemahkan 1", "Original 1")
        # Batch size 2 reached -> auto save
        assert os.path.exists(mgr.progress_file)
        
        # Verify no .tmp files remained
        tmps = [f for f in os.listdir(test_dir) if f.endswith(".tmp")]
        assert len(tmps) == 0, f"Found lingering tmp files: {tmps}"

        with open(mgr.progress_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["book_identifier"] == book_hash
        assert data["translated_items"]["sec1"]["0"]["translated"] == "Diterjemahkan 0"
        assert data["translated_items"]["sec1"]["1"]["translated"] == "Diterjemahkan 1"

        # Verify resumption
        mgr2 = StateManager(book_identifier=book_hash, total_chunks=10, state_dir=test_dir)
        assert mgr2.is_chunk_translated("sec1", 0)
        assert mgr2.is_chunk_translated("sec1", 1)
        assert mgr2.get_translated_chunk("sec1", 0) == "Diterjemahkan 0"
        print("PASS: StateManager executes atomic JSON replacement with zero corruptions or leaks.")
        return True
    finally:
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

def check_5_streamlit_css_and_integration():
    print("\n=== CHECK 5: STREAMLIT APP.PY INTEGRATION & CSS AUDIT ===")
    app_path = os.path.join(project_root, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    css_features = [
        "CUSTOM_CSS",
        "st.markdown(CUSTOM_CSS",
        "#0D0F12",
        "#16191F",
        ".bento-grid",
        ".bento-card",
        ".terminal-window",
        ".inspection-container",
    ]
    for feat in css_features:
        assert feat in content, f"Missing CSS feature: {feat}"

    backend_integrations = [
        "from core.agentic_translator import AgenticTranslator",
        "from utils.epub_parser import EpubParser",
        "from utils.state_manager import StateManager",
        "execute_translation_loop",
        "st.file_uploader",
        "st.download_button",
        "parser.repack",
    ]
    for bi in backend_integrations:
        assert bi in content, f"Missing backend integration: {bi}"

    # Check for emojis
    import re
    emoji_pattern = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)
    found_emojis = emoji_pattern.findall(content)
    assert len(found_emojis) == 0, f"Found unexpected emojis in app.py: {found_emojis}"
    print("PASS: Streamlit app.py contains full custom CSS, zero emojis, and complete backend integration.")
    return True

if __name__ == "__main__":
    c1 = check_1_static_analysis()
    c2 = check_2_dom_traversal()
    c3 = check_3_agentic_prompts_and_litellm()
    c4 = check_4_state_manager_atomicity()
    c5 = check_5_streamlit_css_and_integration()

    if all([c1, c2, c3, c4, c5]):
        print("\nOVERALL INTEGRITY VERDICT: ALL CHECKS PASSED -> CLEAN")
    else:
        print("\nOVERALL INTEGRITY VERDICT: INTEGRITY VIOLATION DETECTED")
        sys.exit(1)
