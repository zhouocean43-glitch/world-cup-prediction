from pathlib import Path
import tempfile
import unittest

import backend.tournament_cache as tournament_cache
from backend.fixtures import GROUP_STAGE_FIXTURES
from backend.odds_provider import extract_h2h_aggregate
from backend.prediction import MarketOdds, odds_to_probabilities, predict_match
from backend.score_provider import build_scoreboard_updates
from backend.simulation import simulate_tournament


class PredictionTests(unittest.TestCase):
    def test_prediction_probabilities_sum_to_one(self):
        result = predict_match("Argentina", "Spain")
        total = sum(result["probabilities"].values())
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_market_odds_remove_margin(self):
        probs = odds_to_probabilities(MarketOdds(team_a=2.1, draw=3.2, team_b=3.8))
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=8)
        self.assertGreater(probs["team_a_win"], probs["team_b_win"])

    def test_opening_match_has_final_score(self):
        opening_match = GROUP_STAGE_FIXTURES[0].to_dict()

        self.assertEqual(opening_match["team_a"], "MEX")
        self.assertEqual(opening_match["team_b"], "RSA")
        self.assertEqual(opening_match["result"]["status"], "final")
        self.assertEqual(opening_match["result"]["team_a_goals"], 2)
        self.assertEqual(opening_match["result"]["team_b_goals"], 0)

    def test_scoreboard_updates_final_score_and_venue(self):
        fixture = GROUP_STAGE_FIXTURES[1].to_dict()
        event = {
            "id": "760414",
            "date": "2026-06-12T02:00Z",
            "name": "Czechia at South Korea",
            "competitions": [
                {
                    "venue": {
                        "fullName": "Estadio Akron",
                        "address": {"city": "Guadalajara", "country": "Mexico"},
                    },
                    "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True, "detail": "FT"}},
                    "competitors": [
                        {"team": {"displayName": "South Korea", "abbreviation": "KOR"}, "score": "2"},
                        {"team": {"displayName": "Czechia", "abbreviation": "CZE"}, "score": "1"},
                    ],
                }
            ],
        }

        updates = build_scoreboard_updates([event], [fixture], "2026-06-12T05:00:00Z")

        self.assertEqual(updates[fixture["id"]]["kickoff"], "2026-06-12T10:00:00+08:00")
        self.assertEqual(updates[fixture["id"]]["stadium"], "Estadio Akron")
        self.assertEqual(updates[fixture["id"]]["city"], "Guadalajara")
        self.assertEqual(updates[fixture["id"]]["result"]["team_a_goals"], 2)
        self.assertEqual(updates[fixture["id"]]["result"]["team_b_goals"], 1)
        self.assertEqual(updates[fixture["id"]]["result"]["winner"], "team_a")

    def test_scoreboard_matches_hyphenated_team_names(self):
        fixture = GROUP_STAGE_FIXTURES[2].to_dict()
        event = {
            "id": "760416",
            "date": "2026-06-12T19:00Z",
            "name": "Bosnia-Herzegovina at Canada",
            "competitions": [
                {
                    "venue": {
                        "fullName": "BMO Field",
                        "address": {"city": "Toronto", "country": "Canada"},
                    },
                    "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
                    "competitors": [
                        {"team": {"displayName": "Canada", "abbreviation": "CAN"}, "score": "0"},
                        {"team": {"displayName": "Bosnia-Herzegovina", "abbreviation": "BIH"}, "score": "0"},
                    ],
                }
            ],
        }

        updates = build_scoreboard_updates([event], [fixture], "2026-06-12T05:00:00Z")

        self.assertEqual(updates[fixture["id"]]["kickoff"], "2026-06-13T03:00:00+08:00")
        self.assertEqual(updates[fixture["id"]]["stadium"], "BMO Field")
        self.assertNotIn("result", updates[fixture["id"]])

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
        original_cache_path = tournament_cache.CACHE_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            tournament_cache.CACHE_PATH = Path(tmpdir) / "tournament_cache.json"
            try:
                first = tournament_cache.get_tournament_result(runs=12, seed=123, refresh=True)
                second = tournament_cache.get_tournament_result(runs=12, seed=123)
            finally:
                tournament_cache.CACHE_PATH = original_cache_path

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["generated_at"], second["generated_at"])
        self.assertEqual(first["probabilities"], second["probabilities"])


if __name__ == "__main__":
    unittest.main()
