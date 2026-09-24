# Technical Architecture & System Specification: Agentic Novel Translator

**Author:** Architecture & Technical Solution Specialist (`survey_explorer_2`)  
**Target:** Local Web App for 500+ Page EPUB Translation to Indonesian  
**Date:** 2026-09-21  
**Integrity Mode:** Development (Read-Only Investigation & Architecture Design)

---

## 1. Executive Summary & Architectural Blueprint

The **Agentic Novel Translator** is designed to solve the critical challenges of long-form literary translation (500+ page EPUBs) into natural, publication-grade Indonesian. Existing automated pipelines suffer from three fundamental failures:
1. **Structural Destruction:** Naive HTML stripping or tag replacement destroys book formatting, CSS styling, italics, dialogue tags, and chapter layouts.
2. **Literal & Wooden Prose:** Single-shot LLM prompts produce machine-translated syntax ("Indo-Inggris" or stiff grammatical calques) that fail to capture literary tone and character voice.
3. **Fragility & Resource Exhaustion:** Translating thousands of individual paragraphs generates massive API overhead, hits rate limits, loses narrative context, and fails when interrupted.

To address these challenges, the system employs a **Decoupled 4-Tier Architecture**:

```
 ┌──────────────────────────────────────────────────────────────┐
 │                      Streamlit UI (app.py)                   │
 │  - Minimalist Editorial Design System (Taste-Skill CSS)      │
 │  - Bento-Grid Telemetry (ETA, Chunks, Tokens, Cost)          │
 │  - Live Inspection Split-Pane & Monospace Terminal           │
 └──────────────┬───────────────────────────────┬───────────────┘
                │                               │
                ▼                               ▼
 ┌──────────────────────────────┐ ┌─────────────────────────────┐
 │  utils/epub_parser.py        │ │  utils/state_manager.py     │
 │  - ebooklib Document Spine   │ │  - Atomic JSON Persistence  │
 │  - BS4 AST Text Extraction   │ │  - Content-Addressable Hash │
 │  - Inline Tag Preservation   │ │  - Resumable Chunk Tracking │
 │  - Adaptive Batch Chunking   │ │  - Progress & Stats Agg     │
 │  - Style-Preserved Repacking │ └──────────────▲──────────────┘
 └──────────────┬───────────────┘                │
                │ Chunks                         │ State Cache
                ▼                                │
 ┌───────────────────────────────────────────────┴──────────────┐
 │             core/agentic_translator.py (LiteLLM)             │
 │  - Step 1: Literary Drafting (Gaya Sastra Gramedia)          │
 │  - Step 2: Ruthless Reflection & Proofreading                │
 │  - Fast-Path Bypass ([STATUS: PERFECT] -> Skip Step 3)       │
 │  - Step 3: Master Polishing & Rewrite                        │
 │  - Glossary Normalization & Enforcement                      │
 │  - Exponential Jitter Backoff & Multi-Provider Handling      │
 └──────────────────────────────────────────────────────────────┘
```

---

## 2. EPUB Pipeline Architecture (`utils/epub_parser.py`)

### 2.1 EPUB Internal Anatomy & `ebooklib` Mechanics
An EPUB is a zipped archive compliant with Open Container Format (OCF) containing:
- `mimetype` and `META-INF/container.xml`
- The Package Document (`.opf`): Manifest, Spine, Guide, Metadata
- XHTML content documents (`ebooklib.ITEM_DOCUMENT`): Chapter files containing styled HTML markup.
- Style sheets (`ebooklib.ITEM_STYLE`): CSS files controlling layout, margins, typography.
- Images (`ebooklib.ITEM_IMAGE`), Fonts (`ebooklib.ITEM_FONT`), and Navigation (`ITEM_NAVIGATION`).

`ebooklib.epub.read_epub` loads these into memory. When modifying items, we must preserve:
1. Manifest order and spine identifiers (`item.get_id()`).
2. CSS references in the `<head>` of each XHTML document (`<link rel="stylesheet" ... />`).
3. Internal anchors (`id="chapter-1"`, `<a href="#footnote-1">`).

### 2.2 BeautifulSoup4 Text Identification & The "Parent-Child Trapping" Bug
In the existing prototype (`utils/epub_parser.py:31-39`), the extraction logic contains a fatal flaw:
```python
target_tags = ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
# Checking if any child is in target_tags
has_block_child = any(child.name in target_tags for child in tag.children if child.name)
if not has_block_child:
    nodes.append(tag)
```
**Why this breaks EPUBs:**
- If a `<p>` tag contains an italicized word wrapped in `<span class="italic">` or `<em>`:
  - The child is `span` (which is in `target_tags`).
  - `has_block_child` evaluates to `True`.
  - The `<p>` tag is **ignored**! Only the `<span>` is added to `nodes`.
  - The rest of the sentence outside the `<span>` is **completely lost and un-translated**!
- Furthermore, in `app.py:60`:
  `node.string = translated_text`
  In BeautifulSoup, assigning to `.string` **destroys all children**! If `<p>She looked at <em>him</em>.</p>` is translated and assigned to `node.string`, the `<em>` tag is annihilated.

#### Correct Architectural Solution: Block vs. Inline Separation
HTML elements must be strictly classified into two categories:

| Category | HTML Tags | Architectural Handling |
|---|---|---|
| **Block Containers** | `p`, `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `blockquote`, `li`, `dt`, `dd`, `caption` | **Translation Units**. Attributes (`class`, `id`, `style`) are strictly preserved. Inner contents are extracted, translated, and re-injected. |
| **Inline Formatting** | `em`, `strong`, `i`, `b`, `span`, `a`, `small`, `sub`, `sup`, `ruby`, `rt`, `rp`, `code` | **Preserved Markup**. Must remain intact *inside* the translation unit. Sent to LLM with instructions to preserve syntactic placement. |
| **Structural Layout** | `div`, `section`, `article`, `main`, `aside` | **Walk-Through Only**. Traversed recursively. Only treated as a translation unit if it contains raw text and zero block descendants. |

### 2.3 Tag & Attribute Preservation Algorithm
To translate a block container while preserving all CSS attributes and inline tags:
1. **Outer Tag Preservation:** Do NOT replace the block tag itself. Preserve its `tag.name`, `class`, `id`, and inline `style`.
2. **Inner HTML Extraction:** Extract inner HTML:
   ```python
   inner_html = "".join(str(child) for child in block_node.contents).strip()
   ```
3. **Re-injection via DOM Replacement:**
   When the translated inner HTML is received:
   ```python
   # Parse translated inner content with BeautifulSoup
   replacement_soup = BeautifulSoup(translated_inner_html, "html.parser")
   # Clear previous children without touching outer tag attributes
   block_node.clear()
   # Append parsed new children
   block_node.extend(replacement_soup.contents)
   ```
This guarantees:
- `<p class="calibre2" id="para_102">` retains its exact `class` and `id`.
- Inline tags like `<em>kata</em>` or `<span class="dialogue">...</span>` are restored cleanly inside the DOM.

### 2.4 Batched Chunking for 500+ Page EPUBs
A 500-page novel contains ~6,000 to 10,000 paragraphs. Translating paragraph-by-paragraph:
- Requires **18,000 to 30,000 LLM calls** (under a 3-step loop).
- Saturated API rate limits (RPM/TPM), 10+ hours processing time.
- Context blindness: Dialogue and pronouns (especially in Japanese/Korean where subjects are omitted) become incoherent.

**Adaptive Batch Chunking Specification:**
- Consecutive block nodes within each chapter document are grouped into a `Chunk`.
- **Target Size:** 1,000 to 1,500 words (~1,500 to 2,500 tokens), corresponding to 15–30 paragraphs.
- **Delimiter Format:**
  Nodes in the chunk are formatted using indexed boundary markers:
  ```html
  <chunk>
  <p id="0">"Where are you going?" she asked, her voice trembling.</p>
  <p id="1">He stopped at the doorway, looking back with an <em>empty</em> expression.</p>
  </chunk>
  ```
- **Parsing the Response:** The translation engine parses `<p id="0">...</p>` and `<p id="1">...</p>` from the LLM output and maps them back to the original DOM nodes.
- **Fallback Guarantee:** If the LLM omits an ID or merges paragraphs, the parser detects the count mismatch and automatically subdivides the chunk or falls back to node-by-node for that segment.
- **Efficiency Gain:** Reduces API calls by **~93%** (from 24,000 calls down to ~1,200 calls) and drastically improves literary consistency.

### 2.5 Clean EPUB Repacking
After all items are translated:
1. Update metadata: `book.set_identifier(...)`, update `dc:language` to `'id'`, append translator attribution to `dc:description`.
2. Ensure valid XHTML serialization:
   ```python
   # Encode with proper UTF-8 and XML header preservation
   item.set_content(soup.encode(formatter="html5"))
   ```
3. Repack via `ebooklib.epub.write_epub(output_path, book, {})`.

---

## 3. State Management & Resumability (`utils/state_manager.py`)

In a 500+ page EPUB pipeline, interruptions (network drop, API timeout, machine restart, user pause) are inevitable.

### 3.1 Content-Addressable Chunk State Schema
The state is stored in a structured JSON file `.progress_{book_name}.json`:

```json
{
  "book_name": "SoloLeveling_Vol1",
  "source_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "created_at": "2026-09-21T04:20:00Z",
  "updated_at": "2026-09-21T05:15:30Z",
  "total_items": 42,
  "total_chunks": 650,
  "completed_chunks": 210,
  "stats": {
    "prompt_tokens": 315000,
    "completion_tokens": 142000,
    "cost_usd": 1.345
  },
  "items": {
    "item_chapter01": {
      "status": "completed",
      "chunks": {
        "0": {
          "status": "completed",
          "source_hash": "7a3f1...",
          "translations": {
            "0": "Paragraf terjemahan 1...",
            "1": "Paragraf terjemahan 2..."
          },
          "tokens": 1450,
          "cost": 0.0042,
          "reflection_verdict": "REVISED"
        }
      }
    }
  }
}
```

### 3.2 Crash Safety: Atomic File Writes
Standard `open(path, 'w')` corrupts the progress file if interrupted mid-write.
The state manager must enforce atomic writes:
```python
def save_state(self):
    temp_file = f"{self.progress_file}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(self.state, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, self.progress_file)  # Atomic on Windows and POSIX
```

---

## 4. Agentic Translation Engine (`core/agentic_translator.py` & `core/prompts.py`)

### 4.1 The 3-Step Agentic Workflow: Draft -> Reflect -> Improve

```
 [Source Text Chunk]
         │
         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Step 1: DRAFTING (Penerjemah Sastra)                   │
 │ Produces literary Indonesian prose with intact tags.   │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
 ┌────────────────────────────────────────────────────────┐
 │ Step 2: REFLECTION (Editor Sastra & Proofreader)       │
 │ Evaluates literalisms, flow, dialog, glossary, tags.   │
 └───────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │ Is critique "TIDAK ADA REVISI"│
         │ or "[STATUS: PERFECT]"?       │
         ▼                               ▼
      [YES]                            [NO]
   Fast-Path!                            │
  (Skip Step 3)                          ▼
         │               ┌────────────────────────────────┐
         │               │ Step 3: IMPROVEMENT (Penulis)  │
         │               │ Rewrites using editor feedback.│
         │               └───────────────┬────────────────┘
         │                               │
         └───────────────┬───────────────┘
                         ▼
             [Final Indonesian Chunk]
```

### 4.2 Prompt Engineering Specifications

#### Step 1: Literary Drafting Prompt (`get_draft_prompt`)
- **Persona:** Penerjemah sastra berpengalaman (spesialis novel fiksi/light novel).
- **Core Directives:**
  1. *Natural Flow:* Terjemahkan sesuai kaidah sastra Indonesia modern (standar penerbitan Gramedia Pustaka Utama). Hindari struktur kalimat bahasa sumber yang kaku.
  2. *Dialogue Nuance:* Sesuaikan ragam tutur dialog karakter agar hidup dan sesuai konteks sosial/emosional karakter.
  3. *Glossary Strictness:* Wajib menggunakan padanan kata dari Glosarium yang diberikan.
  4. *Markup Integrity:* Jangan hapus atau ubah tag pembatas `<p id="...">`, `<em>`, `<b>`, dll.

#### Step 2: Reflection & Proofreading Prompt (`get_reflect_prompt`)
- **Persona:** Penyunting senior fiksi dan kritikus sastra Indonesia.
- **Evaluation Axes:**
  1. *Kekakuan Bahasa / Calque:* Temukan frasa yang berbau terjemahan mesin harfiah.
  2. *Rhythm & Musicality:* Nilai keluwesan rima prosa dan pergantian kalimat panjang/pendek.
  3. *Konsistensi Karakter:* Periksa kata ganti (aku/saya/kau/kamu/dia) agar tidak tertukar.
  4. *Integritas Tag:* Pastikan semua ID paragraf dan format inline utuh.
- **Sentinel Rule:**
  - Jika draf sudah sangat baik dan tidak memerlukan perbaikan berarti, wajib mencantumkan: `[STATUS: PERFECT] TIDAK ADA REVISI`.
  - Jika ada kekurangan, berikan kritik terstruktur per nomor paragraf.

#### Step 3: Literary Improvement Prompt (`get_improve_prompt`)
- **Persona:** Penulis ulang sastra kelas master (Master Literary Stylist).
- **Directives:** Gabungkan draf awal dengan catatan perbaikan editor untuk menghasilkan prosa final yang anggun, dinamis, dan mempertahankan 100% struktur `<p id="...">`. HANYA kembalikan teks hasil terjemahan tanpa komentar pembuka atau penutup.

### 4.3 Glossary Engine
- Accepts input formats: `Original -> Indonesian`, `Original: Indonesian`, or TSV.
- Normalizes into a key-value dictionary.
- Injected into prompts under an explicit priority header:
  ```
  ATURAN GLOSARIUM WAJIB:
  - {source_term} => {target_term} (JANGAN diubah atau diterjemahkan ke kata lain)
  ```
- Post-processing verification: Performs regex validation to warn if a target glossary term is missing from the translation output.

### 4.4 LiteLLM Resilience & Provider Handling
In `core/agentic_translator.py:9-11`, setting `os.environ["API_KEY"] = api_key` breaks LiteLLM when switching between OpenAI, Anthropic, and Gemini.
**Correct Implementation:**
- Pass `api_key=self.api_key` directly to `litellm.completion(model=self.model_name, api_key=self.api_key, ...)`.
- Multi-provider model mappings:
  - `openai/gpt-4o`, `openai/gpt-4o-mini`
  - `anthropic/claude-3-5-sonnet-20240620`, `anthropic/claude-3-haiku-20240307`
  - `gemini/gemini-1.5-pro-latest`, `gemini/gemini-1.5-flash-latest`
  - `deepseek/deepseek-chat`
- Exponential Backoff with Jitter:
  ```python
  import random
  for attempt in range(max_retries):
      try:
          response = litellm.completion(...)
          return response
      except (litellm.RateLimitError, litellm.APIConnectionError, litellm.Timeout) as e:
          if attempt == max_retries - 1:
              raise e
          sleep_time = min(60, (2 ** attempt) * 2 + random.uniform(0.5, 2.0))
          time.sleep(sleep_time)
  ```
- Telemetry Harvesting: Capture `response.usage.prompt_tokens`, `response.usage.completion_tokens`, and calculate cost with `litellm.completion_cost(completion_response=response)`.

---

## 5. Streamlit UI & Taste-Skill CSS Architecture (`app.py`)

### 5.1 Taste-Skill Design Directives (Anti-Generic Editorial Minimalism)
Following the guidelines from `minimalist-ui` and `design-taste-frontend`:
- **Banned Clichés:** No generic purple/indigo AI gradients, no glowing buttons, no heavy box-shadows, no `rounded-full` pills for major cards, no emoji-heavy labels.
- **Aesthetic Direction:** *The Minimalist Publishing Atelier*.
- **Typography:**
  - UI & Body: Geometric modern sans (`Geist Sans`, `Helvetica Neue`, `-apple-system`, `sans-serif`).
  - Headings / Branding: High-contrast editorial style (`Newsreader`, `Playfair Display`, serif accent) or crisp architectural sans.
  - Metrics & Status: Clean monospace (`Geist Mono`, `JetBrains Mono`, `Consolas`, monospace).
- **Color Palette (Warm Obsidian & Bone):**
  - App Background: `#0D0F12` (Obsidian Dark) or `#FBFBFA` (Light Bone).
  - Surface Cards: `#15181E` / `#FFFFFF`.
  - Borders: `1px solid rgba(255, 255, 255, 0.08)` or `1px solid #E5E7EB`.
  - Primary Typography: `#F3F4F6` (High-contrast Off-White).
  - Secondary Typography: `#9CA3AF` (Muted Gray).
  - Accent Color: `#10B981` (Subdued Emerald for progress/success) and `#F59E0B` (Warm Amber for reflection warnings).

### 5.2 Custom CSS Injection Matrix
Injected via `st.markdown('<style>...</style>', unsafe_allow_html=True)`:

```css
/* Typography & Canvas Reset */
@import url('https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600&family=Geist:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: #0D0F12 !important;
    color: #F3F4F6;
}

/* Sidebar Custom Styling */
[data-testid="stSidebar"] {
    background-color: #111317 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
}

/* Bento Metric Cards */
.bento-card {
    background: #15181E;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.bento-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9CA3AF;
    margin-bottom: 4px;
}
.bento-value {
    font-family: 'Geist Mono', monospace;
    font-size: 22px;
    font-weight: 600;
    color: #FFFFFF;
}

/* Monospace Live Telemetry Terminal */
.terminal-log {
    background: #090A0C;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 6px;
    padding: 12px;
    font-family: 'Geist Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #A1A1AA;
    height: 180px;
    overflow-y: auto;
}

/* Action Buttons */
.stButton > button {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    padding: 8px 16px !important;
    transition: opacity 0.15s ease, transform 0.1s ease !important;
}
.stButton > button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}
```

### 5.3 UI Flow & Non-Blocking State Management
Streamlit scripts execute top-to-bottom on each interaction. To handle long-running EPUB translation without locking or losing state:
1. **Session State Store:**
   - `st.session_state.pipeline_status`: `'IDLE'`, `'RUNNING'`, `'PAUSED'`, `'COMPLETED'`, `'ERROR'`
   - `st.session_state.current_item_index`: Integer tracking current document.
   - `st.session_state.telemetry`: Running counts of tokens, elapsed seconds, estimated cost.
   - `st.session_state.recent_logs`: FIFO ring buffer of log entries.
2. **Interactive Controls:**
   - "Start Translation", "Pause", "Resume", "Export State JSON".
3. **Live Inspection Deck:**
   - An interactive tabbed or split-pane view displaying real-time comparisons of the current chunk:
     - Tab 1: Source Text
     - Tab 2: Draft Indonesian
     - Tab 3: Editor Reflection Critique
     - Tab 4: Final Polished Output

---

## 6. Concrete Module Interface Contracts

### 6.1 Data Structures & Schemas (`core/types.py`)

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

@dataclass(frozen=True)
class BookMetadata:
    title: str
    creator: str
    identifier: str
    language: str
    total_documents: int
    estimated_word_count: int

@dataclass
class TextBlockNode:
    node_id: int
    tag_name: str
    attributes: Dict[str, Any]
    inner_html: str

@dataclass
class TextChunk:
    chunk_id: str              # e.g. "item_03_chunk_004"
    item_id: str               # e.g. "chapter03"
    chunk_index: int
    nodes: List[TextBlockNode]
    formatted_prompt_input: str

@dataclass
class TranslationOutput:
    chunk_id: str
    translated_nodes: Dict[int, str]  # node_id -> translated inner HTML
    draft_text: str
    reflection_text: str
    final_text: str
    skipped_step3: bool
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float

@dataclass
class TelemetryStats:
    total_chunks: int
    completed_chunks: int
    pending_chunks: int
    failed_chunks: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    elapsed_seconds: float
    estimated_remaining_seconds: float
```

### 6.2 Module Interface Signatures

#### A. `utils/epub_parser.py`
```python
class EpubParser:
    def __init__(self, file_path: str):
        """Loads EPUB using ebooklib, extracts book metadata, and indexes documents."""
        ...
        
    def get_metadata(self) -> BookMetadata:
        """Returns book metadata (title, author, document count)."""
        ...
        
    def get_html_items(self) -> List[Any]:
        """Returns all ITEM_DOCUMENT spine items in document order."""
        ...
        
    def extract_chunks(self, item: Any, max_words_per_chunk: int = 1200) -> Tuple[BeautifulSoup, List[TextChunk]]:
        """
        Parses an XHTML item into a BeautifulSoup DOM and returns a list of 
        batched TextChunk objects with preserved block tags and inline formatting.
        """
        ...
        
    def apply_chunk_translation(self, chunk: TextChunk, translation: TranslationOutput) -> None:
        """
        Replaces inner contents of the chunk's DOM nodes with translated inner HTML,
        preserving all outer tag names and CSS attributes.
        """
        ...
        
    def commit_item(self, item: Any, soup: BeautifulSoup) -> None:
        """Serializes the modified soup back into the EPUB item with UTF-8 encoding."""
        ...
        
    def save_book(self, output_path: str) -> str:
        """Writes the repacked EPUB to disk and returns the absolute output path."""
        ...
```

#### B. `utils/state_manager.py`
```python
class StateManager:
    def __init__(self, book_name: str, cache_dir: Optional[str] = None):
        """Initializes or loads the atomic JSON progress tracker."""
        ...
        
    def is_chunk_completed(self, item_id: str, chunk_index: int) -> bool:
        """Checks whether the chunk is already translated."""
        ...
        
    def get_chunk_translation(self, item_id: str, chunk_index: int) -> Optional[TranslationOutput]:
        """Retrieves cached translation output for a chunk."""
        ...
        
    def record_chunk(self, item_id: str, chunk_index: int, output: TranslationOutput) -> None:
        """Atomically saves completed chunk translation to disk."""
        ...
        
    def get_telemetry(self) -> TelemetryStats:
        """Calculates running totals for chunks, tokens, costs, and progress percentage."""
        ...
        
    def reset_state(self) -> None:
        """Clears existing progress for a fresh translation run."""
        ...
```

#### C. `core/agentic_translator.py`
```python
class AgenticTranslator:
    def __init__(self, api_key: str, model_name: str, temperature: float = 0.3):
        """Initializes LiteLLM client configuration and sets retry thresholds."""
        ...
        
    def validate_connection(self) -> bool:
        """Verifies API key and model availability with a lightweight probe."""
        ...
        
    def parse_glossary(self, glossary_raw: str) -> Dict[str, str]:
        """Parses raw user glossary text into a normalized mapping."""
        ...
        
    def translate_chunk(
        self, 
        chunk: TextChunk, 
        source_lang: str, 
        target_lang: str = "Indonesia",
        glossary: Optional[Dict[str, str]] = None
    ) -> TranslationOutput:
        """
        Executes the 3-Step Agentic Loop:
        1. Draft translation via get_draft_prompt
        2. Literary reflection via get_reflect_prompt
        3. If reflection indicates [STATUS: PERFECT], skip Step 3.
           Else execute final rewrite via get_improve_prompt.
        Returns validated TranslationOutput with telemetry.
        """
        ...
```

---

## 7. Gap Analysis of Existing Prototype & Refactoring Roadmap

### 7.1 Gap Analysis Matrix

| Component | Current Prototype State | Architectural Defect / Risk | Target Specification |
|---|---|---|---|
| `utils/epub_parser.py` | Line 37: `has_block_child` ignores block tags with inline `span`/`em` children. | Inline markup (`em`, `span`) causes parent `<p>` to be omitted; translated text strips all child tags (`node.string = ...`). | Block/Inline tag separation. Preserve outer attributes, translate inner HTML, replace via `node.clear(); node.extend(...)`. |
| `utils/epub_parser.py` | Single node iteration (`extract_chunks` returns individual nodes). | 10,000+ individual API calls for 500 pages; loss of narrative context across paragraphs; rate limiting. | Adaptive batch chunking (~1,200 words/chunk) with indexed paragraph delimiters (`<p id="N">`). |
| `core/agentic_translator.py` | Line 11: `os.environ["API_KEY"] = api_key`. | Fails across providers (Anthropic expects `ANTHROPIC_API_KEY`, OpenAI expects `OPENAI_API_KEY`). | Pass `api_key` directly to `litellm.completion()`. Support provider-specific configs. |
| `core/agentic_translator.py` | Reflection step has no bypass; always calls Step 3. | High-quality drafts invoke Step 3 redundantly, wasting 33% tokens and doubling latency. | Fast-Path bypass on `[STATUS: PERFECT]` or `TIDAK ADA REVISI`. |
| `utils/state_manager.py` | Non-atomic write (`open(..., 'w')`). | If user interrupts or crash occurs during save, progress JSON is corrupted. | Atomic write via `.tmp` file and `os.replace()`. |
| `app.py` | No custom CSS injected; standard Streamlit default UI. | Violates taste-skill requirement; generic appearance; lacks bento layout and monospace log console. | Inject bespoke Minimalist Editorial CSS (`Geist` fonts, dark obsidian cards, clean borders, live telemetry terminal). |
| `app.py` | Translation loop blocks Streamlit execution thread. | No pause/resume capability; browser timeouts during multi-hour translation. | Generator-based chunk processing with `session_state` persistence and pause/resume flags. |

### 7.2 Implementation Roadmap for Subsequent Sprints
1. **Sprint 1 (EPUB & State Core):**
   - Refactor `utils/epub_parser.py` to implement Block/Inline tag separation and inner HTML preservation.
   - Implement Adaptive Batch Chunking with `<p id="N">` serialization.
   - Refactor `utils/state_manager.py` to enforce atomic saves and rich telemetry tracking.
2. **Sprint 2 (Agentic Engine & Prompts):**
   - Refactor `core/prompts.py` for literary Indonesian prose (Gramedia style) and structured reflection sentinels.
   - Implement Fast-Path bypass, jitter backoff, and usage telemetry in `core/agentic_translator.py`.
3. **Sprint 3 (Streamlit UI & Taste-Skill CSS):**
   - Inject Minimalist Editorial CSS in `app.py`.
   - Build Bento Metric Cards (Chunks, ETA, Tokens, Cost).
   - Implement live inspection split-pane and monospace log terminal.
4. **Sprint 4 (Integration & Verification):**
   - End-to-end test on mock multi-chapter EPUB.
   - Verify style and inline tag preservation across roundtrips.
