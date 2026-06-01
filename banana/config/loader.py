"""Config loading from disk with env-var interpolation."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from banana.config.schema import Config


def _default_config_path() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "~"
    return Path(home).expanduser() / ".bananacoder" / "config.json"


def load_config(path: Path | None = None) -> Config:
    """Load config from JSON file. Returns defaults if file doesn't exist."""
    target = path or _default_config_path()
    if not target.exists():
        return Config()
    raw = json.loads(target.read_text(encoding="utf-8"))
    return Config.model_validate(raw)


def resolve_env_vars(config: Config) -> Config:
    """Replace $VAR and ${VAR} patterns in provider values with env-var values."""

    def _resolve(val: str) -> str:
        pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)|\$\{([^}]+)\}")
        def _replacer(m: re.Match) -> str:
            var = m.group(1) or m.group(2)
            return os.environ.get(var, "")
        return pattern.sub(_replacer, val)

    providers = {}
    for name, p in config.providers.items():
        providers[name] = p.model_copy(update={
            "api_key": _resolve(p.api_key) if p.api_key else p.api_key,
            "api_base": _resolve(p.api_base) if p.api_base else p.api_base,
        })

    return config.model_copy(update={"providers": providers})
