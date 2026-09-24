# Comprehensive Specification and Requirement Mining Report: Agentic Novel Translator

**Author**: Specification and Requirement Miner (`survey_spec_miner_1`)  
**Date**: 2026-09-21  
**Working Directory**: `c:\Mek Project\novelproject\.agents\survey_spec_miner_1`  
**Authoritative Source**: `c:\Mek Project\novelproject\.agents\ORIGINAL_REQUEST.md`, Codebase (`app.py`, `core/`, `utils/`), ECC 2.2.0 Standards, `taste-skill` / `minimalist-ui` Protocols.

---

## 1. Executive Summary

This report establishes the complete specification baseline, requirements taxonomy, feature inventory, edge case catalog, and architectural gap analysis for the **Agentic Novel Translator** — a local web application designed to translate full-length (500+ page) EPUB novels into literary Indonesian using LiteLLM, a 3-step Draft-Reflect-Improve prompt chain, and a Streamlit UI styled according to `taste-skill` design principles.

Empirical probing of the current codebase revealed significant architectural and behavioral gaps between the existing implementation and the authoritative requirements in `ORIGINAL_REQUEST.md`. Most notably:
1. **Destructive HTML Text Replacement**: The current EPUB parser and chunk replacement logic strips all inline formatting tags (e.g., `<em>`, `<strong>`, `<a>`, `<ruby>`), directly violating Acceptance Criterion AC-3.
2. **Resumability Breakdown via Temp Files**: `app.py` writes uploaded EPUBs to a `tempfile.NamedTemporaryFile` with a randomized name, causing `StateManager` to initialize a randomized progress file (e.g., `..tmp8ab9c_progress.json`). As a result, previous progress is never loaded on subsequent runs or app restarts.
3. **Missing Taste-Skill Styling**: `app.py` contains zero custom CSS, violating Acceptance Criterion AC-4.
4. **Prompt Engineering Defects**: The drafting system prompt leaks a literal `{text}` placeholder to the LLM, and the Step 3 Improvement prompt omits glossary definitions, risking glossary corruption during the final rewrite.
5. **Disk I/O Bottleneck for 500+ Pages**: `StateManager.mark_chunk_translated()` synchronously writes the entire JSON state file to disk on every single chunk, introducing immense I/O lag across 10,000+ chunks.

---

## 2. Requirements Extraction

### 2.1 Functional Requirements (FR)

| ID | Module / Component | Requirement Description |
|---|---|---|
| **FR-1.1** | R1: EPUB Pipeline | Accept `.epub` novel uploads via Streamlit UI. |
| **FR-1.2** | R1: EPUB Pipeline | Validate EPUB container structure (ZIP archive, OPF package, manifest). |
| **FR-1.3** | R1: EPUB Pipeline | Parse EPUB using `ebooklib.epub` and extract XHTML/HTML document items in correct spine reading order. |
| **FR-1.4** | R1: EPUB Pipeline | Identify translatable text chunks (paragraphs, headings, lists) while isolating navigation/metadata documents (`nav.xhtml`, `toc.ncx`). |
| **FR-1.5** | R1: EPUB Pipeline | Extract and identify text nodes without stripping surrounding inline HTML tags (`<em>`, `<strong>`, `<span>`, `<a>`, `<ruby>`, `<rt>`). |
| **FR-1.6** | R1: EPUB Pipeline | Replace original text with translated Indonesian text inside the DOM while strictly preserving HTML tags, hierarchy, classes, and attributes. |
| **FR-1.7** | R1: EPUB Pipeline | Repack the modified HTML documents and all existing assets (images, CSS styles, fonts, cover) into a valid `.epub` output file (`<book_name>_ID.epub`). |
| **FR-2.1** | R1: State Manager | Establish persistent book identity using stable identifiers (uploaded filename or EPUB metadata title) rather than volatile temporary paths. |
| **FR-2.2** | R1: State Manager | Track translation status per chunk `(item_id, chunk_index)`. |
| **FR-2.3** | R1: State Manager | Store and retrieve translated chunk content mapped to `(item_id, chunk_index)`. |
| **FR-2.4** | R1: State Manager | Persist state to a JSON file atomically (write to temp file then rename) to prevent state file corruption during abrupt termination. |
| **FR-2.5** | R1: State Manager | Automatically resume from the last completed chunk when an ongoing or previously interrupted translation is restarted. |
| **FR-2.6** | R1: State Manager | Debounce / batch disk writes (e.g. periodically or per chapter) to handle 500+ page novels (10,000+ chunks) without performance degradation. |
| **FR-3.1** | R2: Agentic Translator | Initialize LiteLLM client supporting multi-provider API calls (OpenAI, Anthropic, Google Gemini, OpenRouter). |
| **FR-3.2** | R2: Agentic Translator | Allow dynamic API key configuration and pass keys securely per request. |
| **FR-3.3** | R2: Agentic Translator | Implement 3-step Agentic Prompt Chain: **Draft** -> **Reflect** -> **Improve**. |
| **FR-3.4** | R2: Agentic Translator | **Step 1 (Draft)**: Generate natural literary Indonesian prose adhering to Gramedia novel publication standards. |
| **FR-3.5** | R2: Agentic Translator | **Step 2 (Reflect)**: Literary proofreader analyzes draft against source for awkward phrasing, literal idioms, and tone. If draft is already optimal, output "TIDAK ADA REVISI". |
| **FR-3.6** | R2: Agentic Translator | Early termination: If Step 2 reflection contains "TIDAK ADA REVISI", bypass Step 3 and directly adopt the draft text. |
| **FR-3.7** | R2: Agentic Translator | **Step 3 (Improve)**: Master literary author rewrites draft based on proofreader critique to produce final polished prose. |
| **FR-3.8** | R2: Agentic Translator | Maintain glossary consistency across all prompt steps (Draft, Reflect, and Improve) using custom glossary input (`Source -> Target`). |
| **FR-3.9** | R2: Agentic Translator | Handle API rate limits (HTTP 429), timeouts, and transient network errors with exponential backoff retries. |
| **FR-4.1** | R3: Streamlit UI | Provide file uploader for `.epub` files. |
| **FR-4.2** | R3: Streamlit UI | Provide sidebar controls for API key input (`type="password"`), model selection dropdown, source language, and target language. |
| **FR-4.3** | R3: Streamlit UI | Provide glossary input text area with example syntax. |
| **FR-4.4** | R3: Streamlit UI | Provide primary execution trigger button ("Mulai Terjemahkan") with validation. |
| **FR-4.5** | R3: Streamlit UI | Display dual-level progress tracking: overall chapter progress and chunk-level progress metrics. |
| **FR-4.6** | R3: Streamlit UI | Provide live translation inspection console showing original text, draft, reflection critique, and final improvement. |
| **FR-4.7** | R3: Streamlit UI | Provide download button (`st.download_button`) for the finished translated EPUB. |
| **FR-5.1** | R3: Taste-Skill Design | Inject custom CSS via `st.markdown("<style>...</style>", unsafe_allow_html=True)`. |
| **FR-5.2** | R3: Taste-Skill Design | Implement clean editorial typography (`SF Pro Display`, `Geist Sans`, serif headings like `Newsreader`/`Playfair Display`, `Geist Mono` for logs). |
| **FR-5.3** | R3: Taste-Skill Design | Enforce warm monochrome palette (`#FFFFFF` cards, `#F7F6F3` page background, `#111111` off-black text, `#787774` secondary, `#EAEAEA` borders). |
| **FR-5.4** | R3: Taste-Skill Design | Eliminate AI clichés: ban purple gradients, heavy box-shadows, and pill buttons. |

---

### 2.2 Non-Functional Requirements (NFR)

| ID | Category | Requirement Description |
|---|---|---|
| **NFR-1** | Scalability | Capable of processing 500+ page novels (100,000+ words, 5,000–15,000 paragraphs) without memory exhaustion or process locking. |
| **NFR-2** | Fault Tolerance | Abrupt termination (browser disconnect, power failure, API crash) must not corrupt state or lose completed chunks. |
| **NFR-3** | Translation Quality | Output must read like published Indonesian literature (Gramedia novel standard), avoiding mechanical word-for-word translation. |
| **NFR-4** | Security | API keys must never be logged to console, written to progress files, or exposed in client-side source. |
| **NFR-5** | Modularity | Strict adherence to ECC guidelines: small focused files (<400 lines typical), small functions (<50 lines), separation of concerns (`core/`, `utils/`, `app.py`, `tests/`). |
| **NFR-6** | Cross-Platform Compatibility | Must run cleanly on Windows (PowerShell) with UTF-8 encoding support and proper path handling. |

---

### 2.3 Technical Constraints (TC)

- **TC-1**: Python 3.12 runtime environment.
- **TC-2**: Primary dependencies: `streamlit>=1.30.0`, `beautifulsoup4>=4.12.0`, `EbookLib>=0.18`, `litellm>=1.40.0`, `python-dotenv>=1.0.0`, `tqdm>=4.66.0`.
- **TC-3**: Local execution via Streamlit server (`streamlit run app.py`).
- **TC-4**: EPUB standard compliance (EPUB 2.0 / 3.0 XHTML documents and package manifest).
- **TC-5**: Multi-LLM provider compatibility unified via LiteLLM interface.

---

### 2.4 Acceptance Criteria (AC)

- **AC-1 (Syntax & Compilation)**: Running `python -m py_compile app.py` and other core files passes without syntax errors.
- **AC-2 (Mock Execution)**: Processing a mock HTML string or tiny EPUB through the parser and state manager runs without throwing exceptions.
- **AC-3 (HTML Tag Preservation)**: The EPUB parser logic successfully identifies text nodes without stripping surrounding HTML tags.
- **AC-4 (Custom CSS Injection)**: The `app.py` script contains explicit custom CSS injection (`st.markdown("<style>...</style>")`) reflecting a customized UI following taste-skill standards.
- **AC-5 (Modular Architecture)**: The codebase is cleanly modularized into at least `core/`, `utils/`, and `app.py`.
- **AC-6 (Resumability)**: State manager successfully resumes from existing state file across restarts without re-translating completed chunks.
- **AC-7 (Literary Quality & Glossary)**: Agentic translator executes Draft -> Reflect -> Improve chain, honors glossary substitutions, and skips Improve when Reflect outputs "TIDAK ADA REVISI".
- **AC-8 (Test Suite)**: Automated unit tests achieve test verification across parser, state manager, and translator modules.

---

## 3. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | EPUB Pipeline | EPUB Ingestion | Read and unpack EPUB file structure | EPUB file path / bytes | `epub.EpubBook` instance | Raises `FileNotFoundError` or `epub.EpubException` on invalid zip | `utils/epub_parser.py:9` |
| 2 | EPUB Pipeline | Document Extraction | Extract XHTML document items | `EpubBook` | List of `EpubHtml` items | Empty list if no document items found | `utils/epub_parser.py:16` |
| 3 | EPUB Pipeline | Chunk Identification | Identify translatable tags/nodes | `EpubHtml` item | `(BeautifulSoup, list[Tag])` | Skips tags with length <= 1 | `utils/epub_parser.py:19-41` |
| 4 | EPUB Pipeline | Tag Preservation | Identify text nodes while preserving inline tags (`<em>`, `<strong>`, `<a>`, `<ruby>`) | HTML DOM / Tag node | Intact DOM structure with translated text | Strips inner tags if `node.string` is set directly | `utils/epub_parser.py`, AC-3 |
| 5 | EPUB Pipeline | Reading Order / Spine Sorting | Order document items according to EPUB spine | `EpubBook.spine` | Ordered list of story documents | Non-spine items placed at end or excluded | Probing `ebooklib.epub` |
| 6 | EPUB Pipeline | Navigation Filtering | Distinguish story chapters from `nav.xhtml` / `toc.ncx` | Item ID / properties | Boolean flag `is_story_document` | Corrupts TOC links if translated as regular text | Probing `ebooklib` with mock EPUB |
| 7 | EPUB Pipeline | Repack EPUB | Write modified documents back to EPUB file | Output file path, `EpubBook` | Saved `.epub` file on disk | Raises `IOError` on invalid path or write permissions | `utils/epub_parser.py:43` |
| 8 | State Manager | State Initialization | Initialize progress state file | `book_name` (string) | `StateManager` instance with loaded state dict | Defaults to `{"translated_items": {}}` if missing | `utils/state_manager.py:5-17` |
| 9 | State Manager | Stable Book Identity | Generate unique, persistent book ID from upload | Original filename or EPUB metadata | Persistent ID string | Fails to resume if random tempfile name is used | Code probe of `app.py:12-20` |
| 10 | State Manager | Chunk Status Check | Verify if chunk is already translated | `item_id`, `chunk_index` | `bool` (`True` if translated) | Returns `False` on unknown item or chunk | `utils/state_manager.py:24` |
| 11 | State Manager | Chunk Content Retrieval | Get translated text for a completed chunk | `item_id`, `chunk_index` | `str` or `None` | Returns `None` if not found | `utils/state_manager.py:28` |
| 12 | State Manager | Chunk State Recording | Record translated text into state dict | `item_id`, `chunk_index`, text | None | Initializes sub-dict if `item_id` not present | `utils/state_manager.py:32` |
| 13 | State Manager | Atomic State Persistence | Write state to disk safely via temporary file rename | State dictionary | Written `.json` file | Prevents 0-byte corrupt state file on abrupt crash | State manager gap analysis |
| 14 | State Manager | Batched Disk Flushing | Flush state to disk periodically instead of every chunk | Chunk batch / chapter event | Persisted file on disk | Degrades SSD / freezes loop if flushed 10,000 times | Code probe of `state_manager.py:37` |
| 15 | Translation Engine | Multi-Provider Init | Initialize LiteLLM with API key and model | `api_key`, `model_name` | `AgenticTranslator` instance | Missing key errors on first API invocation | `core/agentic_translator.py:5` |
| 16 | Translation Engine | LLM Invocation with Retry | Call LiteLLM with exponential backoff on rate limits | `system_prompt`, `user_prompt` | LLM response string | Retries 3x, then raises exception | `core/agentic_translator.py:13` |
| 17 | Translation Engine | Step 1: Literary Drafting | Generate initial literary translation draft | Source text, languages, glossary | Draft translation string | Returns unchanged text if empty or whitespace | `core/agentic_translator.py:40` |
| 18 | Translation Engine | Step 2: Proofreader Reflection | Evaluate draft for awkward idioms, flow, and tone | Source text, draft text | Reflection critique string | Returns "TIDAK ADA REVISI" if optimal | `core/agentic_translator.py:44` |
| 19 | Translation Engine | Early Reflection Exit | Skip Step 3 if draft is already evaluated as optimal | Reflection string | Draft text returned directly | Bypasses unnecessary 3rd API call | `core/agentic_translator.py:50` |
| 20 | Translation Engine | Step 3: Master Improvement | Synthesize source, draft, and critique into prose | Source text, draft, critique | Polished final translation | Fails if prompt formatting crashes on braces | `core/agentic_translator.py:53` |
| 21 | Translation Engine | Glossary Consistency | Enforce glossary across all prompt stages | Glossary text (`Src -> Tgt`) | Preserved terminology in outputs | Terms get lost if glossary omitted in Step 3 | Code probe of `core/prompts.py:46` |
| 22 | Translation Engine | Safe Prompt Formatting | Format prompts without curly-brace crashes | Source text with `{}` | Formatted prompt strings | `KeyError` / `ValueError` if using naive `str.format` | Code probe of `core/prompts.py` |
| 23 | Streamlit UI | EPUB File Upload | Upload novel file via UI | File buffer from user | Streamlit `UploadedFile` object | Halts with error warning if no file uploaded | `app.py:102` |
| 24 | Streamlit UI | API & Model Configuration | Sidebar inputs for key and model choice | User text & selection | Config values in session | Halts with warning if API key missing | `app.py:83-92` |
| 25 | Streamlit UI | Language Configuration | Select source and target languages | Dropdown selections | Language string codes | Defaults to JP/EN/KR/CN -> Indonesian | `app.py:93-96` |
| 26 | Streamlit UI | Glossary Text Input | Text area for custom terminology definitions | User string (`A -> B`) | Glossary string passed to translator | Defaults to empty string | `app.py:105-108` |
| 27 | Streamlit UI | Translation Loop Execution | Coordinate parser, state manager, translator | Button click | Translated EPUB saved to disk | Catches exceptions, displays error alert | `app.py:10-76` |
| 28 | Streamlit UI | Real-Time Progress Tracking | Display chapter and chunk progress bars | Current index / total items | UI progress bar & status text | Stalls visual feedback if only updated per chapter | `app.py:26-66` |
| 29 | Streamlit UI | Live Translation Preview | Stream original, draft, critique, and final chunk | Translation step outputs | Rendered preview in UI container | Currently declared but unpopulated in `app.py:28` | `app.py:28` |
| 30 | Streamlit UI | Download Button | Provide download link for finished novel | Output EPUB path | Downloadable EPUB binary | Disabled or hidden until output file exists | `app.py:131-138` |
| 31 | Taste-Skill CSS | Custom CSS Injection | Inject custom CSS via `st.markdown` | Raw CSS string in `<style>` tags | Custom styled Streamlit DOM | Unstyled default UI if omitted | AC-4, `design-taste-frontend` |
| 32 | Taste-Skill CSS | Clean Typographic Hierarchy | Apply editorial typography (`SF Pro`, serif headings) | CSS `@font-face` / system font stack | Refined typography rendering | Falls back to system sans-serif | `minimalist-ui` Protocol |
| 33 | Taste-Skill CSS | Warm Monochrome Palette | Enforce `#FFFFFF`, `#F7F6F3`, `#111111`, `#EAEAEA` | CSS color variables | Cohesive editorial visual feel | Banned generic AI purple gradients | `minimalist-ui` Protocol |
| 34 | Taste-Skill CSS | Bento Card Framing | Clean containers with 1px border and crisp corners | CSS container selectors | Card-framed layout | Eliminates generic card shadows | `minimalist-ui` Protocol |

---

## 4. Edge Cases & Observed Behaviors

| # | Feature | Input / Condition | Observed Behavior | Root Cause / Impact |
|---|---|---|---|---|
| **E-01** | EPUB Text Replacement | Paragraph containing inline formatting: `<p>She looked with <em>fury</em>.</p>` | Setting `node.string = '...'` deletes the `<em>` tag entirely, producing `<p>Dia menatap dengan murka.</p>`. | In BeautifulSoup, assigning `tag.string = "..."` replaces all child tags. Breaks AC-3. |
| **E-02** | EPUB Text Extraction | Mixed text and block children: `<div>Text before <p>child</p> Text after</div>` | Only `<p>child</p>` is extracted; "Text before" and "Text after" are ignored and never translated. | `has_block_child` check in `extract_chunks()` rejects the parent without collecting its direct text strings. |
| **E-03** | Resumability Across Sessions | User re-uploads same novel tomorrow or refreshes browser | Previous state is not loaded; starts from chunk 0. | `app.py` saves to `NamedTemporaryFile` (`tmpXYZ.epub`), so `book_name` is `tmpXYZ`. New run creates `tmpUVW.epub`. |
| **E-04** | Draft Prompt Generation | Calling `get_draft_prompt("Inggris", "Indonesia")` | Returned system prompt contains literal unreplaced `{text}` placeholder. | Double braces in f-string evaluate to literal `{text}`; translator sends it directly as system prompt. |
| **E-05** | Step 3 Glossary Preservation | User specifies `Kuro -> Si Hitam`; Step 1 translates `Si Hitam`, Step 3 runs | Step 3 prompt lacks glossary instructions; master rewriter may rename `Si Hitam` back to `Kuro` or `Bayangan Hitam`. | `get_improve_prompt()` does not accept or include the glossary parameter. |
| **E-06** | Prompt Template Braces | Literary text containing braces: `code { x = 1 }` or JSON snippets | If template strings are formatted via `str.format()` without escaping, Python raises `KeyError` or `ValueError`. | Native string formatting treats `{x}` as template variables. |
| **E-07** | State File Crash Mid-Write | Power outage or process kill while saving state | Progress JSON file becomes 0 bytes or truncated; `load_state` fails and resets to empty state. | `open(..., "w")` without atomic rename corrupts the progress file. |
| **E-08** | High I/O on 500+ Page Novel | 10,000 paragraphs in a 500-page novel | `mark_chunk_translated` writes the entire JSON file to disk 10,000 times, causing severe slowdown. | Synchronous full-file serialization on every chunk without debouncing or batching. |
| **E-09** | EPUB Missing NCX/Nav | Reading an EPUB that lacks an NCX navigation item | `ebooklib.epub.read_epub()` throws `AttributeError: 'NoneType' object has no attribute 'get_name'`. | EbookLib spine reader requires NCX table fallback handling. |
| **E-10** | Windows Console Unicode | Printing Japanese/Chinese source text to console | Python throws `UnicodeEncodeError: 'charmap' codec can't encode characters` under cp1252 Windows console. | Default Windows standard output encoding is not UTF-8 unless configured. |
| **E-11** | Streamlit CSS Absence | Inspecting `app.py` source code | No `<style>` tag exists in `app.py`; UI renders in generic default Streamlit appearance. | AC-4 is completely unfulfilled in the current codebase. |
| **E-12** | Navigation Document Translation | EPUB document items include `nav.xhtml` | Table of contents headings and links in `nav.xhtml` are translated as regular narrative chunks. | `get_items_of_type(ITEM_DOCUMENT)` returns both story chapters and navigation files. |

---

## 5. Architectural Deep-Dive & Gap Analysis

### 5.1 R1: EPUB Pipeline (`utils/epub_parser.py`, `utils/state_manager.py`)

#### Critical Finding 1: Tag Stripping Violation (AC-3)
Acceptance Criterion AC-3 explicitly requires:
> *"The EPUB parser logic successfully identifies text nodes without stripping surrounding HTML tags."*

In the current `app.py` implementation:
```python
soup, nodes = parser.extract_chunks(item)
for chunk_idx, node in enumerate(nodes):
    ...
    node.string = translated_text
item.set_content(str(soup).encode('utf-8'))
```
When `node` contains inline markup (such as `<em>`, `<strong>`, `<span>`, `<a>`, `<ruby>`, `<rt>`), BeautifulSoup's `.string = ...` assignment wipes out all children. For example:
- **Original HTML**: `<p class="dialogue">"Stay back!" she cried, drawing her <em>silver blade</em>.</p>`
- **Observed Replacement**: `<p class="dialogue">"Mundur!" teriaknya sambil menghunus pedang peraknya.</p>`
The `<em>` tag is completely destroyed, degrading the formatting and typography of the published book.

**Required Architectural Fix**:
Instead of replacing entire parent tags with strings, the parser must identify granular text nodes (`NavigableString`) or replace text within leaf text segments, or wrap inline formatting tokens (e.g., using XML-safe markers) so that inline styling is preserved without loss.

#### Critical Finding 2: State Resumability Severed by Temp Files
In `app.py`:
```python
with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp_file:
    tmp_file.write(uploaded_file.getvalue())
    tmp_path = tmp_file.name
parser = EpubParser(tmp_path)
state_manager = StateManager(parser.book_name)
```
Because `parser.book_name` is taken from `os.path.splitext(os.path.basename(tmp_path))[0]`, its name is randomized on every single session (e.g., `tmpa8f2g`). When a user restarts the app or re-uploads the novel to continue, the progress file created is `..tmpa8f2g_progress.json`, while the new session looks for `..tmp9b1kc_progress.json`. State is completely lost across sessions.

**Required Architectural Fix**:
Pass `uploaded_file.name` or the internal EPUB metadata title (`book.get_metadata('DC', 'title')`) as the book identifier to `StateManager`.

#### Critical Finding 3: I/O Bottleneck for 500+ Pages
In a 500-page novel containing ~10,000 paragraphs, calling `save_state()` on every paragraph means rewriting a growing multi-megabyte JSON file 10,000 times. On typical consumer hardware, this adds tens of minutes of pure disk wait time and risks SSD wear.

**Required Architectural Fix**:
Implement batch flushing: update internal memory state immediately, and flush to disk every N chunks (e.g., every 5 chunks) and at the end of each chapter.

---

### 5.2 R2: Agentic Translation Engine (`core/agentic_translator.py`, `core/prompts.py`)

#### Critical Finding 1: Prompt Leaks & Placeholders
In `core/prompts.py`:
```python
def get_draft_prompt(source_lang, target_lang, glossary=""):
...
Teks Asli:
{text}

Terjemahkan teks di atas ke dalam bahasa {target_lang}.
```
Because the string uses double curly braces `{{text}}` inside an f-string, it returns `{text}` literally. In `core/agentic_translator.py`:
```python
draft_sys_prompt = get_draft_prompt(source_lang, target_lang, glossary)
draft_text = self._call_llm(draft_sys_prompt, text)
```
The `{text}` placeholder is never substituted! The LLM receives `{text}` in its system prompt and the actual text in the user prompt.

#### Critical Finding 2: Glossary Dropped in Final Improvement Step
The glossary is only injected into `get_draft_prompt()`. In `get_reflect_prompt()` and `get_improve_prompt()`, no glossary context is provided. If the Master Rewriter rewrites the text in Step 3, it lacks the glossary rules and frequently substitutes different synonyms for specialized names and fantasy terminology.

**Required Architectural Fix**:
Pass glossary constraints into Step 3 (`get_improve_prompt`) to ensure the final rewritten output strictly preserves defined terms.

---

### 5.3 R3: Streamlit UI with Taste-Skill CSS (`app.py`)

#### Critical Finding 1: Total Absence of Custom CSS (AC-4)
The current `app.py` has no `st.markdown("<style>...</style>")` call. It renders with default Streamlit styling.
Acceptance Criterion AC-4 requires explicit custom CSS injection adhering to `taste-skill` standards:
- Editorial typography (system serif/sans-serif hierarchies, banned Inter/Roboto/Open Sans).
- Warm monochrome palette (`#FFFFFF` surfaces, `#F7F6F3` canvas, `#111111` off-black typography, `#EAEAEA` subtle borders).
- Anti-generic aesthetics (no AI-purple gradients, no dark mesh backgrounds, no heavy drop shadows).
- Bento card framing for configuration and upload panels.

#### Critical Finding 2: UI Freezing & Lack of Live Feedback
In `app.py`, `log_container = st.container()` is initialized but never updated during translation. The progress bar only increments per chapter `(i + 1) / total_items`. For a 500-page book with 20 chapters, each chapter takes 20-30 minutes, during which the progress bar sits completely frozen with zero feedback.
Chunk-level progress metrics and live previews of Draft, Reflection, and Improvement are necessary for a responsive user experience.

---

## 6. Verification and Testing Strategy

To satisfy ECC 2.2.0 testing requirements and project acceptance criteria:

### 6.1 Automated Test Plan (`tests/`)

1. **Compilation Test (`tests/test_compilation.py`)**:
   - Executes `python -m py_compile app.py core/*.py utils/*.py`.
   - Verifies all files compile without syntax errors (AC-1).

2. **EPUB Parser & Tag Preservation Test (`tests/test_epub_parser.py`)**:
   - Synthesizes a mock HTML document containing inline formatting tags (`<em>`, `<strong>`, `<span>`, `<a>`, `<ruby>`, `<rt>`).
   - Verifies that text extraction isolates translatable content without stripping or dropping child tags (AC-2, AC-3).
   - Verifies repacking produces valid XHTML.

3. **State Manager Resumability Test (`tests/test_state_manager.py`)**:
   - Initializes `StateManager` with a known book identifier.
   - Marks chunks 0 to 5 as translated and persists state.
   - Instantiates a second `StateManager` instance with the same identifier; asserts chunks 0 to 5 are recognized as translated and their content is intact (AC-2, AC-6).
   - Verifies atomic file write and graceful error handling on corrupt JSON files.

4. **Agentic Translator Unit Test (`tests/test_agentic_translator.py`)**:
   - Mocks `litellm.completion` to simulate LLM responses.
   - Tests Case A: Proofreader outputs "TIDAK ADA REVISI" -> Asserts exactly 2 LLM calls executed and draft returned directly (AC-7).
   - Tests Case B: Proofreader outputs critique -> Asserts exactly 3 LLM calls executed and final improvement returned (AC-7).
   - Tests Case C: Prompt formatting with curly braces `{}` in text -> Asserts no `KeyError` or `ValueError` raised.
   - Tests Case D: Glossary retention -> Asserts glossary instructions exist in Step 1 and Step 3 prompts.

5. **Taste-Skill CSS Verification (`tests/test_ui_styling.py`)**:
   - Inspects `app.py` to ensure `st.markdown("<style>...</style>", unsafe_allow_html=True)` is present and contains required palette and typographic rules (AC-4).

---

## 7. Next Steps for Implementation

1. **Phase 1: EPUB Pipeline & Tag Preservation (`utils/`)**:
   - Fix `utils/epub_parser.py` to preserve inline markup during text extraction and replacement.
   - Update `utils/state_manager.py` with atomic writes, batch flushing, and persistent book naming.
2. **Phase 2: Agentic Translation Engine (`core/`)**:
   - Correct prompt placeholders in `core/prompts.py`.
   - Add glossary injection into Step 3 (Improvement).
   - Implement safe brace formatting and robust LiteLLM exception handling.
3. **Phase 3: Streamlit UI & Taste-Skill CSS (`app.py`)**:
   - Inject comprehensive Taste-Skill CSS styling into `app.py`.
   - Implement dual progress bars (chapter and chunk level) and live translation preview console.
   - Fix temporary file naming so `StateManager` receives the original filename.
4. **Phase 4: Test Suite & ECC Compliance (`tests/`)**:
   - Build automated tests in `tests/` covering AC-1 through AC-8.
   - Verify 80%+ test pass rate and total adherence to ECC standards.
