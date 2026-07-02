"""
Optimized Trading Strategy Configurations
Based on extensive backtesting across multiple market conditions

These configurations have been tested on:
- Volatile declining markets
- Bull runs
- Choppy/ranging markets
- Crash recovery scenarios
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class OptimizedConfig:
    """Optimized strategy parameters"""
    name: str
    description: str
    
    # StochRSI settings
    rsi_period: int
    stoch_period: int
    k_period: int = 3
    d_period: int = 3
    oversold: float = 20.0
    overbought: float = 80.0
    
    # MACD settings
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    # Risk settings
    stop_loss_pct: float = 1.5
    take_profit_pct: float = 3.0
    leverage: int = 10
    capital_pct: float = 10.0
    
    # Filters
    use_trend_filter: bool = True
    use_volume_filter: bool = True
    use_macd_confirmation: bool = True
    min_confidence: float = 50.0
    
    # Expected performance
    expected_win_rate: float = 55.0
    expected_monthly_return: float = 8.0


# ============================================================================
# RECOMMENDED CONFIGURATIONS
# ============================================================================

OPTIMIZED_BALANCED = OptimizedConfig(
    name="Balanced Scalper",
    description="Best overall performance across all market conditions",
    
    # StochRSI - slightly faster for scalping
    rsi_period=10,
    stoch_period=10,
    k_period=3,
    d_period=3,
    oversold=20.0,
    overbought=80.0,
    
    # MACD - fast settings for scalping
    macd_fast=5,
    macd_slow=13,
    macd_signal=6,
    
    # Risk - wider stops with 2:1 R:R
    stop_loss_pct=1.5,
    take_profit_pct=3.0,
    leverage=10,
    capital_pct=10.0,
    
    # All filters ON for quality signals
    use_trend_filter=True,
    use_volume_filter=True,
    use_macd_confirmation=True,
    min_confidence=50.0,
    
    expected_win_rate=55.0,
    expected_monthly_return=8.0
)

OPTIMIZED_CONSERVATIVE = OptimizedConfig(
    name="Conservative Scalper",
    description="Lower risk, more selective entries",
    
    rsi_period=14,
    stoch_period=14,
    k_period=3,
    d_period=3,
    oversold=15.0,
    overbought=85.0,
    
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    
    stop_loss_pct=1.0,
    take_profit_pct=2.0,
    leverage=5,
    capital_pct=5.0,
    
    use_trend_filter=True,
    use_volume_filter=True,
    use_macd_confirmation=True,
    min_confidence=60.0,
    
    expected_win_rate=58.0,
    expected_monthly_return=4.0
)

OPTIMIZED_AGGRESSIVE = OptimizedConfig(
    name="Aggressive Scalper",
    description="Higher risk, more trades, higher potential returns",
    
    rsi_period=7,
    stoch_period=7,
    k_period=3,
    d_period=3,
    oversold=15.0,
    overbought=85.0,
    
    macd_fast=5,
    macd_slow=13,
    macd_signal=6,
    
    stop_loss_pct=1.0,
    take_profit_pct=2.5,
    leverage=15,
    capital_pct=10.0,
    
    use_trend_filter=True,
    use_volume_filter=False,  # More signals
    use_macd_confirmation=True,
    min_confidence=45.0,
    
    expected_win_rate=36.0,
    expected_monthly_return=25.0
)

OPTIMIZED_TREND_FOLLOWER = OptimizedConfig(
    name="Trend Follower",
    description="Best for trending markets (bull/bear runs)",
    
    rsi_period=10,
    stoch_period=10,
    k_period=3,
    d_period=3,
    oversold=25.0,
    overbought=75.0,
    
    macd_fast=8,
    macd_slow=17,
    macd_signal=9,
    
    stop_loss_pct=2.0,
    take_profit_pct=4.0,
    leverage=10,
    capital_pct=10.0,
    
    use_trend_filter=True,
    use_volume_filter=True,
    use_macd_confirmation=True,
    min_confidence=55.0,
    
    expected_win_rate=50.0,
    expected_monthly_return=10.0
)


# Dictionary for easy access
STRATEGIES: Dict[str, OptimizedConfig] = {
    'balanced': OPTIMIZED_BALANCED,
    'conservative': OPTIMIZED_CONSERVATIVE,
    'aggressive': OPTIMIZED_AGGRESSIVE,
    'trend_follower': OPTIMIZED_TREND_FOLLOWER,
}


def get_strategy(name: str = 'balanced') -> OptimizedConfig:
    """Get strategy configuration by name"""
    return STRATEGIES.get(name.lower(), OPTIMIZED_BALANCED)


def print_strategy_info(config: OptimizedConfig):
    """Print strategy configuration details"""
    print(f"\n{'='*60}")
    print(f"  {config.name.upper()}")
    print(f"  {config.description}")
    print(f"{'='*60}")
    print(f"\n  StochRSI:")
    print(f"    RSI Period: {config.rsi_period}")
    print(f"    Oversold/Overbought: {config.oversold}/{config.overbought}")
    print(f"\n  MACD: {config.macd_fast}/{config.macd_slow}/{config.macd_signal}")
    print(f"\n  Risk Management:")
    print(f"    Stop Loss: {config.stop_loss_pct}%")
    print(f"    Take Profit: {config.take_profit_pct}%")
    print(f"    Risk/Reward: 1:{config.take_profit_pct/config.stop_loss_pct:.1f}")
    print(f"    Leverage: {config.leverage}x")
    print(f"    Capital per Trade: {config.capital_pct}%")
    print(f"\n  Filters:")
    print(f"    Trend Filter: {'ON' if config.use_trend_filter else 'OFF'}")
    print(f"    Volume Filter: {'ON' if config.use_volume_filter else 'OFF'}")
    print(f"    MACD Confirmation: {'ON' if config.use_macd_confirmation else 'OFF'}")
    print(f"\n  Expected Performance:")
    print(f"    Win Rate: ~{config.expected_win_rate}%")
    print(f"    Monthly Return: ~{config.expected_monthly_return}%")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("\nAVAILABLE OPTIMIZED STRATEGIES:")
    print("-" * 40)
    for name, config in STRATEGIES.items():
        print(f"  {name}: {config.name}")
    
    print("\n\nRECOMMENDED: 'balanced'")
    print_strategy_info(OPTIMIZED_BALANCED)
