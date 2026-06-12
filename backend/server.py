from __future__ import annotations

import argparse
import json
import mimetypes
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from backend.env import load_local_env

load_local_env()

from backend.data import DEFAULT_GROUPS, all_teams
from backend.fixtures import GROUP_STAGE_FIXTURES
from backend.odds_provider import fetch_champion_futures, fetch_market_odds, odds_api_configured
from backend.prediction import predict_match, prediction_context_from_payload
from backend.score_provider import fetch_scoreboard_updates
from backend.signals import get_fixture_signal, odds_movement
from backend.tournament_cache import get_tournament_result


API_DOCS = {
    "name": "World Cup Prediction Backend",
    "version": "0.1.0",
    "endpoints": {
        "GET /api/health": "Health check.",
        "GET /api/teams": "List demo team profiles.",
        "GET /api/groups": "List demo tournament groups.",
        "GET /api/fixtures": "List group-stage fixtures on a timeline.",
        "GET /api/timeline": "List fixtures with live-style odds, news, and predictions.",
        "GET /api/predict?team_a=Argentina&team_b=Spain": "Single-match prediction.",
        "POST /api/predict": "Prediction with optional market_odds and news signals.",
        "GET /api/tournament?runs=2000&seed=42": "Cached Monte Carlo champion futures. Add refresh=1 to rebuild.",
    },
}

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
ASSETS_DIR = ROOT_DIR / "assets"


class PredictionHandler(BaseHTTPRequestHandler):
    server_version = "WorldCupPredictor/0.1"

    def _send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_error_json(404, "File not found.")
            return

        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_scoped_file(self, root_dir: Path, relative_path: str) -> None:
        root = root_dir.resolve()
        file_path = (root / unquote(relative_path)).resolve()
        try:
            file_path.relative_to(root)
        except ValueError:
            self._send_error_json(404, "File not found.")
            return
        self._send_file(file_path)

    def _send_frontend_asset(self, parsed_path: str) -> bool:
        if parsed_path == "/" or parsed_path == "/app":
            self._send_file(FRONTEND_DIR / "index.html")
            return True

        if parsed_path.startswith("/frontend/"):
            relative = parsed_path.removeprefix("/frontend/")
            self._send_scoped_file(FRONTEND_DIR, relative)
            return True

        if parsed_path.startswith("/assets/"):
            relative = parsed_path.removeprefix("/assets/")
            self._send_scoped_file(ASSETS_DIR, relative)
            return True

        return False

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def _handle_get_like(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if self._send_frontend_asset(parsed.path):
                return
            if parsed.path == "/api":
                self._send_json(200, API_DOCS)
            elif parsed.path == "/api/health":
                self._send_json(200, {"status": "ok"})
            elif parsed.path == "/api/teams":
                self._send_json(200, [team.to_dict() for team in all_teams()])
            elif parsed.path == "/api/groups":
                self._send_json(200, DEFAULT_GROUPS)
            elif parsed.path == "/api/fixtures":
                fixture_rows, _score_status = build_fixture_rows()
                self._send_json(200, fixture_rows)
            elif parsed.path == "/api/timeline":
                refresh_odds = query.get("refresh_odds", ["0"])[0].lower() in {"1", "true", "yes", "on"}
                refresh_scores = query.get("refresh_scores", ["0"])[0].lower() in {"1", "true", "yes", "on"}
                self._send_json(200, build_timeline_payload(refresh_odds=refresh_odds, refresh_scores=refresh_scores))
            elif parsed.path == "/api/predict":
                team_a = query.get("team_a", ["Argentina"])[0]
                team_b = query.get("team_b", ["Spain"])[0]
                self._send_json(200, predict_match(team_a, team_b))
            elif parsed.path == "/api/tournament":
                runs = int(query.get("runs", ["2000"])[0])
                seed = int(query.get("seed", ["42"])[0])
                refresh = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes", "on"}
                result = get_tournament_result(runs=runs, seed=seed, refresh=refresh)
                result["market_futures"] = fetch_live_champion_futures()
                result["market_status"] = build_market_status(result["market_futures"])
                self._send_json(200, result)
            else:
                self._send_error_json(404, f"Unknown endpoint: {parsed.path}")
        except Exception as exc:
            self._send_error_json(400, str(exc))

    def do_GET(self) -> None:
        self._handle_get_like()

    def do_HEAD(self) -> None:
        self._handle_get_like()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/predict":
            self._send_error_json(404, f"Unknown endpoint: {parsed.path}")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body)
            team_a = payload.get("team_a", "Argentina")
            team_b = payload.get("team_b", "Spain")
            context = prediction_context_from_payload(payload)
            self._send_json(200, predict_match(team_a, team_b, context=context))
        except Exception as exc:
            self._send_error_json(400, str(exc))

    def log_message(self, format: str, *args) -> None:
        return


def build_fixture_rows(refresh_scores: bool = False) -> tuple[list[dict], dict]:
    fixture_rows = [fixture.to_dict() for fixture in GROUP_STAGE_FIXTURES]
    scoreboard_updates, score_status = fetch_scoreboard_updates(fixture_rows, refresh=refresh_scores)

    for fixture_row in fixture_rows:
        update = scoreboard_updates.get(fixture_row["id"])
        if update:
            fixture_row.update(update)

    score_status = {
        **score_status,
        "final_count": sum(1 for row in fixture_rows if (row.get("result") or {}).get("status") == "final"),
    }
    return fixture_rows, score_status


def parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_iso(*values: str | None) -> str | None:
    parsed = [parse_iso(value) for value in values if value]
    parsed = [value for value in parsed if value is not None]
    if not parsed:
        return None
    return max(parsed).isoformat().replace("+00:00", "Z")


def build_timeline_payload(refresh_odds: bool = False, refresh_scores: bool = False) -> dict:
    fixtures = []
    fixture_rows, score_status = build_fixture_rows(refresh_scores=refresh_scores)
    latest_signal_update = score_status.get("updated_at")
    live_odds = fetch_live_match_odds(fixture_rows) if (refresh_odds or odds_api_configured()) else {}

    for fixture, fixture_row in zip(GROUP_STAGE_FIXTURES, fixture_rows):
        signal = get_fixture_signal(fixture.id, fixture.team_a, fixture.team_b)
        if fixture.id in live_odds:
            aggregate = live_odds[fixture.id]
            previous_odds = signal.get("market_odds")
            signal = {
                **signal,
                "updated_at": aggregate.updated_at or signal.get("updated_at"),
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
        latest_signal_update = latest_iso(latest_signal_update, signal.get("updated_at"))
        prediction = predict_match(
            fixture.team_a,
            fixture.team_b,
            context=prediction_context_from_payload(
                {
                    "market_odds": signal["market_odds"],
                    "market_weight": signal.get("market_weight", 0.28),
                    "goal_market": signal.get("goal_market"),
                    "news": signal["news"],
                }
            ),
        )
        fixtures.append(
            {
                **fixture_row,
                "signal": signal,
                "prediction": prediction,
            }
        )

    return {
        "updated_at": latest_signal_update,
        "timezone": "Asia/Shanghai",
        "provider_note": provider_note(live_odds),
        "provider_status": provider_status(live_odds, len(fixture_rows)),
        "score_status": score_status,
        "fixtures": fixtures,
    }


def fetch_live_match_odds(fixture_rows: list[dict]) -> dict:
    if not odds_api_configured():
        return {}
    try:
        return fetch_market_odds(fixture_rows)
    except Exception:
        return {}


def fetch_live_champion_futures() -> list[dict]:
    if not odds_api_configured():
        return []
    try:
        return fetch_champion_futures()
    except Exception:
        return []


def build_market_status(market_futures: list[dict]) -> dict:
    if not odds_api_configured():
        return {
            "configured": False,
            "source": None,
            "message": "ODDS_API_KEY is not configured; showing the fixed model champion table.",
        }
    return {
        "configured": True,
        "source": "The Odds API",
        "matched": len(market_futures),
        "message": "Live champion futures are aggregated from configured bookmakers."
        if market_futures
        else "The Odds API is configured, but no matching World Cup outright market was returned.",
    }


def provider_note(live_odds: dict) -> str:
    if live_odds:
        bookmaker_counts = [aggregate.bookmaker_count for aggregate in live_odds.values()]
        return (
            f"已同步博彩公司均值：当前 {len(live_odds)} 场有公开报价，"
            f"单场最多 {max(bookmaker_counts)} 家报价；比分已用大小球盘口校准。"
        )
    if odds_api_configured():
        return "已配置数据源，但当前没有匹配到世界杯小组赛公开报价；页面不会用随机数冒充市场盘口。"
    return "当前未接入实时报价：只显示已保存快照和模型占位线，不生成假盘口波动。"


def provider_status(live_odds: dict, total_fixtures: int) -> dict:
    if live_odds:
        bookmaker_counts = [aggregate.bookmaker_count for aggregate in live_odds.values()]
        bookmakers = sorted(
            {
                bookmaker
                for aggregate in live_odds.values()
                for bookmaker in getattr(aggregate, "bookmakers", [])
            }
        )
        return {
            "configured": True,
            "connected": True,
            "source": "The Odds API",
            "matched": len(live_odds),
            "total_fixtures": total_fixtures,
            "max_bookmakers": max(bookmaker_counts) if bookmaker_counts else 0,
            "bookmakers": bookmakers,
            "bookmaker_label": " / ".join(bookmakers[:6]),
            "calibration": "胜平负 + 大小球",
            "message": f"{len(live_odds)}/{total_fixtures} 场小组赛已有公开盘口。",
        }
    if odds_api_configured():
        return {
            "configured": True,
            "connected": False,
            "source": "The Odds API",
            "matched": 0,
            "total_fixtures": total_fixtures,
            "max_bookmakers": 0,
            "bookmakers": [],
            "bookmaker_label": "等待公开盘口",
            "calibration": "模型占位",
            "message": "已配置数据源，但暂未匹配到小组赛公开报价。",
        }
    return {
        "configured": False,
        "connected": False,
        "source": "未接入",
        "matched": 0,
        "total_fixtures": total_fixtures,
        "max_bookmakers": 0,
        "bookmakers": [],
        "bookmaker_label": "本地模型",
        "calibration": "模型占位",
        "message": "未配置实时赔率源，不生成假盘口波动。",
    }


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), PredictionHandler)
    print(f"World Cup prediction backend running at http://{host}:{port}")
    print("Try: /api/predict?team_a=Argentina&team_b=Spain")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the World Cup prediction backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
