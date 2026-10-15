"""Offline entrypoint for the Walk-Forward Validation Engine.

Per the "Historical Walk-Forward Validation" production requirement: run
a full walk-forward pass over 1-2 years of stored candles, using the same
Chief AI decision pipeline the live loop uses
(`src.engines.replay_engine.decision.compute_replay_decision`), then
print aggregate statistics and generate `ImprovementProposal` rows for
the user to review -- never applied automatically.

This is a CPU-bound offline pass over tens of thousands of candles (one
real Chief AI decision per step), not a web-triggered synchronous call.
For a full 1-2 year M15 history this can take a long time; use `--step`
to trade completeness for runtime, and `--limit` to bound how much
history is loaded.

Requires stored candle history for the given symbol/timeframe (see
`scripts/mt5_historical_backfill.py`). Read-only against MT5/broker state
-- never places an order.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/run_walk_forward_validation.py \\
        --symbol XAUUSD --timeframe M15 --window-size 250 --step 4
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from src.common.logging import configure_logging, get_logger
from src.core.technical_analysis.agent_registry import default_technical_agents
from src.database.postgres.session import get_session
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.validation_engine.recommendations import generate_recommendations
from src.engines.validation_engine.statistics import compute_walk_forward_statistics
from src.engines.validation_engine.walk_forward import run_chief_ai_walk_forward
from src.repositories.candle_repository import CandleRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.symbol_repository import SymbolRepository
from src.settings import get_settings

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol name (default: XAUUSD)")
    parser.add_argument("--timeframe", default="M15", help="Decision timeframe (default: M15)")
    parser.add_argument(
        "--window-size", type=int, default=250, help="Candles per decision step (default: 250)"
    )
    parser.add_argument(
        "--step",
        type=int,
        default=1,
        help="Advance this many candles between decision steps (default: 1, every candle)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=70.0,
        help="Minimum overall confidence (0-100) to BUY/SELL (default: 70.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=70_000,
        help="Maximum candles to load from storage (default: 70000, ~2 years of M15)",
    )
    parser.add_argument(
        "--start", type=datetime.fromisoformat, default=None, help="ISO start timestamp"
    )
    parser.add_argument(
        "--end", type=datetime.fromisoformat, default=None, help="ISO end timestamp"
    )
    parser.add_argument(
        "--persist-recommendations",
        action="store_true",
        help="Persist generated recommendations as pending ImprovementProposal rows",
    )
    return parser.parse_args()


async def main() -> int:
    configure_logging(get_settings())
    args = _parse_args()

    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name(args.symbol)
        if symbol is None:
            print(f"FAILED: symbol {args.symbol!r} not found. Run the seed script first.")
            return 1

        candle_repository = CandleRepository(session)
        candles = await candle_repository.list_range(
            symbol.id, args.timeframe, start=args.start, end=args.end, limit=args.limit
        )
        if len(candles) <= args.window_size:
            print(
                f"FAILED: only {len(candles)} candles stored for {args.symbol} "
                f"{args.timeframe}, need more than --window-size ({args.window_size}). "
                "Run scripts/mt5_historical_backfill.py first."
            )
            return 1
        print(f"Loaded {len(candles)} {args.timeframe} candles for {args.symbol}.")

        similarity_service = HistoricalSimilarityService(
            candle_repository=candle_repository,
            similarity_repository=HistoricalSimilarityRepository(session),
        )

        opportunities = await run_chief_ai_walk_forward(
            symbol_id=symbol.id,
            timeframe=args.timeframe,
            candles=candles,
            technical_agents=default_technical_agents(),
            similarity_service=similarity_service,
            confidence_threshold=args.confidence_threshold,
            window_size=args.window_size,
            step=args.step,
        )
        print(f"Recorded {len(opportunities)} opportunities.")

        statistics = compute_walk_forward_statistics(opportunities)
        print(
            f"Actionable: {statistics.actionable_opportunities} | "
            f"Traded (had a forward simulation): {statistics.traded_opportunities} | "
            f"Win rate: {statistics.win_rate:.1%} | "
            f"Average return: {statistics.average_return_pct:+.3f}%"
        )
        print("\nDepartment combinations (most frequent first):")
        for combo in statistics.combo_statistics[:20]:
            label = ", ".join(combo.departments) or "(none)"
            print(
                f"  [{label}] n={combo.sample_size} win_rate={combo.win_rate:.1%} "
                f"avg_return={combo.average_return_pct:+.3f}%"
            )
        print("\nDepartment contributions:")
        for contribution in statistics.department_contributions:
            print(
                f"  {contribution.department_name}: agreements={contribution.total_agreements} "
                f"win_contribution={contribution.win_contribution_rate:.1%} "
                f"loss_contribution={contribution.loss_contribution_rate:.1%}"
            )

        proposals = generate_recommendations(
            statistics, symbol_name=args.symbol, timeframe=args.timeframe
        )
        print(f"\nGenerated {len(proposals)} recommendation(s) (never applied automatically):")
        for proposal in proposals:
            print(f"  - {proposal.title}")

        if args.persist_recommendations and proposals:
            repository = ImprovementProposalRepository(session)
            for proposal in proposals:
                await repository.add(proposal)
            print(f"Persisted {len(proposals)} pending ImprovementProposal row(s) for review.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
