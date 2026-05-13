"""
providers.py — Multi-provider LLM thin adapter.

Supports: OpenAI, Anthropic, Google Gemini, xAI (Grok), Mistral AI, Groq.
Only 3 SDKs needed: openai (covers OpenAI + xAI + Mistral + Groq), anthropic, google-genai.

Public API:
    - PROVIDERS                            registry of supported providers
    - PRICING                              per (provider, model) input/output USD per 1M tokens
    - CompletionResult                     dataclass returned by complete() / complete_json()
    - LLMClient(provider_id, key, model)   client with .complete() and .complete_json()
    - estimate_cost(usage)                 -> float | None (USD)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict


# ============================================================
# PROVIDER REGISTRY
# ============================================================

PROVIDERS: dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "env_var": "OPENAI_API_KEY",
        "sdk": "openai",
        "base_url": None,
        "key_url": "https://platform.openai.com/api-keys",
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "supports_json_mode": True,
    },
    "anthropic": {
        "name": "Anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "sdk": "anthropic",
        "base_url": None,
        "key_url": "https://console.anthropic.com/settings/keys",
        "default_models": [
            "claude-opus-4-6", "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001", "claude-3-5-sonnet-20241022",
        ],
        "supports_json_mode": True,  # via prefill technique
    },
    "google": {
        "name": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "sdk": "google",
        "base_url": None,
        "key_url": "https://aistudio.google.com/apikey",
        "default_models": [
            "gemini-2.5-pro", "gemini-2.5-flash",
            "gemini-1.5-pro", "gemini-1.5-flash",
        ],
        "supports_json_mode": True,
    },
    "xai": {
        "name": "xAI (Grok)",
        "env_var": "XAI_API_KEY",
        "sdk": "openai",
        "base_url": "https://api.x.ai/v1",
        "key_url": "https://console.x.ai/",
        "default_models": ["grok-3", "grok-3-fast", "grok-3-mini", "grok-2-1212"],
        "supports_json_mode": True,
    },
    "mistral": {
        "name": "Mistral AI",
        "env_var": "MISTRAL_API_KEY",
        "sdk": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys",
        "default_models": [
            "mistral-large-latest", "mistral-medium-latest",
            "mistral-small-latest", "open-mistral-7b",
        ],
        "supports_json_mode": True,
    },
    "groq": {
        "name": "Groq",
        "env_var": "GROQ_API_KEY",
        "sdk": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "default_models": [
            "llama-3.3-70b-versatile", "llama-3.1-70b-versatile",
            "mixtral-8x7b-32768", "gemma2-9b-it",
        ],
        "supports_json_mode": True,
    },
}


# ============================================================
# PRICING — USD per 1M tokens
# Updated 2026-05-13 — public list prices. Some providers may have
# negotiated rates. Models not listed return None (UI shows "~?").
# ============================================================

PRICING: dict[tuple[str, str], dict[str, float]] = {
    # OpenAI
    ("openai", "gpt-5.5"):                   {"input": 5.00,  "output": 30.00},
    ("openai", "gpt-5.4"):                   {"input": 2.50,  "output": 15.00},
    ("openai", "gpt-5.4-mini"):              {"input": 0.75,  "output": 4.50},
    ("openai", "gpt-5.4-nano"):              {"input": 0.20,  "output": 1.25},
    ("openai", "gpt-4o"):                    {"input": 2.50,  "output": 10.00},
    ("openai", "gpt-4o-mini"):               {"input": 0.15,  "output": 0.60},
    ("openai", "gpt-4-turbo"):               {"input": 10.00, "output": 30.00},
    ("openai", "gpt-3.5-turbo"):             {"input": 0.50,  "output": 1.50},
    # Anthropic (Claude 4.x family)
    ("anthropic", "claude-opus-4-7"):        {"input": 5.00, "output": 15.00},
    ("anthropic", "claude-opus-4-6"):        {"input": 5.00, "output": 15.00},
    ("anthropic", "claude-sonnet-4-6"):      {"input": 3.00,  "output": 15.00},
    ("anthropic", "claude-sonnet-4-5"):      {"input": 3.00,  "output": 15.00},
    ("anthropic", "claude-haiku-4-5"):       {"input": 1.00,  "output": 5.00},
    # Google Gemini
    ("google", "gemini-3.1-pro-preview"):    {"input": 2.00, "output": 12.00},
    ("google", "gemini-3.1-flash-lite"):     {"input": 0.25, "output": 1.50},
    ("google", "gemini-2.5-pro"):            {"input": 1.25,  "output": 10.00},
    ("google", "gemini-2.5-flash"):          {"input": 0.30,  "output": 2.50},
    ("google", "gemini-2.5-flash-lite"):     {"input": 0.10,  "output": 0.40},
    # xAI Grok
    ("xai", "grok-4.3"):                     {"input": 1.25,  "output": 2.50},
    ("xai", "grok-4-1-fast-reasoning"):      {"input": 0.20,  "output": 0.50},
    ("xai", "grok-4-1-fast-non-reasoning"):  {"input": 0.20,  "output": 0.50},
    ("xai", "grok-4"):                       {"input": 5.00,  "output": 15.00},
    ("xai", "grok-3"):                       {"input": 3.00,  "output": 15.00},
    ("xai", "grok-3-fast"):                  {"input": 5.00,  "output": 25.00},
    ("xai", "grok-3-mini"):                  {"input": 0.30,  "output": 0.50},
    # Mistral
    ("mistral", "mistral-large-latest"):     {"input": 0.50,  "output": 1.50},
    ("mistral", "mistral-medium-latest"):    {"input": 2.00,  "output": 5.00},
    ("mistral", "mistral-small-latest"):     {"input": 0.15,  "output": 0.60},
    # Groq
    ("groq", "llama-3.3-70b-versatile"):     {"input": 0.59,  "output": 0.79},
    ("groq", "llama-3.1-70b-versatile"):     {"input": 0.59,  "output": 0.79},
    ("groq", "mixtral-8x7b-32768"):          {"input": 0.24,  "output": 0.24},
    ("groq", "gemma2-9b-it"):                {"input": 0.20,  "output": 0.20},
}

PRICING_UPDATED_AT = "2026-05-13"


# ============================================================
# COMPLETION RESULT
# ============================================================

@dataclass
class CompletionResult:
    """Result of a single LLM call. text is always non-empty; tokens may be None."""
    text: str
    input_tokens: int | None
    output_tokens: int | None
    provider: str
    model: str
    latency_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_cost(usage: CompletionResult | dict) -> float | None:
    """Return USD cost for a single call, or None if model/tokens unknown.

    Accepts a CompletionResult or a dict with the same fields (for serialized usage records).
    """
    if isinstance(usage, CompletionResult):
        provider, model = usage.provider, usage.model
        in_tok, out_tok = usage.input_tokens, usage.output_tokens
    else:
        provider = usage.get("provider", "")
        model = usage.get("model", "")
        in_tok = usage.get("input_tokens")
        out_tok = usage.get("output_tokens")
    p = PRICING.get((provider, model))
    if not p or in_tok is None or out_tok is None:
        return None
    return (in_tok * p["input"] + out_tok * p["output"]) / 1_000_000


# ============================================================
# LLM CLIENT
# ============================================================

class LLMClient:
    """
    Unified LLM client for all supported providers.
    - .complete(prompt, ...) -> CompletionResult       (free-form text)
    - .complete_json(prompt, ...) -> CompletionResult  (JSON-mode where possible, with text fallback)
    """

    # Timeout in seconds for all API calls
    _TIMEOUT = 90.0

    def __init__(self, provider_id: str, api_key: str, model: str):
        if provider_id not in PROVIDERS:
            raise ValueError(f"Provider inconnu: '{provider_id}'. Choix: {list(PROVIDERS)}")
        self.provider_id = provider_id
        self.api_key = api_key
        self.model = model
        self._cfg = PROVIDERS[provider_id]
        self._client = self._build_client()

    def _build_client(self):
        sdk = self._cfg["sdk"]
        if sdk == "openai":
            from openai import OpenAI
            kwargs = {"api_key": self.api_key, "timeout": self._TIMEOUT}
            if self._cfg["base_url"]:
                kwargs["base_url"] = self._cfg["base_url"]
            return OpenAI(**kwargs)
        elif sdk == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=self.api_key, timeout=self._TIMEOUT)
        elif sdk == "google":
            from google import genai
            return genai.Client(
                api_key=self.api_key,
                http_options={"timeout": int(self._TIMEOUT * 1000)},
            )
        else:
            raise ValueError(f"SDK inconnu: '{sdk}'")

    # ── completion ───────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> CompletionResult:
        return self._do_complete(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
            json_mode=False,
        )

    def complete_json(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> CompletionResult:
        """Same as .complete() but requests JSON output natively.

        The returned .text is the raw JSON string (parse with json.loads).
        If the underlying model returns malformed JSON, the caller is responsible
        for fallback parsing — use _extract_json_block() helper.
        """
        return self._do_complete(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
            json_mode=True,
        )

    def _do_complete(
        self,
        *,
        prompt: str,
        temperature: float | None,
        max_tokens: int | None,
        system: str | None,
        json_mode: bool,
    ) -> CompletionResult:
        sdk = self._cfg["sdk"]
        temp = temperature if temperature is not None else 0.7
        t0 = time.perf_counter()

        if sdk == "openai":
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            kwargs = dict(model=self.model, messages=messages, temperature=temp)
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = self._client.chat.completions.create(**kwargs)
            text = (response.choices[0].message.content or "").strip()
            usage = getattr(response, "usage", None)
            in_tok = _extract_int(usage, "prompt_tokens", "input_tokens")
            out_tok = _extract_int(usage, "completion_tokens", "output_tokens")

        elif sdk == "anthropic":
            user_message = {"role": "user", "content": prompt}
            messages = [user_message]
            # JSON mode via prefill: force the assistant to start with "{"
            if json_mode:
                messages.append({"role": "assistant", "content": "{"})
            kwargs = dict(
                model=self.model,
                max_tokens=max_tokens if max_tokens is not None else 4096,
                messages=messages,
                temperature=temp,
            )
            if system:
                kwargs["system"] = system
            response = self._client.messages.create(**kwargs)
            raw_text = (response.content[0].text or "").strip()
            # Re-attach the prefilled "{" so the caller sees valid JSON
            text = ("{" + raw_text) if json_mode else raw_text
            usage = getattr(response, "usage", None)
            in_tok = _extract_int(usage, "input_tokens")
            out_tok = _extract_int(usage, "output_tokens")

        elif sdk == "google":
            from google.genai import types as _genai_types
            config_kwargs = dict(
                temperature=temp,
                max_output_tokens=max_tokens if max_tokens is not None else 8192,
                system_instruction=system,
            )
            if json_mode:
                config_kwargs["response_mime_type"] = "application/json"
            gen_config = _genai_types.GenerateContentConfig(**config_kwargs)
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=gen_config,
            )
            text = (response.text or "").strip()
            meta = getattr(response, "usage_metadata", None)
            in_tok = _extract_int(meta, "prompt_token_count", "input_tokens")
            out_tok = _extract_int(meta, "candidates_token_count", "output_tokens")

        else:
            raise ValueError(f"SDK inconnu: '{sdk}'")

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return CompletionResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            provider=self.provider_id,
            model=self.model,
            latency_ms=latency_ms,
        )

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def list_models(provider_id: str, api_key: str) -> list[str]:
        """
        Fetch available text-generation models from the provider's API.
        Returns a sorted list of model IDs.
        Falls back to the default_models list on any error.
        """
        cfg = PROVIDERS.get(provider_id)
        if not cfg:
            return []

        try:
            sdk = cfg["sdk"]
            if sdk == "openai":
                from openai import OpenAI
                kwargs = {"api_key": api_key}
                if cfg["base_url"]:
                    kwargs["base_url"] = cfg["base_url"]
                client = OpenAI(**kwargs)
                models = client.models.list()
                ids = sorted(m.id for m in models.data)
                return ids if ids else cfg["default_models"]

            elif sdk == "anthropic":
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key)
                models = client.models.list(limit=100)
                ids = sorted(m.id for m in models.data)
                return ids if ids else cfg["default_models"]

            elif sdk == "google":
                from google import genai
                client = genai.Client(api_key=api_key)
                models = client.models.list()
                ids = sorted(
                    m.name.removeprefix("models/")
                    for m in models
                    if hasattr(m, "supported_generation_methods")
                    and "generateContent" in (m.supported_generation_methods or [])
                )
                return ids if ids else cfg["default_models"]

        except Exception:
            pass

        return cfg["default_models"]

    @staticmethod
    def validate_key(provider_id: str, api_key: str) -> tuple[bool, str]:
        """Quick validation: try to list models and return (ok, message)."""
        if not api_key or not api_key.strip():
            return False, "La clé API ne peut pas être vide."
        try:
            models = LLMClient.list_models(provider_id, api_key.strip())
            if models:
                return True, f"Clé valide — {len(models)} modèle(s) disponible(s)."
            return False, "Aucun modèle retourné. Vérifiez la clé."
        except Exception as e:
            return False, f"Erreur de validation: {e}"


# ============================================================
# JSON FALLBACK HELPER
# ============================================================

def extract_json_block(text: str) -> dict | None:
    """Best-effort: extract the first balanced { ... } block from text.

    Strips ``` fences, ignores leading commentary, and parses the JSON.
    Returns None if no valid JSON object is found.
    """
    if not text:
        return None
    # Try direct parse first
    s = text.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Find first balanced { ... } using depth counter
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def _extract_int(obj, *attrs) -> int | None:
    """Try each attribute on obj, return the first int found, else None."""
    if obj is None:
        return None
    for a in attrs:
        v = getattr(obj, a, None)
        if isinstance(v, int):
            return v
    return None
