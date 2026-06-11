from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any, Dict

from backend.data import TEAM_PROFILES
from backend.prediction import predict_match


ROOT_DIR = Path(__file__).resolve().parent.parent
SIGNAL_PATH = ROOT_DIR / "data" / "live_signals.json"


BOOKMAKER_SNAPSHOTS = {
    "GA-M1-001": {
        "source": "FOX Sports odds snapshot",
        "market_weight": 0.62,
        "market_odds": {
            "team_a": 1.38,
            "draw": 4.50,
            "team_b": 9.00,
        },
        "american_odds": {
            "team_a": -260,
            "draw": 350,
            "team_b": 800,
        },
        "news": {
            "team_a_absences": 0,
            "team_b_absences": 0,
            "team_a_rest_days": 5,
            "team_b_rest_days": 5,
            "team_a_motivation": 0.72,
            "team_b_motivation": 0.62,
            "headlines": [
                "Mexico open the tournament at home in Mexico City.",
                "Market has Mexico as a heavy favourite; draw and South Africa prices are long.",
                "Weather risk: afternoon thunderstorm chance around Mexico City.",
            ],
        },
    }
}


def load_signal_cache() -> Dict[str, Any]:
    if not SIGNAL_PATH.exists():
        return {
            "updated_at": None,
            "source": "fallback",
            "fixtures": {},
        }
    with open(SIGNAL_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def save_signal_cache(cache: Dict[str, Any]) -> None:
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_PATH, "w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)


def odds_from_model(team_a: str, team_b: str) -> dict:
    prediction = predict_match(team_a, team_b)
    probs = prediction["model_probabilities"]
    margin = 1.065
    return {
        "team_a": round(1 / max(0.03, probs["team_a_win"] * margin), 2),
        "draw": round(1 / max(0.03, probs["draw"] * margin), 2),
        "team_b": round(1 / max(0.03, probs["team_b_win"] * margin), 2),
    }


def moved_odds(
    fixture_id: str,
    base_odds: dict,
    now: str,
    volatility: float,
) -> dict:
    rng = Random(f"{fixture_id}:{now}")
    moved = {}
    for key, value in base_odds.items():
        drift = rng.uniform(-volatility, volatility)
        moved[key] = round(max(1.05, value * (1 + drift)), 2)
    return moved


def odds_movement(previous: dict | None, current: dict) -> dict:
    if not previous:
        return {key: 0.0 for key in current}
    return {
        key: round(current[key] - float(previous.get(key, current[key])), 2)
        for key in current
    }


def fallback_news(team_a: str, team_b: str) -> dict:
    profile_a = TEAM_PROFILES[team_a]
    profile_b = TEAM_PROFILES[team_b]
    a_absences = 1 if profile_a.form < 0.55 else 0
    b_absences = 1 if profile_b.form < 0.55 else 0
    return {
        "team_a_absences": a_absences,
        "team_b_absences": b_absences,
        "team_a_rest_days": 5 if profile_a.form >= profile_b.form else 4,
        "team_b_rest_days": 5 if profile_b.form > profile_a.form else 4,
        "team_a_motivation": round(0.48 + profile_a.form * 0.18, 2),
        "team_b_motivation": round(0.48 + profile_b.form * 0.18, 2),
        "headlines": [
            f"{profile_a.name} recent form index: {profile_a.form:.2f}.",
            f"{profile_b.name} recent form index: {profile_b.form:.2f}.",
            "No verified live injury feed connected yet; using local signal cache.",
        ],
    }


def get_fixture_signal(fixture_id: str, team_a: str, team_b: str) -> dict:
    cache = load_signal_cache()
    fixture_signal = cache.get("fixtures", {}).get(fixture_id, {})
    return {
        "updated_at": fixture_signal.get("updated_at") or cache.get("updated_at"),
        "source": fixture_signal.get("source") or cache.get("source") or "fallback",
        "market_weight": fixture_signal.get("market_weight", 0.28),
        "market_type": fixture_signal.get("market_type", "model_placeholder"),
        "american_odds": fixture_signal.get("american_odds"),
        "bookmaker_count": fixture_signal.get("bookmaker_count", 0),
        "bookmakers": fixture_signal.get("bookmakers", []),
        "market_odds": fixture_signal.get("market_odds") or odds_from_model(team_a, team_b),
        "previous_market_odds": fixture_signal.get("previous_market_odds"),
        "odds_movement": fixture_signal.get("odds_movement", {}),
        "goal_market": fixture_signal.get("goal_market"),
        "news": fixture_signal.get("news") or fallback_news(team_a, team_b),
    }


def build_fallback_signal_cache(
    fixtures: list[dict],
    previous_cache: Dict[str, Any] | None = None,
    provider_odds: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    previous_fixtures = (previous_cache or {}).get("fixtures", {})

    cache = {
        "updated_at": now,
        "source": "local_fallback_provider",
        "fixtures": {},
    }

    for fixture in fixtures:
        fixture_id = fixture["id"]
        base_odds = odds_from_model(fixture["team_a"], fixture["team_b"])
        current_odds = base_odds
        previous_odds = previous_fixtures.get(fixture_id, {}).get("market_odds")
        cache["fixtures"][fixture_id] = {
            "updated_at": now,
            "source": "local_fallback_provider",
            "market_weight": 0.28,
            "market_type": "model_placeholder",
            "market_odds": current_odds,
            "previous_market_odds": previous_odds,
            "odds_movement": odds_movement(previous_odds, current_odds),
            "news": fallback_news(fixture["team_a"], fixture["team_b"]),
        }

    for fixture_id, snapshot in BOOKMAKER_SNAPSHOTS.items():
        if fixture_id in cache["fixtures"]:
            current_odds = snapshot["market_odds"]
            previous_odds = previous_fixtures.get(fixture_id, {}).get("market_odds")
            cache["fixtures"][fixture_id].update(
                {
                    "updated_at": now,
                    "source": snapshot["source"],
                    "market_weight": snapshot["market_weight"],
                    "market_type": "bookmaker_snapshot",
                    "market_odds": current_odds,
                    "previous_market_odds": previous_odds,
                    "odds_movement": odds_movement(previous_odds, current_odds),
                    "american_odds": snapshot["american_odds"],
                    "news": snapshot["news"],
                }
            )

    for fixture_id, aggregate in (provider_odds or {}).items():
        if fixture_id not in cache["fixtures"]:
            continue
        previous_odds = previous_fixtures.get(fixture_id, {}).get("market_odds")
        cache["fixtures"][fixture_id].update(
            {
                "updated_at": now,
                "source": aggregate.source,
                "market_weight": 0.70,
                "market_type": "bookmaker_aggregate",
                "market_odds": aggregate.market_odds,
                "previous_market_odds": previous_odds,
                "odds_movement": odds_movement(previous_odds, aggregate.market_odds),
                "bookmaker_count": aggregate.bookmaker_count,
                "bookmakers": aggregate.bookmakers,
                "bookmaker_prices": aggregate.bookmaker_prices or [],
                "goal_market": aggregate.goal_market,
                "last_bookmaker_update": aggregate.updated_at,
            }
        )

    return cache
