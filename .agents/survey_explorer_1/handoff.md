# Handoff Report: Codebase State Survey

**Agent**: Codebase State Surveyor (`survey_explorer_1`)  
**Parent / Recipient**: `89c23ebb-eae6-41b7-bc9d-3dbc4e374d7b`  
**Working Directory**: `c:\Mek Project\novelproject\.agents\survey_explorer_1`  
**Target Path**: `c:\Mek Project\novelproject`  
**Date**: 2026-09-21  

---

## 1. Observation

### Codebase Inventory & Syntax Check
- **Files in scope**:
  - `app.py` (142 lines, 5,854 bytes)
  - `core/agentic_translator.py` (63 lines, 2,571 bytes)
  - `core/prompts.py` (64 lines, 2,183 bytes)
  - `utils/epub_parser.py` (46 lines, 1,779 bytes)
  - `utils/state_manager.py` (42 lines, 1,767 bytes)
  - `requirements.txt` (7 lines, 106 bytes)
- **Compilation Check**:
  Command: `python -m py_compile app.py core/prompts.py core/agentic_translator.py utils/epub_parser.py utils/state_manager.py`
  Result: Exit code 0, 0 stderr (all files compile without syntax errors).
- **Python Environment**:
  Command: `python --version` -> `Python 3.12.10`
  Package status: All packages (`streamlit` 1.64.0, `beautifulsoup4` 4.15.0, `EbookLib` 0.20, `litellm` 1.102.0, `python-dotenv` 1.2.3, `tqdm` 4.68.4, `lxml` 6.1.3) are installed and import cleanly.

### Defect 1: EPUB Inline Tag Destruction & Missing Text (Verbatim Evidence)
- **Source**: `utils/epub_parser.py` lines 28–41:
  ```python
  target_tags = ['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
  ...
  has_block_child = any(child.name in target_tags for child in tag.children if child.name)
  if not has_block_child:
      nodes.append(tag)
  ```
  and `app.py` line 60:
  ```python
  node.string = translated_text
  ```
- **Empirical test result** from `.agents/survey_explorer_1/verify_components.py`:
  - Input: `<p class="calibre2">This paragraph has <em>inline emphasis</em> and <b>bold</b> words.</p>`
  - Output after `node.string`: `<p class="calibre2">Paragraf ini memiliki penekanan dan kata tebal.</p>`
  - `Did <em> survive node.string replacement?: False` (all inline tags obliterated).
  - Input: `<p class="calibre3">This paragraph has a <span class="styled">styled span</span> inside it.</p>`
  - Nodes captured: `['styled span']`. The surrounding paragraph text (`"This paragraph has a "` and `" inside it."`) was skipped and never translated.

### Defect 2: Broken Resume in State Manager (Verbatim Evidence)
- **Source**: `app.py` lines 12–19:
  ```python
  with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp_file:
      tmp_file.write(uploaded_file.getvalue())
      tmp_path = tmp_file.name
  parser = EpubParser(tmp_path)
  state_manager = StateManager(parser.book_name)
  ```
- `parser.book_name` in `utils/epub_parser.py` line 12:
  ```python
  self.book_name = os.path.splitext(os.path.basename(file_path))[0]
  ```
- **Observed Result**: Every upload yields a unique random temporary filename (e.g. `tmp_x78abc`). `StateManager` generates `.{tmp_x78abc}_progress.json`. Subsequent uploads of the same novel generate new temp filenames, making resume completely fail.

### Defect 3: Acceptance Criteria R3 Failure (Missing Custom CSS & Taste Guidelines)
- `ORIGINAL_REQUEST.md` Line 35:
  `- [ ] The app.py script contains explicit custom CSS injection (st.markdown("<style>...</style>")) reflecting a customized UI.`
- In `app.py`: There are zero occurrences of `<style>` or `st.markdown("<style>...</style>")`.
- In `app.py`: Contains emojis (`📚`, `⚙️`, `📖`, `🚀`, `✅`, `⬇️`), which violates `minimalist-ui` Absolute Negative Constraints line 20: *"DO NOT use emojis anywhere in code, markup, text content, headings, or alt text."*

### Defect 4: Missing Tests & Package Structure
- `find_by_name` for `__init__.py` under `core` and `utils`: 0 results.
- `find_by_name` for `tests`: No test files exist for the novel translator. Current test coverage is 0% (ECC requires 80%+ with TDD).

---

## 2. Logic Chain

1. **Premise 1**: Acceptance Criterion R1 requires the EPUB pipeline to extract HTML text nodes and repack without breaking original styles or formatting.
2. **Observation 1**: Assigning `node.string = translated_text` in BeautifulSoup strips all inner child elements (`<em>`, `<b>`, `<i>`, `<a>`, `<ruby>`). Additionally, treating `'span'` as a block child skips paragraph wrappers, causing outer text to be omitted from translation.
3. **Inference 1**: The current EPUB parser directly violates Acceptance Criterion R1 and produces damaged EPUBs.
4. **Premise 2**: Acceptance Criterion R3 requires `app.py` to contain explicit custom CSS injection (`st.markdown("<style>...</style>")`) and follow taste-skill standards.
5. **Observation 2**: `grep_search` and inspection of `app.py` show zero instances of `<style>` and multiple forbidden emojis.
6. **Inference 2**: `app.py` fails Acceptance Criterion R3.
7. **Premise 3**: The user request specifies a robust workflow for 500+ page novels.
8. **Observation 3**: State tracking relies on random tempfile names (breaking resume), executes 3 API calls per chunk sequentially (~15,000 calls per book), lacks batching and streaming, writes to disk on every chunk synchronously, and places download buttons inside transient button callbacks.
9. **Inference 3**: The current prototype cannot successfully or reliably translate a 500+ page novel in production without major refactoring.

---

## 3. Caveats

- We did not execute live LLM calls against paid API endpoints (OpenAI, Anthropic, Gemini) as no API keys were provided in the survey request; LiteLLM completion logic was verified via static code analysis and dependency import verification.
- The global Python environment contains all necessary packages, but no isolated virtual environment (`.venv`) exists in the project root. Future implementations may prefer an isolated virtual environment.

---

## 4. Conclusion

The codebase contains a rudimentary structural skeleton that passes Python syntax validation, but it **fails 2 out of 3 core acceptance criteria** (EPUB style preservation and Taste-Skill custom CSS injection) and has a broken state resume mechanism.

**Specific Required Actions for Implementer**:
1. Refactor `utils/epub_parser.py` to parse block-level tags while preserving inline markup (`<em>`, `<b>`, `<i>`, `<span>`, `<a>`, `<ruby>`), and update prompts to instruct the LLM to preserve inline HTML tags.
2. Fix `utils/state_manager.py` and `app.py` to key progress files by file hash or clean book title instead of `tempfile.NamedTemporaryFile` random paths, and store them in `.cache/` or `.state/`.
3. Overhaul `app.py` with explicit custom CSS (`st.markdown("<style>...</style>", unsafe_allow_html=True)`) adhering to `minimalist-ui` (editorial serif/sans typography, warm monochrome palette, no emojis, bento grid layout), with `st.session_state` persistence and an agentic inspection panel.
4. Add `core/__init__.py`, `utils/__init__.py`, and a complete `tests/` suite achieving 80%+ test coverage under ECC TDD standards.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

1. **Verify Syntax Compilation**:
   ```powershell
   python -m py_compile app.py core/prompts.py core/agentic_translator.py utils/epub_parser.py utils/state_manager.py
   ```
2. **Verify EPUB Tag Stripping & Span Bug**:
   Run the empirical test script:
   ```powershell
   python .agents/survey_explorer_1/verify_components.py
   ```
   Inspect stdout for `Did <em> survive node.string replacement?: False` and `What got extracted from p.calibre3: ['styled span']`.
3. **Verify Absence of Custom CSS in `app.py`**:
   ```powershell
   python -c "content = open('app.py', encoding='utf-8').read(); print('Has <style> tag:', '<style>' in content)"
   ```
   Output will be `False`.
4. **Verify Dependencies**:
   ```powershell
   python -c "import streamlit, litellm, bs4, ebooklib, dotenv, tqdm; print('All modules imported successfully')"
   ```
