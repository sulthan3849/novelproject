# Comprehensive Codebase State Survey Report

**Date**: 2026-09-21  
**Project**: Agentic Novel Translator (500+ Page EPUB to Indonesian)  
**Surveyor**: Codebase State Surveyor (`survey_explorer_1`)  
**Target Root**: `c:\Mek Project\novelproject`  
**Reference Request**: `c:\Mek Project\novelproject\.agents\ORIGINAL_REQUEST.md`

---

## 1. Executive Summary

The existing repository contains a prototype implementation of the Agentic Novel Translator comprising 5 Python source files (`app.py`, `core/prompts.py`, `core/agentic_translator.py`, `utils/epub_parser.py`, and `utils/state_manager.py`) and a `requirements.txt` file.

While all source files pass syntax validation (`python -m py_compile`), the codebase is in a **fragile pre-alpha state with critical functional bugs and major non-compliance against the acceptance criteria**:
1. **Critical Acceptance Criteria Failure (R3 / AC 3.1)**: `app.py` contains **zero custom CSS** (`st.markdown("<style>...</style>")`), completely failing the taste-skill / minimalist design requirement. Furthermore, it uses standard generic Streamlit defaults and forbidden emojis (`📚`, `🚀`, `⚙️`, `📖`).
2. **Critical Functional Defect in EPUB Formatting (R1 / AC 1.3)**: `utils/epub_parser.py` combined with `app.py` line 60 (`node.string = translated_text`) **completely strips all inline HTML formatting tags** (`<em>`, `<b>`, `<i>`, `<a>`, `<ruby>`, `<rt>`). In addition, treating `<span>` as a block child causes surrounding text in paragraphs containing `<span>` to be skipped and **lost forever from translation**.
3. **Broken Resume Mechanism in State Manager**: In `app.py`, the EPUB file is saved via `tempfile.NamedTemporaryFile`, which generates a random temporary filename (e.g., `tmp3k9_xyz.epub`). Because `StateManager` bases its progress cache filename on `parser.book_name`, every re-upload or session restart creates a brand-new cache file, rendering the resume functionality non-functional.
4. **Prompt & Engine Inconsistencies**: `core/prompts.py` contains `{text}` in `get_draft_prompt`, but `agentic_translator.py` never formats it, leaving literal `{text}` inside the LLM system prompt. Furthermore, the 3-step chain lacks streaming, progress callbacks, token counting, context window passing, and sanitization of LLM conversational filler.
5. **Architectural & ECC Standard Gaps**: Neither `core/` nor `utils/` contain `__init__.py`. There are no automated tests (`tests/` directory is completely absent), violating the ECC 80%+ test coverage rule.

---

## 2. File-by-File Inventory & Audit

| File Path | Lines | Size | Status | Purpose | Primary Issues Identified |
|---|---|---|---|---|---|
| `requirements.txt` | 7 | 106 B | Complete | Dependency specification | Missing development/testing dependencies (`pytest`, `pytest-cov`, `ruff`); lacks pinning for sub-dependencies. |
| `core/prompts.py` | 64 | 2,183 B | Working (with flaws) | Draft, Reflect, Improve prompt templates | Literal `{text}` unformatted in draft prompt; prompt returns monolithic text without structured separation of system/user roles; no instruction to preserve inline HTML tags. |
| `core/agentic_translator.py` | 63 | 2,571 B | Functional prototype | 3-step translation loop using LiteLLM | Hardcoded `os.environ["API_KEY"]`; naive retry mechanism; no streaming/progress callbacks; no context window between paragraphs; linear execution (3 calls/chunk = 15,000 calls/book). |
| `utils/epub_parser.py` | 46 | 1,779 B | Broken logic | EPUB reading & HTML chunk extraction | Strips inline HTML tags; skips text surrounding `<span>`; deprecation warnings with `ebooklib`; lacks metadata preservation. |
| `utils/state_manager.py` | 42 | 1,767 B | Functional prototype | JSON-based translation state tracker | Generates un-sanitized hidden dotfiles in root; broken resume when used with tempfiles; synchronous disk write on every single chunk; `mark_item_completed` is a no-op `pass`. |
| `app.py` | 142 | 5,854 B | Non-compliant | Streamlit dashboard UI | Zero custom CSS injected; contains forbidden emojis; download button vanishes on widget reruns due to missing `st.session_state` persistence; blocks UI thread for hours without cancellation/pause. |

---

## 3. Deep Dive Technical Analysis

### 3.1 `utils/epub_parser.py` & HTML Node Handling (Critical Defect)

#### Empirical Observation & Reproduction
In `utils/epub_parser.py` (lines 28–41):
```python
target_tags = ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
nodes = []
for tag in soup.find_all(target_tags):
    text = tag.get_text(strip=True)
    if text and len(text) > 1:
        has_block_child = any(child.name in target_tags for child in tag.children if child.name)
        if not has_block_child:
            nodes.append(tag)
```
And in `app.py` (line 60):
```python
node.string = translated_text
```

When executed against real-world novel markup containing inline styles (verified via `.agents/survey_explorer_1/verify_components.py`):
```html
<p class="calibre2">This paragraph has <em>inline emphasis</em> and <b>bold</b> words.</p>
<p class="calibre3">This paragraph has a <span class="styled">styled span</span> inside it.</p>
```

**Results:**
1. **Destruction of Inline Tags**: For `<p class="calibre2">`, `has_block_child` evaluates to `False` (since `em` and `b` are not in `target_tags`). The entire `<p>` tag is returned in `nodes`. When `node.string = translated_text` executes, BeautifulSoup's `.string` setter **erases all children**, stripping `<em>` and `<b>` completely:
   - *Before*: `<p class="calibre2">This paragraph has <em>inline emphasis</em> and <b>bold</b> words.</p>`
   - *After*: `<p class="calibre2">Paragraf ini memiliki penekanan dan kata tebal.</p>`
   - *Outcome*: `<em>` and `<b>` tags are destroyed.
2. **Text Dropping**: For `<p class="calibre3">`, `'span'` is present in `target_tags`. As a result, `has_block_child` evaluates to `True` on the `<p>` element! The `<p>` tag is discarded. Only the inner `<span>` is captured in `nodes`.
   - *Result*: The text `"This paragraph has a "` and `" inside it."` is **never translated**, leaving garbled half-translated sentences.

---

### 3.2 `utils/state_manager.py` & State Persistence

#### Observations & Root Causes
1. **Resume Invalidation by Temporary Files**:
   In `app.py` line 12:
   ```python
   with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp_file:
       tmp_file.write(uploaded_file.getvalue())
       tmp_path = tmp_file.name
   parser = EpubParser(tmp_path)
   state_manager = StateManager(parser.book_name)
   ```
   `parser.book_name` is computed from `os.path.splitext(os.path.basename(file_path))[0]`. Since Windows `NamedTemporaryFile` creates filenames like `tmpa8c3j2x.epub`, `parser.book_name` is `tmpa8c3j2x`.
   If the user re-uploads the exact same EPUB to resume tomorrow, a new temp file `tmp99f8d1a.epub` is generated. `StateManager` looks for `.tmp99f8d1a_progress.json`, finds nothing, and restarts translation from 0%!
2. **Excessive Synchronous I/O**:
   `mark_chunk_translated()` calls `self.save_state()` on line 37 every single time a chunk finishes. For a 500-page book with ~5,000 paragraphs, this performs 5,000 file rewrites of an ever-growing JSON structure on disk without atomic write guards (`tempfile` + `os.replace`), creating high disk thrashing and risk of file corruption if the process terminates during a write.
3. **Filename Sanitation**:
   If `book_name` is derived from original file names containing illegal Windows filesystem characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`, or non-ASCII characters), opening `.{book_name}_progress.json` throws `OSError: [Errno 22] Invalid argument`.

---

### 3.3 `core/prompts.py` & `core/agentic_translator.py`

#### Observations & Deficiencies
1. **Prompt Template Misalignment**:
   In `core/prompts.py` line 21:
   ```python
   def get_draft_prompt(source_lang, target_lang, glossary=""):
       ...
       return f"""...
   Teks Asli:
   {{text}}

   Terjemahkan teks di atas ke dalam bahasa {target_lang}.
   """
   ```
   In `core/agentic_translator.py` line 41:
   ```python
   draft_sys_prompt = get_draft_prompt(source_lang, target_lang, glossary)
   draft_text = self._call_llm(draft_sys_prompt, text)
   ```
   `draft_sys_prompt` still literally contains `"{text}"`. It is passed as the system prompt, while `text` is passed as the user prompt. This confuses the model because the system prompt contains an unresolved placeholder string.
2. **Missing Inline Tag Preservation Instructions**:
   Neither `get_draft_prompt`, `get_reflect_prompt`, nor `get_improve_prompt` instructs the LLM to preserve HTML tags (such as `<i>`, `<b>`, `<em>`, `<span class="...">`). If the parser passes tagged text, the LLM will hallucinate or drop the markup unless explicitly instructed with strict formatting guidelines.
3. **No Guard against Conversational Output**:
   Models often output conversational wrappers (e.g., *"Tentu, ini terjemahan akhirnya:"* or enclosing quotes `"`). `agentic_translator.py` has no sanitization regex or cleaner to strip conversational noise before writing into the book.
4. **Extreme Granularity & Performance Inefficiency**:
   Making 3 sequential LLM API calls for every single paragraph (`<p>`) without batching means:
   - Average 500-page novel = ~5,000 paragraphs.
   - Total LLM completions = ~15,000 completions.
   - At ~2 seconds per API call, runtime = 30,000 seconds (~8.3 hours) of uninterrupted single-threaded execution.
   - A single connection hiccup or unhandled exception aborts the entire run (line 57: `return None`).

---

### 3.4 `app.py` & UI Compliance (Taste-Skill Standards)

#### Requirements vs. Current Implementation
- **Requirement R3**: *"Build a Streamlit dashboard (app.py) for EPUB upload, API key input, glossary configuration, and live progress tracking. Inject custom CSS to elevate the design following taste-skill standards (minimalist, clean typography, anti-generic)."*
- **Acceptance Criteria**: *"`app.py` script contains explicit custom CSS injection (`st.markdown("<style>...</style>")`) reflecting a customized UI."*

| Feature / Directive | Required Standard (`minimalist-ui`) | Current State in `app.py` | Compliance |
|---|---|---|---|
| Custom CSS Injection | Explicit `<style>` with bespoke fonts, warm monochrome palette | No `<style>` tags anywhere in `app.py` | **FAIL** |
| Typography | High-contrast editorial type (`Geist Sans`, `Newsreader`, `SF Pro`) | Default Streamlit font | **FAIL** |
| Palette | Warm monochrome (`#FFFFFF`, `#F7F6F3`, `#111111`, `#EAEAEA`) | Default Streamlit theme | **FAIL** |
| Emoji Prohibition | Strict ban on emojis anywhere in UI/markup | Heavy emoji usage (`📚`, `⚙️`, `📖`, `🚀`, `✅`, `⬇️`) | **FAIL** |
| UI State Management | `st.session_state` to survive reruns | Download button nested in `if st.button()` (disappears on rerun) | **FAIL** |
| Progress & Inspection | Live progress tracking with chunk preview & ETA | Basic single `st.progress((i+1)/total_items)` with no inspection | **PARTIAL** |
| Control Controls | Pause, Resume, Stop controls | None; blocking `while/for` loop | **MISSING** |

---

## 4. Python Environment & Dependency Audit

### Environment Profile
- **OS**: Windows 11 (AMD64)
- **Python Version**: `3.12.10` (`C:\Users\Mek Gacor\AppData\Local\Programs\Python\Python312\python.exe`)
- **Package Manager**: Pip `25.0.1`

### Dependency Status

| Package | Specified in `requirements.txt` | Installed Version | Import Verification | Notes |
|---|---|---|---|---|
| `streamlit` | `>=1.30.0` | `1.64.0` | **PASS** | Functional |
| `beautifulsoup4` | `>=4.12.0` | `4.15.0` | **PASS** | Functional (`bs4`) |
| `EbookLib` | `>=0.18` | `0.20` | **PASS** | Functional (`ebooklib`) |
| `litellm` | `>=1.40.0` | `1.102.0` | **PASS** | Functional |
| `python-dotenv` | `>=1.0.0` | `1.2.3` | **PASS** | Functional (`dotenv`) |
| `tqdm` | `>=4.66.0` | `4.68.4` | **PASS** | Functional |
| `lxml` | Not specified | `6.1.3` | **PASS** | Auto-installed by `EbookLib` |

All dependencies from `requirements.txt` are verified installed and importable in Python 3.12.10.

---

## 5. Acceptance Criteria Verification Matrix

| Category | Criterion | Status | Evidence / Notes |
|---|---|---|---|
| **Core Execution** | `python -m py_compile app.py` and core files pass without syntax errors | **PASSED** | Verified: all 5 source files compile with exit code 0. |
| **Core Execution** | Processing mock HTML/EPUB through parser and state manager runs without exceptions | **PARTIAL** | Runs without exceptions on basic flat text, but fails on styled HTML. |
| **Core Execution** | EPUB parser identifies text nodes without stripping surrounding HTML tags | **FAILED** | Assigning `node.string` strips `<em>`, `<b>`, `<i>`, etc.; `span` causes text loss. |
| **Design & Standards** | `app.py` contains explicit custom CSS injection (`<style>...</style>`) | **FAILED** | Zero custom CSS injected in `app.py`. |
| **Design & Standards** | Codebase cleanly modularized into `core/`, `utils/`, and `app.py` | **PARTIAL** | Folder structure exists, but lacks `__init__.py`, tests, or config files. |

---

## 6. Actionable Remediation Roadmap

To achieve full compliance with `ORIGINAL_REQUEST.md` and ECC production standards, the implementation team must execute the following modifications:

### Step 1: Fix EPUB Parser & HTML Tag Preservation (`utils/epub_parser.py`)
1. Refactor `extract_chunks` to distinguish block-level containers (`p`, `h1`-`h6`, `li`, `blockquote`) from inline styling elements (`em`, `strong`, `i`, `b`, `span`, `a`, `ruby`, `rt`).
2. When extracting chunks, extract the **inner HTML** or structured leaf nodes of block elements rather than plain text.
3. Replace content using `node.clear()` followed by appending parsed soup or `node.replace_with()`, ensuring inline tags and styles are preserved intact.

### Step 2: Fix State Manager & Resume Logic (`utils/state_manager.py` & `app.py`)
1. Base the cache key on the **EPUB content hash** (e.g. SHA-256 of first 64KB + file size) or a sanitized version of `uploaded_file.name`, NOT the random temporary file path.
2. Store progress files in a designated `.cache/` or `.state/` directory rather than cluttering the root directory with dotfiles.
3. Use atomic file writes (`tempfile.NamedTemporaryFile` + `os.replace`) and batch disk writes (flush every N chunks or every chapter) to prevent disk thrashing.

### Step 3: Align Prompts & Agentic Engine (`core/prompts.py` & `core/agentic_translator.py`)
1. Fix the `{text}` placeholder in `get_draft_prompt` to properly separate system instructions from input content.
2. Add explicit prompt instructions to **preserve HTML tags verbatim** (e.g., *"Pertahankan tag HTML seperti `<em>...</em>` atau `<b>...</b>` di posisi yang tepat pada kalimat terjemahan"*).
3. Implement post-processing to strip accidental conversational filler or markdown code blocks from LLM responses.
4. Support paragraph batching (translating small groups of consecutive paragraphs together) to reduce API latency by 70–80%.
5. Introduce a rolling context window (passing the preceding 1–2 translated paragraphs as context) to ensure narrative coherence and accurate pronoun translation.

### Step 4: Redesign Streamlit Dashboard with Taste-Skill CSS (`app.py`)
1. Inject custom CSS matching `minimalist-ui` guidelines:
   - Premium typography (`'Geist Sans'`, `'Helvetica Neue'`, sans-serif; `'Newsreader'`, serif for headings).
   - High-contrast warm monochrome palette (`#FFFFFF` background, `#111111` text, `#EAEAEA` borders).
   - Bento-style layout cards with crisp `1px solid #EAEAEA` borders and subtle micro-interactions.
   - Strip all generic emojis and replace with clean SVG/CSS badges.
2. Refactor state management using `st.session_state` so the download button and progress persist across user interactions and page reruns.
3. Add a real-time **Agentic Inspection Panel** showing:
   - Original Chunk Text
   - Draft Translation
   - Reflection/Editor Critique
   - Final Improved Output
4. Add pause/resume/cancel controls and live processing metrics (ETA, chunks completed / total, token usage).

### Step 5: Establish Test Suite & Package Structure (ECC Standards)
1. Add `core/__init__.py` and `utils/__init__.py`.
2. Create `tests/` with comprehensive unit and integration tests:
   - `test_epub_parser.py`: Verify node extraction without stripping `<em>`, `<b>`, `<span>`.
   - `test_state_manager.py`: Verify persistence, resume on duplicate file upload, and atomic saving.
   - `test_prompts.py`: Verify formatting with and without glossary.
   - `test_agentic_translator.py`: Mock LiteLLM to test Draft -> Reflect -> Improve flow.
3. Ensure coverage exceeds 80% as mandated by ECC rules.
