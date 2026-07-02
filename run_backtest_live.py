#!/usr/bin/env python3
"""
Live Data Backtest Runner
Fetches real data from Blofin and runs backtest

Usage:
    1. Set up credentials:
       python config/secure_config.py
       
    2. Run backtest:
       python run_backtest_live.py --exchange blofin --days 30 --timeframe 15m
"""
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.scalping_strategy import AdvancedScalpingStrategy
from backtest.engine import Backtester
from config.settings import SCALPING_CONFIGS


def load_credentials(exchange: str):
    """Load credentials from .env file"""
    env_file = '.env'
    
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')
        return True
    return False


def fetch_data(exchange: str, symbol: str, timeframe: str, days: int):
    """Fetch data from specified exchange"""
    
    if exchange == 'blofin':
        from exchanges.blofin_data import BlofinDataFetcher
        
        fetcher = BlofinDataFetcher(
            api_key=os.getenv('BLOFIN_API_KEY'),
            api_secret=os.getenv('BLOFIN_API_SECRET'),
            passphrase=os.getenv('BLOFIN_PASSPHRASE')
        )
        
        # Test connection first
        if not fetcher.test_connection():
            return None
        
        # Map timeframe format
        tf_map = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1h': '1H', '4h': '4H', '1d': '1D'}
        interval = tf_map.get(timeframe, '15m')
        
        return fetcher.fetch_historical_data(symbol, interval, days)
    
    elif exchange == 'mexc':
        # MEXC implementation
        import ccxt
        
        mexc = ccxt.mexc({
            'apiKey': os.getenv('MEXC_API_KEY'),
            'secret': os.getenv('MEXC_API_SECRET'),
            'options': {'defaultType': 'swap'}
        })
        
        # Fetch OHLCV
        import pandas as pd
        from datetime import datetime, timedelta
        
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        ohlcv = mexc.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        return df
    
    else:
        print(f"Unsupported exchange: {exchange}")
        return None


def run_backtest(df, strategy_name: str = 'balanced', leverage: int = None, 
                 stop_loss: float = None, take_profit: float = None):
    """Run backtest with optimized parameters"""
    
    # Load optimized config
    try:
        from config.optimized_strategies import get_strategy, print_strategy_info
        config = get_strategy(strategy_name)
        print_strategy_info(config)
    except ImportError:
        # Fallback to default
        from config.settings import SCALPING_CONFIGS
        config = None
    
    if config:
        # Use optimized settings
        strategy = AdvancedScalpingStrategy(
            stoch_rsi_settings={
                'rsi_period': config.rsi_period,
                'stoch_period': config.stoch_period,
                'k_period': config.k_period,
                'd_period': config.d_period
            },
            macd_settings={
                'fast_period': config.macd_fast,
                'slow_period': config.macd_slow,
                'signal_period': config.macd_signal
            },
            oversold=config.oversold,
            overbought=config.overbought,
            use_trend_filter=config.use_trend_filter,
            use_volume_filter=config.use_volume_filter,
            require_macd_confirmation=config.use_macd_confirmation,
            min_confidence=config.min_confidence
        )
        
        # Use config values unless overridden
        actual_leverage = leverage if leverage else config.leverage
        actual_sl = stop_loss if stop_loss else config.stop_loss_pct
        actual_tp = take_profit if take_profit else config.take_profit_pct
    else:
        # Fallback strategy
        strategy = AdvancedScalpingStrategy(
            stoch_rsi_settings={'rsi_period': 10, 'stoch_period': 10, 'k_period': 3, 'd_period': 3},
            macd_settings={'fast_period': 5, 'slow_period': 13, 'signal_period': 6},
            oversold=20, overbought=80,
            use_trend_filter=True, use_volume_filter=True,
            require_macd_confirmation=True, min_confidence=50.0
        )
        actual_leverage = leverage if leverage else 10
        actual_sl = stop_loss if stop_loss else 1.5
        actual_tp = take_profit if take_profit else 3.0
    
    # Create backtester
    backtester = Backtester(
        initial_capital=10000,
        commission_rate=0.0006,
        slippage_pct=0.01,
        leverage=actual_leverage,
        capital_percentage=10,
        stop_loss_pct=actual_sl,
        take_profit_pct=actual_tp
    )
    
    # Run backtest
    result = backtester.run(df, strategy)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Backtest with live exchange data")
    parser.add_argument("--exchange", "-e", default="blofin",
                       choices=["blofin", "mexc"],
                       help="Exchange to fetch data from")
    parser.add_argument("--symbol", "-s", default="BTC-USDT",
                       help="Trading pair")
    parser.add_argument("--timeframe", "-t", default="15m",
                       choices=["1m", "5m", "15m", "30m", "1h", "1H"],
                       help="Candle timeframe")
    parser.add_argument("--days", "-d", type=int, default=30,
                       help="Days of history to fetch")
    parser.add_argument("--strategy", default="balanced",
                       choices=["balanced", "conservative", "aggressive", "trend_follower"],
                       help="Strategy preset to use")
    parser.add_argument("--leverage", "-l", type=int, default=None,
                       help="Trading leverage (overrides strategy default)")
    parser.add_argument("--stop-loss", type=float, default=None,
                       help="Stop loss percentage (overrides strategy default)")
    parser.add_argument("--take-profit", type=float, default=None,
                       help="Take profit percentage (overrides strategy default)")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("     LIVE DATA BACKTEST")
    print("="*60)
    
    # Load credentials
    if not load_credentials(args.exchange):
        print("\n[WARNING]  No .env file found!")
        print("   Run: python config/secure_config.py")
        print("   to set up your credentials securely.\n")
        return
    
    print(f"\nExchange:   {args.exchange.upper()}")
    print(f"Symbol:     {args.symbol}")
    print(f"Timeframe:  {args.timeframe}")
    print(f"Days:       {args.days}")
    print(f"Strategy:   {args.strategy}")
    
    # Fetch data
    print("\n" + "-"*60)
    print("Fetching data...")
    
    # Map timeframe for Blofin API
    tf = args.timeframe
    if tf == '1h':
        tf = '1H'
    
    df = fetch_data(args.exchange, args.symbol, tf, args.days)
    
    if df is None or df.empty:
        print("[ERROR] Failed to fetch data. Check your credentials and connection.")
        return
    
    print(f"\n[DATA] Data Summary:")
    print(f"   Period: {df.index[0]} to {df.index[-1]}")
    print(f"   Candles: {len(df)}")
    print(f"   Price Range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    
    # Run backtest
    print("\n" + "-"*60)
    print("Running backtest...")
    
    result = run_backtest(df, args.strategy, args.leverage, 
                         args.stop_loss, args.take_profit)
    
    # Print results
    result.print_summary()
    
    # Save trade log
    if result.trades:
        import pandas as pd
        trades_df = pd.DataFrame([t.to_dict() for t in result.trades])
        filename = f"trades_{args.exchange}_{args.symbol.replace('-', '')}_{args.timeframe}.csv"
        trades_df.to_csv(filename, index=False)
        print(f"\n[FILE] Trade log saved to: {filename}")
    
    return result


if __name__ == "__main__":
    main()
