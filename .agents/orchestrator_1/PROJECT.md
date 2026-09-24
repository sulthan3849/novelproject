# Project: Agentic Novel Translator

## Architecture
- **utils/epub_parser.py**: Parses EPUB files using `ebooklib` and `BeautifulSoup4`. Extracts text nodes by differentiating Block elements (`<p>`, `<blockquote>`, `<h1>`-`<h6>`, `<li>`, `<td>`, `<th>`, `<aside>`, `<caption>`, `<section>`) from Inline markup (`<em>`, `<strong>`, `<span>`, `<a>`, `<i>`, `<b>`, `<ruby>`). Skips outer container divs to extract innermost leaf text nodes without DOM detachment. Replaces inner contents without deleting surrounding or nested HTML tags. Repacks the translated document into a valid EPUB structure preserving all stylesheets and metadata.
- **utils/state_manager.py**: Tracks progress per chunk and chapter. Keys state using a stable SHA-256 content hash. Uses thread locking (`threading.Lock`), crash-resilient atomic persistence (`.tmp` -> `os.replace` with Windows retry loop), multi-instance progress merging, and schema corruption recovery (`.corrupted_<ts>` backup).
- **core/prompts.py**: Prompt engineering module for the 3-step translation loop (Draft -> Reflect -> Improve) calibrated for literary, publisher-grade Indonesian (Gramedia standard). Enforces glossary mapping across all three stages and supports `[STATUS: PERFECT]` fast-path indicator.
- **core/agentic_translator.py**: Executes the LiteLLM agentic loop. Passes `api_key` explicitly into `litellm.completion()`, handles jittered exponential backoff for rate limits, applies glossary mappings across draft, reflect, and improve, supports fast-path bypass on `[STATUS: PERFECT]`, and tracks token / latency telemetry.
- **app.py**: Streamlit application with bespoke Taste-Skill CSS styling (Minimalist Editorial / Anti-Generic, clean typography, obsidian dark cards, bento metrics, monospace terminal for logs, split-pane original vs translated preview, download button, session flush in finally block).
- **tests/**: Automated unit, integration, and adversarial stress test suite meeting ECC standards (63 tests, 91% code coverage, offline mock harnesses).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | EPUB Text Extraction | Extract text blocks from EPUB spine items | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Inline Tag Preservation | Identify text nodes without stripping inline HTML tags (`<em>`, `<span>`, etc.) | M1 | ORIGINAL_REQUEST §R1, AC-3 |
| 3 | EPUB Repacking | Repack modified spine items into valid EPUB with intact CSS/metadata | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Stable Book Keying | Key StateManager by content SHA-256 hash to allow resumption across sessions | M1 | Survey Finding |
| 5 | Atomic State Persistence | Save state via tempfile and atomic rename to prevent JSON corruption | M1 | Survey Finding |
| 6 | Chunk Completion Tracking | Record translated status, text, and timestamp per chunk | M1 | ORIGINAL_REQUEST §R1 |
| 7 | Draft Prompt Generation | System prompt for initial literary translation with glossary | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Reflect Prompt Generation | System prompt for critique of tone, fluency, and terminology with fast-path | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Improve Prompt Generation | System prompt for final polishing with persistent glossary context | M2 | ORIGINAL_REQUEST §R2 |
| 10 | LiteLLM Integration | Direct API key passing to `litellm.completion` for multi-provider support | M2 | ORIGINAL_REQUEST §R2 |
| 11 | 3-Step Agentic Loop | Draft -> Reflect -> Improve execution flow with Fast-Path bypass | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Glossary Mapping Support | Terminology injection and enforcement across translation steps | M2 | ORIGINAL_REQUEST §R2 |
| 13 | Rate Limit & Retry Logic | Exponential backoff with jitter on API failure | M2 | Survey Finding |
| 14 | Taste-Skill CSS Injection | Bespoke CSS injected via `st.markdown("<style>...</style>")` | M3 | ORIGINAL_REQUEST §R3, AC-4 |
| 15 | File Upload & Hash | Upload EPUB and generate persistent session hash | M3 | ORIGINAL_REQUEST §R3 |
| 16 | API Configuration | UI inputs for LiteLLM provider, model name, and API key | M3 | ORIGINAL_REQUEST §R3 |
| 17 | Glossary Editor | UI table/input for user-defined terminology glossary | M3 | ORIGINAL_REQUEST §R3 |
| 18 | Live Progress & Bento Telemetry | Bento grid displaying progress percentage, chunk count, tokens, cost estimate | M3 | ORIGINAL_REQUEST §R3 |
| 19 | Live Preview Pane | Split view of original text block vs translated Indonesian text | M3 | ORIGINAL_REQUEST §R3 |
| 20 | EPUB Export & Download | Repack and serve the translated EPUB for download | M3 | ORIGINAL_REQUEST §R3 |
| 21 | Test Suite & Harness | Comprehensive pytest suite for utils, core, and integration (63 tests, 91% cov) | M4 | ORIGINAL_REQUEST §AC, ECC Rule |
| 22 | Forensic Integrity Audit | Systematic audit for authentic implementation and zero hardcoded fakes | M5 | Coordination Rule 3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | EPUB Pipeline & State Management | `utils/epub_parser.py`, `utils/state_manager.py`, `utils/__init__.py` | none | DONE |
| M2 | Agentic Translation Engine | `core/prompts.py`, `core/agentic_translator.py`, `core/__init__.py` | none | DONE |
| M3 | Streamlit UI with Taste-Skill CSS | `app.py` | M1, M2 | DONE |
| M4 | E2E Testing Suite | `tests/`, `TEST_READY.md` | M1, M2, M3 | DONE |
| M5 | Review, Challenge & Forensic Audit | Verification, review approval, challenger tests, auditor clean verdict | M4 | DONE |

## Interface Contracts
### `utils.epub_parser.EpubParser`
```python
class EpubParser:
    def __init__(self, file_path: str, book_hash: Optional[str] = None): ...
    def extract_chunks(self) -> List[Dict[str, Any]]: ...
    def update_node(self, node: Any, translated_text_or_html: str) -> None: ...
    def repack(self, output_path: str) -> str: ...
```

### `utils.state_manager.StateManager`
```python
class StateManager:
    def __init__(self, book_identifier: str, total_chunks: int = 0, state_dir: Optional[str] = None): ...
    def is_chunk_translated(self, item_id: str, node_index: int) -> bool: ...
    def mark_chunk_translated(self, item_id: str, node_index: int, translated_text: str, original_text: str = "") -> None: ...
    def get_translated_chunk(self, item_id: str, node_index: int) -> Optional[str]: ...
    def get_progress(self) -> Dict[str, Any]: ...
    def flush(self) -> None: ...
    def save_state(self) -> None: ...
```

### `core.agentic_translator.AgenticTranslator`
```python
class AgenticTranslator:
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None, source_lang: str = "English", target_lang: str = "Indonesian", glossary: Optional[Dict[str, str]] = None): ...
    def translate_chunk(self, text: str, context: Optional[str] = None) -> TranslationResult: ...
```

## Code Layout
```
c:\Mek Project\novelproject\
├── app.py                      # Streamlit UI with taste-skill CSS
├── core/
│   ├── __init__.py
│   ├── agentic_translator.py   # LiteLLM Draft-Reflect-Improve loop
│   └── prompts.py              # System prompts with glossary support
├── utils/
│   ├── __init__.py
│   ├── epub_parser.py          # EPUB BeautifulSoup DOM parser and repacker
│   └── state_manager.py        # Content-hashed thread-safe atomic state manager
├── tests/
│   ├── __init__.py
│   ├── test_epub_pipeline.py   # Tests for parsing, tag preservation, repacking
│   ├── test_state_manager.py   # Tests for persistence, hashing, resume
│   ├── test_agentic_loop.py    # Tests for LiteLLM loop, prompts, fast path
│   ├── test_e2e_integration.py # End-to-end translation pipeline test
│   └── test_adversarial_reverification.py # Adversarial stress tests (concurrency, corruption, leaf divs)
├── TEST_INFRA.md
├── TEST_READY.md
└── requirements.txt
```
