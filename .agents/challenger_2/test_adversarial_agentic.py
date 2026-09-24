"""
Adversarial & Empirical Stress Test Suite for Agentic Novel Translator.
Conducted by Challenger 2 (Agentic Loop & Runtime Stress Verifier).

Scope:
1. LiteLLM Adversarial Resilience: HTTP 429 rate limits, timeouts, connection drops,
   context window exceeded, malformed responses, exponential backoff & jitter verification.
2. Fast-Path Bypass Logic: [STATUS: PERFECT] triggers, TIDAK ADA REVISI, false-positive negations,
   case-sensitivity, empty/malformed reflections.
3. Glossary Propagation & Enforcement: Draft, Reflect, and Improve prompt contracts,
   missing glossary in Step 2 reflection prompt, unicode/special char robustness.
4. Streamlit Session State & Hash Keying: SHA-256 stability, synthetic session resumes,
   state isolation across books, JSON corruption recovery, atomic file replacement,
   and AppTest synthetic UI harness.
"""

import hashlib
import json
import os
import random
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, call, patch

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Tag
import litellm

from core.agentic_translator import AgenticTranslator, TranslationResult
from core.prompts import (
    format_glossary,
    get_draft_prompt,
    get_reflect_prompt,
    get_improve_prompt,
)
from utils.epub_parser import EpubParser
from utils.state_manager import StateManager
from app import execute_translation_loop, parse_glossary, render_bento_metrics


class MockChoice:
    def __init__(self, content: str = ""):
        self.message = MagicMock(content=content)


class MockUsage:
    def __init__(self, total_tokens: int = 50):
        self.total_tokens = total_tokens


class MockCompletionResponse:
    def __init__(self, content: str = "", total_tokens: int = 50):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(total_tokens)


def build_test_epub(file_path: str, title: str = "Adversarial Test Novel", num_chapters: int = 2) -> str:
    """Helper to build a small synthetic EPUB for empirical tests."""
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:test-adv-12345")
    book.set_title(title)
    book.set_language("en")
    book.add_author("Test Author")
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    spine = ["nav"]
    for i in range(1, num_chapters + 1):
        content = f"""<?xml version="1.0" encoding="utf-8"?>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head><title>Chapter {i}</title></head>
        <body>
            <h1>Chapter {i}</h1>
            <p>Sentence <em>emphasized</em> in chapter {i}.</p>
            <p>Second paragraph with <strong>bold</strong> text.</p>
        </body>
        </html>"""
        ch = epub.EpubHtml(title=f"Chapter {i}", file_name=f"chapter{i}.xhtml", lang="en")
        ch.set_content(content.encode("utf-8"))
        book.add_item(ch)
        spine.append(ch)

    book.spine = spine
    epub.write_epub(file_path, book, {})
    return file_path


class TestAdversarialLiteLLM(unittest.TestCase):
    """Stress-tests for LiteLLM failure modes, transient errors, timeouts, and backoff."""

    def setUp(self):
        self.translator = AgenticTranslator(
            model_name="gpt-4o-mini",
            api_key="sk-adversarial-test-key",
        )

    # 1.1 HTTP 429 Rate-Limit with recovery
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_http_429_rate_limit_recovery(self, mock_completion, mock_sleep):
        """Verify 429 RateLimitError retries with backoff and succeeds upon transient resolution."""
        rate_limit_err = litellm.exceptions.RateLimitError(
            message="Rate limit 429 exceeded",
            model="gpt-4o-mini",
            llm_provider="openai",
        )
        mock_completion.side_effect = [
            rate_limit_err,
            rate_limit_err,
            MockCompletionResponse("Sukses setelah 429", total_tokens=40),
        ]

        text, tokens = self.translator._call_llm("sys", "user", max_retries=5)

        self.assertEqual(text, "Sukses setelah 429")
        self.assertEqual(tokens, 40)
        self.assertEqual(mock_completion.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    # 1.2 Backoff delays & Jitter math verification
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_exponential_backoff_and_jitter_delays(self, mock_completion, mock_sleep):
        """Verify backoff delays follow min(32, 1.8^attempt) + uniform(0.2, 1.2)."""
        rate_err = litellm.exceptions.RateLimitError("429", model="gpt-4o-mini", llm_provider="openai")
        mock_completion.side_effect = [rate_err, rate_err, rate_err, MockCompletionResponse("OK")]

        self.translator._call_llm("sys", "user", max_retries=5)

        self.assertEqual(mock_sleep.call_count, 3)
        delays = [c[0][0] for c in mock_sleep.call_args_list]

        # Attempt 0: base = 1.8^0 = 1.0, jitter in [0.2, 1.2] -> delay in [1.2, 2.2]
        self.assertTrue(1.2 <= delays[0] <= 2.2, f"Delay 0 was {delays[0]}")

        # Attempt 1: base = 1.8^1 = 1.8, jitter in [0.2, 1.2] -> delay in [2.0, 3.0]
        self.assertTrue(2.0 <= delays[1] <= 3.0, f"Delay 1 was {delays[1]}")

        # Attempt 2: base = 1.8^2 = 3.24, jitter in [0.2, 1.2] -> delay in [3.44, 4.44]
        self.assertTrue(3.44 <= delays[2] <= 4.44, f"Delay 2 was {delays[2]}")

    # 1.3 Connection Timeouts
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_connection_timeout_and_api_connection_error(self, mock_completion, mock_sleep):
        """Verify connection timeouts and network drops retry and recover."""
        timeout_err = litellm.exceptions.Timeout("Request timed out", model="gpt-4o-mini", llm_provider="openai")
        conn_err = litellm.exceptions.APIConnectionError("Connection reset by peer", model="gpt-4o-mini", llm_provider="openai")

        mock_completion.side_effect = [
            timeout_err,
            conn_err,
            MockCompletionResponse("Pulih dari timeout", total_tokens=30),
        ]

        text, tokens = self.translator._call_llm("sys", "user", max_retries=4)
        self.assertEqual(text, "Pulih dari timeout")
        self.assertEqual(mock_completion.call_count, 3)

    # 1.4 Exhaustion after max retries
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_exhaustion_raises_original_exception(self, mock_completion, mock_sleep):
        """Verify exhausting retries raises the exact underlying LiteLLM exception."""
        rate_err = litellm.exceptions.RateLimitError("Quota exhausted", model="gpt-4o-mini", llm_provider="openai")
        mock_completion.side_effect = rate_err

        with self.assertRaises(litellm.exceptions.RateLimitError):
            self.translator._call_llm("sys", "user", max_retries=3)

        self.assertEqual(mock_completion.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    # 1.5 Context Window Exceeded Error
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_context_window_exceeded_error_handling(self, mock_completion, mock_sleep):
        """Verify ContextWindowExceededError behavior under retry harness."""
        ctx_err = litellm.exceptions.ContextWindowExceededError(
            "Maximum context length exceeded (8192 tokens)",
            model="gpt-4o-mini",
            llm_provider="openai",
        )
        mock_completion.side_effect = ctx_err

        with self.assertRaises(litellm.exceptions.ContextWindowExceededError):
            self.translator._call_llm("sys", "user", max_retries=2)

    # 1.6 Malformed Responses: Empty choices list
    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_malformed_response_empty_choices_handled_and_retried(self, mock_completion, mock_sleep):
        """Verify response with empty choices [] triggers retry and recovers when subsequent call succeeds."""
        bad_response = MagicMock()
        bad_response.choices = []  # malformed!

        good_response = MockCompletionResponse("Sukses setelah choices kosong", total_tokens=25)
        mock_completion.side_effect = [bad_response, good_response]

        text, tokens = self.translator._call_llm("sys", "user", max_retries=3)
        self.assertEqual(text, "Sukses setelah choices kosong")
        self.assertEqual(mock_completion.call_count, 2)

    # 1.7 Malformed Responses: message.content is None
    @patch("core.agentic_translator.litellm.completion")
    def test_malformed_response_none_content_returns_empty_string(self, mock_completion):
        """Verify message with content=None safely resolves to empty string without AttributeError."""
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=None))]
        resp.usage = MockUsage(total_tokens=15)
        mock_completion.return_value = resp

        text, tokens = self.translator._call_llm("sys", "user")
        self.assertEqual(text, "")
        self.assertEqual(tokens, 15)

    # 1.8 Usage is None or missing total_tokens
    @patch("core.agentic_translator.litellm.completion")
    def test_missing_usage_telemetry_defaults_to_zero(self, mock_completion):
        """Verify response without usage attribute does not raise AttributeError and reports 0 tokens."""
        resp = MagicMock()
        resp.choices = [MockChoice("Hasil tanpa usage")]
        resp.usage = None
        mock_completion.return_value = resp

        text, tokens = self.translator._call_llm("sys", "user")
        self.assertEqual(text, "Hasil tanpa usage")
        self.assertEqual(tokens, 0)

    # 1.9 Outer Markdown Fences Stripping
    def test_strip_outer_markdown_fences_variations(self):
        """Verify stripping of various model markdown fence conventions."""
        cases = [
            ("```html\n<p>Paragraf</p>\n```", "<p>Paragraf</p>"),
            ("```markdown\n# Judul\n```", "# Judul"),
            ("```\nTeks biasa\n```", "Teks biasa"),
            ("```html\n<em>Kata</em> dan <strong>tebal</strong>\n```", "<em>Kata</em> dan <strong>tebal</strong>"),
            ("<p>Teks tanpa fence</p>", "<p>Teks tanpa fence</p>"),
            ("```html\nBaris 1\nBaris 2\n```", "Baris 1\nBaris 2"),
        ]
        for raw, expected in cases:
            stripped = self.translator._strip_outer_markdown_fences(raw)
            self.assertEqual(stripped, expected, f"Failed for raw: {raw}")


class TestFastPathBypassAdversarial(unittest.TestCase):
    """Adversarial stress-testing of Fast-Path detection and bypass logic."""

    def setUp(self):
        self.translator = AgenticTranslator(api_key="sk-test")

    # 2.1 Standard Fast Path with [STATUS: PERFECT]
    @patch("core.agentic_translator.litellm.completion")
    def test_fast_path_exact_marker_bypasses_step_3(self, mock_completion):
        """Verify [STATUS: PERFECT] executes only Draft & Reflect (2 calls) and returns draft."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf awal yang luar biasa.", total_tokens=30),
            MockCompletionResponse("[STATUS: PERFECT]\nGaya bahasa sudah Gramedia standard.", total_tokens=20),
        ]

        res = self.translator.translate_chunk("Original pristine text.")
        self.assertEqual(mock_completion.call_count, 2)
        self.assertTrue(res.fast_path)
        self.assertEqual(res.final, "Draf awal yang luar biasa.")
        self.assertEqual(res.tokens_used, 50)
        self.assertEqual(self.translator.fast_path_count, 1)

    # 2.2 Standard 3-Step when critique has no status perfect
    @patch("core.agentic_translator.litellm.completion")
    def test_standard_flow_requires_improvement(self, mock_completion):
        """Verify regular critique triggers Step 3 (Improvement) with 3 total calls."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf kaku.", total_tokens=25),
            MockCompletionResponse("Kritik: Terlalu harfiah. Perbaiki struktur kalimat.", total_tokens=30),
            MockCompletionResponse("Terjemahan final yang mengalir luwes.", total_tokens=35),
        ]

        res = self.translator.translate_chunk("Original text.")
        self.assertEqual(mock_completion.call_count, 3)
        self.assertFalse(res.fast_path)
        self.assertEqual(res.final, "Terjemahan final yang mengalir luwes.")
        self.assertEqual(res.tokens_used, 90)
        self.assertEqual(self.translator.fast_path_count, 0)

    # 2.3 Adversarial: False-Positive Negation
    @patch("core.agentic_translator.litellm.completion")
    def test_adversarial_negated_fast_path_marker(self, mock_completion):
        """
        Adversarial test: If reflection says 'BUKAN [STATUS: PERFECT], sangat buruk',
        check whether simple substring containment causes a premature false fast-path bypass!
        """
        mock_completion.side_effect = [
            MockCompletionResponse("Draf cacat.", total_tokens=20),
            MockCompletionResponse("Draf ini JELAS BUKAN [STATUS: PERFECT], ada banyak cacat.", total_tokens=25),
            MockCompletionResponse("Final perbaikan.", total_tokens=30),
        ]

        res = self.translator.translate_chunk("Test input.")
        # Note: In current implementation, '[STATUS: PERFECT]' in reflection_text evaluates to True!
        # Document whether it triggers false-positive bypass:
        if res.fast_path:
            print("[Adversarial Vulnerability Confirmed] Substring check triggers Fast-Path on negated '[STATUS: PERFECT]'!")
        self.assertTrue(res.fast_path)  # Documents empirical behavior of current implementation

    # 2.4 Adversarial: Lowercase marker sensitivity
    @patch("core.agentic_translator.litellm.completion")
    def test_lowercase_status_perfect_does_not_trigger(self, mock_completion):
        """
        Verify whether lowercase '[status: perfect]' triggers fast path.
        In current implementation, '[STATUS: PERFECT]' in reflection_text is case-sensitive.
        """
        mock_completion.side_effect = [
            MockCompletionResponse("Draf teks.", total_tokens=20),
            MockCompletionResponse("[status: perfect]\nSemua bagus.", total_tokens=20),
            MockCompletionResponse("Final yang dipoles.", total_tokens=25),
        ]

        res = self.translator.translate_chunk("Test input.")
        # Lowercase should NOT trigger fast path because check is case-sensitive
        self.assertEqual(mock_completion.call_count, 3)
        self.assertFalse(res.fast_path)

    # 2.5 Reflection with 'TIDAK ADA REVISI'
    @patch("core.agentic_translator.litellm.completion")
    def test_tidak_ada_revisi_case_insensitivity(self, mock_completion):
        """Verify 'tidak ada revisi' in lowercase triggers fast path due to .upper() check."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf teks.", total_tokens=20),
            MockCompletionResponse("Menurut editor, tidak ada revisi yang diperlukan.", total_tokens=20),
        ]

        res = self.translator.translate_chunk("Test input.")
        self.assertEqual(mock_completion.call_count, 2)
        self.assertTrue(res.fast_path)


class TestGlossaryPropagationAndEnforcement(unittest.TestCase):
    """Stress-testing glossary mapping formatting and propagation across 3 steps."""

    def setUp(self):
        self.glossary_dict = {
            "Shadow Monarch": "Raja Bayangan",
            "Mana Crystal": "Kristal Mana",
            "Hunter's Guild": "Serikat Pemburu",
        }
        self.translator = AgenticTranslator(
            model_name="gpt-4o-mini",
            api_key="sk-test",
            glossary=self.glossary_dict,
        )

    # 3.1 Step 1 (Draft) glossary presence
    @patch("core.agentic_translator.litellm.completion")
    def test_glossary_present_in_draft_system_prompt(self, mock_completion):
        """Verify glossary mappings are injected into Step 1 Draft prompt."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf", total_tokens=10),
            MockCompletionResponse("[STATUS: PERFECT]", total_tokens=10),
        ]
        self.translator.translate_chunk("The Shadow Monarch found a Mana Crystal.")

        draft_call_args = mock_completion.call_args_list[0]
        sys_msg = draft_call_args.kwargs["messages"][0]["content"]
        self.assertIn("Raja Bayangan", sys_msg)
        self.assertIn("Kristal Mana", sys_msg)
        self.assertIn("Serikat Pemburu", sys_msg)

    # 3.2 Step 2 (Reflect) glossary inspection (EMPIRICAL AUDIT)
    @patch("core.agentic_translator.litellm.completion")
    def test_glossary_omission_in_reflect_step(self, mock_completion):
        """
        Empirical check: Verify whether Step 2 (Reflection) system or user prompt contains the glossary.
        Observation: get_reflect_prompt does not take a glossary argument, nor does user_reflect_prompt include it!
        """
        mock_completion.side_effect = [
            MockCompletionResponse("Draf", total_tokens=10),
            MockCompletionResponse("Kritik", total_tokens=10),
            MockCompletionResponse("Final", total_tokens=10),
        ]
        self.translator.translate_chunk("The Shadow Monarch found a Mana Crystal.")

        reflect_call_args = mock_completion.call_args_list[1]
        sys_msg = reflect_call_args.kwargs["messages"][0]["content"]
        user_msg = reflect_call_args.kwargs["messages"][1]["content"]

        # Empirically verify that glossary is NOT in Step 2 reflection prompt:
        has_glossary_in_reflect_sys = "Raja Bayangan" in sys_msg
        has_glossary_in_reflect_user = "Raja Bayangan" in user_msg

        print(
            f"[Glossary Audit] Step 2 Reflect SysMsg has glossary: {has_glossary_in_reflect_sys}, "
            f"UserMsg has glossary: {has_glossary_in_reflect_user}"
        )
        self.assertFalse(has_glossary_in_reflect_sys)
        self.assertFalse(has_glossary_in_reflect_user)

    # 3.3 Step 3 (Improve) glossary presence
    @patch("core.agentic_translator.litellm.completion")
    def test_glossary_present_in_improve_system_prompt(self, mock_completion):
        """Verify glossary mappings are injected into Step 3 Improve prompt."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf", total_tokens=10),
            MockCompletionResponse("Kritik: Perhalus gaya bahasa.", total_tokens=10),
            MockCompletionResponse("Final", total_tokens=10),
        ]
        self.translator.translate_chunk("The Shadow Monarch found a Mana Crystal.")

        improve_call_args = mock_completion.call_args_list[2]
        sys_msg = improve_call_args.kwargs["messages"][0]["content"]
        self.assertIn("Raja Bayangan", sys_msg)
        self.assertIn("Kristal Mana", sys_msg)

    # 3.4 Unicode and special characters in glossary
    def test_glossary_with_unicode_and_special_chars(self):
        """Verify format_glossary handles Japanese Kanji, symbols, and quotes cleanly."""
        glos = {
            "暗殺者": "Pembunuh Bayangan",
            "Ruler's Authority": "Otoritas Penguasa",
            "Special -> Arrow": "Panah Khusus",
            "Key:Value": "Nilai Kunci",
        }
        formatted = format_glossary(glos)
        self.assertIn("暗殺者 -> Pembunuh Bayangan", formatted)
        self.assertIn("Ruler's Authority -> Otoritas Penguasa", formatted)

    # 3.5 Glossary string parsing in app.py
    def test_parse_glossary_edge_cases(self):
        """Verify app.py parse_glossary handles comments, blank lines, colons, arrows."""
        raw_text = """
        # Ini komentar
        Shadow -> Bayangan
        Hunter : Pemburu
        
        SingleWordWithoutSeparator
        Arrow -> With -> Multiple -> Arrows
        """
        parsed = parse_glossary(raw_text)
        self.assertEqual(parsed.get("Shadow"), "Bayangan")
        self.assertEqual(parsed.get("Hunter"), "Pemburu")
        self.assertNotIn("SingleWordWithoutSeparator", parsed)
        self.assertEqual(parsed.get("Arrow"), "With -> Multiple -> Arrows")


class TestStreamlitRuntimeAndSessionState(unittest.TestCase):
    """Stress-testing StateManager persistence, SHA-256 stability, and synthetic execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_st_test_")
        self.epub_path = os.path.join(self.temp_dir, "novel_sample.epub")
        build_test_epub(self.epub_path, title="State Test Novel", num_chapters=2)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 4.1 Deterministic Content Hash Keying
    def test_sha256_content_hash_stability(self):
        """Verify identical files produce identical book_hash regardless of filename."""
        parser1 = EpubParser(self.epub_path)
        hash1 = parser1.book_hash

        # Copy to different filename
        copy_path = os.path.join(self.temp_dir, "renamed_copy.epub")
        shutil.copyfile(self.epub_path, copy_path)
        parser2 = EpubParser(copy_path)
        hash2 = parser2.book_hash

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    # 4.2 Multi-session state isolation
    def test_state_isolation_between_distinct_books(self):
        """Verify state files for different book hashes do not collide."""
        state_dir = os.path.join(self.temp_dir, ".state")
        sm_a = StateManager("book_hash_alpha_111", total_chunks=10, state_dir=state_dir)
        sm_b = StateManager("book_hash_beta_222", total_chunks=20, state_dir=state_dir)

        sm_a.mark_chunk_translated("item1", 0, "Terjemahan A", "Original A")
        sm_a.flush()

        sm_b.mark_chunk_translated("item1", 0, "Terjemahan B", "Original B")
        sm_b.flush()

        # Re-load both
        sm_a_reloaded = StateManager("book_hash_alpha_111", state_dir=state_dir)
        sm_b_reloaded = StateManager("book_hash_beta_222", state_dir=state_dir)

        self.assertEqual(sm_a_reloaded.get_translated_chunk("item1", 0), "Terjemahan A")
        self.assertEqual(sm_b_reloaded.get_translated_chunk("item1", 0), "Terjemahan B")
        self.assertEqual(sm_a_reloaded.state["total_chunks"], 10)
        self.assertEqual(sm_b_reloaded.state["total_chunks"], 20)

    # 4.3 Atomic file recovery on corrupted state file
    def test_resilience_to_corrupted_json_state_file(self):
        """Verify StateManager recovers gracefully when state JSON is truncated or corrupted."""
        state_dir = os.path.join(self.temp_dir, ".state")
        os.makedirs(state_dir, exist_ok=True)
        corrupted_file = os.path.join(state_dir, "corrupted_book_progress.json")

        with open(corrupted_file, "w", encoding="utf-8") as f:
            f.write('{"book_identifier": "corrupted", "total_chunks": 50, "translated_items": { INVALID JSON')

        # Instantiating StateManager should not crash; it should catch exception and start fresh
        sm = StateManager("corrupted_book", total_chunks=50, state_dir=state_dir)
        self.assertEqual(sm.get_completed_count(), 0)
        self.assertEqual(sm.state["total_chunks"], 50)

    # 4.4 Simulation of execute_translation_loop with synthetic mocks
    @patch("core.agentic_translator.litellm.completion")
    def test_execute_translation_loop_synthetic_session(self, mock_completion):
        """Simulate execute_translation_loop driving EpubParser, StateManager, and AgenticTranslator."""
        call_count = [0]

        def dynamic_response(*args, **kwargs):
            call_count[0] += 1
            # Return draft or [STATUS: PERFECT] alternating
            if call_count[0] % 2 == 1:
                return MockCompletionResponse("Draf Terjemahan Bab", total_tokens=20)
            else:
                return MockCompletionResponse("[STATUS: PERFECT]\nSangat natural.", total_tokens=10)

        mock_completion.side_effect = dynamic_response

        parser = EpubParser(self.epub_path)
        all_nodes = parser.extract_text_nodes()
        total_chunks = len(all_nodes)
        self.assertGreater(total_chunks, 0)

        state_dir = os.path.join(self.temp_dir, ".state")
        sm = StateManager(parser.book_hash, total_chunks=total_chunks, state_dir=state_dir)
        translator = AgenticTranslator(api_key="sk-test")

        metric_placeholder = MagicMock()
        progress_bar = MagicMock()
        inspection_placeholder = MagicMock()
        terminal_placeholder = MagicMock()

        output_path = execute_translation_loop(
            parser=parser,
            state_manager=sm,
            translator=translator,
            source_lang="English",
            target_lang="Indonesian",
            glossary_dict={},
            metric_placeholder=metric_placeholder,
            progress_bar=progress_bar,
            inspection_placeholder=inspection_placeholder,
            terminal_placeholder=terminal_placeholder,
        )

        self.assertIsNotNone(output_path)
        self.assertTrue(os.path.exists(output_path))
        self.assertEqual(sm.get_completed_count(), total_chunks)

        # Repacked EPUB verification
        repacked_parser = EpubParser(output_path)
        self.assertEqual(len(repacked_parser.get_html_items()), len(parser.get_html_items()))

    # 4.5 Streamlit AppTest synthetic session execution
    def test_streamlit_apptest_synthetic_run(self):
        """Run Streamlit AppTest to verify app.py boots cleanly without runtime exceptions."""
        from streamlit.testing.v1 import AppTest

        app_path = os.path.abspath("app.py")
        at = AppTest.from_file(app_path, default_timeout=15.0)
        at.run()

        self.assertFalse(at.exception, f"AppTest raised unexpected exception: {at.exception}")
        # Verify sidebar presence
        self.assertTrue(len(at.sidebar) > 0)


if __name__ == "__main__":
    unittest.main()
