"""
Trading Bot Configuration Settings
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class Timeframe(Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"


class Exchange(Enum):
    BLOFIN = "blofin"
    MEXC = "mexc"
    HYPERLIQUID = "hyperliquid"


@dataclass
class StochRSISettings:
    """StochRSI indicator settings"""
    rsi_period: int = 14
    stoch_period: int = 14
    k_period: int = 3
    d_period: int = 3
    oversold: float = 20.0
    overbought: float = 80.0


@dataclass
class MACDSettings:
    """MACD indicator settings"""
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9


@dataclass
class RiskSettings:
    """Risk management settings"""
    leverage: int = 10
    capital_percentage: float = 10.0  # % of total capital per trade
    stop_loss_pct: float = 0.5  # Stop loss percentage
    take_profit_pct: float = 1.0  # Take profit percentage
    max_positions: int = 1
    max_daily_trades: int = 20
    max_daily_loss_pct: float = 5.0  # Max daily loss as % of capital


@dataclass 
class TradingSettings:
    """Main trading configuration"""
    symbol: str = "BTC/USDT:USDT"
    timeframe: Timeframe = Timeframe.M5
    exchange: Exchange = Exchange.MEXC
    
    stoch_rsi: StochRSISettings = field(default_factory=StochRSISettings)
    macd: MACDSettings = field(default_factory=MACDSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    
    # Entry conditions
    require_macd_confirmation: bool = True
    require_stoch_confirmation: bool = True
    
    # Additional filters
    use_volume_filter: bool = True
    volume_threshold: float = 1.5  # Volume must be 1.5x average
    
    use_trend_filter: bool = True
    trend_ema_period: int = 50


@dataclass
class BacktestSettings:
    """Backtesting configuration"""
    initial_capital: float = 10000.0
    commission_rate: float = 0.0006  # 0.06% taker fee
    slippage_pct: float = 0.01  # 0.01% slippage
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# Default configurations for different timeframes
SCALPING_CONFIGS = {
    "1m": TradingSettings(
        timeframe=Timeframe.M1,
        stoch_rsi=StochRSISettings(
            rsi_period=7,
            stoch_period=7,
            k_period=3,
            d_period=3,
            oversold=15.0,
            overbought=85.0
        ),
        macd=MACDSettings(fast_period=6, slow_period=13, signal_period=4),
        risk=RiskSettings(
            stop_loss_pct=0.3,
            take_profit_pct=0.5,
            max_daily_trades=50
        )
    ),
    "5m": TradingSettings(
        timeframe=Timeframe.M5,
        stoch_rsi=StochRSISettings(
            rsi_period=10,
            stoch_period=10,
            k_period=3,
            d_period=3,
            oversold=18.0,
            overbought=82.0
        ),
        macd=MACDSettings(fast_period=8, slow_period=17, signal_period=6),
        risk=RiskSettings(
            stop_loss_pct=0.4,
            take_profit_pct=0.8,
            max_daily_trades=30
        )
    ),
    "15m": TradingSettings(
        timeframe=Timeframe.M15,
        stoch_rsi=StochRSISettings(
            rsi_period=14,
            stoch_period=14,
            k_period=3,
            d_period=3,
            oversold=20.0,
            overbought=80.0
        ),
        macd=MACDSettings(fast_period=12, slow_period=26, signal_period=9),
        risk=RiskSettings(
            stop_loss_pct=0.5,
            take_profit_pct=1.0,
            max_daily_trades=15
        )
    )
}
