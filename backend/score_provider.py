from __future__ import annotations

import copy
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.data import TEAM_ALIASES, TEAM_PROFILES


CHINA_TZ = timezone(timedelta(hours=8))
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
DEFAULT_SCOREBOARD_DATES = "20260601-20260720"
DEFAULT_SCOREBOARD_LIMIT = "950"
DEFAULT_CACHE_SECONDS = 300

EXTRA_TEAM_ALIASES = {
    "bosnia herzegovina": "BIH",
    "cote divoire": "CIV",
    "côte divoire": "CIV",
    "congo democratic republic": "COD",
    "democratic republic of congo": "COD",
    "curacao": "CUR",
    "curaçao": "CUR",
    "haiti": "HTI",
}

ESPN_ABBREVIATION_ALIASES = {
    "CUW": "CUR",
    "CGO": "COD",
    "HAI": "HTI",
}

_CACHE: dict[str, Any] = {
    "expires_at": None,
    "updates": {},
    "status": {},
}


def normalize_team_name(name: str) -> str:
    normalized = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def team_code_from_name(name: str | None) -> str | None:
    if not name:
        return None

    code = name.strip().upper()
    if code in TEAM_PROFILES:
        return code
    if code in ESPN_ABBREVIATION_ALIASES:
        return ESPN_ABBREVIATION_ALIASES[code]

    aliases = {normalize_team_name(key): value for key, value in TEAM_ALIASES.items()}
    aliases.update(EXTRA_TEAM_ALIASES)
    normalized = normalize_team_name(name)
    if normalized in aliases:
        return aliases[normalized]

    for team_code, profile in TEAM_PROFILES.items():
        if normalize_team_name(profile.name) == normalized:
            return team_code
    return None


def team_code_from_competitor(competitor: dict) -> str | None:
    team = competitor.get("team") or {}
    for candidate in (
        team.get("displayName"),
        team.get("shortDisplayName"),
        team.get("name"),
        team.get("abbreviation"),
    ):
        code = team_code_from_name(candidate)
        if code:
            return code
    return None


def to_china_iso(espn_date: str | None) -> str | None:
    if not espn_date:
        return None
    parsed = datetime.fromisoformat(espn_date.replace("Z", "+00:00"))
    return parsed.astimezone(CHINA_TZ).isoformat()


def int_score(value: str | int | None) -> int:
    if value in {None, ""}:
        return 0
    return int(value)


def result_summary(fixture: dict, team_a_goals: int, team_b_goals: int) -> str:
    team_a = fixture["team_a_name"]
    team_b = fixture["team_b_name"]
    score = f"{team_a_goals}-{team_b_goals}"
    if team_a_goals > team_b_goals:
        return f"{team_a} beat {team_b} {score}."
    if team_a_goals < team_b_goals:
        return f"{team_b} beat {team_a} {team_b_goals}-{team_a_goals}."
    return f"{team_a} drew {team_b} {score}."


def extract_event_update(event: dict, fixture: dict, fetched_at: str) -> dict | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None

    competition = competitions[0]
    competitors = competition.get("competitors") or []
    scores_by_code: dict[str, int] = {}
    for competitor in competitors:
        code = team_code_from_competitor(competitor)
        if code:
            scores_by_code[code] = int_score(competitor.get("score"))

    fixture_codes = {fixture["team_a"], fixture["team_b"]}
    if set(scores_by_code) != fixture_codes:
        return None

    update: dict[str, Any] = {
        "scoreboard": {
            "source": "ESPN FIFA World Cup scoreboard",
            "event_id": event.get("id"),
            "event_name": event.get("name"),
            "status": ((competition.get("status") or {}).get("type") or {}).get("name"),
            "detail": ((competition.get("status") or {}).get("type") or {}).get("detail"),
            "updated_at": fetched_at,
        }
    }

    kickoff = to_china_iso(event.get("date"))
    if kickoff:
        update["kickoff"] = kickoff

    venue = competition.get("venue") or {}
    address = venue.get("address") or {}
    if venue.get("fullName"):
        update["stadium"] = venue["fullName"]
    if address.get("city"):
        update["city"] = address["city"]
    if address.get("country"):
        update["country"] = address["country"]
    if venue or kickoff:
        update["data_quality"] = "espn_scoreboard_fixture_meta"

    status_type = ((competition.get("status") or {}).get("type") or {})
    if status_type.get("completed"):
        team_a_goals = scores_by_code[fixture["team_a"]]
        team_b_goals = scores_by_code[fixture["team_b"]]
        if team_a_goals > team_b_goals:
            winner = "team_a"
        elif team_a_goals < team_b_goals:
            winner = "team_b"
        else:
            winner = "draw"
        update["result"] = {
            "status": "final",
            "team_a_goals": team_a_goals,
            "team_b_goals": team_b_goals,
            "winner": winner,
            "source": "ESPN FIFA World Cup scoreboard",
            "updated_at": fetched_at,
            "event_id": event.get("id"),
            "summary": result_summary(fixture, team_a_goals, team_b_goals),
        }

    return update


def build_scoreboard_updates(events: list[dict], fixtures: list[dict], fetched_at: str) -> dict[str, dict]:
    updates: dict[str, dict] = {}
    for fixture in fixtures:
        for event in events:
            update = extract_event_update(event, fixture, fetched_at)
            if update is not None:
                updates[fixture["id"]] = update
                break
    return updates


def fetch_espn_scoreboard_events() -> list[dict]:
    params = {
        "limit": os.getenv("ESPN_SCOREBOARD_LIMIT", DEFAULT_SCOREBOARD_LIMIT),
        "dates": os.getenv("ESPN_SCOREBOARD_DATES", DEFAULT_SCOREBOARD_DATES),
    }
    url = f"{ESPN_SCOREBOARD_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("events", [])


def fetch_scoreboard_updates(fixtures: list[dict], refresh: bool = False) -> tuple[dict[str, dict], dict]:
    now = datetime.now(timezone.utc)
    expires_at = _CACHE.get("expires_at")
    if not refresh and expires_at and expires_at > now:
        return copy.deepcopy(_CACHE["updates"]), copy.deepcopy(_CACHE["status"])

    fetched_at = now.isoformat().replace("+00:00", "Z")
    try:
        events = fetch_espn_scoreboard_events()
        updates = build_scoreboard_updates(events, fixtures, fetched_at)
        status = {
            "configured": True,
            "connected": True,
            "source": "ESPN FIFA World Cup scoreboard",
            "matched": len(updates),
            "event_count": len(events),
            "final_count": sum(1 for update in updates.values() if update.get("result")),
            "updated_at": fetched_at,
            "cache_seconds": int(os.getenv("ESPN_SCOREBOARD_CACHE_SECONDS", DEFAULT_CACHE_SECONDS)),
            "message": "赛程、球场与完赛比分会从 ESPN scoreboard 自动同步。",
        }
    except Exception as exc:
        updates = {}
        status = {
            "configured": True,
            "connected": False,
            "source": "ESPN FIFA World Cup scoreboard",
            "matched": 0,
            "event_count": 0,
            "final_count": 0,
            "updated_at": fetched_at,
            "message": f"比分源暂时不可用：{exc}",
        }

    ttl = status.get("cache_seconds", DEFAULT_CACHE_SECONDS)
    _CACHE.update(
        {
            "expires_at": now + timedelta(seconds=ttl),
            "updates": copy.deepcopy(updates),
            "status": copy.deepcopy(status),
        }
    )
    return updates, status
