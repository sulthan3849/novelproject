## 2026-09-21T04:20:46Z

You are Worker 1 (Implementation Track).
Working directory: c:\Mek Project\novelproject\.agents\worker_1
Project root: c:\Mek Project\novelproject

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Required reading before starting:
1. ORIGINAL_REQUEST.md: c:\Mek Project\novelproject\.agents\ORIGINAL_REQUEST.md
2. PROJECT.md: c:\Mek Project\novelproject\.agents\PROJECT.md
3. Survey reports:
   - c:\Mek Project\novelproject\.agents\survey_explorer_1\handoff.md
   - c:\Mek Project\novelproject\.agents\survey_spec_miner_1\handoff.md
   - c:\Mek Project\novelproject\.agents\survey_explorer_2\handoff.md
4. Taste skills:
   - c:\Mek Project\novelproject\.agents\skills\minimalist-ui\SKILL.md
   - c:\Mek Project\novelproject\.agents\skills\design-taste-frontend\SKILL.md

Exclusive file write ownership:
- utils/epub_parser.py
- utils/state_manager.py
- utils/__init__.py
- core/prompts.py
- core/agentic_translator.py
- core/__init__.py
- app.py

Implementation Tasks:
1. M1 - EPUB Pipeline (utils/epub_parser.py & utils/state_manager.py):
   - In epub_parser.py: Refactor DOM node extraction. Differentiate Block elements ('p', 'blockquote', 'h1'-'h6', 'li') from Inline formatting elements ('em', 'strong', 'span', 'a', 'i', 'b', 'ruby'). Text extraction must NEVER strip inline tags or discard paragraphs containing spans. When updating a node with translated text/HTML, preserve outer tag attributes (class, id, style) and re-insert translated content cleanly. Provide robust repacking.
   - In state_manager.py: Key progress tracking using a stable hash (SHA-256 of the EPUB file bytes or normalized book title) so that file uploads and sessions can reliably resume without starting from 0. Implement atomic disk persistence (writing to .tmp and os.replace). Add batch-saving or in-memory dirty tracking to avoid disk bottlenecks across 500+ page novels.
   - Add utils/__init__.py.

2. M2 - Agentic Translation Engine (core/prompts.py & core/agentic_translator.py):
   - In prompts.py: Fix the literal '{text}' placeholder leak in get_draft_prompt. Add glossary parameter support to get_improve_prompt so terminology is strictly preserved across all 3 steps. Calibrate reflection prompt for publishing-standard Indonesian literary prose and support '[STATUS: PERFECT]' marker for fast-path bypass.
   - In agentic_translator.py: Pass api_key directly to litellm.completion(..., api_key=self.api_key) rather than mutating os.environ['API_KEY']. Implement the 3-step loop (Draft -> Reflect -> Improve) with Fast-Path bypass when reflect indicates [STATUS: PERFECT]. Implement exponential backoff with jitter on API rate limit or network errors.
   - Add core/__init__.py.

3. M3 - Streamlit UI with Taste-Skill CSS (app.py):
   - Inject comprehensive custom CSS via st.markdown("<style>...</style>", unsafe_allow_html=True) adhering to minimalist-ui and design-taste-frontend standards:
     * Dark obsidian palette (#0D0F12 background, #16191F cards/containers, #E6E8EC text, #5E6AD2 or warm muted accent).
     * Refined typography (Inter/Geist/sans-serif, clean hierarchy, no giant generic banners).
     * Bento metric cards (chunks processed, ETA, tokens used, estimated cost).
     * Monospace live log terminal showing translation status.
     * Clean split-pane inspection (Original text vs Translated Indonesian).
     * Stable content hashing of uploaded EPUBs to connect directly with StateManager for seamless resume.
     * Eliminate all generic AI emojis (📚, 🚀, etc.) in favor of clean typographic labels.
     * Export / Download button for repacked EPUB.

Verification:
- Run python -m py_compile app.py core/agentic_translator.py core/prompts.py utils/epub_parser.py utils/state_manager.py
- Test mock EPUB / HTML parsing to ensure inline tags ('<em>', '<b>') are preserved 100%.
- Document all changes, test commands, and outputs in c:\Mek Project\novelproject\.agents\worker_1\handoff.md.
- Send a message when finished.
