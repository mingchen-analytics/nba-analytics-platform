"""Read config/rules.yaml (all tunable thresholds and definitions live there, not in code).

`load_rules()` returns the shared values; `load_rules(profile="pbpstats_compat")` or
`load_rules(profile="custom")` returns them with that profile merged on top
("copy first, then deviate", CLAUDE.md). The result records the profile it used.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from nba_platform.db import PROJECT_ROOT

RULES_YAML = PROJECT_ROOT / "config" / "rules.yaml"
PROFILES = ("pbpstats_compat", "custom")


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def load_rules(path: Path = RULES_YAML, profile: str | None = None) -> dict:
    with open(path, encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    if not rules or "rules_version" not in rules:
        raise ValueError(f"{path}: missing rules_version")
    profiles = rules.pop("profiles", {}) or {}
    if profile is None:
        return rules
    if profile not in profiles:
        raise ValueError(f"unknown rules profile {profile!r}; available: {sorted(profiles)}")
    merged = _merge(rules, profiles[profile])
    merged["profile"] = profile
    return merged
