# Original User Request

## 2026-09-21T04:14:18Z

# Teamwork Project Prompt — Draft

> Status: Launched.
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: [none — teamwork routes from the description]

Build a local web app (Agentic Novel Translator) that translates 500+ page EPUBs to Indonesian using LiteLLM and a Draft-Reflect-Improve workflow. The UI must use Streamlit with custom CSS to apply `taste-skill` design principles, and the codebase must be modular following ECC workflow standards.

Working directory: c:\Mek Project\novelproject\novel-translator
Integrity mode: development

## Requirements

### R1. EPUB Pipeline
Implement an EPUB parser (`utils/epub_parser.py`) and state manager (`utils/state_manager.py`) capable of extracting HTML text nodes, tracking completion state per chunk, and repacking the EPUB without breaking original styles or formatting.

### R2. Agentic Translation Engine
Implement the translation loop (`core/agentic_translator.py`) utilizing LiteLLM with a 3-step Draft, Reflect, and Improve prompt chain, including glossary mapping support.

### R3. Streamlit UI with Taste-Skill CSS
Build a Streamlit dashboard (`app.py`) for EPUB upload, API key input, glossary configuration, and live progress tracking. Inject custom CSS to elevate the design following `taste-skill` standards (minimalist, clean typography, anti-generic).

## Acceptance Criteria

### Core Execution
- [ ] Running `python -m py_compile app.py` and other core files passes without syntax errors.
- [ ] Processing a mock HTML string or tiny EPUB through the parser and state manager runs without throwing exceptions.
- [ ] The EPUB parser logic successfully identifies text nodes without stripping surrounding HTML tags.

### Design and Standards
- [ ] The `app.py` script contains explicit custom CSS injection (`st.markdown("<style>...</style>")`) reflecting a customized UI.
- [ ] The codebase is cleanly modularized into at least `core/`, `utils/`, and `app.py`.
