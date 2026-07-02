"""
Cross-Sectional Momentum Strategy
------------------------------------
Ranks the universe by trailing formation-window return every rebalance and
builds a dollar-balanced long/short book. Optional ML pair-reliability
filter (strategies/ml_pair_selector.py) can narrow leg eligibility after
ranking -- it never replaces or reorders the core rank.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import pandas as pd


@dataclass
class StrategyParams:
    universe: List[str]
    formation_window_hours: int = 14 * 24
    rebalance_hours: int = 3 * 24
    n_long: int = 3
    n_short: int = 3
    taker_fee_bps: float = 4.5
    base_leverage: float = 2.0
    phase_offset_hours: int = 0


@dataclass
class TargetBook:
    timestamp: pd.Timestamp
    longs: List[str]
    shorts: List[str]
    weights: Dict[str, float]


class CrossSectionalMomentumStrategy:
    def __init__(self, params: StrategyParams):
        self.p = params
        if len(self.p.universe) < self.p.n_long + self.p.n_short:
            raise ValueError("Universe too small for n_long + n_short")

    def trailing_returns(self, price_panel: pd.DataFrame, at_idx: int) -> pd.Series:
        lookback = self.p.formation_window_hours
        if at_idx - lookback < 0:
            return pd.Series(dtype=float)
        now_prices = price_panel.iloc[at_idx]
        past_prices = price_panel.iloc[at_idx - lookback]
        valid = now_prices.notna() & past_prices.notna() & (past_prices != 0)
        rets = (now_prices[valid] / past_prices[valid]) - 1.0
        return rets.reindex(self.p.universe).dropna()

    def rank_and_select(self, returns: pd.Series) -> Tuple[List[str], List[str]]:
        ranked = returns.sort_values(ascending=False)
        if len(ranked) < self.p.n_long + self.p.n_short:
            return [], []
        return list(ranked.index[:self.p.n_long]), list(ranked.index[-self.p.n_short:])

    def build_target_book(self, timestamp: pd.Timestamp, price_panel: pd.DataFrame,
                           at_idx: int, ml_selector: Optional[object] = None) -> TargetBook:
        rets = self.trailing_returns(price_panel, at_idx)
        longs, shorts = self.rank_and_select(rets)

        if ml_selector is not None and getattr(ml_selector.cfg, "enabled", False) and longs and shorts:
            ranked = rets.sort_values(ascending=False)
            pool_mult = ml_selector.cfg.candidate_pool_multiplier
            long_pool = list(ranked.index[: self.p.n_long * pool_mult])
            short_pool = list(ranked.index[-self.p.n_short * pool_mult:])

            feat_df = ml_selector.compute_features(price_panel, at_idx, self.p.universe)
            long_eligible = ml_selector.filter_eligible(long_pool, feat_df)
            short_eligible = ml_selector.filter_eligible(short_pool, feat_df)

            filtered_longs = [s for s in ranked.index if s in long_eligible][: self.p.n_long]
            filtered_shorts = [s for s in ranked.index[::-1] if s in short_eligible][: self.p.n_short]

            # fail-safe: only accept the filtered book if both legs still fill;
            # otherwise fall back to the plain, unfiltered rank
            if len(filtered_longs) == self.p.n_long and len(filtered_shorts) == self.p.n_short:
                longs, shorts = filtered_longs, filtered_shorts

        weights: Dict[str, float] = {}
        if longs and shorts:
            long_w, short_w = 0.5 / self.p.n_long, -0.5 / self.p.n_short
            weights.update({s: long_w for s in longs})
            weights.update({s: short_w for s in shorts})
        return TargetBook(timestamp=timestamp, longs=longs, shorts=shorts, weights=weights)

    def is_rebalance_due(self, last_rebalance_idx, current_idx: int) -> bool:
        if last_rebalance_idx is None:
            return True
        return (current_idx - last_rebalance_idx) >= self.p.rebalance_hours

    def fee_fraction(self) -> float:
        return self.p.taker_fee_bps / 10_000.0
