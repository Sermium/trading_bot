# Backtest package
from .engine import Backtester, BacktestResult, Trade, Position, PositionSide
from .trailing_stop import (
    TrailingStopBacktester,
    TrailingStopConfig,
    TRAILING_CONFIGS,
    get_config
)
