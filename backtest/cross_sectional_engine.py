"""
Backtest engine for Cross-Sectional Momentum.
Consumes the SAME strategy, risk-stack, and (optional) ML selector classes
used live -- no parallel backtest-only reimplementation of any logic.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from strategies.cross_sectional_momentum import (
    CrossSectionalMomentumStrategy, StrategyParams, TargetBook
)
from strategies.cross_sectional_risk import (
    CrossSectionalRiskStack, RiskStackConfig, RiskStackState
)
from strategies.ml_pair_selector import MLPairSelector, MLFilterConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    strategy_params: StrategyParams = None
    risk_config: RiskStackConfig = field(default_factory=RiskStackConfig)
    ml_config: MLFilterConfig = field(default_factory=MLFilterConfig)  # enabled=False by default
    use_risk_stack: bool = True


@dataclass
class RebalanceRecord:
    timestamp: pd.Timestamp
    longs: List[str]
    shorts: List[str]
    book_pnl_pct: float
    flattened_by_profit_lock: bool
    legs_stopped: List[str] = field(default_factory=list)


class CrossSectionalBacktest:
    def __init__(self, config: BacktestConfig):
        self.cfg = config
        self.strategy = CrossSectionalMomentumStrategy(config.strategy_params)
        self.risk_stack = CrossSectionalRiskStack(config.risk_config)
        self.ml_selector = MLPairSelector(config.ml_config)

    def run(self, price_panel: pd.DataFrame) -> Dict:
        p = self.strategy.p
        equity = self.cfg.initial_capital
        equity_curve: List[Dict] = []
        rebalance_log: List[RebalanceRecord] = []
        book_return_history: List[float] = []

        state = RiskStackState()
        current_book: Optional[TargetBook] = None
        entry_prices: Dict[str, float] = {}
        book_notional_at_entry: float = 0.0
        last_rebalance_idx: Optional[int] = None
        fee_frac = self.strategy.fee_fraction()

        n = len(price_panel)
        start_idx = p.formation_window_hours + p.phase_offset_hours

        for idx in range(start_idx, n):
            ts = price_panel.index[idx]
            current_prices = price_panel.iloc[idx].to_dict()

            # resolve any ML training labels whose holding period has matured
            self.ml_selector.resolve_pending(idx, price_panel, fee_frac)

            book_pnl_pct = 0.0
            if current_book is not None and current_book.weights:
                leg_pnls = []
                for sym, w in current_book.weights.items():
                    ep, cp = entry_prices.get(sym), current_prices.get(sym)
                    if ep is None or cp is None or (isinstance(cp, float) and np.isnan(cp)):
                        continue
                    leg_ret = (cp / ep - 1.0) * np.sign(w)
                    leg_pnls.append(leg_ret * abs(w) * 2)
                book_pnl_pct = float(np.sum(leg_pnls)) if leg_pnls else 0.0

            bar_book_return = 0.0
            if equity_curve:
                bar_book_return = (equity - equity_curve[-1]['equity']) / equity_curve[-1]['equity']
            book_return_history.append(bar_book_return)

            if self.cfg.use_risk_stack:
                breaker_tripped = self.risk_stack.check_circuit_breaker(state, equity)
                if breaker_tripped and current_book is not None:
                    equity = self._flatten_book(current_book, entry_prices, current_prices,
                                                equity, book_notional_at_entry, fee_frac)
                    rebalance_log.append(RebalanceRecord(
                        timestamp=ts, longs=current_book.longs, shorts=current_book.shorts,
                        book_pnl_pct=book_pnl_pct, flattened_by_profit_lock=False,
                        flattened_by_circuit_breaker=True))
                    current_book = None
                    state.flattened_until_next_rebalance = True

            if self.cfg.use_risk_stack and current_book is not None and not state.flattened_until_next_rebalance:
                if self.risk_stack.update_profit_lock(state, book_pnl_pct):
                    equity = self._flatten_book(current_book, entry_prices, current_prices,
                                                 equity, book_notional_at_entry, fee_frac)
                    rebalance_log.append(RebalanceRecord(
                        timestamp=ts, longs=current_book.longs, shorts=current_book.shorts,
                        book_pnl_pct=book_pnl_pct, flattened_by_profit_lock=True))
                    current_book = None
                    state.flattened_until_next_rebalance = True

            if self.cfg.use_risk_stack and current_book is not None:
                legs_hit = self.risk_stack.legs_to_stop(state, current_prices)
                if legs_hit:
                    equity = self._stop_legs(current_book, legs_hit, entry_prices, current_prices,
                                              equity, book_notional_at_entry, fee_frac)
                    for sym in legs_hit:
                        current_book.weights.pop(sym, None)
                        state.legs.pop(sym, None)

            is_due = self.strategy.is_rebalance_due(last_rebalance_idx, idx)
            if is_due:
                if state.circuit_breaker_tripped:
                    # Breaker is tripped and has not been manually reset -- do NOT
                    # open new exposure. Skip this rebalance entirely and keep waiting.
                    logger.warning(f"Rebalance skipped at {ts}: circuit breaker active, "
                                    f"awaiting manual reset.")
                    last_rebalance_idx = idx  # still advance schedule so it doesn't fire every bar
                else:
                    new_book = self.strategy.build_target_book(
                        ts, price_panel, idx, ml_selector=self.ml_selector
                    )
                    if current_book is not None and current_book.weights:
                        equity = self._flatten_book(current_book, entry_prices, current_prices,
                                                    equity, book_notional_at_entry, fee_frac)
                        rebalance_log.append(RebalanceRecord(
                            timestamp=ts, longs=current_book.longs, shorts=current_book.shorts,
                            book_pnl_pct=book_pnl_pct, flattened_by_profit_lock=False))

                    self.risk_stack.reset_for_new_rebalance(state)
                    state.flattened_until_next_rebalance = False
                    last_rebalance_idx = idx

                    if new_book.weights:
                        vol_scalar = self.risk_stack.volatility_scalar(book_return_history) if self.cfg.use_risk_stack else 1.0
                        gross_notional = equity * p.base_leverage * vol_scalar
                        entry_prices = {sym: current_prices[sym] for sym in new_book.weights}
                        entry_fee = sum(abs(w) * gross_notional * fee_frac for w in new_book.weights.values())
                        equity -= entry_fee
                        book_notional_at_entry = gross_notional
                        self.risk_stack.register_legs(state, new_book.weights, entry_prices)
                        if self.ml_selector.cfg.enabled:
                            feat_df = self.ml_selector.compute_features(price_panel, idx, p.universe)
                            for sym, w in new_book.weights.items():
                                if sym in feat_df.index:
                                    self.ml_selector.register_pending(
                                        rebalance_idx=idx, resolve_idx=idx + p.rebalance_hours,
                                        symbol=sym, side="long" if w > 0 else "short",
                                        features=feat_df.loc[sym].to_dict())
                        current_book = new_book
                    else:
                        current_book = None

            equity_curve.append({'timestamp': ts, 'equity': equity})

        return self._summarize(equity_curve, rebalance_log)

    def _leg_pnl_dollars(self, weight, entry_price, exit_price, gross_notional):
        direction = np.sign(weight)
        return direction * (exit_price / entry_price - 1.0) * abs(weight) * gross_notional

    def _flatten_book(self, book, entry_prices, current_prices, equity, gross_notional, fee_frac):
        pnl, fees = 0.0, 0.0
        for sym, w in book.weights.items():
            ep, cp = entry_prices.get(sym), current_prices.get(sym)
            if ep is None or cp is None or (isinstance(cp, float) and np.isnan(cp)):
                continue
            pnl += self._leg_pnl_dollars(w, ep, cp, gross_notional)
            fees += abs(w) * gross_notional * fee_frac
        return equity + pnl - fees

    def _stop_legs(self, book, legs_hit, entry_prices, current_prices, equity, gross_notional, fee_frac):
        pnl, fees = 0.0, 0.0
        for sym in legs_hit:
            w = book.weights.get(sym)
            if w is None:
                continue
            ep, cp = entry_prices.get(sym), current_prices.get(sym)
            if ep is None or cp is None:
                continue
            pnl += self._leg_pnl_dollars(w, ep, cp, gross_notional)
            fees += abs(w) * gross_notional * fee_frac
            logger.warning(f"Per-leg disaster stop hit: {sym} at {cp} (entry {ep})")
        return equity + pnl - fees

    def _summarize(self, equity_curve, rebalance_log, price_panel, start_idx, p):
        eq_df = pd.DataFrame(equity_curve)
        if eq_df.empty:
            return {'error': 'no bars processed'}

        eq_df['peak'] = eq_df['equity'].cummax()
        eq_df['drawdown'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
        max_dd = float(abs(eq_df['drawdown'].min()))

        returns = eq_df['equity'].pct_change().dropna()
        sharpe = float(returns.mean() / returns.std() * np.sqrt(24 * 365)) if returns.std() > 0 else 0.0
        net_return = float(eq_df['equity'].iloc[-1] / eq_df['equity'].iloc[0] - 1.0)

        n_bars_tradeable = len(price_panel) - start_idx
        expected_rebalances = int(n_bars_tradeable / p.rebalance_hours)
        n_breaker_flattens = sum(1 for r in rebalance_log if r.flattened_by_circuit_breaker)
        n_profit_lock_flattens = sum(1 for r in rebalance_log if r.flattened_by_profit_lock)
        n_normal_rebalances = len(rebalance_log) - n_breaker_flattens - n_profit_lock_flattens

        logger.info(f"Expected rebalances: ~{expected_rebalances} | "
                    f"Logged events: {len(rebalance_log)} "
                    f"(normal={n_normal_rebalances}, profit_lock={n_profit_lock_flattens}, "
                    f"circuit_breaker={n_breaker_flattens})")
        if n_breaker_flattens > 0:
            logger.warning(f"Circuit breaker tripped {n_breaker_flattens}x during this run and "
                            f"required manual reset each time -- book was likely flat for extended "
                            f"periods. Do not compare Sharpe/return directly to a run with 0 trips.")

        return {
            'equity_curve': eq_df[['timestamp', 'equity', 'drawdown']],
            'rebalances': rebalance_log,
            'n_rebalances': len(rebalance_log),
            'n_normal_rebalances': n_normal_rebalances,
            'n_profit_lock_flattens': n_profit_lock_flattens,
            'n_circuit_breaker_flattens': n_breaker_flattens,
            'expected_rebalances': expected_rebalances,
            'net_return': net_return,
            'max_drawdown': max_dd,
            'sharpe': sharpe,
            'final_equity': float(eq_df['equity'].iloc[-1]),
        }


def rebalance_phase_sweep(price_panel, base_params, risk_config,
                           ml_config=None, offsets_hours=None) -> pd.DataFrame:
    """Re-runs the backtest at several rebalance-phase offsets to check the
    edge isn't an artifact of one arbitrary rebalance clock. Run this with
    ml_config passed in both enabled and disabled forms to check whether
    the ML filter is phase-robust too, not just the base strategy."""
    if offsets_hours is None:
        offsets_hours = [0, 12, 24, 36, 48, 60]
    if ml_config is None:
        ml_config = MLFilterConfig()  # disabled

    rows = []
    for off in offsets_hours:
        params = StrategyParams(**{**base_params.__dict__, 'phase_offset_hours': off})
        bt = CrossSectionalBacktest(BacktestConfig(
            initial_capital=10_000.0,
            strategy_params=params,
            risk_config=risk_config,
            ml_config=ml_config,
            use_risk_stack=True,
        ))
        result = bt.run(price_panel)
        rows.append({
            'offset_hours': off,
            'sharpe': result.get('sharpe'),
            'net_return': result.get('net_return'),
            'max_drawdown': result.get('max_drawdown'),
            'n_rebalances': result.get('n_rebalances'),
        })
    return pd.DataFrame(rows)
