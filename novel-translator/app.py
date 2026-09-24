import hashlib
import os
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import streamlit as st

from core.agentic_translator import AgenticTranslator
from utils.epub_parser import EpubParser
from utils.state_manager import StateManager

# Set page configuration with clean typographic branding (strictly zero emojis)
st.set_page_config(
    page_title="Agentic Novel Translator",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Comprehensive Taste-Skill Custom CSS injection adhering to minimalist-ui & design-taste-frontend
CUSTOM_CSS = """
<style>
/* Base canvas and typography reset */
html, body, [class*="css"] {
    font-family: 'Geist', 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #E6E8EC;
}

.stApp {
    background-color: #0D0F12;
    color: #E6E8EC;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #12151B;
    border-right: 1px solid #222731;
}

section[data-testid="stSidebar"] hr {
    border-color: #222731;
    margin: 1.5rem 0;
}

/* Typography hierarchy */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Geist', 'SF Pro Display', sans-serif;
    font-weight: 600;
    color: #FFFFFF;
    letter-spacing: -0.02em;
}

.app-title {
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #FFFFFF;
    margin-bottom: 0.25rem;
    display: flex;
    align-items: center;
    gap: 10px;
}

.app-badge {
    font-family: 'Geist Mono', 'SF Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background-color: #1E232D;
    color: #5E6AD2;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid rgba(94, 106, 210, 0.3);
}

.app-subtitle {
    font-size: 0.95rem;
    color: #8B949E;
    margin-bottom: 2rem;
    line-height: 1.5;
}

/* Bento grid telemetry cards */
.bento-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 1.75rem;
}

.bento-card {
    background-color: #16191F;
    border: 1px solid #222731;
    border-radius: 8px;
    padding: 16px 20px;
    transition: border-color 0.15s ease;
}

.bento-card:hover {
    border-color: #2E3545;
}

.bento-label {
    font-family: 'Geist Mono', 'SF Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8B949E;
    margin-bottom: 6px;
}

.bento-value {
    font-size: 22px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.02em;
    line-height: 1.2;
}

.bento-subtext {
    font-size: 12px;
    color: #6E7681;
    margin-top: 4px;
}

/* Inspection split pane */
.inspection-container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 1.5rem;
}

.inspection-pane {
    background-color: #16191F;
    border: 1px solid #222731;
    border-radius: 8px;
    padding: 20px;
    min-height: 200px;
    font-size: 14px;
    line-height: 1.6;
    color: #C9D1D9;
}

.pane-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #222731;
    padding-bottom: 10px;
    margin-bottom: 12px;
    font-family: 'Geist Mono', 'SF Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8B949E;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 9999px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.badge-fastpath {
    background-color: #2E2A1A;
    color: #FBBF24;
    border: 1px solid rgba(251, 191, 36, 0.25);
}

.badge-standard {
    background-color: #1E232D;
    color: #5E6AD2;
    border: 1px solid rgba(94, 106, 210, 0.25);
}

.badge-success {
    background-color: #162B22;
    color: #34D399;
    border: 1px solid rgba(52, 211, 153, 0.25);
}

/* Monospace live log terminal */
.terminal-window {
    background-color: #0A0C0E;
    border: 1px solid #222731;
    border-radius: 8px;
    font-family: 'Geist Mono', 'SF Mono', 'JetBrains Mono', monospace;
    font-size: 12px;
    color: #8B949E;
    padding: 16px;
    margin-top: 1rem;
    max-height: 240px;
    overflow-y: auto;
}

.terminal-header {
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid #1E232D;
    padding-bottom: 8px;
    margin-bottom: 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: #6E7681;
}

.terminal-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #34D399;
    display: inline-block;
}

.terminal-line {
    line-height: 1.6;
    margin-bottom: 3px;
    word-break: break-all;
}

.terminal-time {
    color: #484F58;
    margin-right: 6px;
}

.terminal-tag {
    color: #5E6AD2;
    font-weight: 600;
    margin-right: 6px;
}

.terminal-tag-success {
    color: #34D399;
    font-weight: 600;
    margin-right: 6px;
}

.terminal-tag-warning {
    color: #FBBF24;
    font-weight: 600;
    margin-right: 6px;
}

/* Form controls override */
.stTextInput input, .stSelectbox [data-baseweb="select"], .stTextArea textarea {
    background-color: #16191F !important;
    color: #E6E8EC !important;
    border: 1px solid #2A2F3D !important;
    border-radius: 6px !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #5E6AD2 !important;
    box-shadow: 0 0 0 1px #5E6AD2 !important;
}

/* Primary buttons */
.stButton > button {
    background-color: #16191F;
    color: #E6E8EC;
    border: 1px solid #2E3545;
    border-radius: 6px;
    font-weight: 500;
    letter-spacing: 0.02em;
    padding: 0.55rem 1.25rem;
    transition: all 0.15s ease;
}

.stButton > button:hover {
    background-color: #1E232D;
    border-color: #5E6AD2;
    color: #FFFFFF;
}

.stButton > button[kind="primary"] {
    background-color: #5E6AD2;
    color: #FFFFFF;
    border: 1px solid #5E6AD2;
    font-weight: 600;
}

.stButton > button[kind="primary"]:hover {
    background-color: #4D58C0;
    border-color: #4D58C0;
}

/* Download button */
.stDownloadButton > button {
    background-color: #162B22 !important;
    color: #34D399 !important;
    border: 1px solid rgba(52, 211, 153, 0.4) !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
}

.stDownloadButton > button:hover {
    background-color: #1E3A2F !important;
    border-color: #34D399 !important;
    color: #FFFFFF !important;
}

/* Streamlit alerts override */
div[data-testid="stAlert"] {
    background-color: #16191F;
    border: 1px solid #2A2F3D;
    border-radius: 6px;
    color: #E6E8EC;
}

/* Streamlit progress bar override */
.stProgress > div > div > div > div {
    background-color: #5E6AD2;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def parse_glossary(text: str) -> Dict[str, str]:
    """Parses user input glossary strings into key-value pairs."""
    glossary = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "->" in line:
            parts = line.split("->", 1)
            glossary[parts[0].strip()] = parts[1].strip()
        elif ":" in line:
            parts = line.split(":", 1)
            glossary[parts[0].strip()] = parts[1].strip()
    return glossary


def render_bento_metrics(
    completed_chunks: int,
    total_chunks: int,
    fast_path_count: int,
    total_tokens: int,
    cost_estimate: float,
):
    """Renders the 4-cell Bento Grid Telemetry Cards."""
    pct = (completed_chunks / total_chunks * 100.0) if total_chunks > 0 else 0.0
    fp_pct = (fast_path_count / max(1, completed_chunks) * 100.0) if completed_chunks > 0 else 0.0

    st.markdown(
        f"""
        <div class="bento-grid">
            <div class="bento-card">
                <div class="bento-label">CHUNKS PROCESSED</div>
                <div class="bento-value">{completed_chunks:,} <span style="font-size: 14px; font-weight: normal; color: #8B949E;">/ {total_chunks:,}</span></div>
                <div class="bento-subtext">{pct:.1f}% total completion</div>
            </div>
            <div class="bento-card">
                <div class="bento-label">PIPELINE EFFICIENCY</div>
                <div class="bento-value">{pct:.1f}%</div>
                <div class="bento-subtext">Deterministic progress</div>
            </div>
            <div class="bento-card">
                <div class="bento-label">FAST-PATH BYPASS</div>
                <div class="bento-value">{fast_path_count:,} <span style="font-size: 13px; color: #FBBF24;">({fp_pct:.0f}%)</span></div>
                <div class="bento-subtext">Step 3 bypassed on [STATUS: PERFECT]</div>
            </div>
            <div class="bento-card">
                <div class="bento-label">TELEMETRY & COST</div>
                <div class="bento-value">{total_tokens:,} <span style="font-size: 14px; font-weight: normal; color: #8B949E;">tok</span></div>
                <div class="bento-subtext">Est. cost: ${cost_estimate:.4f}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def execute_translation_loop(
    parser: EpubParser,
    state_manager: StateManager,
    translator: AgenticTranslator,
    source_lang: str,
    target_lang: str,
    glossary_dict: Dict[str, str],
    metric_placeholder: Any,
    progress_bar: Any,
    inspection_placeholder: Any,
    terminal_placeholder: Any,
) -> Optional[str]:
    """
    Main agentic translation execution loop.
    Iterates through document items in spine order, preserves inline tags,
    streams live logs to the monospace terminal, and writes atomic updates.
    """
    html_items = parser.get_html_items()
    logs: List[str] = [
        f"[{time.strftime('%H:%M:%S')}] [INIT] Pipeline started for '{parser.title}'",
        f"[{time.strftime('%H:%M:%S')}] [HASH] Content SHA-256: {parser.book_hash[:16]}...",
        f"[{time.strftime('%H:%M:%S')}] [CACHE] Resuming from atomic state ({state_manager.get_completed_count()} chunks completed)",
    ]

    def update_terminal(tag: str, msg: str, level: str = "normal"):
        ts = time.strftime("%H:%M:%S")
        tag_cls = "terminal-tag"
        if level == "success":
            tag_cls = "terminal-tag-success"
        elif level == "warning":
            tag_cls = "terminal-tag-warning"
        logs.append(f"<div class='terminal-line'><span class='terminal-time'>[{ts}]</span> <span class='{tag_cls}'>[{tag}]</span> {msg}</div>")
        terminal_html = (
            "<div class='terminal-window'>"
            "<div class='terminal-header'><span class='terminal-dot'></span> LIVE AGENTIC TELEMETRY STREAM</div>"
            + "".join(logs[-12:])
            + "</div>"
        )
        terminal_placeholder.markdown(terminal_html, unsafe_allow_html=True)

    update_terminal("START", f"Processing {len(html_items)} document items across the spine", "normal")

    total_chunks = state_manager.state.get("total_chunks", 1)
    cost_per_1k_tokens = 0.00015  # gpt-4o-mini baseline estimate

    try:
        for item_idx, item in enumerate(html_items):
            item_id = item.get_id()
            soup, nodes = parser.extract_chunks(item)

            if not nodes:
                continue

            for chunk_idx, node in enumerate(nodes):
                original_inner = "".join(str(c) for c in node.contents).strip()
                if not original_inner:
                    continue

                # Check resume state
                if state_manager.is_chunk_translated(item_id, chunk_idx):
                    translated_text = state_manager.get_translated_chunk(item_id, chunk_idx)
                    parser.update_node(node, translated_text or "")
                    continue

                # Translate using AgenticTranslator
                try:
                    result = translator.translate_chunk(
                        text=original_inner,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        glossary=glossary_dict,
                    )
                    translated_text = str(result)
                    state_manager.mark_chunk_translated(item_id, chunk_idx, translated_text, original_inner)
                    parser.update_node(node, translated_text)

                    completed = state_manager.get_completed_count()
                    progress_val = min(1.0, completed / max(1, total_chunks))
                    progress_bar.progress(progress_val)

                    # Update Bento Metrics
                    cost = (translator.total_tokens_used / 1000.0) * cost_per_1k_tokens
                    with metric_placeholder.container():
                        render_bento_metrics(
                            completed,
                            total_chunks,
                            translator.fast_path_count,
                            translator.total_tokens_used,
                            cost,
                        )

                    # Update Split-Pane Live Inspection
                    badge_html = (
                        "<span class='badge badge-fastpath'>FAST-PATH BYPASS</span>"
                        if result.fast_path
                        else "<span class='badge badge-standard'>3-STEP REFINED</span>"
                    )
                    inspection_placeholder.markdown(
                        f"""
                        <div class="inspection-container">
                            <div class="inspection-pane">
                                <div class="pane-header">
                                    <span>SOURCE TEXT &bull; ITEM {item_id} [{chunk_idx}]</span>
                                    <span class="badge" style="background:#1E232D; color:#8B949E;">{node.name.upper()}</span>
                                </div>
                                <div>{original_inner}</div>
                            </div>
                            <div class="inspection-pane">
                                <div class="pane-header">
                                    <span>INDONESIAN TRANSLATION &bull; GRAMEDIA STANDARD</span>
                                    {badge_html}
                                </div>
                                <div style="color: #FFFFFF;">{translated_text}</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # Update terminal log
                    if result.fast_path:
                        update_terminal("FAST-PATH", f"Item {item_id}:{chunk_idx} validated [STATUS: PERFECT] by editor", "warning")
                    else:
                        update_terminal("IMPROVE", f"Item {item_id}:{chunk_idx} polished by Master Rewriter", "normal")

                except Exception as e:
                    update_terminal("ERROR", f"Failed on {item_id}:{chunk_idx}: {e}", "warning")
                    st.error(f"Translation pipeline interrupted: {e}")
                    return None

            # Flush state atomically at chapter boundary
            state_manager.flush()
            update_terminal("FLUSH", f"Item {item_id} persisted atomically to disk", "success")
    finally:
        state_manager.flush()

    # Repack book
    update_terminal("REPACK", "Generating final publication-ready EPUB archive...", "normal")
    output_filename = f"{parser.book_name}_Indonesian.epub"
    output_path = os.path.join(tempfile.gettempdir(), output_filename)
    parser.repack(output_path)
    update_terminal("COMPLETE", f"Export ready: {output_filename}", "success")
    return output_path


def main():
    # Header branding
    st.markdown(
        """
        <div class="app-title">
            AGENTIC NOVEL TRANSLATOR
            <span class="app-badge">LITERARY ENGINE V2</span>
        </div>
        <div class="app-subtitle">
            Autonomous Draft-Reflect-Improve pipeline for 500+ page EPUBs calibrated for Gramedia publishing standards.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sidebar configuration
    with st.sidebar:
        st.markdown("### SYSTEM CONFIGURATION")
        api_key = st.text_input(
            "API Key",
            type="password",
            placeholder="sk-...",
            help="Directly passed to LiteLLM. Never persisted or written to os.environ.",
        )
        model_choice = st.selectbox(
            "Model Provider",
            [
                "gpt-4o-mini",
                "gpt-4o",
                "claude-3-5-sonnet-20240620",
                "claude-3-haiku-20240307",
                "gemini/gemini-1.5-pro-latest",
                "gemini/gemini-1.5-flash-latest",
            ],
            index=0,
            help="LiteLLM supported frontier model string.",
        )

        st.markdown("---")
        st.markdown("### LINGUISTIC TARGETS")
        source_lang = st.selectbox(
            "Source Language",
            ["English", "Japanese", "Chinese", "Korean", "German", "French"],
            index=0,
        )
        target_lang = st.selectbox(
            "Target Language",
            ["Indonesian (Gramedia Standard)"],
            index=0,
        )

        st.markdown("---")
        st.markdown("### PERSISTENCE & STORAGE")
        st.caption("Sessions are deterministic and keyed by EPUB SHA-256. Progress survives reloads and browser disconnects.")

    # Main layout columns: File upload and Glossary configuration
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown("#### 1. UPLOAD EPUB MANUSCRIPT")
        uploaded_file = st.file_uploader(
            "Select EPUB file",
            type=["epub"],
            help="Standard EPUB format. Structural styles and inline formatting are strictly preserved.",
            label_visibility="collapsed",
        )

    with col2:
        st.markdown("#### 2. TERMINOLOGY GLOSSARY (OPTIONAL)")
        st.caption("One mapping per line. Format: Original -> Indonesian")
        glossary_raw = st.text_area(
            "Glossary",
            height=130,
            placeholder="Shadow Sovereign -> Penguasa Bayangan\nHunter Association -> Asosiasi Pemburu\nMana Core -> Inti Mana",
            label_visibility="collapsed",
        )
        glossary_dict = parse_glossary(glossary_raw)

    st.markdown("---")

    # Document initialization and session discovery
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        book_hash = hashlib.sha256(file_bytes).hexdigest()

        # Save to deterministic cache path
        cache_dir = os.path.join(tempfile.gettempdir(), "novel_translator_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cached_epub_path = os.path.join(cache_dir, f"{book_hash}.epub")

        if not os.path.exists(cached_epub_path):
            with open(cached_epub_path, "wb") as f:
                f.write(file_bytes)

        try:
            parser = EpubParser(cached_epub_path, book_hash=book_hash)
            all_nodes = parser.extract_text_nodes()
            total_chunks = len(all_nodes)
        except Exception as e:
            st.error(f"Unable to parse EPUB file: {e}")
            return

        state_manager = StateManager(book_hash, total_chunks=total_chunks)
        completed_count = state_manager.get_completed_count()

        # Render Bento Grid before execution
        bento_placeholder = st.empty()
        with bento_placeholder.container():
            render_bento_metrics(
                completed_count,
                total_chunks,
                0,
                0,
                0.0,
            )

        # Session detection message
        if completed_count > 0 and completed_count < total_chunks:
            st.info(
                f"Existing translation session detected: {completed_count:,} of {total_chunks:,} chunks completed. "
                "Resuming will continue without re-translating completed chunks."
            )
        elif completed_count >= total_chunks and total_chunks > 0:
            st.success(
                f"Translation complete: All {total_chunks:,} chunks are finished. "
                "You can export the repacked EPUB below or reset progress to re-translate."
            )

        # Action controls
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1], gap="medium")
        
        with ctrl_col1:
            btn_label = "RESUME TRANSLATION" if completed_count > 0 else "START AGENTIC TRANSLATION"
            start_btn = st.button(btn_label, type="primary", use_container_width=True)

        with ctrl_col2:
            if st.button("RESET PROGRESS", use_container_width=True):
                state_manager.reset_state()
                st.rerun()

        with ctrl_col3:
            # Check if output already exists in session state
            saved_output_key = f"output_{book_hash}"
            if saved_output_key in st.session_state and os.path.exists(st.session_state[saved_output_key]):
                with open(st.session_state[saved_output_key], "rb") as ep_file:
                    st.download_button(
                        "EXPORT REPACKED EPUB",
                        data=ep_file,
                        file_name=f"{parser.book_name}_Indonesian.epub",
                        mime="application/epub+zip",
                        use_container_width=True,
                    )

        # Live placeholders
        progress_bar = st.progress(completed_count / max(1, total_chunks))
        inspection_placeholder = st.empty()
        terminal_placeholder = st.empty()

        # Initial inspection placeholder render
        inspection_placeholder.markdown(
            """
            <div class="inspection-container">
                <div class="inspection-pane">
                    <div class="pane-header">
                        <span>SOURCE TEXT INSPECTION</span>
                        <span class="badge" style="background:#1E232D; color:#8B949E;">STANDBY</span>
                    </div>
                    <div style="color: #6E7681;">Awaiting pipeline trigger...</div>
                </div>
                <div class="inspection-pane">
                    <div class="pane-header">
                        <span>INDONESIAN TRANSLATION</span>
                        <span class="badge" style="background:#1E232D; color:#8B949E;">STANDBY</span>
                    </div>
                    <div style="color: #6E7681;">Live translation will render here block by block.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Execution trigger
        if start_btn:
            if not api_key:
                st.error("API Key required. Please provide your API key in the sidebar configuration.")
            else:
                translator = AgenticTranslator(
                    model_name=model_choice,
                    api_key=api_key,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    glossary=glossary_dict,
                )

                output_path = execute_translation_loop(
                    parser=parser,
                    state_manager=state_manager,
                    translator=translator,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    glossary_dict=glossary_dict,
                    metric_placeholder=bento_placeholder,
                    progress_bar=progress_bar,
                    inspection_placeholder=inspection_placeholder,
                    terminal_placeholder=terminal_placeholder,
                )

                if output_path and os.path.exists(output_path):
                    st.session_state[saved_output_key] = output_path
                    st.success("Translation successfully completed and EPUB repacked.")
                    with open(output_path, "rb") as ep_file:
                        st.download_button(
                            "EXPORT REPACKED EPUB",
                            data=ep_file,
                            file_name=f"{parser.book_name}_Indonesian.epub",
                            mime="application/epub+zip",
                            use_container_width=True,
                        )
    else:
        # Empty state display
        st.markdown(
            """
            <div style="background-color: #16191F; border: 1px dashed #222731; border-radius: 8px; padding: 48px; text-align: center; margin-top: 1rem;">
                <div style="font-family: 'Geist Mono', 'SF Mono', monospace; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #8B949E; margin-bottom: 8px;">AWAITING EPUB UPLOAD</div>
                <div style="font-size: 15px; color: #C9D1D9; max-width: 480px; margin: 0 auto; line-height: 1.5;">
                    Upload an EPUB manuscript above to begin the agentic translation pipeline. The engine automatically inspects the spine, extracts text nodes while preserving inline formatting, and prepares deterministic resume tracking.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
