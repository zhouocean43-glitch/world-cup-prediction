from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import exp, factorial
from typing import Dict, Iterable, Optional, Tuple

from backend.data import TeamProfile, get_team


OutcomeProbs = Dict[str, float]


@dataclass(frozen=True)
class MarketOdds:
    team_a: float
    draw: float
    team_b: float


@dataclass(frozen=True)
class NewsSignal:
    team_a_absences: int = 0
    team_b_absences: int = 0
    team_a_rest_days: int = 4
    team_b_rest_days: int = 4
    team_a_motivation: float = 0.5
    team_b_motivation: float = 0.5


@dataclass(frozen=True)
class PredictionContext:
    market_odds: Optional[MarketOdds] = None
    news: NewsSignal = NewsSignal()
    market_weight: float = 0.25
    market_total_goals: Optional[float] = None
    goal_market_weight: float = 0.70


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize(probs: OutcomeProbs) -> OutcomeProbs:
    total = sum(max(0.0, value) for value in probs.values())
    if total <= 0:
        return {"team_a_win": 1 / 3, "draw": 1 / 3, "team_b_win": 1 / 3}
    return {key: max(0.0, value) / total for key, value in probs.items()}


def blend(first: OutcomeProbs, second: OutcomeProbs, second_weight: float) -> OutcomeProbs:
    weight = clamp(second_weight, 0.0, 1.0)
    return normalize(
        {
            "team_a_win": first["team_a_win"] * (1 - weight) + second["team_a_win"] * weight,
            "draw": first["draw"] * (1 - weight) + second["draw"] * weight,
            "team_b_win": first["team_b_win"] * (1 - weight) + second["team_b_win"] * weight,
        }
    )


def news_adjusted_elo(team_a: TeamProfile, team_b: TeamProfile, signal: NewsSignal) -> Tuple[float, float]:
    absence_penalty = 18.0
    rest_bonus = 7.0
    motivation_bonus = 28.0

    team_a_elo = (
        team_a.elo
        - signal.team_a_absences * absence_penalty
        + (signal.team_a_rest_days - 4) * rest_bonus
        + (signal.team_a_motivation - 0.5) * motivation_bonus
    )
    team_b_elo = (
        team_b.elo
        - signal.team_b_absences * absence_penalty
        + (signal.team_b_rest_days - 4) * rest_bonus
        + (signal.team_b_motivation - 0.5) * motivation_bonus
    )
    return team_a_elo, team_b_elo


def elo_outcome_probs(team_a_elo: float, team_b_elo: float) -> OutcomeProbs:
    diff = team_a_elo - team_b_elo
    no_draw_team_a = 1.0 / (1.0 + 10 ** (-diff / 400.0))
    draw = clamp(0.285 - abs(diff) / 2400.0, 0.135, 0.295)
    return normalize(
        {
            "team_a_win": (1 - draw) * no_draw_team_a,
            "draw": draw,
            "team_b_win": (1 - draw) * (1 - no_draw_team_a),
        }
    )


def poisson_pmf(lam: float, goals: int) -> float:
    return exp(-lam) * (lam ** goals) / factorial(goals)


def expected_goals(team: TeamProfile, opponent: TeamProfile, team_elo: float, opponent_elo: float) -> float:
    base_goals = 1.22
    elo_factor = exp((team_elo - opponent_elo) / 1150.0)
    form_factor = 0.92 + team.form * 0.16
    return clamp(base_goals * team.attack * opponent.defense * elo_factor * form_factor, 0.20, 3.80)


@lru_cache(maxsize=4096)
def scoreline_distribution(lambda_a: float, lambda_b: float, max_goals: int = 8) -> Tuple[Tuple[int, int, float], ...]:
    lambda_a = round(lambda_a, 4)
    lambda_b = round(lambda_b, 4)
    rows = []
    total = 0.0
    for goals_a in range(max_goals + 1):
        prob_a = poisson_pmf(lambda_a, goals_a)
        for goals_b in range(max_goals + 1):
            prob = prob_a * poisson_pmf(lambda_b, goals_b)
            rows.append((goals_a, goals_b, prob))
            total += prob
    return tuple((a, b, p / total) for a, b, p in rows)


def poisson_outcome_probs(lambda_a: float, lambda_b: float) -> OutcomeProbs:
    probs = {"team_a_win": 0.0, "draw": 0.0, "team_b_win": 0.0}
    for goals_a, goals_b, prob in scoreline_distribution(lambda_a, lambda_b):
        if goals_a > goals_b:
            probs["team_a_win"] += prob
        elif goals_a == goals_b:
            probs["draw"] += prob
        else:
            probs["team_b_win"] += prob
    return normalize(probs)


def calibrate_lambdas_to_market(
    lambda_a: float,
    lambda_b: float,
    target_probs: OutcomeProbs,
    market_total_goals: Optional[float],
    weight: float,
) -> tuple[float, float]:
    base_total = lambda_a + lambda_b
    target_total = clamp(market_total_goals or base_total, 1.2, 4.3)
    total = base_total * (1 - clamp(weight, 0.0, 1.0)) + target_total * clamp(weight, 0.0, 1.0)

    best = (lambda_a, lambda_b)
    best_loss = float("inf")
    for step in range(5, 96):
        share = step / 100
        candidate_a = clamp(total * share, 0.15, 4.1)
        candidate_b = clamp(total - candidate_a, 0.15, 4.1)
        probs = poisson_outcome_probs(candidate_a, candidate_b)
        loss = (
            (probs["team_a_win"] - target_probs["team_a_win"]) ** 2
            + (probs["draw"] - target_probs["draw"]) ** 2 * 1.25
            + (probs["team_b_win"] - target_probs["team_b_win"]) ** 2
        )
        if loss < best_loss:
            best = (candidate_a, candidate_b)
            best_loss = loss

    blend_weight = clamp(weight, 0.0, 1.0)
    return (
        lambda_a * (1 - blend_weight) + best[0] * blend_weight,
        lambda_b * (1 - blend_weight) + best[1] * blend_weight,
    )


def odds_to_probabilities(odds: MarketOdds) -> OutcomeProbs:
    if odds.team_a <= 1 or odds.draw <= 1 or odds.team_b <= 1:
        raise ValueError("Decimal odds must be greater than 1.0.")
    implied = {
        "team_a_win": 1 / odds.team_a,
        "draw": 1 / odds.draw,
        "team_b_win": 1 / odds.team_b,
    }
    return normalize(implied)


def top_scorelines(lambda_a: float, lambda_b: float, limit: int = 6) -> list[dict]:
    rows = sorted(scoreline_distribution(lambda_a, lambda_b), key=lambda row: row[2], reverse=True)
    return [
        {
            "team_a_goals": goals_a,
            "team_b_goals": goals_b,
            "probability": round(prob, 4),
        }
        for goals_a, goals_b, prob in rows[:limit]
    ]


def predict_match(
    team_a_query: str,
    team_b_query: str,
    context: Optional[PredictionContext] = None,
) -> dict:
    if context is None:
        context = PredictionContext()

    team_a = get_team(team_a_query)
    team_b = get_team(team_b_query)
    if team_a.code == team_b.code:
        raise ValueError("Choose two different teams.")

    team_a_elo, team_b_elo = news_adjusted_elo(team_a, team_b, context.news)
    lambda_a = expected_goals(team_a, team_b, team_a_elo, team_b_elo)
    lambda_b = expected_goals(team_b, team_a, team_b_elo, team_a_elo)

    elo_probs = elo_outcome_probs(team_a_elo, team_b_elo)
    poisson_probs = poisson_outcome_probs(lambda_a, lambda_b)
    model_probs = blend(elo_probs, poisson_probs, second_weight=0.50)

    final_probs = model_probs
    market_probs = None
    if context.market_odds is not None:
        market_probs = odds_to_probabilities(context.market_odds)
        lambda_a, lambda_b = calibrate_lambdas_to_market(
            lambda_a,
            lambda_b,
            market_probs,
            context.market_total_goals,
            context.goal_market_weight,
        )
        poisson_probs = poisson_outcome_probs(lambda_a, lambda_b)
        model_probs = blend(elo_probs, poisson_probs, second_weight=0.50)
        final_probs = blend(model_probs, market_probs, context.market_weight)

    edge = final_probs["team_a_win"] - final_probs["team_b_win"]
    if abs(edge) < 0.04:
        lean = "balanced"
    elif edge > 0:
        lean = team_a.name
    else:
        lean = team_b.name

    return {
        "team_a": team_a.to_dict(),
        "team_b": team_b.to_dict(),
        "expected_goals": {
            "team_a": round(lambda_a, 3),
            "team_b": round(lambda_b, 3),
        },
        "probabilities": {key: round(value, 4) for key, value in final_probs.items()},
        "model_probabilities": {key: round(value, 4) for key, value in model_probs.items()},
        "market_probabilities": (
            {key: round(value, 4) for key, value in market_probs.items()}
            if market_probs is not None
            else None
        ),
        "top_scorelines": top_scorelines(lambda_a, lambda_b),
        "lean": lean,
        "explanation": [
            f"Elo difference after context: {team_a.name} {team_a_elo - team_b_elo:+.0f}.",
            "Score probabilities come from a Poisson goal model calibrated by market totals when available.",
            "Market odds are blended only when the request includes decimal odds.",
            "News signals adjust Elo-like strength before probabilities are produced.",
        ],
    }


def parse_market_odds(raw: Optional[dict]) -> Optional[MarketOdds]:
    if not raw:
        return None
    return MarketOdds(
        team_a=float(raw["team_a"]),
        draw=float(raw["draw"]),
        team_b=float(raw["team_b"]),
    )


def parse_news_signal(raw: Optional[dict]) -> NewsSignal:
    if not raw:
        return NewsSignal()
    return NewsSignal(
        team_a_absences=int(raw.get("team_a_absences", 0)),
        team_b_absences=int(raw.get("team_b_absences", 0)),
        team_a_rest_days=int(raw.get("team_a_rest_days", 4)),
        team_b_rest_days=int(raw.get("team_b_rest_days", 4)),
        team_a_motivation=float(raw.get("team_a_motivation", 0.5)),
        team_b_motivation=float(raw.get("team_b_motivation", 0.5)),
    )


def prediction_context_from_payload(payload: dict) -> PredictionContext:
    goal_market = payload.get("goal_market") or {}
    return PredictionContext(
        market_odds=parse_market_odds(payload.get("market_odds")),
        news=parse_news_signal(payload.get("news")),
        market_weight=float(payload.get("market_weight", 0.25)),
        market_total_goals=(
            float(goal_market["total_goals"])
            if goal_market.get("total_goals") is not None
            else None
        ),
        goal_market_weight=float(payload.get("goal_market_weight", 0.70)),
    )
