from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from backend.simulation import simulate_tournament


ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT_DIR / "data" / "tournament_cache.json"
CACHE_VERSION = "champion-futures-v1"
_CACHE_LOCK = Lock()


def _cache_shell() -> dict:
    return {
        "version": CACHE_VERSION,
        "items": {},
    }


def _cache_key(runs: int, seed: int) -> str:
    return f"runs={runs}:seed={seed}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return _cache_shell()

    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _cache_shell()

    if payload.get("version") != CACHE_VERSION:
        return _cache_shell()
    if not isinstance(payload.get("items"), dict):
        payload["items"] = {}
    return payload


def _save_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_tournament_result(runs: int = 2000, seed: int = 42, refresh: bool = False) -> dict:
    normalized_runs = max(1, min(int(runs), 100000))
    normalized_seed = int(seed)
    key = _cache_key(normalized_runs, normalized_seed)

    with _CACHE_LOCK:
        payload = _load_cache()
        cached = payload["items"].get(key)
        if cached and not refresh:
            result = copy.deepcopy(cached)
            result["cached"] = True
            return result

        result = simulate_tournament(runs=normalized_runs, seed=normalized_seed)
        result.update(
            {
                "cache_key": key,
                "cached": False,
                "generated_at": _utc_now(),
            }
        )
        payload["items"][key] = copy.deepcopy(result)
        _save_cache(payload)
        return result
