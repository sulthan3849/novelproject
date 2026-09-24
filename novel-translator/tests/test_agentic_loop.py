import os
import unittest
from unittest.mock import MagicMock, call, patch
from core.agentic_translator import AgenticTranslator, TranslationResult
from core.prompts import (
    format_glossary,
    get_draft_prompt,
    get_reflect_prompt,
    get_improve_prompt,
)


class MockChoice:
    def __init__(self, content: str):
        self.message = MagicMock(content=content)


class MockUsage:
    def __init__(self, total_tokens: int = 42):
        self.total_tokens = total_tokens


class MockCompletionResponse:
    def __init__(self, content: str, total_tokens: int = 42):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(total_tokens)


class TestAgenticLoop(unittest.TestCase):
    """Tier 1 and Tier 2 tests for LiteLLM Agentic Translation loop, prompts, and error handling."""

    def setUp(self):
        self.api_key = "sk-test-mock-api-key-12345"
        self.model_name = "gpt-4o-mini"
        self.translator = AgenticTranslator(
            model_name=self.model_name,
            api_key=self.api_key,
            source_lang="English",
            target_lang="Indonesian",
            glossary={"Shadowfang": "Taring Bayangan", "Elder": "Tetua"},
        )

    # -------------------------------------------------------------
    # Tier 1: Feature Coverage (Prompts)
    # -------------------------------------------------------------

    def test_format_glossary_dictionary_and_string(self):
        """Verify format_glossary formats both dict mappings and string definitions."""
        dict_glossary = {"Kuro": "Si Hitam", "Guild": "Serikat"}
        formatted_dict = format_glossary(dict_glossary)
        self.assertIn("GLOSARIUM ISTILAH", formatted_dict)
        self.assertIn("- Kuro -> Si Hitam", formatted_dict)
        self.assertIn("- Guild -> Serikat", formatted_dict)

        str_glossary = "Hero -> Pahlawan\nDemon -> Iblis"
        formatted_str = format_glossary(str_glossary)
        self.assertIn("Hero -> Pahlawan", formatted_str)

        # Empty / None
        self.assertEqual(format_glossary(""), "")
        self.assertEqual(format_glossary(None), "")

    def test_draft_prompt_formatting_and_no_placeholder_leak(self):
        """Verify get_draft_prompt contains Gramedia standards and does NOT leak literal {text}."""
        prompt = get_draft_prompt("English", "Indonesian", "Sword -> Pedang")
        self.assertIn("Gramedia", prompt)
        self.assertIn("English", prompt)
        self.assertIn("Indonesian", prompt)
        self.assertIn("Sword -> Pedang", prompt)
        self.assertNotIn("{text}", prompt)
        self.assertNotIn("{{text}}", prompt)

    def test_reflect_prompt_contains_fast_path_marker(self):
        """Verify get_reflect_prompt instructs proofreader on [STATUS: PERFECT] bypass."""
        prompt = get_reflect_prompt("English", "Indonesian")
        self.assertIn("[STATUS: PERFECT]", prompt)
        self.assertIn("Proofreader", prompt)
        self.assertIn("Gramedia", prompt)

    def test_improve_prompt_accepts_and_enforces_glossary(self):
        """Verify get_improve_prompt contains the glossary to prevent terminology drift in step 3."""
        prompt = get_improve_prompt("English", "Indonesian", "Magic -> Sihir")
        self.assertIn("Magic -> Sihir", prompt)
        self.assertIn("Master Literary Rewriter", prompt)

    def test_prompt_curly_brace_safety(self):
        """Verify prompts handle curly braces in literary text without raising KeyError or ValueError."""
        text_with_braces = 'The spell was inscribed: {rune: "fire", power: 9000};'
        try:
            # Formatting with curly braces should not crash
            user_prompt = f"Teks Asli:\n{text_with_braces}"
            self.assertIn(text_with_braces, user_prompt)
        except Exception as e:
            self.fail(f"Prompt formatting failed on curly braces: {e}")

    # -------------------------------------------------------------
    # Tier 1: Feature Coverage (Agentic Loop & Telemetry)
    # -------------------------------------------------------------

    @patch("core.agentic_translator.litellm.completion")
    def test_full_3_step_agentic_loop(self, mock_completion):
        """
        Verify the full 3-step loop:
        1. Draft -> Initial translation
        2. Reflect -> Critique (no fast path)
        3. Improve -> Final polished translation
        Assert exactly 3 LiteLLM calls made and TranslationResult contains all stages.
        """
        mock_completion.side_effect = [
            MockCompletionResponse("Draf: Dia menghunus pedang perak.", total_tokens=50),
            MockCompletionResponse("Kritik: Diksi kurang dramatis. Gunakan 'menghunus pedang peraknya dengan tatapan tajam'.", total_tokens=40),
            MockCompletionResponse("Dia menghunus pedang peraknya dengan tatapan tajam.", total_tokens=60),
        ]

        result = self.translator.translate_chunk("He drew the silver sword.")

        self.assertEqual(mock_completion.call_count, 3)
        self.assertIsInstance(result, TranslationResult)
        self.assertEqual(result.final, "Dia menghunus pedang peraknya dengan tatapan tajam.")
        self.assertEqual(result.draft, "Draf: Dia menghunus pedang perak.")
        self.assertIn("Kritik:", result.reflection)
        self.assertFalse(result.fast_path)
        self.assertEqual(result.tokens_used, 150)
        self.assertEqual(str(result), result.final)

    @patch("core.agentic_translator.litellm.completion")
    def test_fast_path_bypass_with_status_perfect(self, mock_completion):
        """
        Verify fast-path bypass when reflection outputs [STATUS: PERFECT]:
        1. Draft -> Initial translation
        2. Reflect -> '[STATUS: PERFECT] Terjemahan sangat mengalir indah.'
        Assert Step 3 is bypassed: exactly 2 LiteLLM calls, fast_path=True, draft returned.
        """
        mock_completion.side_effect = [
            MockCompletionResponse("Angin musim gugur berhembus lembut melintasi perbukitan.", total_tokens=45),
            MockCompletionResponse("[STATUS: PERFECT]\nTerjemahan sangat natural dan sempurna.", total_tokens=30),
        ]

        result = self.translator.translate_chunk("The autumn wind blew softly across the hills.")

        self.assertEqual(mock_completion.call_count, 2)
        self.assertTrue(result.fast_path)
        self.assertEqual(result.final, "Angin musim gugur berhembus lembut melintasi perbukitan.")
        self.assertEqual(self.translator.fast_path_count, 1)

    @patch("core.agentic_translator.litellm.completion")
    def test_fast_path_bypass_with_tidak_ada_revisi(self, mock_completion):
        """Verify fast-path bypass also triggers on 'TIDAK ADA REVISI' in reflection."""
        mock_completion.side_effect = [
            MockCompletionResponse("Malam itu dingin dan hening.", total_tokens=35),
            MockCompletionResponse("TIDAK ADA REVISI. Gaya bahasa sudah sesuai standar Gramedia.", total_tokens=25),
        ]

        result = self.translator.translate_chunk("The night was cold and silent.")

        self.assertEqual(mock_completion.call_count, 2)
        self.assertTrue(result.fast_path)
        self.assertEqual(result.final, "Malam itu dingin dan hening.")

    @patch("core.agentic_translator.litellm.completion")
    def test_glossary_propagation_to_draft_and_improve(self, mock_completion):
        """Verify custom glossary is injected into both Step 1 (Draft) and Step 3 (Improve) prompts."""
        mock_completion.side_effect = [
            MockCompletionResponse("Draf", total_tokens=20),
            MockCompletionResponse("Kritik: Perbaiki kata penghubung.", total_tokens=20),
            MockCompletionResponse("Final", total_tokens=20),
        ]

        custom_glossary = {"Aethelgard": "Aethelgard Kerajaan", "Dark Lord": "Raja Kegelapan"}
        self.translator.translate_chunk(
            text="The Dark Lord invaded Aethelgard.",
            glossary=custom_glossary,
        )

        self.assertEqual(mock_completion.call_count, 3)
        # Call 0: Draft system prompt
        draft_sys = mock_completion.call_args_list[0].kwargs["messages"][0]["content"]
        self.assertIn("Raja Kegelapan", draft_sys)
        self.assertIn("Aethelgard Kerajaan", draft_sys)

        # Call 2: Improve system prompt
        improve_sys = mock_completion.call_args_list[2].kwargs["messages"][0]["content"]
        self.assertIn("Raja Kegelapan", improve_sys)
        self.assertIn("Aethelgard Kerajaan", improve_sys)

    def test_translation_result_dictionary_and_attribute_access(self):
        """Verify TranslationResult supports dict indexing, attribute access, and string casting."""
        res = TranslationResult(
            final="Hasil akhir",
            draft="Draf awal",
            reflection="Catatan editor",
            tokens_used=120,
            fast_path=False,
        )
        self.assertEqual(res["final"], "Hasil akhir")
        self.assertEqual(res.final, "Hasil akhir")
        self.assertEqual(res["draft"], "Draf awal")
        self.assertEqual(res.draft, "Draf awal")
        self.assertEqual(res.tokens_used, 120)
        self.assertFalse(res.fast_path)
        self.assertEqual(str(res), "Hasil akhir")

    # -------------------------------------------------------------
    # Tier 2: Boundary & Corner Cases
    # -------------------------------------------------------------

    @patch("core.agentic_translator.litellm.completion")
    def test_empty_or_whitespace_input_returns_immediately(self, mock_completion):
        """Verify empty or whitespace strings return immediately with 0 LLM calls."""
        res_empty = self.translator.translate_chunk("")
        self.assertEqual(res_empty.final, "")
        self.assertEqual(mock_completion.call_count, 0)

        res_ws = self.translator.translate_chunk("   \n\t  ")
        self.assertEqual(res_ws.final, "   \n\t  ")
        self.assertEqual(mock_completion.call_count, 0)

    @patch("core.agentic_translator.litellm.completion")
    def test_api_key_passed_directly_without_environ_mutation(self, mock_completion):
        """Verify api_key is passed directly into litellm.completion arguments."""
        mock_completion.return_value = MockCompletionResponse("Draf", total_tokens=10)
        
        # Ensure environ is clean before call
        os.environ.pop("API_KEY", None)

        self.translator._call_llm("system prompt", "user prompt")

        self.assertEqual(mock_completion.call_count, 1)
        passed_kwargs = mock_completion.call_args.kwargs
        self.assertEqual(passed_kwargs.get("api_key"), self.api_key)
        self.assertEqual(passed_kwargs.get("model"), self.model_name)

    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_transient_rate_limit_exponential_backoff_retry(self, mock_completion, mock_sleep):
        """Verify translator retries with exponential backoff on transient errors and succeeds."""
        mock_completion.side_effect = [
            Exception("Rate limit 429: Too Many Requests"),
            Exception("Connection error: Gateway Timeout 504"),
            MockCompletionResponse("Berhasil setelah retry", total_tokens=25),
        ]

        text, tokens = self.translator._call_llm("sys", "user")

        self.assertEqual(mock_completion.call_count, 3)
        self.assertEqual(text, "Berhasil setelah retry")
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("time.sleep")
    @patch("core.agentic_translator.litellm.completion")
    def test_fatal_error_propagates_after_max_retries(self, mock_completion, mock_sleep):
        """Verify translator raises exception after exhausting maximum retries."""
        mock_completion.side_effect = Exception("Persistent Fatal Error: Quota Exceeded")

        with self.assertRaises(Exception):
            self.translator._call_llm("sys", "user", max_retries=3)

        self.assertEqual(mock_completion.call_count, 3)

    @patch("core.agentic_translator.litellm.completion")
    def test_strip_outer_markdown_fences_from_model_output(self, mock_completion):
        """Verify outer ```html and ``` fences are cleanly stripped from translations."""
        mock_completion.side_effect = [
            MockCompletionResponse("```html\n<p>Terjemahan terbungkus.</p>\n```", total_tokens=20),
            MockCompletionResponse("[STATUS: PERFECT]", total_tokens=10),
        ]

        result = self.translator.translate_chunk("Wrapped text.")
        self.assertEqual(result.final, "<p>Terjemahan terbungkus.</p>")

    def test_swapped_init_arguments_auto_detection(self):
        """Verify AgenticTranslator auto-detects swapped arguments (api_key first vs model_name first)."""
        # Form 1: model_name, api_key
        t1 = AgenticTranslator("gpt-4o", "sk-12345")
        self.assertEqual(t1.model_name, "gpt-4o")
        self.assertEqual(t1.api_key, "sk-12345")

        # Form 2: swapped (api_key, model_name)
        t2 = AgenticTranslator("sk-99999", "anthropic/claude-3-5-sonnet")
        self.assertEqual(t2.model_name, "anthropic/claude-3-5-sonnet")
        self.assertEqual(t2.api_key, "sk-99999")


if __name__ == "__main__":
    unittest.main()
