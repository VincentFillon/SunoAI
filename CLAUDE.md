# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run in development
python app.py

# Build standalone executable (build + auto-sign with self-signed cert)
python build.py
# Output: dist/SunoAI.exe (signed)

# Options:
# python build.py --cert-only   # (re)generate certificate only
# python build.py --build-only  # build without signing
# pyinstaller SunoAI.spec --clean  # raw PyInstaller (no signing)
```

There are no automated tests in this project. Verification is manual.

## Architecture

Desktop GUI application generating Suno AI music prompts via LLMs. Five-phase pipeline:

1. **Phase 0** (optional) — opportunistic pre-clarification for vague intents (<25 words or missing genre+mood/instrument cues).
2. **Phase 1** — style analysis (JSON), populates the editable analysis fields.
3. **Phase 2** — typed personalization questions (single-choice chips, multi-select, free text). The LLM tags each question with an `impact` axis (theme, imagery, energy_arc, vocal_register, language_switch, section_focus).
4. **Phase 3A** — title + style descriptor (focused LLM call with low temperature).
5. **Phase 3B** — lyrics with rich Suno bracket instructions (longer call with few-shot example matched to vocal presence + genre family).

Phase 3A is skipped on regeneration when the user feedback does not mention style/sound, halving regen cost in the common case.

### Module responsibilities

- **[app.py](app.py)** — PySide6 UI. Manages `AppState` FSM, `QThread` workers, all widgets. No business logic.
- **[core.py](core.py)** — Pure business logic: phase orchestration, JSON-first response parsing with text fallback, retry/backoff with rate-limit awareness, semantic validation (rhyme/structure/language/clichés), session dict, atomic save. No I/O, no UI imports.
- **[providers.py](providers.py)** — `LLMClient` with `.complete()` and `.complete_json()` returning `CompletionResult` (text + tokens + latency). Native JSON mode per SDK (`response_format`, Anthropic prefill, `response_mime_type`). Includes `PRICING` table and `estimate_cost()`. `PROVIDERS` registry covers 6 providers behind 3 SDKs.
- **[prompts.py](prompts.py)** — All LLM templates (`PHASE0_TEMPLATE`, `PHASE1_ANALYSIS`, `PHASE3A_STYLE`, `PHASE3B_LYRICS`, `COMPOSITION_SYSTEM`), the Suno meta-tag canonical table, the few-shot library indexed by `(vocal_presence, genre_family)`, language stopwords for validation, the section-name canonical map (FR↔EN), and the `LYRICS_CLICHES` list.
- **[settings.py](settings.py)** — `config.json` read/write, PyInstaller-aware path resolution (`sys.frozen`).
- **[history_index.py](history_index.py)** — SQLite + FTS5 index (`history.db` next to the executable). Powers fast pagination, debounced live search, and monthly usage aggregates. Falls back to LIKE if FTS5 is unavailable.
- **[prompt_generator.py](prompt_generator.py)** — Original CLI fallback (intact, not imported by the GUI).

### Session lifecycle

`IDLE → ANALYZING → QUESTIONS_READY → GENERATING → OUTPUT_READY`

`session` dict initialized by `core.init_session()`. Key fields beyond the obvious:
- `intent_axes` — structured intent (mood/energy/era/instrumentation/vocal_style/language)
- `phase0_missing_axes`, `phase0_best_guess` — pre-clarification output
- `questions` — list of typed dicts (`id`, `type`, `prompt`, `options`, `impact`); `questions_raw` is the legacy pipe-separated string kept for backward compatibility
- `usage` — list of per-call records `{phase, input_tokens, output_tokens, latency_ms, provider, model, cost_usd}`

### Config file

`config.json` lives next to the executable (never bundled). Created by the Settings panel on first launch. Structure: `{"provider": "...", "model": "...", "OPENAI_API_KEY": "...", ...}` — keys stored by their env var name.

### Threading model

LLM calls run in `QThread` with `QObject` workers (`AnalyzeWorker`, `GenerateWorker`). Signals are auto-queued to the main thread. Workers expose:

- `status(str)` — human progress messages
- `usage(dict)` — per-call usage record (refreshes the cost badge live)
- `rate_limit(float)` — countdown trigger for `RateLimitBanner`
- `finished()` / `error(str)` / `cancelled()` / `stopped()`

`core.run_*` functions all accept `on_retry`, `on_rate_limit`, `on_usage`, `stop_event` callbacks; the workers wire them to their signals.

### Output files

Sessions are saved as Markdown files in `outputs/` (timestamped filenames). The HTML comment header carries the full session JSON metadata (including `usage`). Subsequent generations append a `---` separator + new block. History parsing remains backward-compatible with older files.

### Search & history

`history.db` (SQLite) is created next to the executable on first launch. The app reindexes the `outputs/` directory in the background at startup using cheap mtime comparison. The history panel uses:

- Debounced live search (250 ms) via FTS5 (or LIKE fallback).
- Lazy parsing — only the current page's files are read from disk.
- Per-session aggregates (tokens, cost) feed the Usage tab in Settings.

### Cost / observability

`PRICING` table in [providers.py](providers.py) is dated `# Updated YYYY-MM-DD`. `estimate_cost()` returns `None` for unknown (provider, model) pairs; the UI shows `~?` in that case. Live cost badge is on the stepper; full session total is shown in Step 4; monthly aggregates per (provider, model) appear in the Settings panel.

### PyInstaller notes

- PySide6 has built-in PyInstaller hooks. The spec lists local modules (`core`, `providers`, `prompts`, `settings`, `history_index`) in `hiddenimports` for safety.
- All SDK hidden imports listed explicitly in [SunoAI.spec](SunoAI.spec).
- Path resolution in `core.py`, `settings.py`, `history_index.py` uses `sys.frozen` to locate files next to `sys.executable` when packaged.
- `history.db` is created next to the executable on first run — never bundled.
