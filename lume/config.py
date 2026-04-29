"""
Lume global config — stored at ~/.lume/config.toml.

Structure:
    [github]
    pat = "ghp_..."          # personal access token (optional if gh CLI auth present)

    [[projects]]
    name = "my-project"
    path = "/Users/name/lume-projects/my-project"
    remote = "https://github.com/user/my-project"
    active = true
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import toml

LUME_DIR = Path.home() / ".lume"
CONFIG_PATH = LUME_DIR / "config.toml"


def _ensure_lume_dir() -> None:
    LUME_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    _ensure_lume_dir()
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r") as f:
        return toml.load(f)


def save_config(cfg: dict) -> None:
    _ensure_lume_dir()
    with open(CONFIG_PATH, "w") as f:
        toml.dump(cfg, f)


# ── GitHub PAT ──────────────────────────────────────────────────────────────

def get_anthropic_api_key() -> Optional[str]:
    """Return Anthropic API key from ANTHROPIC_API_KEY env var or config.toml [anthropic] api_key."""
    import os
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key
    cfg = load_config()
    return cfg.get("anthropic", {}).get("api_key")


def set_anthropic_api_key(key: str) -> None:
    cfg = load_config()
    cfg.setdefault("anthropic", {})["api_key"] = key
    save_config(cfg)


def get_gemini_api_key() -> Optional[str]:
    """Return Gemini API key from GOOGLE_API_KEY env var or config.toml [gemini] api_key."""
    import os
    env_key = os.environ.get("GOOGLE_API_KEY")
    if env_key:
        return env_key
    cfg = load_config()
    return cfg.get("gemini", {}).get("api_key")


def set_gemini_api_key(key: str) -> None:
    cfg = load_config()
    cfg.setdefault("gemini", {})["api_key"] = key
    save_config(cfg)


def get_freesound_api_key() -> str | None:
    """Return FREESOUND_API_KEY from environment or config file."""
    import os
    key = os.environ.get("FREESOUND_API_KEY")
    if key:
        return key
    cfg = load_config()
    return cfg.get("freesound_api_key") or None


def set_freesound_api_key(key: str) -> None:
    cfg = load_config()
    cfg["freesound_api_key"] = key
    save_config(cfg)


def get_github_pat() -> Optional[str]:
    cfg = load_config()
    return cfg.get("github", {}).get("pat")


def set_github_pat(pat: str) -> None:
    cfg = load_config()
    cfg.setdefault("github", {})["pat"] = pat
    save_config(cfg)


# ── Project registry ─────────────────────────────────────────────────────────

def list_projects() -> list[dict]:
    cfg = load_config()
    return cfg.get("projects", [])


def get_active_project() -> Optional[dict]:
    for p in list_projects():
        if p.get("active"):
            return p
    return None


def register_project(name: str, path: str, remote: str, source_directory: str = "") -> None:
    cfg = load_config()
    projects = cfg.get("projects", [])
    # deactivate all others
    for p in projects:
        p["active"] = False
    # check for existing entry by name
    existing = next((p for p in projects if p["name"] == name), None)
    if existing:
        existing.update({"path": path, "remote": remote, "active": True})
        if source_directory:
            existing["source_directory"] = source_directory
    else:
        entry = {"name": name, "path": path, "remote": remote, "active": True}
        if source_directory:
            entry["source_directory"] = source_directory
        projects.append(entry)
    cfg["projects"] = projects
    save_config(cfg)


def set_active_project(name: str) -> bool:
    cfg = load_config()
    projects = cfg.get("projects", [])
    found = False
    for p in projects:
        p["active"] = p["name"] == name
        if p["name"] == name:
            found = True
    cfg["projects"] = projects
    save_config(cfg)
    return found
