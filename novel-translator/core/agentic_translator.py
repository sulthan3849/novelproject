import random
import re
import time
from typing import Any, Dict, Optional, Tuple, Union
import litellm
from core.prompts import get_draft_prompt, get_reflect_prompt, get_improve_prompt


class TranslationResult(dict):
    """
    Result dictionary carrying translation content and telemetry.
    Supports attribute access, dict indexing, and str() conversion.
    """

    def __init__(
        self,
        final: str,
        draft: str = "",
        reflection: str = "",
        tokens_used: int = 0,
        fast_path: bool = False,
    ):
        super().__init__(
            final=final,
            draft=draft,
            reflection=reflection,
            tokens_used=tokens_used,
            fast_path=fast_path,
        )

    @property
    def final(self) -> str:
        return self["final"]

    @property
    def draft(self) -> str:
        return self["draft"]

    @property
    def reflection(self) -> str:
        return self["reflection"]

    @property
    def tokens_used(self) -> int:
        return self["tokens_used"]

    @property
    def fast_path(self) -> bool:
        return self["fast_path"]

    def __str__(self) -> str:
        return self["final"]


class AgenticTranslator:
    """
    Agentic Novel Translation Engine executing a 3-step prompt chain:
    Draft -> Reflect -> Improve.
    Features:
    - Direct api_key passing to litellm.completion (no os.environ mutation)
    - Fast-Path bypass when reflection indicates [STATUS: PERFECT]
    - Exponential backoff with random jitter for API rate limits and connection drops
    - Persistent terminology glossary preservation across all 3 stages
    - Telemetry tracking for token usage and fast-path rate
    """

    def __init__(
        self,
        model_name: Optional[str] = "gpt-4o-mini",
        api_key: Optional[str] = None,
        source_lang: str = "English",
        target_lang: str = "Indonesian",
        glossary: Optional[Union[Dict[str, str], str]] = None,
        **kwargs: Any,
    ):
        # Auto-detect swapped arguments (e.g. if instantiated as AgenticTranslator(api_key, model_name))
        arg1 = model_name or ""
        arg2 = api_key or ""
        
        # If arg1 looks like an API key (e.g. sk-...) and arg2 looks like a model name (e.g. gpt-4o, claude, gemini)
        if (arg1.startswith("sk-") or "key" in arg1.lower()) and any(m in arg2.lower() for m in ["gpt", "claude", "gemini", "llama", "deepseek"]):
            self.api_key = arg1
            self.model_name = arg2
        elif kwargs.get("api_key"):
            self.api_key = kwargs.get("api_key")
            self.model_name = model_name or "gpt-4o-mini"
        else:
            self.model_name = model_name or "gpt-4o-mini"
            self.api_key = api_key

        self.source_lang = source_lang
        self.target_lang = target_lang
        self.glossary = glossary or ""
        
        # Telemetry counters
        self.total_tokens_used = 0
        self.total_chunks_processed = 0
        self.fast_path_count = 0

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_retries: int = 5,
    ) -> Tuple[str, int]:
        """
        Executes a LiteLLM completion with exponential backoff and jitter.
        Directly passes self.api_key to litellm.completion().
        Returns: (response_text, tokens_used)
        """
        last_exception = None
        for attempt in range(max_retries):
            try:
                # Prepare call arguments
                call_kwargs: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                }
                if self.api_key:
                    call_kwargs["api_key"] = self.api_key

                response = litellm.completion(**call_kwargs)
                raw_text = response.choices[0].message.content or ""
                cleaned_text = raw_text.strip()
                
                # Extract token usage
                tokens = 0
                if hasattr(response, "usage") and response.usage:
                    tokens = getattr(response.usage, "total_tokens", 0) or 0

                self.total_tokens_used += tokens
                return cleaned_text, tokens

            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    # Exponential backoff with random jitter
                    base_delay = min(32.0, (1.8 ** attempt))
                    jitter = random.uniform(0.2, 1.2)
                    delay = base_delay + jitter
                    print(
                        f"[AgenticTranslator] Transient API error ({type(e).__name__}: {e}). "
                        f"Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                else:
                    print(f"[AgenticTranslator] Fatal error after {max_retries} attempts: {e}")
                    raise last_exception

        raise RuntimeError(f"Failed LLM call after {max_retries} retries: {last_exception}")

    def _strip_outer_markdown_fences(self, text: str) -> str:
        """Strips surrounding ```html or ``` markdown fences if returned by model."""
        content = text.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        return content

    def translate_chunk(
        self,
        text: str,
        context: Optional[str] = None,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        glossary: Optional[Union[Dict[str, str], str]] = None,
    ) -> TranslationResult:
        """
        Executes the 3-Step Agentic Translation Loop:
        1. Draft: Produce initial literary translation adhering to Gramedia standards and glossary.
        2. Reflect: Editorial proofreader critiques tone, fluency, idioms, and inline tags.
           - Fast-Path: If reflection contains '[STATUS: PERFECT]', Step 3 is bypassed.
        3. Improve: Master Rewriter refines draft incorporating reflection and glossary.
        """
        if not text or not text.strip():
            return TranslationResult(final=text, draft="", reflection="", tokens_used=0, fast_path=True)

        s_lang = source_lang or self.source_lang
        t_lang = target_lang or self.target_lang
        glos = glossary if glossary is not None else self.glossary

        total_chunk_tokens = 0

        # -------------------------------------------------------------
        # 1. DRAFTING
        # -------------------------------------------------------------
        draft_sys_prompt = get_draft_prompt(s_lang, t_lang, glos)
        if context and context.strip():
            user_draft_prompt = f"Konteks Paragraf Sebelumnya:\n{context.strip()}\n\nTeks yang Diterjemahkan:\n{text}"
        else:
            user_draft_prompt = text

        draft_text, draft_tokens = self._call_llm(draft_sys_prompt, user_draft_prompt)
        draft_text = self._strip_outer_markdown_fences(draft_text)
        total_chunk_tokens += draft_tokens

        # -------------------------------------------------------------
        # 2. REFLECTION (PROOFREADING & QUALITY CONTROL)
        # -------------------------------------------------------------
        reflect_sys_prompt = get_reflect_prompt(s_lang, t_lang, glos)
        user_reflect_prompt = f"Teks Asli ({s_lang}):\n{text}\n\nDraf Terjemahan ({t_lang}):\n{draft_text}"
        
        reflection_text, reflect_tokens = self._call_llm(reflect_sys_prompt, user_reflect_prompt)
        total_chunk_tokens += reflect_tokens

        # Fast-Path Check: Detect [STATUS: PERFECT] marker or 'TIDAK ADA REVISI'
        # Robust against stray substring matches by checking exact lines or tokens
        lines = [line.strip() for line in reflection_text.splitlines() if line.strip()]
        
        has_status_perfect = False
        for line in lines:
            # Check exact line or line prefix
            if (
                line in ("[STATUS: PERFECT]", "STATUS: PERFECT")
                or line.startswith("[STATUS: PERFECT]")
                or line.startswith("STATUS: PERFECT")
            ):
                # Ensure not negated
                if not re.search(r'\b(bukan|tidak|belum|bukanlah)\b', line, re.IGNORECASE):
                    has_status_perfect = True
                    break

        has_tidak_ada_revisi = "TIDAK ADA REVISI" in reflection_text.upper()
        if has_tidak_ada_revisi and re.search(r'\b(bukan|belum)\s+tidak\s+ada\s+revisi\b', reflection_text, re.IGNORECASE):
            has_tidak_ada_revisi = False

        is_fast_path = has_status_perfect or has_tidak_ada_revisi

        if is_fast_path:
            self.fast_path_count += 1
            self.total_chunks_processed += 1
            return TranslationResult(
                final=draft_text,
                draft=draft_text,
                reflection=reflection_text,
                tokens_used=total_chunk_tokens,
                fast_path=True,
            )

        # -------------------------------------------------------------
        # 3. IMPROVEMENT (FINAL POLISHING BY MASTER REWRITER)
        # -------------------------------------------------------------
        improve_sys_prompt = get_improve_prompt(s_lang, t_lang, glos)
        user_improve_prompt = (
            f"Teks Asli ({s_lang}):\n{text}\n\n"
            f"Draf Terjemahan ({t_lang}):\n{draft_text}\n\n"
            f"Kritik & Masukan Editor:\n{reflection_text}"
        )

        final_text, improve_tokens = self._call_llm(improve_sys_prompt, user_improve_prompt)
        final_text = self._strip_outer_markdown_fences(final_text)
        total_chunk_tokens += improve_tokens

        self.total_chunks_processed += 1
        return TranslationResult(
            final=final_text,
            draft=draft_text,
            reflection=reflection_text,
            tokens_used=total_chunk_tokens,
            fast_path=False,
        )
