import unittest

from backend.odds_provider import extract_h2h_aggregate
from backend.prediction import MarketOdds, odds_to_probabilities, predict_match
from backend.simulation import simulate_tournament
from backend.tournament_cache import get_tournament_result


class PredictionTests(unittest.TestCase):
    def test_prediction_probabilities_sum_to_one(self):
        result = predict_match("Argentina", "Spain")
        total = sum(result["probabilities"].values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_market_odds_remove_margin(self):
        probs = odds_to_probabilities(MarketOdds(team_a=2.1, draw=3.2, team_b=3.8))
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=8)
        self.assertGreater(probs["team_a_win"], probs["team_b_win"])

    def test_h2h_aggregate_averages_major_bookmakers(self):
        fixture = {
            "team_a_name": "Mexico",
            "team_b_name": "South Africa",
        }
        event = {
            "home_team": "Mexico",
            "away_team": "South Africa",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "last_update": "2026-06-11T12:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Mexico", "price": 1.4},
                                {"name": "Draw", "price": 4.4},
                                {"name": "South Africa", "price": 9.0},
                            ],
                        }
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "last_update": "2026-06-11T12:01:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Mexico", "price": 1.5},
                                {"name": "Draw", "price": 4.6},
                                {"name": "South Africa", "price": 8.8},
                            ],
                        }
                    ],
                },
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "last_update": "2026-06-11T12:02:00Z",
                    "markets": [
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 2.1, "point": 2.5},
                                {"name": "Under", "price": 1.75, "point": 2.5},
                            ],
                        }
                    ],
                },
            ],
        }

        aggregate = extract_h2h_aggregate(event, fixture)

        self.assertIsNotNone(aggregate)
        self.assertEqual(aggregate.bookmaker_count, 2)
        self.assertEqual(aggregate.market_odds, {"team_a": 1.45, "draw": 4.5, "team_b": 8.9})
        self.assertIsNotNone(aggregate.goal_market)
        self.assertEqual(aggregate.goal_market["bookmaker_count"], 1)
        self.assertGreater(aggregate.goal_market["total_goals"], 2.0)

    def test_tournament_simulation_shape(self):
        result = simulate_tournament(runs=20, seed=7)
        self.assertEqual(result["runs"], 20)
        self.assertEqual(len(result["probabilities"]), 48)
        champion_total = sum(row["champion"] for row in result["probabilities"])
        self.assertAlmostEqual(champion_total, 1.0, places=3)

    def test_tournament_cache_keeps_refresh_stable(self):
        first = get_tournament_result(runs=12, seed=123, refresh=True)
        second = get_tournament_result(runs=12, seed=123)

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["generated_at"], second["generated_at"])
        self.assertEqual(first["probabilities"], second["probabilities"])


if __name__ == "__main__":
    unittest.main()
