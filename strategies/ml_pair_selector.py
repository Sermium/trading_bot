"""
ML Pair-Reliability Filter (optional overlay, OFF by default)
------------------------------------------------------------------
Does NOT choose the universe and does NOT replace the trailing-return
ranking. It scores each ranked candidate leg on whether momentum has
historically "paid off" for that specific symbol, and can narrow (never
widen) the eligible pool for each rebalance.

Trained walk-forward, expanding window, with labels only added once their
holding period has actually resolved -- no lookahead.

CAVEAT: 18 symbols and a multi-day rebalance cadence means the training
set grows slowly and rows are highly cross-correlated. Validate this
overlay with the same OOS split and rebalance-phase sweep used for the
core strategy before trusting any backtest improvement it shows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

try:
    from sklearn.ensemble import GradientBoostingClassifier
except ImportError:  # sklearn not installed -- filter degrades to a no-op
    GradientBoostingClassifier = None


@dataclass
class MLFilterConfig:
    enabled: bool = False
    min_training_samples: int = 60
    refit_every_n_rebalances: int = 5
    probability_threshold: float = 0.50
    feature_lookback_days: int = 60
    max_depth: int = 3
    n_estimators: int = 100
    candidate_pool_multiplier: int = 2   # widen pool before filtering, e.g. 2x n_long


@dataclass
class PendingLabel:
    rebalance_idx: int
    resolve_idx: int
    symbol: str
    side: str
    features: Dict[str, float]


class MLPairSelector:
    def __init__(self, cfg: MLFilterConfig):
        self.cfg = cfg
        self.model = None
        self.feature_names: List[str] = []
        self.pending: List[PendingLabel] = []
        self.training_rows: List[Tuple[Dict[str, float], int]] = []
        self.rebalances_since_fit = 0

    def compute_features(self, price_panel: pd.DataFrame, at_idx: int,
                          universe: List[str]) -> pd.DataFrame:
        lookback_hours = self.cfg.feature_lookback_days * 24
        start = max(0, at_idx - lookback_hours)
        window = price_panel.iloc[start:at_idx + 1]

        rows = {}
        for sym in universe:
            if sym not in window.columns:
                continue
            s = window[sym].dropna()
            if len(s) < 48:
                continue

            daily = s.resample("1D").last().dropna() if isinstance(s.index, pd.DatetimeIndex) else s
            daily_rets = daily.pct_change().dropna()

            ret_14d = (s.iloc[-1] / s.iloc[max(0, len(s) - 14 * 24)] - 1.0) if len(s) > 14 * 24 else np.nan
            ret_3d = (s.iloc[-1] / s.iloc[max(0, len(s) - 3 * 24)] - 1.0) if len(s) > 3 * 24 else np.nan
            vol_30d = daily_rets.tail(30).std() * np.sqrt(365) if len(daily_rets) > 5 else np.nan
            autocorr_1d = daily_rets.autocorr(lag=1) if len(daily_rets) > 10 else np.nan
            consistency = float(np.sign(ret_14d) == np.sign(ret_3d)) if pd.notna(ret_14d) and pd.notna(ret_3d) else np.nan

            rows[sym] = {
                "ret_14d": ret_14d, "ret_3d": ret_3d,
                "ret_consistency": consistency,
                "vol_30d": vol_30d, "autocorr_1d": autocorr_1d,
            }

        return pd.DataFrame(rows).T.dropna()

    def register_pending(self, rebalance_idx: int, resolve_idx: int,
                          symbol: str, side: str, features: Dict[str, float]):
        self.pending.append(PendingLabel(rebalance_idx, resolve_idx, symbol, side, features))

    def resolve_pending(self, current_idx: int, price_panel: pd.DataFrame, fee_frac: float):
        still_pending = []
        for p in self.pending:
            if current_idx < p.resolve_idx:
                still_pending.append(p)
                continue
            if p.symbol not in price_panel.columns:
                continue
            entry_price = price_panel[p.symbol].iloc[p.rebalance_idx]
            exit_price = price_panel[p.symbol].iloc[p.resolve_idx]
            if pd.isna(entry_price) or pd.isna(exit_price):
                continue
            raw_ret = exit_price / entry_price - 1.0
            directional_ret = raw_ret if p.side == "long" else -raw_ret
            label = int(directional_ret > (2 * fee_frac))  # net of round-trip fees
            self.training_rows.append((p.features, label))
        self.pending = still_pending

    def _maybe_refit(self):
        if GradientBoostingClassifier is None:
            return
        if len(self.training_rows) < self.cfg.min_training_samples:
            return
        self.rebalances_since_fit += 1
        if self.model is not None and self.rebalances_since_fit < self.cfg.refit_every_n_rebalances:
            return

        X = pd.DataFrame([r[0] for r in self.training_rows])
        y = np.array([r[1] for r in self.training_rows])
        self.feature_names = list(X.columns)
        X = X.fillna(X.median())

        model = GradientBoostingClassifier(
            n_estimators=self.cfg.n_estimators,
            max_depth=self.cfg.max_depth,
            random_state=42,
        )
        model.fit(X, y)
        self.model = model
        self.rebalances_since_fit = 0

    def filter_eligible(self, candidates: List[str], feat_df: pd.DataFrame) -> List[str]:
        if not self.cfg.enabled:
            return candidates
        self._maybe_refit()
        if self.model is None:
            return candidates  # not enough history yet -- no-op

        eligible = []
        for sym in candidates:
            if sym not in feat_df.index:
                eligible.append(sym)   # missing features -> don't penalize
                continue
            x = feat_df.loc[[sym], self.feature_names].fillna(0)
            prob = self.model.predict_proba(x)[0][1]
            if prob >= self.cfg.probability_threshold:
                eligible.append(sym)
        return eligible if eligible else candidates  # never let it zero-out the book
