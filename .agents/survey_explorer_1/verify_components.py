import os
import sys
import tempfile
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from utils.state_manager import StateManager
from core.prompts import get_draft_prompt, get_reflect_prompt, get_improve_prompt
from core.agentic_translator import AgenticTranslator

print("=== 1. VERIFYING STATE MANAGER ===")
sm = StateManager("test_novel_survey")
print("Progress file path:", sm.progress_file)
sm.mark_chunk_translated("item_001", 0, "Halo dunia")
print("is_chunk_translated('item_001', 0):", sm.is_chunk_translated("item_001", 0))
print("get_translated_chunk('item_001', 0):", sm.get_translated_chunk("item_001", 0))
if os.path.exists(sm.progress_file):
    os.remove(sm.progress_file)
    print("State file cleaned up successfully.")

print("\n=== 2. VERIFYING PROMPTS ===")
draft_p = get_draft_prompt("Inggris", "Indonesia", "Guild -> Serikat")
print("Draft prompt length:", len(draft_p))
print("Draft prompt contains '{text}':", "{text}" in draft_p)
reflect_p = get_reflect_prompt("Inggris", "Indonesia")
formatted_reflect = reflect_p.format(source_text="Hello", draft_text="Halo")
print("Formatted reflect length:", len(formatted_reflect))
improve_p = get_improve_prompt("Inggris", "Indonesia")
formatted_improve = improve_p.format(source_text="Hello", draft_text="Halo", reflection_text="Bagus")
print("Formatted improve length:", len(formatted_improve))

print("\n=== 3. VERIFYING EPUB PARSER HTML LOGIC ===")
html_sample = """<html>
<body>
  <h1>Chapter 1: The Beginning</h1>
  <p class="calibre1">This is a normal paragraph with standard text.</p>
  <p class="calibre2">This paragraph has <em>inline emphasis</em> and <b>bold</b> words.</p>
  <p class="calibre3">This paragraph has a <span class="styled">styled span</span> inside it.</p>
</body>
</html>"""

soup = BeautifulSoup(html_sample, "html.parser")
target_tags = ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
nodes = []
for tag in soup.find_all(target_tags):
    text = tag.get_text(strip=True)
    if text and len(text) > 1:
        has_block_child = any(child.name in target_tags for child in tag.children if child.name)
        if not has_block_child:
            nodes.append(tag)

print(f"Extracted {len(nodes)} nodes:")
for idx, node in enumerate(nodes):
    print(f"  [{idx}] <{node.name}>: '{node.get_text(strip=True)}'")

print("\n=== 4. VERIFYING REPLACEMENT IN BEAUTIFUL SOUP ===")
# Simulating node.string = translated_text on calibre2 (with <em> and <b>)
node_em_b = [n for n in nodes if "inline emphasis" in n.get_text()][0]
print("Before replacement:", str(node_em_b))
node_em_b.string = "Paragraf ini memiliki penekanan dan kata tebal."
print("After replacement:", str(node_em_b))
# Check if <em> or <b> survived
has_em = "<em" in str(node_em_b)
print("Did <em> survive node.string replacement?:", has_em)

print("\n=== 5. CHECKING MISSING TEXT IN SPAN CASE ===")
# Check calibre3
p_with_span = soup.find("p", class_="calibre3")
print("Whole p.calibre3 text:", repr(p_with_span.get_text(strip=True)))
extracted_from_p_span = [n.get_text(strip=True) for n in nodes if n in p_with_span.descendants or n == p_with_span]
print("What got extracted from p.calibre3:", extracted_from_p_span)

print("\n=== 6. VERIFYING AGENTIC TRANSLATOR INITIALIZATION ===")
translator = AgenticTranslator(api_key="test_dummy_key", model_name="gemini/gemini-1.5-pro-latest")
print("AgenticTranslator initialized. Model:", translator.model_name)
