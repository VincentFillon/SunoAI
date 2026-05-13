"""
settings.py — Configuration persistence for Suno AI Prompt Generator.

Config stored in config.json next to the executable (never bundled).
Supports multiple provider keys — switching provider preserves previous keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from providers import PROVIDERS

# ============================================================
# KEYRING — optional secure key storage
# ============================================================

try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except Exception:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "SunoAI"


# ============================================================
# PATH RESOLUTION — PyInstaller-aware
# ============================================================

def get_config_path() -> Path:
    """Resolve config.json path next to the exe (frozen) or script."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "config.json"


# ============================================================
# LOAD / SAVE
# ============================================================

def load_config() -> dict | None:
    """Return parsed config dict, or None if not found / invalid."""
    path = get_config_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Minimum viable config: provider + model
        if data.get("provider") and data.get("model"):
            return data
        return None
    except Exception:
        return None


def save_config(provider: str, model: str, api_key: str) -> None:
    """
    Write/update config.json.
    API key is stored in the OS Credential Manager (keyring) when available,
    otherwise falls back to config.json. Other provider keys are always preserved.
    """
    path = get_config_path()
    data: dict = {}

    # Load existing config to preserve other provider keys
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data["provider"] = provider
    data["model"] = model

    env_var = PROVIDERS[provider]["env_var"]
    if _KEYRING_AVAILABLE:
        # Store key securely in OS Credential Manager; remove it from JSON
        _keyring.set_password(_KEYRING_SERVICE, env_var, api_key.strip())
        data.pop(env_var, None)
    else:
        data[env_var] = api_key.strip()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_api_key(provider: str) -> str | None:
    """
    Return the stored API key for the given provider, or None.
    Checks the OS Credential Manager first (if available), then config.json
    as fallback (handles migration from older versions).
    """
    env_var = PROVIDERS[provider]["env_var"]
    if _KEYRING_AVAILABLE:
        try:
            key = _keyring.get_password(_KEYRING_SERVICE, env_var)
            if key:
                return key
        except Exception:
            pass
    # Fallback: read from config.json (legacy or keyring unavailable)
    data = load_config()
    if not data:
        return None
    return data.get(env_var) or None


def get_current_provider() -> str | None:
    data = load_config()
    return data.get("provider") if data else None


def get_current_model() -> str | None:
    data = load_config()
    return data.get("model") if data else None
