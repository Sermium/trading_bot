#!/usr/bin/env python3
"""
Run Trailing Stop Strategy Backtest

This is the winning configuration:
- 50x Leverage
- 15m Timeframe  
- Trailing Stop (locks in profits)
- Progressive Sizing (scales up on wins)

Usage:
    python run_trailing_strategy.py --days 30 --config tight
    python run_trailing_strategy.py --exchange blofin --days 30
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.scalping_strategy import AdvancedScalpingStrategy
from backtest.trailing_stop import (
    TrailingStopBacktester, 
    TrailingStopConfig,
    TRAILING_CONFIGS,
    get_config
)


def load_env():
    """Load environment variables from .env file"""
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def fetch_live_data(exchange: str, symbol: str, timeframe: str, days: int):
    """Fetch live data from exchange"""
    if exchange == 'blofin':
        from exchanges.blofin_data import BlofinDataFetcher
        fetcher = BlofinDataFetcher()
        
        if not fetcher.test_connection():
            print("[ERROR] Could not connect to Blofin")
            return None
        
        return fetcher.fetch_historical_data(symbol, timeframe, days)
    
    return None


def generate_test_data(days: int, timeframe: str):
    """Generate synthetic test data"""
    from utils.realistic_data import generate_btc_pattern_data
    
    # Use crash_recovery pattern as it has good volatility
    return generate_btc_pattern_data(
        pattern="crash_recovery",
        days=days,
        timeframe=timeframe
    )


def create_strategy():
    """Create the optimized strategy"""
    return AdvancedScalpingStrategy(
        stoch_rsi_settings={
            'rsi_period': 7,
            'stoch_period': 7,
            'k_period': 3,
            'd_period': 3
        },
        macd_settings={
            'fast_period': 5,
            'slow_period': 13,
            'signal_period': 6
        },
        oversold=20,
        overbought=80,
        use_trend_filter=True,
        use_volume_filter=False,
        require_macd_confirmation=True,
        min_confidence=45.0
    )


def main():
    parser = argparse.ArgumentParser(
        description="Run Trailing Stop Strategy Backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_trailing_strategy.py --days 30
  python run_trailing_strategy.py --config medium --days 60
  python run_trailing_strategy.py --exchange blofin --days 30
  python run_trailing_strategy.py --leverage 20 --sl 0.5 --tp 2.0

Available configs: tight, medium, wide, conservative
        """
    )
    
    # Data source
    parser.add_argument("--exchange", "-e", default=None,
                       help="Exchange to fetch data from (blofin)")
    parser.add_argument("--symbol", "-s", default="BTC-USDT",
                       help="Trading pair")
    parser.add_argument("--timeframe", "-t", default="15m",
                       help="Candle timeframe")
    parser.add_argument("--days", "-d", type=int, default=30,
                       help="Days of data")
    
    # Strategy config
    parser.add_argument("--config", "-c", default="tight",
                       choices=["tight", "medium", "wide", "conservative"],
                       help="Pre-defined configuration")
    
    # Custom parameters (override config)
    parser.add_argument("--leverage", type=int, default=None,
                       help="Leverage (default: 50)")
    parser.add_argument("--sl", type=float, default=None,
                       help="Initial stop loss %")
    parser.add_argument("--tp", type=float, default=None,
                       help="Take profit %")
    parser.add_argument("--trail-activate", type=float, default=None,
                       help="Trailing activation % (profit to activate)")
    parser.add_argument("--trail-distance", type=float, default=None,
                       help="Trailing distance %")
    parser.add_argument("--base-size", type=float, default=None,
                       help="Base position size %")
    parser.add_argument("--max-size", type=float, default=None,
                       help="Max position size %")
    parser.add_argument("--capital", type=float, default=10000,
                       help="Initial capital")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("   TRAILING STOP STRATEGY")
    print("   50x Leverage | Progressive Sizing | Smart Exits")
    print("=" * 70)
    
    # Load config
    config = get_config(args.config)
    
    # Override with custom parameters
    if args.leverage:
        config.leverage = args.leverage
    if args.sl:
        config.initial_stop_pct = args.sl
    if args.tp:
        config.take_profit_pct = args.tp
    if args.trail_activate:
        config.trailing_activation_pct = args.trail_activate
    if args.trail_distance:
        config.trailing_distance_pct = args.trail_distance
    if args.base_size:
        config.base_capital_pct = args.base_size
    if args.max_size:
        config.max_capital_pct = args.max_size
    config.initial_capital = args.capital
    
    # Print config
    print(f"\n[CONFIG] {args.config.upper()}")
    print(f"  Leverage:           {config.leverage}x")
    print(f"  Initial Stop:       {config.initial_stop_pct}%")
    print(f"  Take Profit:        {config.take_profit_pct}%")
    print(f"  Trail Activation:   {config.trailing_activation_pct}%")
    print(f"  Trail Distance:     {config.trailing_distance_pct}%")
    print(f"  Position Size:      {config.base_capital_pct}% → {config.max_capital_pct}%")
    print(f"  Initial Capital:    ${config.initial_capital:,.2f}")
    
    # Get data
    print(f"\n[DATA] Fetching {args.days} days of {args.timeframe} data...")
    
    if args.exchange:
        load_env()
        df = fetch_live_data(args.exchange, args.symbol, args.timeframe, args.days)
        if df is None:
            print("[ERROR] Failed to fetch live data, using synthetic data")
            df = generate_test_data(args.days, args.timeframe)
    else:
        df = generate_test_data(args.days, args.timeframe)
    
    if df is None or df.empty:
        print("[ERROR] No data available")
        return
    
    print(f"  Period: {df.index[0]} to {df.index[-1]}")
    print(f"  Candles: {len(df)}")
    print(f"  Price Range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    
    # Create strategy and backtester
    print(f"\n[RUN] Running backtest...")
    
    strategy = create_strategy()
    backtester = TrailingStopBacktester(config)
    
    result = backtester.run(df, strategy)
    
    # Print results
    result.print_summary()
    
    # Save trades to CSV
    if result.trades:
        import pandas as pd
        trades_df = pd.DataFrame([t.to_dict() for t in result.trades])
        filename = f"trades_trailing_{args.timeframe}_{args.days}d.csv"
        trades_df.to_csv(filename, index=False)
        print(f"\n[FILE] Trade log saved to: {filename}")
    
    return result


if __name__ == "__main__":
    main()
