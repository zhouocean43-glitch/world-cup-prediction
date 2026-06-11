from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.env import load_local_env
from backend.fixtures import GROUP_STAGE_FIXTURES
from backend.odds_provider import fetch_market_odds
from backend.signals import build_fallback_signal_cache, load_signal_cache, save_signal_cache


def main() -> None:
    load_local_env()
    fixtures = [fixture.to_dict() for fixture in GROUP_STAGE_FIXTURES]
    previous_cache = load_signal_cache()
    provider_odds = fetch_market_odds(fixtures)
    cache = build_fallback_signal_cache(
        fixtures,
        previous_cache=previous_cache,
        provider_odds=provider_odds,
    )
    save_signal_cache(cache)
    print(f"Updated {len(fixtures)} fixture signals.")
    if provider_odds:
        print(f"Provider: The Odds API aggregate ({len(provider_odds)} matched fixtures).")
    else:
        print("Provider: local fallback + static bookmaker snapshots.")
        print("Set ODDS_API_KEY to aggregate DraftKings/FanDuel/BetMGM/Caesars/Bet365/Pinnacle/Betfair style markets.")


if __name__ == "__main__":
    main()
