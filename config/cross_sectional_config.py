"""
Cross-Sectional Momentum Configuration
----------------------------------------
Replaces config/profitable_config.py, config/optimized_strategies.py, and
config/REAL_PROFITABLE_CONFIG.py for this strategy. Those files tuned a
single-symbol scalper to one historical path; this strategy is deliberately
validated out-of-sample and across rebalance-phase offsets instead of
optimized to a single backtest run.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class CrossSectionalConfig:
    # Universe: base assets only. Exchange-specific instrument IDs are
    # resolved at fetch/order time via exchanges/multi_symbol_data.py
    universe: List[str] = field(default_factory=lambda: [
        "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX",
        "LINK", "DOT", "ATOM", "INJ", "SUI", "ARB", "OP", "NEAR",
        "AAVE", "UNI",
    ])

    formation_window_days: int = 14
    rebalance_days: int = 3
    n_long: int = 3
    n_short: int = 3

    taker_fee_bps: float = 4.5
    base_leverage: float = 2.0

    # Risk stack
    profit_lock_arm_pct: float = 0.02
    profit_lock_giveback_pct: float = 0.02
    per_leg_stop_pct: float = 0.20
    target_book_vol_annualized: float = 0.30
    vol_lookback_days: int = 30
    account_max_drawdown_pct: float = 0.20

    # Data
    bar_timeframe: str = "1h"          # hourly bars for formation + risk checks
    quote_asset: str = "USDT"


DEFAULT_CONFIG = CrossSectionalConfig()
