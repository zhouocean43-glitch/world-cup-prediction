from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import exp, factorial
from pathlib import Path
from typing import Dict, Iterable, Optional

from backend.data import TEAM_ALIASES, TEAM_PROFILES

THE_ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
API_FOOTBALL_URL = "https://v3.football.api-sports.io/{endpoint}"
DEFAULT_SPORT_KEYS = [
    "soccer_fifa_world_cup",
]
DEFAULT_OUTRIGHT_SPORT_KEY = "soccer_fifa_world_cup_winner"
DEFAULT_API_FOOTBALL_LEAGUE = "1"
DEFAULT_API_FOOTBALL_SEASON = "2026"
DEFAULT_THE_ODDS_API_CACHE_SECONDS = 86400
DEFAULT_API_FOOTBALL_CACHE_SECONDS = 1800
DEFAULT_API_FOOTBALL_MAX_PAGES = 3
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
THE_ODDS_MARKET_CACHE_PATH = DATA_DIR / "the_odds_market_cache.json"
API_FOOTBALL_MARKET_CACHE_PATH = DATA_DIR / "api_football_market_cache.json"
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
    "côte divoire": "cote d ivoire",
    "cote divoire": "cote d ivoire",
    "congo dr": "dr congo",
    "bosnia herzegovina": "bosnia and herzegovina",
    "bosnia and herzegovina": "bosnia",
}

_API_FOOTBALL_CACHE: dict = {
    "expires_at": None,
    "odds": {},
}
_THE_ODDS_API_CACHE: dict = {
    "expires_at": None,
    "odds": {},
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


def api_football_configured() -> bool:
    return bool(os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY"))


def market_odds_configured() -> bool:
    return odds_api_configured() or api_football_configured()


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


def should_use_api_football_bookmaker(bookmaker_name: str) -> bool:
    configured = os.getenv("API_FOOTBALL_BOOKMAKERS")
    if configured:
        allowed = {
            normalize_bookmaker_name(name)
            for name in configured.split(",")
            if name.strip()
        }
        return normalize_bookmaker_name(bookmaker_name) in allowed

    label = normalize_bookmaker_name(bookmaker_name)
    return any(preferred in label or label in preferred for preferred in PREFERRED_BOOKMAKER_NAMES)


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


def api_football_key() -> str | None:
    return os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY")


def api_football_cache_seconds() -> int:
    try:
        return max(300, int(os.getenv("API_FOOTBALL_CACHE_SECONDS", DEFAULT_API_FOOTBALL_CACHE_SECONDS)))
    except ValueError:
        return DEFAULT_API_FOOTBALL_CACHE_SECONDS


def the_odds_api_cache_seconds() -> int:
    try:
        return max(3600, int(os.getenv("THE_ODDS_API_CACHE_SECONDS", DEFAULT_THE_ODDS_API_CACHE_SECONDS)))
    except ValueError:
        return DEFAULT_THE_ODDS_API_CACHE_SECONDS


def api_football_max_pages() -> int:
    try:
        return max(1, int(os.getenv("API_FOOTBALL_ODDS_MAX_PAGES", DEFAULT_API_FOOTBALL_MAX_PAGES)))
    except ValueError:
        return DEFAULT_API_FOOTBALL_MAX_PAGES


def aggregate_to_dict(aggregate: OddsAggregate) -> dict:
    return asdict(aggregate)


def aggregate_from_dict(row: dict) -> OddsAggregate:
    return OddsAggregate(
        market_odds=row["market_odds"],
        source=row["source"],
        bookmaker_count=int(row.get("bookmaker_count", 0)),
        bookmakers=list(row.get("bookmakers", [])),
        updated_at=row.get("updated_at"),
        bookmaker_prices=row.get("bookmaker_prices"),
        goal_market=row.get("goal_market"),
    )


def parse_cache_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_market_cache(path: Path, memory_cache: dict, fixtures: list[dict]) -> dict[str, OddsAggregate] | None:
    now = datetime.now(timezone.utc)
    fixture_ids = tuple(fixture["id"] for fixture in fixtures)

    expires_at = memory_cache.get("expires_at")
    if expires_at and expires_at > now and tuple(memory_cache.get("fixture_ids", ())) == fixture_ids:
        cached = memory_cache.get("odds", {})
        return {fixture["id"]: cached[fixture["id"]] for fixture in fixtures if fixture["id"] in cached}

    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        disk_expires_at = parse_cache_time(payload.get("expires_at"))
        if not disk_expires_at or disk_expires_at <= now:
            return None
        if tuple(payload.get("fixture_ids", ())) != fixture_ids:
            return None
        odds = {
            fixture_id: aggregate_from_dict(row)
            for fixture_id, row in (payload.get("odds") or {}).items()
        }
    except Exception:
        return None

    memory_cache.update({"expires_at": disk_expires_at, "fixture_ids": fixture_ids, "odds": odds})
    return {fixture["id"]: odds[fixture["id"]] for fixture in fixtures if fixture["id"] in odds}


def save_market_cache(
    path: Path,
    memory_cache: dict,
    fixtures: list[dict],
    odds: dict[str, OddsAggregate],
    ttl_seconds: int,
) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    fixture_ids = tuple(fixture["id"] for fixture in fixtures)
    memory_cache.update({"expires_at": expires_at, "fixture_ids": fixture_ids, "odds": odds})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                    "fixture_ids": list(fixture_ids),
                    "odds": {fixture_id: aggregate_to_dict(aggregate) for fixture_id, aggregate in odds.items()},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        return


def api_football_request(endpoint: str, params: dict) -> dict:
    key = api_football_key()
    if not key:
        return {"response": []}

    url = API_FOOTBALL_URL.format(endpoint=urllib.parse.quote(endpoint))
    url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": key,
            "User-Agent": "world-cup-prediction/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_api_football_fixtures() -> dict[int, dict]:
    payload = api_football_request(
        "fixtures",
        {
            "league": os.getenv("API_FOOTBALL_LEAGUE", DEFAULT_API_FOOTBALL_LEAGUE),
            "season": os.getenv("API_FOOTBALL_SEASON", DEFAULT_API_FOOTBALL_SEASON),
        },
    )
    fixtures = {}
    for row in payload.get("response", []):
        fixture_id = (row.get("fixture") or {}).get("id")
        teams = row.get("teams") or {}
        home_code = team_code_from_market_name(((teams.get("home") or {}).get("name")) or "")
        away_code = team_code_from_market_name(((teams.get("away") or {}).get("name")) or "")
        if fixture_id and home_code and away_code:
            fixtures[int(fixture_id)] = {
                "home": home_code,
                "away": away_code,
                "date": (row.get("fixture") or {}).get("date"),
            }
    return fixtures


def fetch_api_football_odds_rows() -> list[dict]:
    rows = []
    max_pages = api_football_max_pages()
    base_params = {
        "league": os.getenv("API_FOOTBALL_LEAGUE", DEFAULT_API_FOOTBALL_LEAGUE),
        "season": os.getenv("API_FOOTBALL_SEASON", DEFAULT_API_FOOTBALL_SEASON),
    }

    for page in range(1, max_pages + 1):
        payload = api_football_request("odds", {**base_params, "page": page})
        rows.extend(payload.get("response", []))
        total_pages = int((payload.get("paging") or {}).get("total") or page)
        if page >= total_pages:
            break
    return rows


def api_football_fixture_matches(reference: dict, fixture: dict) -> bool:
    return {reference.get("home"), reference.get("away")} == {fixture["team_a"], fixture["team_b"]}


def api_football_price_map(values: list[dict], reference: dict, fixture: dict) -> dict:
    prices: dict[str, float] = {}
    for value in values:
        label = normalize_name(str(value.get("value", "")))
        odd = decimal_price(value.get("odd"))
        if label in {"home", "1"}:
            prices[reference["home"]] = odd
        elif label in {"away", "2"}:
            prices[reference["away"]] = odd
        elif label in {"draw", "x"}:
            prices["draw"] = odd
        else:
            code = team_code_from_market_name(label)
            if code in {fixture["team_a"], fixture["team_b"]}:
                prices[code] = odd
    return prices


def api_football_total_markets(values: list[dict], bookmaker_name: str, updated_at: str | None) -> list[dict]:
    grouped: dict[float, dict[str, float]] = {}
    for value in values:
        label = normalize_name(str(value.get("value", "")))
        parts = label.split()
        if len(parts) < 2 or parts[0] not in {"over", "under"}:
            continue
        try:
            point = float(parts[1])
        except ValueError:
            continue
        grouped.setdefault(point, {})[parts[0]] = decimal_price(value.get("odd"))

    markets = []
    for point, prices in grouped.items():
        if "over" not in prices or "under" not in prices:
            continue
        markets.append(
            {
                "bookmaker": bookmaker_name,
                "updated_at": updated_at,
                "line": point,
                "over": prices["over"],
                "under": prices["under"],
                "total_goals": total_goals_mean_from_market(point, prices["over"], prices["under"]),
            }
        )
    return markets


def extract_api_football_aggregate(row: dict, fixture: dict, reference: dict) -> Optional[OddsAggregate]:
    team_a_prices = []
    draw_prices = []
    team_b_prices = []
    used_bookmakers = []
    bookmaker_prices = []
    goal_markets = []
    updated_at = row.get("update")

    for bookmaker in row.get("bookmakers", []):
        bookmaker_name = bookmaker.get("name") or str(bookmaker.get("id") or "API-Football")
        if not should_use_api_football_bookmaker(bookmaker_name):
            continue

        for bet in bookmaker.get("bets", []):
            bet_name = normalize_name(bet.get("name", ""))
            values = bet.get("values", [])
            if bet_name in {"match winner", "fulltime result", "winner"}:
                prices = api_football_price_map(values, reference, fixture)
                if fixture["team_a"] in prices and fixture["team_b"] in prices and "draw" in prices:
                    team_a_prices.append(prices[fixture["team_a"]])
                    draw_prices.append(prices["draw"])
                    team_b_prices.append(prices[fixture["team_b"]])
                    used_bookmakers.append(bookmaker_name)
                    bookmaker_prices.append(
                        {
                            "bookmaker": bookmaker_name,
                            "updated_at": updated_at,
                            "team_a": prices[fixture["team_a"]],
                            "draw": prices["draw"],
                            "team_b": prices[fixture["team_b"]],
                        }
                    )
            elif bet_name in {"goals over under", "over under", "total goals"}:
                goal_markets.extend(api_football_total_markets(values, bookmaker_name, updated_at))

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
        source="API-Football aggregate",
        bookmaker_count=len(used_bookmakers),
        bookmakers=used_bookmakers,
        updated_at=updated_at,
        bookmaker_prices=bookmaker_prices,
        goal_market=aggregate_goal_market(goal_markets),
    )


def fetch_api_football_market_odds(fixtures: list[dict], refresh: bool = False) -> Dict[str, OddsAggregate]:
    if not api_football_configured() or not fixtures:
        return {}

    if not refresh:
        cached = load_market_cache(API_FOOTBALL_MARKET_CACHE_PATH, _API_FOOTBALL_CACHE, fixtures)
        if cached is not None:
            return cached

    try:
        fixture_references = fetch_api_football_fixtures()
        odds_rows = fetch_api_football_odds_rows()
    except Exception:
        return {}

    aggregates: Dict[str, OddsAggregate] = {}
    for fixture in fixtures:
        for row in odds_rows:
            fixture_id = ((row.get("fixture") or {}).get("id"))
            reference = fixture_references.get(int(fixture_id)) if fixture_id else None
            if not reference or not api_football_fixture_matches(reference, fixture):
                continue
            aggregate = extract_api_football_aggregate(row, fixture, reference)
            if aggregate is not None:
                aggregates[fixture["id"]] = aggregate
                break

    save_market_cache(API_FOOTBALL_MARKET_CACHE_PATH, _API_FOOTBALL_CACHE, fixtures, aggregates, api_football_cache_seconds())
    return aggregates


def fetch_the_odds_market_odds(fixtures: list[dict], refresh: bool = False) -> Dict[str, OddsAggregate]:
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key or not fixtures:
        return {}

    if not refresh:
        cached = load_market_cache(THE_ODDS_MARKET_CACHE_PATH, _THE_ODDS_API_CACHE, fixtures)
        if cached is not None:
            return cached

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

    save_market_cache(THE_ODDS_MARKET_CACHE_PATH, _THE_ODDS_API_CACHE, fixtures, aggregates, the_odds_api_cache_seconds())
    return aggregates


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


def fetch_market_odds(
    fixtures: list[dict],
    refresh_the_odds: bool = False,
    refresh_api_football: bool = False,
) -> Dict[str, OddsAggregate]:
    aggregates: Dict[str, OddsAggregate] = {}

    # API-Football has a larger daily request budget here, so let it be the
    # higher-frequency source. The Odds API fills gaps but is protected by a
    # much longer cache because the monthly credits are already limited.
    for fixture_id, aggregate in fetch_api_football_market_odds(fixtures, refresh=refresh_api_football).items():
        aggregates[fixture_id] = aggregate

    missing_fixtures = [fixture for fixture in fixtures if fixture["id"] not in aggregates]
    for fixture_id, aggregate in fetch_the_odds_market_odds(missing_fixtures, refresh=refresh_the_odds).items():
        aggregates.setdefault(fixture_id, aggregate)

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
