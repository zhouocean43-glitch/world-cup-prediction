from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from random import Random
from typing import Dict, Iterable, List, Tuple

from backend.data import DEFAULT_GROUPS, TEAM_PROFILES, TeamProfile, validate_groups
from backend.prediction import expected_goals, scoreline_distribution


@dataclass
class TableRow:
    team: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def to_dict(self) -> dict:
        row = asdict(self)
        row["goal_difference"] = self.goal_difference
        row["team_name"] = TEAM_PROFILES[self.team].name
        return row


def round_robin(teams: Iterable[str]) -> List[Tuple[str, str]]:
    team_list = list(teams)
    return [
        (team_list[i], team_list[j])
        for i in range(len(team_list))
        for j in range(i + 1, len(team_list))
    ]


def sample_score(team_a: TeamProfile, team_b: TeamProfile, rng: Random) -> Tuple[int, int]:
    lambda_a = expected_goals(team_a, team_b, team_a.elo, team_b.elo)
    lambda_b = expected_goals(team_b, team_a, team_b.elo, team_a.elo)
    cursor = rng.random()
    cumulative = 0.0
    for goals_a, goals_b, prob in scoreline_distribution(lambda_a, lambda_b):
        cumulative += prob
        if cursor <= cumulative:
            return goals_a, goals_b
    return 0, 0


def update_table(table: Dict[str, TableRow], team_a: str, team_b: str, goals_a: int, goals_b: int) -> None:
    row_a = table[team_a]
    row_b = table[team_b]

    row_a.played += 1
    row_b.played += 1
    row_a.goals_for += goals_a
    row_a.goals_against += goals_b
    row_b.goals_for += goals_b
    row_b.goals_against += goals_a

    if goals_a > goals_b:
        row_a.wins += 1
        row_b.losses += 1
        row_a.points += 3
    elif goals_a < goals_b:
        row_b.wins += 1
        row_a.losses += 1
        row_b.points += 3
    else:
        row_a.draws += 1
        row_b.draws += 1
        row_a.points += 1
        row_b.points += 1


def rank_rows(rows: Iterable[TableRow]) -> List[TableRow]:
    return sorted(
        rows,
        key=lambda row: (
            row.points,
            row.goal_difference,
            row.goals_for,
            TEAM_PROFILES[row.team].elo,
        ),
        reverse=True,
    )


def simulate_group(group_name: str, teams: List[str], rng: Random) -> List[TableRow]:
    table = {code: TableRow(team=code) for code in teams}
    for team_a, team_b in round_robin(teams):
        goals_a, goals_b = sample_score(TEAM_PROFILES[team_a], TEAM_PROFILES[team_b], rng)
        update_table(table, team_a, team_b, goals_a, goals_b)
    return rank_rows(table.values())


def select_knockout_teams(group_tables: Dict[str, List[TableRow]]) -> Tuple[List[str], Dict[str, List[str]]]:
    positions: Dict[str, List[str]] = {"winners": [], "runners_up": [], "thirds": []}
    third_rows: List[Tuple[str, TableRow]] = []

    for group in sorted(group_tables):
        rows = group_tables[group]
        positions["winners"].append(rows[0].team)
        positions["runners_up"].append(rows[1].team)
        third_rows.append((group, rows[2]))

    ranked_thirds = sorted(
        third_rows,
        key=lambda item: (
            item[1].points,
            item[1].goal_difference,
            item[1].goals_for,
            TEAM_PROFILES[item[1].team].elo,
        ),
        reverse=True,
    )
    positions["thirds"] = [row.team for _, row in ranked_thirds[:8]]
    return positions["winners"] + positions["runners_up"] + positions["thirds"], positions


def knockout_win_probability(team_a: TeamProfile, team_b: TeamProfile) -> float:
    return 1.0 / (1.0 + 10 ** (-(team_a.elo - team_b.elo) / 420.0))


def simulate_knockout_match(team_a: str, team_b: str, rng: Random) -> str:
    goals_a, goals_b = sample_score(TEAM_PROFILES[team_a], TEAM_PROFILES[team_b], rng)
    if goals_a > goals_b:
        return team_a
    if goals_b > goals_a:
        return team_b
    return team_a if rng.random() < knockout_win_probability(TEAM_PROFILES[team_a], TEAM_PROFILES[team_b]) else team_b


def build_round_of_32(positions: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    winners = positions["winners"]
    runners_up = positions["runners_up"]
    thirds = positions["thirds"]

    pairings: List[Tuple[str, str]] = []
    for idx in range(8):
        pairings.append((winners[idx], thirds[idx]))
    for idx in range(4):
        pairings.append((winners[idx + 8], runners_up[idx]))
    pairings.extend(
        [
            (runners_up[4], runners_up[5]),
            (runners_up[6], runners_up[7]),
            (runners_up[8], runners_up[9]),
            (runners_up[10], runners_up[11]),
        ]
    )
    return pairings


def simulate_one_tournament(groups: Dict[str, List[str]], rng: Random) -> dict:
    validate_groups(groups)
    group_tables = {
        group: simulate_group(group, teams, rng)
        for group, teams in sorted(groups.items())
    }
    _, positions = select_knockout_teams(group_tables)

    stage_teams = {
        "round_of_32": positions["winners"] + positions["runners_up"] + positions["thirds"],
        "round_of_16": [],
        "quarterfinal": [],
        "semifinal": [],
        "final": [],
        "champion": [],
    }

    current_pairings = build_round_of_32(positions)
    next_stage_names = ["round_of_16", "quarterfinal", "semifinal", "final", "champion"]

    for stage_name in next_stage_names:
        winners: List[str] = []
        for team_a, team_b in current_pairings:
            winners.append(simulate_knockout_match(team_a, team_b, rng))
        stage_teams[stage_name] = winners
        current_pairings = [
            (winners[i], winners[i + 1])
            for i in range(0, len(winners), 2)
        ] if len(winners) > 1 else []

    return {
        "group_tables": {
            group: [row.to_dict() for row in rows]
            for group, rows in group_tables.items()
        },
        "stage_teams": stage_teams,
    }


def simulate_tournament(
    runs: int = 2000,
    seed: int = 42,
    groups: Dict[str, List[str]] | None = None,
) -> dict:
    if groups is None:
        groups = DEFAULT_GROUPS
    runs = max(1, min(int(runs), 100000))

    rng = Random(seed)
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sample_tables = None

    for run_idx in range(runs):
        result = simulate_one_tournament(groups, rng)
        if run_idx == 0:
            sample_tables = result["group_tables"]
        for stage, teams in result["stage_teams"].items():
            for team in teams:
                counts[stage][team] += 1

    teams = sorted(TEAM_PROFILES.values(), key=lambda team: counts["champion"].get(team.code, 0), reverse=True)
    probabilities = []
    for team in teams:
        probabilities.append(
            {
                "team": team.name,
                "code": team.code,
                "round_of_32": round(counts["round_of_32"].get(team.code, 0) / runs, 4),
                "round_of_16": round(counts["round_of_16"].get(team.code, 0) / runs, 4),
                "quarterfinal": round(counts["quarterfinal"].get(team.code, 0) / runs, 4),
                "semifinal": round(counts["semifinal"].get(team.code, 0) / runs, 4),
                "final": round(counts["final"].get(team.code, 0) / runs, 4),
                "champion": round(counts["champion"].get(team.code, 0) / runs, 4),
            }
        )

    return {
        "runs": runs,
        "seed": seed,
        "format": "demo_48_team_world_cup_top2_plus_8_thirds",
        "note": "Demo bracket mapping. Replace with official fixture/bracket provider for production.",
        "probabilities": probabilities,
        "sample_group_tables": sample_tables,
    }

