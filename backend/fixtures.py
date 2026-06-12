from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple

from backend.data import DEFAULT_GROUPS, TEAM_PROFILES


CHINA_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Fixture:
    id: str
    group: str
    matchday: int
    kickoff: str
    team_a: str
    team_b: str
    stadium: str
    city: str
    country: str
    weather: dict
    data_quality: str
    result: dict | None = None

    def to_dict(self) -> dict:
        row = asdict(self)
        row["team_a_name"] = TEAM_PROFILES[self.team_a].name
        row["team_b_name"] = TEAM_PROFILES[self.team_b].name
        row["team_a_flag"] = TEAM_PROFILES[self.team_a].to_dict()["flag"]
        row["team_b_flag"] = TEAM_PROFILES[self.team_b].to_dict()["flag"]
        return row


KNOWN_FIXTURE_META = {
    1: {
        "stadium": "Mexico City Stadium",
        "city": "Mexico City",
        "country": "Mexico",
        "kickoff": datetime(2026, 6, 12, 3, 0, tzinfo=CHINA_TZ),
        "weather": {
            "summary": "下午有雷阵雨风险",
            "temperature_c": 24,
            "precipitation_risk": "medium",
            "source": "weather snapshot",
        },
        "data_quality": "official_fixture_live_weather",
    },
    2: {
        "stadium": "Guadalajara Stadium",
        "city": "Guadalajara",
        "country": "Mexico",
        "kickoff": datetime(2026, 6, 12, 10, 0, tzinfo=CHINA_TZ),
        "weather": {
            "summary": "多云间晴，夜间湿度偏高",
            "temperature_c": 22,
            "precipitation_risk": "low",
            "source": "weather snapshot",
        },
        "data_quality": "official_fixture_live_weather",
    },
}


KNOWN_RESULTS = {
    1: {
        "status": "final",
        "team_a_goals": 2,
        "team_b_goals": 0,
        "winner": "team_a",
        "source": "ESPN / FOX Sports final score",
        "updated_at": "2026-06-12T05:30:00+08:00",
        "summary": "Mexico beat South Africa 2-0 in the 2026 World Cup opener.",
    },
}


DEFAULT_FIXTURE_META = {
    "stadium": "Official venue pending import",
    "city": "Host city pending import",
    "country": "USA / Canada / Mexico",
    "weather": {
        "summary": "临近比赛刷新天气",
        "temperature_c": None,
        "precipitation_risk": "pending",
        "source": "pending",
    },
    "data_quality": "teams_official_fixture_meta_pending",
}


def group_pairings(teams: Iterable[str]) -> List[Tuple[str, str]]:
    team_list = list(teams)
    if len(team_list) != 4:
        raise ValueError("Group fixtures require exactly four teams.")
    return [
        (team_list[0], team_list[1]),
        (team_list[2], team_list[3]),
        (team_list[1], team_list[3]),
        (team_list[0], team_list[2]),
        (team_list[0], team_list[3]),
        (team_list[1], team_list[2]),
    ]


def fixture_slots(start: datetime, count: int) -> List[datetime]:
    daily_hours = [0, 3, 6, 9]
    slots: List[datetime] = []
    current_day = start.date()

    while len(slots) < count:
        for hour in daily_hours:
            slot = datetime(
                current_day.year,
                current_day.month,
                current_day.day,
                hour,
                0,
                tzinfo=CHINA_TZ,
            )
            if slot >= start:
                slots.append(slot)
                if len(slots) == count:
                    break
        current_day = current_day + timedelta(days=1)

    return slots


def build_group_stage_fixtures(groups: Dict[str, List[str]] | None = None) -> List[Fixture]:
    if groups is None:
        groups = DEFAULT_GROUPS

    all_matches: List[Tuple[str, int, str, str]] = []
    for matchday in range(3):
        for group in sorted(groups):
            pairings = group_pairings(groups[group])
            day_pairings = pairings[matchday * 2 : matchday * 2 + 2]
            for team_a, team_b in day_pairings:
                all_matches.append((group, matchday + 1, team_a, team_b))

    slots = fixture_slots(
        start=datetime(2026, 6, 12, 3, 0, tzinfo=CHINA_TZ),
        count=len(all_matches),
    )

    fixtures: List[Fixture] = []
    for idx, ((group, matchday, team_a, team_b), kickoff) in enumerate(
        zip(all_matches, slots),
        start=1,
    ):
        meta = dict(DEFAULT_FIXTURE_META)
        if idx in KNOWN_FIXTURE_META:
            meta.update(KNOWN_FIXTURE_META[idx])
        fixture_kickoff = meta.pop("kickoff", kickoff)
        fixtures.append(
            Fixture(
                id=f"G{group}-M{matchday}-{idx:03d}",
                group=group,
                matchday=matchday,
                kickoff=fixture_kickoff.isoformat(),
                team_a=team_a,
                team_b=team_b,
                stadium=meta["stadium"],
                city=meta["city"],
                country=meta["country"],
                weather=meta["weather"],
                data_quality=meta["data_quality"],
                result=KNOWN_RESULTS.get(idx),
            )
        )

    return fixtures


GROUP_STAGE_FIXTURES = build_group_stage_fixtures()
