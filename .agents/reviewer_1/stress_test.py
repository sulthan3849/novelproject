import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from bs4 import BeautifulSoup
from utils.epub_parser import EpubParser
from utils.state_manager import StateManager
from core.agentic_translator import AgenticTranslator, TranslationResult
from core.prompts import format_glossary, get_draft_prompt, get_reflect_prompt, get_improve_prompt

print("--- STRESS TEST 1: update_node with various HTML and entities ---")
parser = EpubParser.__new__(EpubParser)
soup = BeautifulSoup('<p class="lead" id="p1">Original</p>', 'html.parser')
p = soup.find('p')
parser.update_node(p, '<b>Bold</b> & <i>Italic</i> &amp; &lt;special&gt; < unclosed')
print("Result soup:", str(soup))

print("\n--- STRESS TEST 2: Nested divs without standard block tags ---")
soup_nested = BeautifulSoup('<div><div><span>Leaf text</span></div></div>', 'html.parser')
class MockItem:
    def get_content(self):
        return str(soup_nested).encode('utf-8')
    def get_id(self):
        return 'item1'

parser._item_soups = {}
_, nodes = parser.extract_chunks(MockItem())
print(f"Nodes found: {len(nodes)} (names: {[n.name for n in nodes]})")

print("\n--- STRESS TEST 3: StateManager edge cases ---")
import tempfile
temp_dir = tempfile.mkdtemp()
sm = StateManager(book_identifier="stress_test_book", total_chunks=10, state_dir=temp_dir, save_batch_size=5)

# Test 3a: Non-string chunk keys
sm.mark_chunk_translated(123, 456, "Translated 123:456")
print("is_chunk_translated(123, 456):", sm.is_chunk_translated(123, 456))
print("is_chunk_translated('123:456'):", sm.is_chunk_translated("123:456"))
print("get_translated_text('123:456'):", sm.get_translated_text("123:456"))

# Test 3b: Dirty flag when total_chunks is updated
sm2 = StateManager(book_identifier="stress_test_book", total_chunks=20, state_dir=temp_dir)
print("Updated total_chunks:", sm2.state["total_chunks"])

print("\n--- STRESS TEST 4: AgenticTranslator fast path variations ---")
fast_markers = [
    "[STATUS: PERFECT]",
    "STATUS: PERFECT",
    "status: perfect",  # lowercase
    "Tidak Ada Revisi",
    "TIDAK ADA REVISI",
    "Catatan: tidak ada revisi diperlukan",
]
for marker in fast_markers:
    is_fp = (
        "[STATUS: PERFECT]" in marker
        or "STATUS: PERFECT" in marker
        or "TIDAK ADA REVISI" in marker.upper()
    )
    print(f"Marker '{marker}': fast_path={is_fp}")

print("\n--- STRESS TEST 5: TranslationResult mutability check ---")
tr = TranslationResult(final="final text", draft="draft text", reflection="ref", tokens_used=100, fast_path=True)
print("tr.final before:", tr.final)
tr['final'] = "modified text"
print("tr.final after dict mutation:", tr.final)

print("\nALL STRESS TESTS FINISHED")
