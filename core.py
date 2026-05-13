"""
core.py — Pure logic for Suno AI Prompt Generator.

No user I/O, no sys.exit(). All errors raised as RuntimeError or ValueError.
Imports prompts from prompts.py and CompletionResult from providers.py.

Pipeline (all phases share a `session` dict + LLMClient):
    run_phase0_intent    (optional pre-clarification on vague intents)
    run_phase1_analysis  (style analysis, JSON output)
    run_composition      (orchestrates Phase 3A + Phase 3B)
        run_composition_style    (title + style descriptor, Phase 3A)
        run_composition_lyrics   (lyrics with rich brackets, Phase 3B)
    save_session         (atomic markdown write)

Usage tracking: every call appends to session["usage"] with input/output tokens, latency,
provider, model, phase label, and estimated cost (USD) where pricing is known.
"""

from __future__ import annotations

import os
import sys
import time
import json
import re
import random
import tempfile
import datetime
import glob
from pathlib import Path

from providers import CompletionResult, estimate_cost, extract_json_block
from prompts import (
    COMPOSITION_SYSTEM,
    PHASE0_TEMPLATE,
    PHASE1_ANALYSIS,
    PHASE3A_STYLE,
    PHASE3B_LYRICS,
    SUNO_BRACKETS_TABLE,
    LYRICS_CLICHES,
    STOPWORDS_BY_LANG,
    canonical_section,
    pick_few_shot,
    render_few_shot_block,
)

# ============================================================
# PATHS — PyInstaller-aware
# ============================================================

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
OUTPUTS_DIR = str(_BASE_DIR / "outputs")

# ============================================================
# CONSTANTS
# ============================================================

API_RETRY_COUNT = 3
RATE_LIMIT_WAIT = 60  # seconds

VALID_VOCAL_PRESENCE = {"NONE", "MINIMAL", "MODERATE", "FULL"}

_AUTH_ERROR_KEYWORDS = (
    "api_key", "authentication", "unauthorized", "invalid_api_key",
    "auth_error", "permission",
)
_RATE_LIMIT_KEYWORDS = (
    "429", "quota", "rate_limit", "rate limit", "resource_exhausted",
    "too many requests", "requests per minute", "requests per day", "ratelimit",
)


# ============================================================
# SESSION
# ============================================================

def init_session() -> dict:
    """Create an empty session dict with all expected keys."""
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "id": session_id,
        "user_intent": "",
        # Phase 0 — pre-clarification
        "phase0_missing_axes": [],
        "phase0_best_guess": {},
        # Phase 1 — analysis
        "intent_axes": {},
        "vocal_presence": "",
        "vocal_delivery": "",
        "song_structure": "",
        "rhyme_pattern": "",
        "lyrical_tone": "",
        "sonic_identity": "",
        "detected_language": "",
        "questions": [],           # New: list of typed question dicts
        "questions_raw": "",       # Legacy: pipe-separated string
        # Phase 2 — answers
        "lyrics_language": "",
        "answers": [],
        # Output
        "title": "",
        "style_prompt": "",
        "lyrics": "",
        "generation_count": 0,
        "regen_feedback": "",
        # Debug
        "last_composition_prompt": "",
        # Metadata
        "provider": "",
        "model": "",
        # Usage / cost
        "usage": [],
    }


# ============================================================
# API WRAPPER
# ============================================================

class CancelledError(Exception):
    """Raised when an API call is cancelled by the user."""


def call_with_retry(
    client,
    prompt: str,
    *,
    label: str = "API",
    on_retry=None,
    on_rate_limit=None,
    stop_event=None,
    json_mode: bool = False,
    **llm_kwargs,
) -> CompletionResult:
    """Call client.complete() or .complete_json() with retry + backoff.

    `on_retry(msg: str)` is called before each retry with a human status.
    `on_rate_limit(wait_seconds: float)` is called once when a 429 triggers the long wait.
    `stop_event` (threading.Event) cancels the call between attempts and during waits.
    """
    last_error = None
    for attempt in range(1, API_RETRY_COUNT + 1):
        if stop_event and stop_event.is_set():
            raise CancelledError("Requête annulée")
        try:
            if json_mode:
                result = client.complete_json(prompt, **llm_kwargs)
            else:
                result = client.complete(prompt, **llm_kwargs)
            if not result.text or not result.text.strip():
                raise ValueError("Réponse vide de l'API")
            return result
        except CancelledError:
            raise
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in _AUTH_ERROR_KEYWORDS):
                raise RuntimeError(f"[{label}] Erreur d'authentification : {e}")
            last_error = e
            if attempt < API_RETRY_COUNT:
                is_rate_limit = any(k in err_str for k in _RATE_LIMIT_KEYWORDS)
                if is_rate_limit:
                    wait = float(RATE_LIMIT_WAIT)
                    msg = f"[{label}] Limite de débit atteinte (429). Pause de {int(wait)} s avant relance…"
                    if on_rate_limit:
                        try:
                            on_rate_limit(wait)
                        except Exception:
                            pass
                else:
                    wait = min(60.0, 2 ** attempt + random.uniform(0.0, 1.0))
                    msg = f"[{label}] Tentative {attempt} échouée : {e}. Relance dans {wait:.1f} s…"
                if on_retry:
                    on_retry(msg)
                end_time = time.monotonic() + wait
                while time.monotonic() < end_time:
                    if stop_event and stop_event.is_set():
                        raise CancelledError("Requête annulée")
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"[{label}] Échec après {API_RETRY_COUNT} tentatives : {last_error}")


def _record_usage(session: dict, phase: str, result: CompletionResult,
                  on_usage=None) -> None:
    """Append a usage record to session['usage'] with computed cost.

    If `on_usage(rec)` is provided, it is called with the newly-appended record.
    """
    rec = result.to_dict()
    rec["phase"] = phase
    rec["cost_usd"] = estimate_cost(result)
    session.setdefault("usage", []).append(rec)
    if on_usage:
        try:
            on_usage(rec)
        except Exception:
            pass


def _parse_json_safe(text: str) -> dict | None:
    """Best-effort JSON parse: strict first, fallback to extract_json_block."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return extract_json_block(text)


# ============================================================
# PHASE 0 — PRE-CLARIFICATION
# ============================================================

_GENRE_TOKENS = {
    "rock", "metal", "pop", "hip-hop", "hiphop", "rap", "techno", "house", "jazz",
    "folk", "reggae", "blues", "r&b", "rnb", "funk", "punk", "indie", "ambient",
    "trap", "reggaeton", "trance", "dubstep", "disco", "soul", "gospel", "country",
    "classical", "electronic", "edm", "ska", "drill", "afrobeat", "k-pop", "kpop",
    "synthwave", "shoegaze", "post-rock", "post-hardcore", "grunge", "emo",
    "hardstyle", "bossa", "samba", "cumbia", "salsa", "flamenco",
}
_MOOD_TOKENS = {
    "sad", "happy", "melancholic", "aggressive", "calm", "dark", "bright", "intense",
    "soft", "raw", "gritty", "intime", "intimate", "triste", "joyeux", "sombre",
    "calme", "énergique", "energique", "mélancolique", "melancolique", "violent",
    "doux", "grave", "euphoric", "euphorique", "wistful", "nostalgique", "nostalgic",
    "hypnotique", "hypnotic", "anthemic", "anthémique", "moody", "ominous",
}
_INSTR_TOKENS = {
    "guitar", "guitare", "piano", "drums", "batterie", "synth", "synthé", "synthe",
    "bass", "basse", "vocal", "vocals", "voix", "voice", "strings", "cordes",
    "horn", "horns", "cuivre", "cuivres", "sax", "saxophone", "violin", "violon",
    "808", "kick", "snare", "hi-hat", "hihat", "pad", "arp", "arpeggio", "arpège",
    "fingerpicked", "palm-muted", "trumpet", "trompette", "harmonica", "accordeon",
    "accordéon",
}


def _is_intent_rich(intent: str) -> bool:
    """Heuristic: ≥25 words AND mentions a genre AND a mood/instrument cue."""
    if not intent:
        return False
    words = intent.split()
    if len(words) < 25:
        return False
    low = intent.lower()
    has_genre = any(g in low for g in _GENRE_TOKENS)
    has_mood = any(m in low for m in _MOOD_TOKENS)
    has_instr = any(i in low for i in _INSTR_TOKENS)
    return has_genre and (has_mood or has_instr)


def run_phase0_intent(client, session: dict, on_retry=None, on_rate_limit=None,
                      on_usage=None, stop_event=None) -> None:
    """Pre-clarification — only runs if the intent is vague.

    On success, populates session["phase0_missing_axes"] and session["phase0_best_guess"].
    On failure, swallows the error and proceeds (Phase 0 is best-effort).
    """
    intent = (session.get("user_intent") or "").strip()
    if not intent or _is_intent_rich(intent):
        return
    prompt = PHASE0_TEMPLATE.format(user_intent=intent)
    try:
        result = call_with_retry(
            client, prompt, label="Phase 0",
            on_retry=on_retry, on_rate_limit=on_rate_limit,
            stop_event=stop_event,
            json_mode=True,
            temperature=0.3,
            max_tokens=400,
        )
        _record_usage(session, "phase0", result, on_usage=on_usage)
        data = _parse_json_safe(result.text) or {}
        missing = data.get("missing_axes") or []
        guess = data.get("best_guess_filling") or {}
        if isinstance(missing, list):
            session["phase0_missing_axes"] = [str(x) for x in missing if x]
        if isinstance(guess, dict):
            session["phase0_best_guess"] = {str(k): str(v) for k, v in guess.items() if v}
    except CancelledError:
        raise
    except Exception:
        # Phase 0 is opportunistic — failures must not block Phase 1.
        pass


def _format_phase0_hint(session: dict) -> str:
    missing = session.get("phase0_missing_axes") or []
    guess = session.get("phase0_best_guess") or {}
    if not missing and not guess:
        return ""
    parts = ["Pre-analysis hints (use only if consistent with the user's intent):"]
    if missing:
        parts.append("- Potentially missing axes in the description: " + ", ".join(missing))
    if guess:
        guess_str = ", ".join(f"{k}={v}" for k, v in guess.items())
        parts.append("- Best-guess filling: " + guess_str)
    return "\n".join(parts) + "\n"


# ============================================================
# PHASE 1 — STYLE ANALYSIS (JSON output)
# ============================================================

def run_phase1_analysis(client, session: dict, on_retry=None, on_rate_limit=None,
                        on_usage=None, stop_event=None) -> None:
    """Run style analysis (Phase 1). Modifies session in place.

    Tries JSON output first; falls back to defaults on the last attempt.
    """
    phase0_hint = _format_phase0_hint(session)
    correction = ""
    last_error = None
    last_data: dict | None = None

    for attempt in range(1, API_RETRY_COUNT + 1):
        if stop_event and stop_event.is_set():
            raise CancelledError("Requête annulée")
        is_last = attempt == API_RETRY_COUNT
        prompt = PHASE1_ANALYSIS.format(
            user_intent=session["user_intent"],
            phase0_hint=phase0_hint,
        ) + correction
        try:
            result = call_with_retry(
                client, prompt, label="Phase 1",
                on_retry=on_retry, on_rate_limit=on_rate_limit,
                stop_event=stop_event,
                json_mode=True,
                temperature=0.3,
                max_tokens=2000,
            )
            _record_usage(session, "analysis", result, on_usage=on_usage)
            data = _parse_json_safe(result.text)
            if not data or not isinstance(data, dict):
                raise ValueError("Sortie JSON invalide")
            last_data = data
            _apply_analysis(session, data, strict=not is_last)
            return
        except CancelledError:
            raise
        except (ValueError, RuntimeError) as e:
            last_error = e
            if not is_last:
                correction = (
                    f"\n\nATTENTION: Ta réponse précédente était mal formée ({e}). "
                    f"Retourne EXACTEMENT un objet JSON valide conforme au schéma demandé. "
                    f"Pas de markdown, pas de commentaire."
                )
                if on_retry:
                    on_retry(f"Phase 1 — reformatage requis, tentative {attempt + 1}/{API_RETRY_COUNT}…")
            else:
                # Last attempt: try to recover with whatever we have
                try:
                    _apply_analysis(session, last_data or {}, strict=False)
                    if on_retry:
                        on_retry("Phase 1 — analyse partielle acceptée avec valeurs par défaut.")
                    return
                except Exception:
                    raise RuntimeError(f"Erreur fatale Phase 1 : {last_error}")


def _apply_analysis(session: dict, data: dict, strict: bool = True) -> None:
    """Apply Phase 1 JSON data to session, with defaults when not strict."""
    intent = data.get("intent") or {}
    if not isinstance(intent, dict):
        intent = {}
    session["intent_axes"] = intent

    vp = _norm_vocal_presence(data.get("vocal_presence"), strict=strict)
    session["vocal_presence"] = vp

    vd = data.get("vocal_delivery")
    if not vd:
        vd = "n/a" if vp in ("NONE", "MINIMAL") else "standard vocal delivery"
    session["vocal_delivery"] = str(vd).strip()

    sstr = data.get("song_structure")
    if isinstance(sstr, list):
        session["song_structure"] = " / ".join(str(s).strip() for s in sstr if str(s).strip())
    elif isinstance(sstr, str) and sstr.strip():
        session["song_structure"] = sstr.strip()
    else:
        if strict:
            raise ValueError("song_structure manquant")
        session["song_structure"] = "verse / chorus / verse / chorus / bridge / outro"

    rhyme = data.get("rhyme_pattern") or ""
    rhyme = rhyme.strip() if isinstance(rhyme, str) else ""
    if not rhyme:
        rhyme = "n/a" if vp in ("NONE", "MINIMAL") else "AABB"
    session["rhyme_pattern"] = rhyme

    tone = data.get("lyrical_tone") or ""
    tone = tone.strip() if isinstance(tone, str) else ""
    if not tone:
        tone = "n/a" if vp in ("NONE", "MINIMAL") else "expressive, evocative"
    session["lyrical_tone"] = tone

    sid = data.get("sonic_identity")
    if isinstance(sid, list):
        session["sonic_identity"] = ", ".join(str(s).strip() for s in sid if str(s).strip())
    elif isinstance(sid, str) and sid.strip():
        session["sonic_identity"] = sid.strip()
    else:
        if strict:
            raise ValueError("sonic_identity manquant")
        session["sonic_identity"] = "modern production"

    lang = data.get("detected_language") or intent.get("language") or ""
    lang = lang.strip() if isinstance(lang, str) else ""
    session["detected_language"] = lang or "English"

    raw_qs = data.get("questions") or []
    if not isinstance(raw_qs, list):
        raw_qs = []
    cleaned_qs = []
    for q in raw_qs[:3]:
        if not isinstance(q, dict):
            continue
        prompt_text = (q.get("prompt") or "").strip()
        if not prompt_text:
            continue
        impact = (q.get("impact") or "").strip().lower()
        if impact == "none":
            continue
        qtype = (q.get("type") or "free").strip().lower()
        if qtype not in ("single", "multi", "free"):
            qtype = "free"
        opts = q.get("options") or []
        if not isinstance(opts, list):
            opts = []
        opts = [str(o).strip() for o in opts if str(o).strip()]
        cleaned_qs.append({
            "id": str(q.get("id") or f"q{len(cleaned_qs) + 1}"),
            "type": qtype,
            "prompt": prompt_text,
            "options": opts,
            "impact": impact or "theme",
        })
    session["questions"] = cleaned_qs
    session["questions_raw"] = " | ".join(q["prompt"] for q in cleaned_qs)


def _norm_vocal_presence(v, strict: bool = True) -> str:
    vp_raw = str(v or "").upper().strip()
    vp = vp_raw.split()[0] if vp_raw else ""
    if vp not in VALID_VOCAL_PRESENCE:
        if strict:
            raise ValueError(f"VOCAL_PRESENCE invalide : '{v}'")
        return "FULL"
    return vp


# ============================================================
# PHASE 3A — TITLE + STYLE
# ============================================================

def run_composition_style(client, session: dict, on_retry=None, on_rate_limit=None,
                          on_usage=None, stop_event=None) -> None:
    """Generate title + style descriptor (Phase 3A). Modifies session in place."""
    user_context = _build_user_context(session)
    previous_gen_hint = _build_previous_gen_hint(session)
    intent = session.get("intent_axes") or {}
    prompt = PHASE3A_STYLE.format(
        user_intent=session["user_intent"],
        vocal_presence=session["vocal_presence"],
        vocal_delivery=session["vocal_delivery"],
        sonic_identity=session["sonic_identity"],
        lyrical_tone=session["lyrical_tone"],
        era=intent.get("era") or "contemporary",
        mood=intent.get("mood") or "expressive",
        lyrics_language=session["lyrics_language"] or session["detected_language"],
        user_context=user_context,
        previous_gen_hint=previous_gen_hint,
    )
    correction = ""
    last_error = None
    last_title = ""
    last_style = ""
    for attempt in range(1, API_RETRY_COUNT + 1):
        if stop_event and stop_event.is_set():
            raise CancelledError("Requête annulée")
        full_prompt = prompt + correction
        try:
            result = call_with_retry(
                client, full_prompt, label="Phase 3A",
                on_retry=on_retry, on_rate_limit=on_rate_limit,
                stop_event=stop_event,
                json_mode=True,
                system=COMPOSITION_SYSTEM,
                temperature=0.4,
                max_tokens=600,
            )
            _record_usage(session, "composition_style", result, on_usage=on_usage)
            data = _parse_json_safe(result.text)
            if not data or not data.get("title") or not data.get("style"):
                raise ValueError("Champ 'title' ou 'style' manquant dans la sortie")
            title = str(data["title"]).strip().strip('"').strip("'")
            style = str(data["style"]).strip()
            last_title = title
            last_style = style
            mech = _validate_style(title, style)
            if mech and attempt < API_RETRY_COUNT:
                vlist = "\n".join(f"- {v}" for v in mech)
                correction = (
                    f"\n\nFix the following STYLE/TITLE issues, then return the JSON again:\n{vlist}"
                )
                if on_retry:
                    on_retry(
                        f"Phase 3A — {len(mech)} violation(s) détectée(s), "
                        f"correction tentative {attempt + 1}/{API_RETRY_COUNT}…"
                    )
                continue
            session["title"] = title
            session["style_prompt"] = style
            return
        except CancelledError:
            raise
        except (ValueError, RuntimeError) as e:
            last_error = e
            if attempt < API_RETRY_COUNT:
                correction = (
                    f"\n\nATTENTION: Sortie mal formée ({e}). Retourne UN SEUL OBJET JSON "
                    f'{{\"title\": \"...\", \"style\": \"...\"}} et rien d\'autre.'
                )
                if on_retry:
                    on_retry(f"Phase 3A — reformatage requis, tentative {attempt + 1}/{API_RETRY_COUNT}…")
            else:
                if last_title and last_style:
                    # Graceful degradation
                    session["title"] = last_title
                    session["style_prompt"] = last_style
                    if on_retry:
                        on_retry("Phase 3A — best-effort accepté malgré violations restantes.")
                    return
                raise RuntimeError(f"Erreur fatale Phase 3A : {last_error}")


def _validate_style(title: str, style: str) -> list[str]:
    """Mechanical checks for title + style — keeps Phase 3A tight."""
    v: list[str] = []
    if not title:
        v.append("TITLE is empty.")
    elif len(title.split()) > 6:
        v.append(f"TITLE too long ({len(title.split())} words, maximum 6).")
    if "..." in style or "..." in title:
        v.append("Ellipses (...) are forbidden in TITLE/STYLE.")
    if "—" in style or "—" in title:
        v.append("Em-dashes (—) are forbidden in TITLE/STYLE.")
    sw = len(style.split())
    if sw < 20:
        v.append(f"STYLE too short ({sw} words, minimum 20). Add specific production descriptors.")
    elif sw > 50:
        v.append(f"STYLE too long ({sw} words, maximum 50). Remove filler.")
    return v


# ============================================================
# PHASE 3B — LYRICS
# ============================================================

def run_composition_lyrics(client, session: dict, on_retry=None, on_rate_limit=None,
                           on_usage=None, stop_event=None) -> None:
    """Generate lyrics (Phase 3B). Requires session['title'] and session['style_prompt']."""
    user_context = _build_user_context(session)
    previous_gen_hint = _build_previous_gen_hint(session)

    intent = session.get("intent_axes") or {}
    hints = [
        intent.get("vocal_style") or "",
        intent.get("instrumentation") or "",
        session.get("sonic_identity") or "",
        session.get("user_intent") or "",
    ]
    if isinstance(hints[1], list):
        hints[1] = " ".join(str(x) for x in hints[1])
    example = pick_few_shot(session["vocal_presence"], [str(h) for h in hints])
    few_shot_block = render_few_shot_block(example)

    prompt = PHASE3B_LYRICS.format(
        user_intent=session["user_intent"],
        vocal_presence=session["vocal_presence"],
        vocal_delivery=session["vocal_delivery"],
        song_structure=session["song_structure"],
        rhyme_pattern=session["rhyme_pattern"],
        lyrical_tone=session["lyrical_tone"],
        sonic_identity=session["sonic_identity"],
        lyrics_language=session["lyrics_language"] or session["detected_language"],
        title=session["title"],
        style=session["style_prompt"],
        user_context=user_context,
        previous_gen_hint=previous_gen_hint,
        few_shot_block=few_shot_block,
        brackets_table=SUNO_BRACKETS_TABLE,
    )
    correction = ""
    last_error = None
    last_lyrics = ""
    regen = session["generation_count"] > 0
    for attempt in range(1, API_RETRY_COUNT + 1):
        if stop_event and stop_event.is_set():
            raise CancelledError("Requête annulée")
        full_prompt = prompt + correction
        try:
            result = call_with_retry(
                client, full_prompt, label="Phase 3B",
                on_retry=on_retry, on_rate_limit=on_rate_limit,
                stop_event=stop_event,
                json_mode=True,
                system=COMPOSITION_SYSTEM,
                temperature=0.85 if regen else 0.75,
                max_tokens=3000,
            )
            _record_usage(session, "composition_lyrics", result, on_usage=on_usage)
            data = _parse_json_safe(result.text)
            if not data or not data.get("lyrics"):
                raise ValueError("Champ 'lyrics' manquant dans la sortie")
            lyrics = str(data["lyrics"]).strip()
            last_lyrics = lyrics
            analysis = _session_analysis_view(session)
            violations = validate_composition(
                title=session["title"],
                style=session["style_prompt"],
                lyrics=lyrics,
                analysis=analysis,
            )
            if violations and attempt < API_RETRY_COUNT:
                vlist = "\n".join(f"- {v}" for v in violations)
                correction = (
                    f"\n\nFix the following LYRICS violations and return the JSON again:\n{vlist}\n"
                    f'Return only {{"lyrics": "..."}} and nothing else.'
                )
                if on_retry:
                    on_retry(
                        f"Phase 3B — {len(violations)} violation(s) détectée(s), "
                        f"correction tentative {attempt + 1}/{API_RETRY_COUNT}…"
                    )
                continue
            session["lyrics"] = lyrics
            session["last_composition_prompt"] = full_prompt
            return
        except CancelledError:
            raise
        except (ValueError, RuntimeError) as e:
            last_error = e
            if attempt < API_RETRY_COUNT:
                correction = (
                    f"\n\nATTENTION: Sortie mal formée ({e}). Retourne UN SEUL OBJET JSON "
                    f'avec la forme {{"lyrics": "..."}} et rien d\'autre.'
                )
                if on_retry:
                    on_retry(f"Phase 3B — reformatage requis, tentative {attempt + 1}/{API_RETRY_COUNT}…")
            else:
                if last_lyrics:
                    session["lyrics"] = last_lyrics
                    session["last_composition_prompt"] = full_prompt
                    if on_retry:
                        on_retry("Phase 3B — best-effort accepté malgré violations restantes.")
                    return
                raise RuntimeError(f"Erreur fatale Phase 3B : {last_error}")


def run_composition(client, session: dict, on_retry=None, on_rate_limit=None,
                    on_usage=None, stop_event=None) -> None:
    """Orchestrate Phase 3A + Phase 3B.

    On regeneration, Phase 3A is skipped when the user feedback does not mention style/sound
    cues — saves ~half the regeneration cost while still varying the lyrics.
    """
    skip_3a = False
    if session["generation_count"] > 0 and session.get("title") and session.get("style_prompt"):
        feedback = (session.get("regen_feedback") or "").lower()
        style_terms = re.compile(
            r"\b(style|son|sound|production|instrument|texture|bpm|tempo|genre|ambiance|arrangement|mood|énergie|energy)\b"
        )
        if feedback and not style_terms.search(feedback):
            skip_3a = True
        elif not feedback:
            # No feedback on regen → user wants different lyrics with same vibe
            skip_3a = True
    if not skip_3a:
        run_composition_style(client, session,
                              on_retry=on_retry, on_rate_limit=on_rate_limit,
                              on_usage=on_usage, stop_event=stop_event)
    elif on_retry:
        on_retry("Phase 3A — sautée (style/title réutilisés).")
    run_composition_lyrics(client, session,
                           on_retry=on_retry, on_rate_limit=on_rate_limit,
                           on_usage=on_usage, stop_event=stop_event)
    session["generation_count"] += 1


def _build_user_context(session: dict) -> str:
    lines = [f"{q} -> {a}" for q, a in session["answers"] if a]
    return "\n".join(lines) if lines else "No additional direction — use your best judgment."


def _build_previous_gen_hint(session: dict) -> str:
    if session["generation_count"] == 0:
        return ""
    feedback = (session.get("regen_feedback") or "").strip()
    fb_block = ""
    if feedback:
        fb_block = (
            f"\nUser feedback on previous generation: {feedback}\n"
            f"Address this feedback directly — it is the primary constraint for this regeneration.\n"
        )
    return (
        "\n--- PREVIOUS GENERATION (DO NOT repeat) ---\n"
        f"Previous title: {session['title']}\n"
        f"Previous style: {session['style_prompt']}\n"
        f"{fb_block}"
        "Generate something MEANINGFULLY DIFFERENT — different imagery, different structural approach, different opening line.\n"
    )


def _session_analysis_view(session: dict) -> dict:
    return {
        "vocal_presence": session["vocal_presence"],
        "vocal_delivery": session["vocal_delivery"],
        "song_structure": session["song_structure"],
        "rhyme_pattern": session["rhyme_pattern"],
        "lyrical_tone": session["lyrical_tone"],
        "lyrics_language": session["lyrics_language"] or session["detected_language"],
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_composition(title: str, style: str, lyrics: str, analysis: dict | None = None) -> list[str]:
    """Mechanical + semantic checks on the composition.

    Returns a list of violation strings (empty = all good).
    `analysis` is the session analysis view; when None, only mechanical checks run.
    """
    violations: list[str] = []
    analysis = analysis or {}

    # ── Mechanical ───────────────────────────────────────────
    style_words = len(style.split())
    if style_words < 20:
        violations.append(
            f"STYLE too short ({style_words} words, minimum 20). "
            f"Add specific production descriptors: subgenre, instruments, vocal texture, era, atmosphere."
        )
    elif style_words > 50:
        violations.append(
            f"STYLE too long ({style_words} words, maximum 50). Remove filler phrases."
        )

    brackets = re.findall(r"\[([^\]]+)\]", lyrics)
    if not brackets:
        violations.append(
            "LYRICS contains no bracketed section labels at all. "
            "Every section must start with [Section - vocal, instrument, energy, mood]."
        )
    else:
        rich = [b for b in brackets if re.search(r"-\s*.{10,}", b)]
        if len(rich) < max(1, len(brackets) // 2):
            violations.append(
                f"LYRICS has only {len(rich)} rich bracket(s) out of {len(brackets)}. "
                f"Every bracket must include description after the dash."
            )

    long_lines = []
    for i, line in enumerate(lyrics.splitlines(), 1):
        s = line.strip()
        if s and not s.startswith("["):
            if len(s.split()) > 12:
                long_lines.append(f"line {i} ({len(s.split())} words)")
    if long_lines:
        violations.append(
            f"LYRICS has {len(long_lines)} line(s) exceeding 12 words — Suno will rush the delivery. "
            f"Break them: {', '.join(long_lines[:3])}."
        )

    if "..." in lyrics:
        violations.append("LYRICS contains ellipses (...). Remove them or replace with a line break.")

    for line in lyrics.splitlines():
        s = line.strip()
        if s and not s.startswith("["):
            if "—" in s or " -- " in s:
                violations.append("LYRICS contains em-dashes (—) in lyric lines. Remove them.")
                break

    # ── Semantic (when analysis present) ─────────────────────
    if analysis:
        vp = (analysis.get("vocal_presence") or "").upper()

        # Clichés
        low = lyrics.lower()
        hits = [c for c in LYRICS_CLICHES if c in low]
        if hits:
            violations.append(
                "LYRICS contains banned clichés: " + ", ".join(hits[:5])
                + ". Replace each with a CONCRETE PHYSICAL IMAGE specific to this song."
            )

        # Structure (FULL only — others are too loose to enforce)
        section_names = [_section_root(b) for b in brackets]
        if vp == "FULL":
            canonicals = {canonical_section(s) for s in section_names if s}
            if "verse" not in canonicals:
                violations.append(
                    "LYRICS has no verse section — at least one [Verse] is required for FULL vocal presence."
                )
            if "chorus" not in canonicals:
                violations.append(
                    "LYRICS has no chorus/refrain section — required for FULL vocal presence."
                )

        # Vocal presence vs lyric density
        non_bracket = [l for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")]
        density = len(non_bracket)
        if vp == "NONE" and density > 0:
            violations.append(
                "VOCAL_PRESENCE=NONE but lyric lines were written. Use only bracketed instructions."
            )
        elif vp == "MINIMAL" and density > 4:
            violations.append(
                f"VOCAL_PRESENCE=MINIMAL but {density} lyric line(s). Keep only one short hook."
            )
        elif vp == "FULL" and density < 8:
            violations.append(
                f"VOCAL_PRESENCE=FULL but only {density} lyric line(s). "
                f"Write complete verses and choruses."
            )

        # Rhyme pattern
        rhyme = (analysis.get("rhyme_pattern") or "").upper().strip()
        if vp in ("FULL", "MODERATE") and rhyme in ("AABB", "ABAB", "ABBA"):
            ratio = _rhyme_match_ratio(lyrics, rhyme)
            if ratio < 0.6:
                violations.append(
                    f"Rhyme pattern {rhyme} not consistently respected (≈{int(ratio * 100)}% match). "
                    f"Adjust end-rhymes to fit the declared scheme."
                )

        # Language
        lang = (analysis.get("lyrics_language") or "").strip().lower()
        if lang and lang in STOPWORDS_BY_LANG and vp in ("FULL", "MODERATE", "MINIMAL"):
            mismatch = _language_mismatch_ratio(lyrics, lang)
            if mismatch > 0.25:
                violations.append(
                    f"More than {int(mismatch * 100)}% of lyric lines don't match the chosen language "
                    f"({lang}). Rewrite stray lines in the target language."
                )

    return violations


def _section_root(bracket_content: str) -> str:
    """Get the section name (before ' - ') from a bracket body."""
    return bracket_content.split("-", 1)[0].strip()


def _rhyme_match_ratio(lyrics: str, pattern: str) -> float:
    """Coarse rhyme heuristic over 4-line stanzas of non-bracket lines."""
    lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")]
    if len(lines) < 4:
        return 1.0
    pattern_idx = {"AABB": [0, 0, 1, 1],
                   "ABAB": [0, 1, 0, 1],
                   "ABBA": [0, 1, 1, 0]}.get(pattern.upper())
    if not pattern_idx:
        return 1.0
    ok, total = 0, 0
    for start in range(0, len(lines) - 3, 4):
        stanza = lines[start:start + 4]
        last_words = [_strip_punct(s.split()[-1]).lower() for s in stanza if s.split()]
        if len(last_words) != 4:
            continue
        groups: dict[int, list[str]] = {}
        for i, g in enumerate(pattern_idx):
            groups.setdefault(g, []).append(last_words[i])
        for grp in groups.values():
            if len(grp) < 2:
                continue
            total += 1
            if _rhymes_loose(grp[0], grp[1]):
                ok += 1
    if total == 0:
        return 1.0
    return ok / total


def _strip_punct(w: str) -> str:
    return re.sub(r"[^\w']+$", "", w)


def _rhymes_loose(a: str, b: str) -> bool:
    """Loose rhyme: last 2-3 letters match. Not phonetic, but cheap and ≥60% useful."""
    if not a or not b:
        return False
    if a == b:
        return True
    return a[-3:] == b[-3:] or a[-2:] == b[-2:]


def _language_mismatch_ratio(lyrics: str, lang: str) -> float:
    """Ratio of lyric lines that don't contain a single stopword from `lang`."""
    stopwords = STOPWORDS_BY_LANG.get(lang) or set()
    if not stopwords:
        return 0.0
    lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")]
    if not lines:
        return 0.0
    mismatches = 0
    countable = 0
    for line in lines:
        tokens = re.findall(r"[a-zàâäçéèêëîïôöùûüÿœæñü]+", line.lower())
        if len(tokens) < 4:
            continue
        countable += 1
        if not any(t in stopwords for t in tokens):
            mismatches += 1
    if countable == 0:
        return 0.0
    return mismatches / countable


# ============================================================
# SAVE
# ============================================================

def _atomic_write(filepath: str, content: str) -> None:
    """Write content atomically: write to a temp file, then rename."""
    dir_path = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _format_usage_footer(usage: list[dict]) -> str:
    """Compact human-readable usage line for the markdown footer."""
    if not usage:
        return ""
    total_in = sum((u.get("input_tokens") or 0) for u in usage)
    total_out = sum((u.get("output_tokens") or 0) for u in usage)
    costs = [u.get("cost_usd") for u in usage]
    if all(c is None for c in costs):
        cost_str = "~?"
    else:
        total_cost = sum(c for c in costs if c is not None)
        cost_str = f"~${total_cost:.4f}"
    return f"*Tokens : {total_in:,} in / {total_out:,} out — coût estimé {cost_str}*"


def save_session(session: dict) -> str:
    """Save session to markdown, appending a generation block if file exists."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUTS_DIR, f"{session['id']}.md")

    meta = {
        "id": session["id"],
        "user_intent": session.get("user_intent", ""),
        "provider": session.get("provider", ""),
        "model": session.get("model", ""),
        # Analysis
        "intent_axes":       session.get("intent_axes", {}),
        "vocal_presence":    session.get("vocal_presence", ""),
        "vocal_delivery":    session.get("vocal_delivery", ""),
        "song_structure":    session.get("song_structure", ""),
        "rhyme_pattern":     session.get("rhyme_pattern", ""),
        "lyrical_tone":      session.get("lyrical_tone", ""),
        "sonic_identity":    session.get("sonic_identity", ""),
        "detected_language": session.get("detected_language", ""),
        "questions":         session.get("questions", []),
        "questions_raw":     session.get("questions_raw", ""),
        # Phase 2
        "lyrics_language":   session.get("lyrics_language", ""),
        "answers":           session.get("answers", []),
        # Usage
        "usage":             session.get("usage", []),
    }

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ref_display = session.get("user_intent", "")

    answers_md = "\n".join(
        f"- {q} -> {a}" for q, a in session["answers"] if a
    ) or "- (aucune réponse fournie)"

    model_info = f"{session.get('provider', '')} / {session.get('model', '')}".strip(" /")

    prompt_section = ""
    last_prompt = session.get("last_composition_prompt", "")
    if last_prompt:
        prompt_section = f"""
<details>
<summary>Prompt used</summary>

```
{last_prompt}
```

</details>
"""

    usage_footer = _format_usage_footer(session.get("usage") or [])

    block = f"""
---

## Generation #{session['generation_count']} — {ts}

**Reference:** {ref_display}
**Language:** {session['lyrics_language']}

### User Answers
{answers_md}

### TITLE
{session['title']}

### STYLE
{session['style_prompt']}

### LYRICS
{session['lyrics']}

*Model: {model_info}*
{usage_footer}
{prompt_section}"""

    header = (
        f"<!-- session_data: {json.dumps(meta, ensure_ascii=False)} -->\n\n"
        f"# Suno Generation — {session['id']}\n"
    )

    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()
        # Update header (overwrite session_data with the latest one — keeps usage tally fresh)
        existing = re.sub(
            r"<!-- session_data: .*? -->",
            f"<!-- session_data: {json.dumps(meta, ensure_ascii=False)} -->",
            existing,
            count=1,
            flags=re.DOTALL,
        )
        _atomic_write(filepath, existing + block)
    else:
        _atomic_write(filepath, header + block)

    return filepath


# ============================================================
# HISTORY
# ============================================================

def _parse_session_file(filepath: str) -> dict | None:
    """Parse a session .md file. Returns dict with metadata + generations, or None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        header_match = re.search(r"<!-- session_data: ({.*?}) -->", content, re.DOTALL)
        if not header_match:
            return None
        session_data = json.loads(header_match.group(1))

        raw_blocks = re.split(r"\n---\n", content)
        generations = []
        for block in raw_blocks[1:]:
            gen_match = re.search(r"## Generation #(\d+) — (.+)", block)
            if not gen_match:
                continue
            gen_num = int(gen_match.group(1))
            gen_ts = gen_match.group(2).strip()
            title_m = re.search(r"### TITLE\n(.*?)(?=\n###|\n<details|\*Model|\*Tokens|\Z)", block, re.DOTALL)
            style_m = re.search(r"### STYLE\n(.*?)(?=\n###|\n<details|\*Model|\*Tokens|\Z)", block, re.DOTALL)
            lyrics_m = re.search(r"### LYRICS\n(.*?)(?=\n###|\n<details|\*Model|\*Tokens|\Z)", block, re.DOTALL)
            prompt_m = re.search(r"```\n(.*?)```", block, re.DOTALL)
            generations.append({
                "gen_num": gen_num,
                "ts":      gen_ts,
                "title":   title_m.group(1).strip() if title_m else "",
                "style":   style_m.group(1).strip() if style_m else "",
                "lyrics":  lyrics_m.group(1).strip() if lyrics_m else "",
                "prompt":  prompt_m.group(1).strip() if prompt_m else "",
            })
        if not generations:
            return None
        return {
            "filepath":     filepath,
            "session_data": session_data,
            "generations":  sorted(generations, key=lambda g: g["gen_num"]),
        }
    except Exception:
        return None


def load_history() -> list[dict]:
    """Load all session files from OUTPUTS_DIR, newest first."""
    pattern = os.path.join(OUTPUTS_DIR, "*.md")
    files = sorted(glob.glob(pattern), reverse=True)
    entries = []
    for fp in files:
        parsed = _parse_session_file(fp)
        if parsed:
            entries.append(parsed)
    return entries


def list_history_files() -> list[str]:
    """Return sorted .md file paths, newest first, without parsing."""
    pattern = os.path.join(OUTPUTS_DIR, "*.md")
    return sorted(glob.glob(pattern), reverse=True)


def filter_history_files(files: list[str], query: str) -> list[str]:
    """Filter by searching the session header (first 2KB) for the query."""
    if not query.strip():
        return files
    q = query.strip().lower()
    out = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                header = f.read(2048)
            if q in header.lower():
                out.append(fp)
        except Exception:
            pass
    return out


def load_history_page(files: list[str], offset: int, limit: int) -> list[dict]:
    """Parse only the slice files[offset:offset+limit]."""
    entries = []
    for fp in files[offset:offset + limit]:
        parsed = _parse_session_file(fp)
        if parsed:
            entries.append(parsed)
    return entries


def session_from_history(entry: dict) -> dict:
    """Reconstruct a full session dict from a history entry (for Régénérer)."""
    sd = entry["session_data"]
    last_gen = entry["generations"][-1]

    session = init_session()
    session["id"] = sd.get("id", session["id"])

    # Backward compat: old files use style+artist, new files use user_intent
    session["user_intent"] = (
        sd.get("user_intent")
        or " / ".join(filter(None, [sd.get("style", ""), sd.get("artist", "")]))
        or ""
    )

    # Phase 1
    session["intent_axes"]       = sd.get("intent_axes", {}) or {}
    session["vocal_presence"]    = sd.get("vocal_presence", "")
    session["vocal_delivery"]    = sd.get("vocal_delivery", "")
    session["song_structure"]    = sd.get("song_structure", "")
    session["rhyme_pattern"]     = sd.get("rhyme_pattern", "")
    session["lyrical_tone"]      = sd.get("lyrical_tone", "")
    session["sonic_identity"]    = sd.get("sonic_identity", "")
    session["detected_language"] = sd.get("detected_language", "")
    # Questions — prefer typed list if present, else rebuild from legacy string
    typed_qs = sd.get("questions")
    if isinstance(typed_qs, list) and typed_qs:
        session["questions"] = typed_qs
        session["questions_raw"] = " | ".join(
            (q.get("prompt") or "") for q in typed_qs if isinstance(q, dict)
        )
    else:
        legacy_raw = sd.get("questions_raw", "") or ""
        session["questions_raw"] = legacy_raw
        session["questions"] = [
            {"id": f"q{i + 1}", "type": "free", "prompt": p.strip(), "options": [], "impact": "theme"}
            for i, p in enumerate(legacy_raw.split("|")) if p.strip()
        ]

    # Phase 2
    session["lyrics_language"] = sd.get("lyrics_language", "")
    raw_answers = sd.get("answers", [])
    session["answers"] = [(a[0], a[1]) for a in raw_answers if len(a) == 2]

    # Latest generation output
    session["title"]                  = last_gen["title"]
    session["style_prompt"]           = last_gen["style"]
    session["lyrics"]                 = last_gen["lyrics"]
    session["generation_count"]       = last_gen["gen_num"]
    session["last_composition_prompt"] = last_gen.get("prompt", "")

    # Metadata
    session["provider"] = sd.get("provider", "")
    session["model"]    = sd.get("model", "")
    session["usage"]    = sd.get("usage", []) or []

    return session
