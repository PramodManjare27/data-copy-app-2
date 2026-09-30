"""
Loaders/writers for the two families of external config that drive what shows
up on the copy wizard:

  * pg_tables*.json   -> list of PG2PG table-copy definitions
  * adls_*.conf       -> list of ADLS2ADLS location-copy definitions (JSON body)

Both are plain JSON on disk (the .conf extension is kept because that's the
filename convention requested; contents are JSON so they're trivially editable
from the admin screen and easy to validate).
"""
import json
from pathlib import Path
from typing import Any, Dict, List


def _read_json_file(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = [data]
    return data


def _write_json_file(path: str, data: List[Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def read_raw_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return "[]"
    return p.read_text(encoding="utf-8")


def write_raw_text(path: str, text: str) -> None:
    """Validates JSON before writing so the admin editor can't brick a config."""
    json.loads(text)  # raises ValueError if invalid
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# PG2PG
# ---------------------------------------------------------------------------

def load_pg_tables(json_path: str) -> List[Dict[str, Any]]:
    return _read_json_file(json_path)


def pg_tables_for_target(json_path: str, target_env: str) -> List[Dict[str, Any]]:
    """Filter PG table entries to those whose target_env matches the env the
    user picked on the wizard (relevant for preprod_dev, which has 5 variants
    of the same copy_id, one per DEV target)."""
    entries = load_pg_tables(json_path)
    return [e for e in entries if e.get("target_env") == target_env]


def distinct_target_envs(json_path: str) -> List[str]:
    entries = load_pg_tables(json_path)
    seen = []
    for e in entries:
        te = e.get("target_env")
        if te and te not in seen:
            seen.append(te)
    return seen


def save_pg_tables(json_path: str, entries: List[Dict[str, Any]]) -> None:
    _write_json_file(json_path, entries)


# ---------------------------------------------------------------------------
# ADLS2ADLS
# ---------------------------------------------------------------------------

def load_adls_conf(conf_path: str) -> List[Dict[str, Any]]:
    return _read_json_file(conf_path)


def adls_entries_for_target(conf_path: str, target_env: str) -> List[Dict[str, Any]]:
    entries = load_adls_conf(conf_path)
    return [e for e in entries if e.get("target-env") == target_env]


def save_adls_conf(conf_path: str, entries: List[Dict[str, Any]]) -> None:
    _write_json_file(conf_path, entries)
