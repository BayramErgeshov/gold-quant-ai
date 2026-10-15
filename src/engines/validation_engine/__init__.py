"""Walk-Forward Validation Engine.

Per the "Historical Walk-Forward Validation" production requirement: a
full walk-forward pass over 1-2 years of history, replaying candles
exactly as if live, using the SAME Chief AI decision pipeline the live
loop uses (`src.engines.replay_engine.decision.compute_replay_decision`,
already guaranteed to never see a future candle). Distinct from the
lighter-weight `src.engines.backtesting_engine` (which decides via a bare
buy/sell/wait `SignalFunction`, with no department detail): every
recorded `WalkForwardOpportunity` carries which departments agreed or
disagreed, the Trade Quality Score, and (for actionable opportunities)
forward-simulated P/L, Maximum Favorable/Adverse Excursion and holding
time.

Findings here only ever produce `ImprovementProposal` recommendations
for the user to review -- "No production strategy may change
automatically" (this platform's own operating instructions).
"""
