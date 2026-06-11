from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from collections import defaultdict
from math import exp, factorial
from typing import Dict, Iterable, Optional

from backend.data import TEAM_ALIASES, TEAM_PROFILES

THE_ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
DEFAULT_SPORT_KEYS = [
    "soccer_fifa_world_cup",
]
DEFAULT_OUTRIGHT_SPORT_KEY = "soccer_fifa_world_cup_winner"
DEFAULT_BOOKMAKERS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "betrivers",
    "williamhill_us",
    "bet365",
    "pinnacle",
    "betfair",
    "unibet",
    "bovada",
]
PREFERRED_BOOKMAKER_NAMES = {
    "draftkings",
    "fanduel",
    "betmgm",
    "betrivers",
    "williamhill",
    "williamhillus",
    "caesars",
    "bet365",
    "pinnacle",
    "betfair",
    "unibet",
    "bovada",
}


TEAM_NAME_ALIASES = {
    "korea republic": "south korea",
    "usa": "united states",
    "u.s.": "united states",
    "u.s.a.": "united states",
    "czechia": "czech republic",
    "türkiye": "turkey",
    "ivory coast": "cote d ivoire",
    "côte d'ivoire": "cote d ivoire",
    "congo dr": "dr congo",
    "bosnia and herzegovina": "bosnia",
}


@dataclass(frozen=True)
class OddsAggregate:
    market_odds: dict
    source: str
    bookmaker_count: int
    bookmakers: list[str]
    updated_at: str | None = None
    bookmaker_prices: list[dict] | None = None
    goal_market: dict | None = None


def normalize_name(name: str) -> str:
    normalized = (
        name.lower()
        .replace(".", "")
        .replace("-", " ")
        .replace("'", "")
        .replace("  ", " ")
        .strip()
    )
    return TEAM_NAME_ALIASES.get(normalized, normalized)


def normalize_bookmaker_name(name: str) -> str:
    return (
        name.lower()
        .replace(".", "")
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
        .strip()
    )


def odds_api_configured() -> bool:
    return bool(os.getenv("ODDS_API_KEY"))


def should_use_bookmaker(bookmaker: dict) -> bool:
    if os.getenv("ODDS_API_BOOKMAKERS"):
        return True

    labels = {
        normalize_bookmaker_name(str(bookmaker.get("key", ""))),
        normalize_bookmaker_name(str(bookmaker.get("title", ""))),
    }
    return any(
        preferred in label or label in preferred
        for preferred in PREFERRED_BOOKMAKER_NAMES
        for label in labels
        if label
    )


def team_code_from_market_name(name: str) -> str | None:
    normalized = normalize_name(name)
    if normalized in TEAM_ALIASES:
        return TEAM_ALIASES[normalized]

    for code, profile in TEAM_PROFILES.items():
        if normalize_name(profile.name) == normalized:
            return code
    return None


def decimal_price(price: float) -> float:
    return round(float(price), 2)


def average(values: Iterable[float]) -> Optional[float]:
    rows = [float(value) for value in values if value and float(value) > 1.0]
    if not rows:
        return None
    return sum(rows) / len(rows)


def no_vig_two_way(first_odds: float, second_odds: float) -> tuple[float, float]:
    first = 1 / first_odds
    second = 1 / second_odds
    total = first + second
    return first / total, second / total


def poisson_total_cdf(mean: float, max_goals: int) -> float:
    return sum(exp(-mean) * (mean ** goals) / factorial(goals) for goals in range(max_goals + 1))


def total_goals_mean_from_market(point: float, over_odds: float, under_odds: float) -> float:
    over_prob, _ = no_vig_two_way(over_odds, under_odds)
    threshold = int(point // 1) + 1

    low, high = 0.2, 6.5
    for _ in range(42):
        mid = (low + high) / 2
        modeled_over = 1 - poisson_total_cdf(mid, threshold - 1)
        if modeled_over < over_prob:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def event_matches_fixture(event: dict, fixture: dict) -> bool:
    fixture_names = {
        normalize_name(fixture["team_a_name"]),
        normalize_name(fixture["team_b_name"]),
    }
    event_names = {
        normalize_name(event.get("home_team", "")),
        normalize_name(event.get("away_team", "")),
    }
    return fixture_names == event_names


def extract_h2h_aggregate(event: dict, fixture: dict) -> Optional[OddsAggregate]:
    team_a_name = normalize_name(fixture["team_a_name"])
    team_b_name = normalize_name(fixture["team_b_name"])

    team_a_prices = []
    draw_prices = []
    team_b_prices = []
    used_bookmakers = []
    bookmaker_prices = []
    goal_markets = []
    last_updates = []

    for bookmaker in event.get("bookmakers", []):
        if not should_use_bookmaker(bookmaker):
            continue

        bookmaker_name = bookmaker.get("title") or bookmaker.get("key")
        bookmaker_updated_at = bookmaker.get("last_update")
        for market in bookmaker.get("markets", []):
            market_key = market.get("key")
            if market_key == "h2h":
                prices: Dict[str, float] = {}
                for outcome in market.get("outcomes", []):
                    outcome_name = normalize_name(outcome.get("name", ""))
                    prices[outcome_name] = decimal_price(outcome.get("price"))

                if team_a_name in prices and team_b_name in prices and "draw" in prices:
                    team_a_prices.append(prices[team_a_name])
                    draw_prices.append(prices["draw"])
                    team_b_prices.append(prices[team_b_name])
                    used_bookmakers.append(bookmaker_name)
                    if bookmaker_updated_at:
                        last_updates.append(bookmaker_updated_at)
                    bookmaker_prices.append(
                        {
                            "bookmaker": bookmaker_name,
                            "updated_at": bookmaker_updated_at,
                            "team_a": prices[team_a_name],
                            "draw": prices["draw"],
                            "team_b": prices[team_b_name],
                        }
                    )
            elif market_key == "totals":
                totals_prices: Dict[str, dict] = {}
                for outcome in market.get("outcomes", []):
                    outcome_name = normalize_name(outcome.get("name", ""))
                    totals_prices[outcome_name] = {
                        "price": decimal_price(outcome.get("price")),
                        "point": float(outcome.get("point")),
                    }

                if "over" in totals_prices and "under" in totals_prices:
                    over = totals_prices["over"]
                    under = totals_prices["under"]
                    if over["point"] == under["point"]:
                        goal_markets.append(
                            {
                                "bookmaker": bookmaker_name,
                                "updated_at": bookmaker_updated_at,
                                "line": over["point"],
                                "over": over["price"],
                                "under": under["price"],
                                "total_goals": total_goals_mean_from_market(
                                    over["point"],
                                    over["price"],
                                    under["price"],
                                ),
                            }
                        )

    team_a = average(team_a_prices)
    draw = average(draw_prices)
    team_b = average(team_b_prices)
    if team_a is None or draw is None or team_b is None:
        return None

    return OddsAggregate(
        market_odds={
            "team_a": round(team_a, 2),
            "draw": round(draw, 2),
            "team_b": round(team_b, 2),
        },
        source="The Odds API aggregate",
        bookmaker_count=len(used_bookmakers),
        bookmakers=used_bookmakers,
        updated_at=max(last_updates) if last_updates else None,
        bookmaker_prices=bookmaker_prices,
        goal_market=aggregate_goal_market(goal_markets),
    )


def aggregate_goal_market(goal_markets: list[dict]) -> dict | None:
    if not goal_markets:
        return None

    bookmakers = sorted({row["bookmaker"] for row in goal_markets if row.get("bookmaker")})
    return {
        "source": "The Odds API totals aggregate",
        "bookmaker_count": len(bookmakers),
        "bookmakers": bookmakers,
        "line": round(sum(row["line"] for row in goal_markets) / len(goal_markets), 2),
        "over": round(sum(row["over"] for row in goal_markets) / len(goal_markets), 2),
        "under": round(sum(row["under"] for row in goal_markets) / len(goal_markets), 2),
        "total_goals": round(sum(row["total_goals"] for row in goal_markets) / len(goal_markets), 3),
        "updated_at": max([row["updated_at"] for row in goal_markets if row.get("updated_at")] or [None]),
    }


def fetch_the_odds_api_events(api_key: str, sport_key: str, markets: str = "h2h,totals") -> list[dict]:
    params = {
        "apiKey": api_key,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    bookmakers = os.getenv("ODDS_API_BOOKMAKERS")
    if bookmakers:
        params["bookmakers"] = bookmakers
    else:
        params["regions"] = os.getenv("ODDS_API_REGIONS", "us,uk,eu")

    url = THE_ODDS_API_URL.format(sport=urllib.parse.quote(sport_key))
    url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_market_odds(fixtures: list[dict]) -> Dict[str, OddsAggregate]:
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        return {}

    sport_keys = [
        key.strip()
        for key in os.getenv("ODDS_API_SPORT_KEYS", ",".join(DEFAULT_SPORT_KEYS)).split(",")
        if key.strip()
    ]

    aggregates: Dict[str, OddsAggregate] = {}
    for sport_key in sport_keys:
        try:
            events = fetch_the_odds_api_events(api_key, sport_key)
        except Exception:
            continue

        for fixture in fixtures:
            if fixture["id"] in aggregates:
                continue
            for event in events:
                if event_matches_fixture(event, fixture):
                    aggregate = extract_h2h_aggregate(event, fixture)
                    if aggregate is not None:
                        aggregates[fixture["id"]] = aggregate
                        break

    return aggregates


def fetch_champion_futures() -> list[dict]:
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        return []

    sport_key = os.getenv("ODDS_API_OUTRIGHT_SPORT_KEY", DEFAULT_OUTRIGHT_SPORT_KEY)
    events = fetch_the_odds_api_events(api_key, sport_key, markets="outrights")

    prices_by_team: dict[str, list[float]] = defaultdict(list)
    bookmakers_by_team: dict[str, list[str]] = defaultdict(list)
    updates_by_team: dict[str, list[str]] = defaultdict(list)

    for event in events:
        for bookmaker in event.get("bookmakers", []):
            if not should_use_bookmaker(bookmaker):
                continue

            bookmaker_name = bookmaker.get("title") or bookmaker.get("key")
            bookmaker_updated_at = bookmaker.get("last_update")
            for market in bookmaker.get("markets", []):
                if market.get("key") != "outrights":
                    continue

                for outcome in market.get("outcomes", []):
                    code = team_code_from_market_name(outcome.get("name", ""))
                    if not code:
                        continue

                    price = decimal_price(outcome.get("price"))
                    if price <= 1:
                        continue

                    prices_by_team[code].append(price)
                    bookmakers_by_team[code].append(bookmaker_name)
                    if bookmaker_updated_at:
                        updates_by_team[code].append(bookmaker_updated_at)

    average_odds = {
        code: average(prices)
        for code, prices in prices_by_team.items()
    }
    raw_probability_total = sum(
        1 / odds
        for odds in average_odds.values()
        if odds
    )

    rows = []
    for code, odds in average_odds.items():
        if odds is None:
            continue

        unique_bookmakers = sorted(set(bookmakers_by_team[code]))
        rows.append(
            {
                "team": TEAM_PROFILES[code].name,
                "code": code,
                "odds": round(odds, 2),
                "implied_probability": round((1 / odds) / raw_probability_total, 4)
                if raw_probability_total
                else 0,
                "bookmaker_count": len(unique_bookmakers),
                "bookmakers": unique_bookmakers,
                "updated_at": max(updates_by_team[code]) if updates_by_team[code] else None,
                "source": "The Odds API outrights aggregate",
            }
        )

    return sorted(rows, key=lambda row: row["odds"])
