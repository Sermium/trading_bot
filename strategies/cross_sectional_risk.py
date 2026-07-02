"""
strategies/cross_sectional_risk.py

Risk Stack for Cross-Sectional Momentum
-----------------------------------------
Four independent, layered risk controls:
1. Book-level trailing profit lock  — arms at +2% book P&L, gives back 2%
   from peak -> flattens book, sits out until next rebalance.
2. Per-leg disaster stops           — reduce-only stop 20% from entry, per leg.
3. Volatility targeting             — scales gross exposure to realized book vol.
4. Account-level circuit breaker    — hard drawdown limit, flattens account,
   halts new exposure until a manual reset.

Same code path for live and backtest -- no strategy logic lives here, only
sizing and force-close decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RiskStackConfig:
    profit_lock_arm_pct: float = 0.02
    profit_lock_giveback_pct: float = 0.02
    per_leg_stop_pct: float = 0.20
    target_book_vol_annualized: float = 0.30
    vol_lookback_hours: int = 30 * 24
    min_vol_scalar: float = 0.25
    max_vol_scalar: float = 1.5
    account_max_drawdown_pct: float = 0.20


@dataclass
class LegState:
    symbol: str
    side: str
    entry_price: float
    weight: float


@dataclass
class RiskStackState:
    book_peak_equity: float = 0.0
    book_pnl_pct_since_rebalance: float = 0.0
    profit_lock_armed: bool = False
    flattened_until_next_rebalance: bool = False
    account_peak_equity: Optional[float] = None
    circuit_breaker_tripped: bool = False
    legs: Dict[str, LegState] = field(default_factory=dict)


class CrossSectionalRiskStack:
    def __init__(self, config: RiskStackConfig):
        self.cfg = config

    def check_circuit_breaker(self, state: RiskStackState, account_equity: float) -> bool:
        if state.account_peak_equity is None:
            state.account_peak_equity = account_equity
        state.account_peak_equity = max(state.account_peak_equity, account_equity)

        if state.circuit_breaker_tripped:
            return True

        drawdown = (state.account_peak_equity - account_equity) / state.account_peak_equity
        if drawdown >= self.cfg.account_max_drawdown_pct:
            state.circuit_breaker_tripped = True
            logger.warning(f"CIRCUIT BREAKER tripped: drawdown {drawdown:.2%} "
                            f">= {self.cfg.account_max_drawdown_pct:.2%}. Manual reset required.")
            return True
        return False

    def manual_reset_circuit_breaker(self, state: RiskStackState, current_equity: float):
        state.circuit_breaker_tripped = False
        state.account_peak_equity = current_equity
        logger.info("Circuit breaker manually reset.")

    def update_profit_lock(self, state: RiskStackState, book_pnl_pct: float) -> bool:
        state.book_pnl_pct_since_rebalance = book_pnl_pct
        state.book_peak_equity = max(state.book_peak_equity, book_pnl_pct)

        if not state.profit_lock_armed and book_pnl_pct >= self.cfg.profit_lock_arm_pct:
            state.profit_lock_armed = True
            logger.info(f"Profit lock ARMED at book P&L {book_pnl_pct:.2%}")

        if state.profit_lock_armed:
            giveback = state.book_peak_equity - book_pnl_pct
            if giveback >= self.cfg.profit_lock_giveback_pct:
                logger.info(f"Profit lock TRIGGERED: peak {state.book_peak_equity:.2%}, "
                            f"now {book_pnl_pct:.2%}, giveback {giveback:.2%}")
                return True
        return False

    def reset_for_new_rebalance(self, state: RiskStackState):
        state.book_peak_equity = 0.0
        state.book_pnl_pct_since_rebalance = 0.0
        state.profit_lock_armed = False
        state.flattened_until_next_rebalance = False
        state.legs = {}

    def register_legs(self, state: RiskStackState, weights: Dict[str, float],
                       entry_prices: Dict[str, float]):
        state.legs = {
            sym: LegState(symbol=sym, side="long" if w > 0 else "short",
                          entry_price=entry_prices[sym], weight=w)
            for sym, w in weights.items()
        }

    def legs_to_stop(self, state: RiskStackState, current_prices: Dict[str, float]) -> List[str]:
        triggered = []
        for sym, leg in state.legs.items():
            price = current_prices.get(sym)
            if price is None:
                continue
            adverse_move = ((leg.entry_price - price) / leg.entry_price if leg.side == "long"
                             else (price - leg.entry_price) / leg.entry_price)
            if adverse_move >= self.cfg.per_leg_stop_pct:
                triggered.append(sym)
        return triggered

    def volatility_scalar(self, book_return_history: List[float]) -> float:
        lookback = self.cfg.vol_lookback_hours
        hist = book_return_history[-lookback:]
        if len(hist) < 24:
            return 1.0
        realized_vol = np.std(hist) * np.sqrt(24 * 365)
        if realized_vol <= 1e-9:
            return self.cfg.max_vol_scalar
        scalar = self.cfg.target_book_vol_annualized / realized_vol
        return float(np.clip(scalar, self.cfg.min_vol_scalar, self.cfg.max_vol_scalar))
