#!/usr/bin/env python3
"""
Backtest Runner Script
Run backtests with various configurations and generate reports
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.scalping_strategy import ScalpingStrategy, AdvancedScalpingStrategy
from backtest.engine import Backtester, BacktestResult
from config.settings import SCALPING_CONFIGS, TradingSettings


def fetch_historical_data(symbol: str = "BTCUSDT", 
                          timeframe: str = "5m",
                          days: int = 30) -> pd.DataFrame:
    """
    Fetch historical data from Binance public API (no API key needed)
    
    Args:
        symbol: Trading pair
        timeframe: Candle timeframe
        days: Number of days of history
        
    Returns:
        DataFrame with OHLCV data
    """
    import requests
    
    # Binance public klines endpoint
    url = "https://api.binance.com/api/v3/klines"
    
    # Calculate timestamps
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    
    # Map timeframe
    tf_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", 
        "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d"
    }
    
    all_data = []
    current_start = start_time
    
    print(f"Fetching {days} days of {timeframe} data for {symbol}...")
    
    while current_start < end_time:
        params = {
            "symbol": symbol,
            "interval": tf_map.get(timeframe, "5m"),
            "startTime": current_start,
            "endTime": end_time,
            "limit": 1000
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if not data or isinstance(data, dict):
                break
            
            all_data.extend(data)
            
            if len(data) < 1000:
                break
            
            # Move to next batch
            current_start = data[-1][0] + 1
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
    
    if not all_data:
        print("No data received!")
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Convert to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    df = df[['open', 'high', 'low', 'close', 'volume']]
    
    print(f"Loaded {len(df)} candles from {df.index[0]} to {df.index[-1]}")
    
    return df


def generate_synthetic_data(days: int = 30, timeframe: str = "5m") -> pd.DataFrame:
    """
    Generate synthetic BTC-like price data for testing
    Uses geometric Brownian motion with mean reversion
    """
    # Calculate number of candles
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
    minutes = tf_minutes.get(timeframe, 5)
    num_candles = (days * 24 * 60) // minutes
    
    # Parameters for BTC-like movement
    initial_price = 95000  # Starting price
    daily_volatility = 0.02  # 2% daily volatility
    candle_volatility = daily_volatility / np.sqrt(1440 / minutes)
    
    # Generate returns
    np.random.seed(42)
    returns = np.random.normal(0.0001, candle_volatility, num_candles)
    
    # Add some trends and reversions
    trend = np.sin(np.linspace(0, 4 * np.pi, num_candles)) * 0.0005
    returns = returns + trend
    
    # Generate close prices
    closes = initial_price * np.cumprod(1 + returns)
    
    # Generate OHLC from closes
    data = []
    for i, close in enumerate(closes):
        noise = np.random.uniform(0.001, 0.003)
        high = close * (1 + noise)
        low = close * (1 - noise)
        open_price = closes[i-1] if i > 0 else initial_price
        
        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        volume = np.random.uniform(100, 1000) * (1 + abs(returns[i]) * 50)
        
        data.append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    # Create DataFrame
    start_date = datetime.now() - timedelta(days=days)
    timestamps = pd.date_range(start=start_date, periods=num_candles, freq=f"{minutes}min")
    
    df = pd.DataFrame(data, index=timestamps)
    
    print(f"Generated {len(df)} synthetic candles")
    
    return df


def run_single_backtest(df: pd.DataFrame, 
                       config_name: str = "5m",
                       initial_capital: float = 10000,
                       leverage: int = 10,
                       stop_loss_pct: float = 0.5,
                       take_profit_pct: float = 1.0) -> BacktestResult:
    """Run a single backtest with given parameters"""
    
    # Get base config
    if config_name in SCALPING_CONFIGS:
        settings = SCALPING_CONFIGS[config_name]
    else:
        settings = SCALPING_CONFIGS["5m"]
    
    # Create strategy
    strategy = AdvancedScalpingStrategy(
        stoch_rsi_settings={
            'rsi_period': settings.stoch_rsi.rsi_period,
            'stoch_period': settings.stoch_rsi.stoch_period,
            'k_period': settings.stoch_rsi.k_period,
            'd_period': settings.stoch_rsi.d_period
        },
        macd_settings={
            'fast_period': settings.macd.fast_period,
            'slow_period': settings.macd.slow_period,
            'signal_period': settings.macd.signal_period
        },
        oversold=settings.stoch_rsi.oversold,
        overbought=settings.stoch_rsi.overbought,
        use_trend_filter=settings.use_trend_filter,
        use_volume_filter=settings.use_volume_filter,
        require_macd_confirmation=settings.require_macd_confirmation,
        min_confidence=60.0
    )
    
    # Create backtester
    backtester = Backtester(
        initial_capital=initial_capital,
        commission_rate=0.0006,  # 0.06% taker fee
        slippage_pct=0.01,
        leverage=leverage,
        capital_percentage=10.0,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct
    )
    
    # Run backtest
    result = backtester.run(df, strategy)
    
    return result


def run_optimization(df: pd.DataFrame, timeframe: str = "5m") -> dict:
    """
    Run parameter optimization
    Tests different combinations and returns best parameters
    """
    print("\n" + "="*60)
    print("PARAMETER OPTIMIZATION")
    print("="*60)
    
    best_result = None
    best_params = None
    best_score = -float('inf')
    
    results = []
    
    # Parameter grid
    param_grid = {
        'stop_loss_pct': [0.3, 0.5, 0.7],
        'take_profit_pct': [0.5, 0.8, 1.0, 1.5],
        'leverage': [5, 10, 15],
        'oversold': [15, 20, 25],
        'overbought': [75, 80, 85]
    }
    
    total_combinations = (len(param_grid['stop_loss_pct']) * 
                         len(param_grid['take_profit_pct']) * 
                         len(param_grid['leverage']))
    
    print(f"Testing {total_combinations} parameter combinations...")
    
    count = 0
    for sl in param_grid['stop_loss_pct']:
        for tp in param_grid['take_profit_pct']:
            for lev in param_grid['leverage']:
                count += 1
                
                # Create strategy with custom parameters
                strategy = AdvancedScalpingStrategy(
                    stoch_rsi_settings={
                        'rsi_period': 10,
                        'stoch_period': 10,
                        'k_period': 3,
                        'd_period': 3
                    },
                    macd_settings={
                        'fast_period': 8,
                        'slow_period': 17,
                        'signal_period': 6
                    },
                    oversold=20,
                    overbought=80,
                    use_trend_filter=True,
                    use_volume_filter=True,
                    require_macd_confirmation=True,
                    min_confidence=60.0
                )
                
                backtester = Backtester(
                    initial_capital=10000,
                    leverage=lev,
                    stop_loss_pct=sl,
                    take_profit_pct=tp
                )
                
                result = backtester.run(df, strategy)
                
                # Score: Optimize for profit factor * win rate with drawdown penalty
                if result.total_trades > 0:
                    score = (result.profit_factor * (result.win_rate / 100) * 
                            (1 - result.max_drawdown_pct / 100))
                else:
                    score = 0
                
                results.append({
                    'sl': sl,
                    'tp': tp,
                    'leverage': lev,
                    'win_rate': result.win_rate,
                    'profit_factor': result.profit_factor,
                    'net_pnl': result.net_pnl,
                    'max_dd': result.max_drawdown_pct,
                    'trades': result.total_trades,
                    'score': score
                })
                
                if score > best_score:
                    best_score = score
                    best_result = result
                    best_params = {'sl': sl, 'tp': tp, 'leverage': lev}
                
                print(f"\r  Progress: {count}/{total_combinations}", end="")
    
    print("\n")
    
    # Sort results by score
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('score', ascending=False)
    
    print("Top 5 Parameter Combinations:")
    print("-" * 80)
    print(results_df.head(10).to_string(index=False))
    print("-" * 80)
    
    return {
        'best_params': best_params,
        'best_result': best_result,
        'all_results': results_df
    }


def generate_report(result: BacktestResult, 
                   output_file: str = None) -> str:
    """Generate detailed backtest report"""
    
    report = []
    report.append("=" * 70)
    report.append("                    BACKTEST PERFORMANCE REPORT")
    report.append("=" * 70)
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Summary
    report.append("-" * 70)
    report.append("EXECUTIVE SUMMARY")
    report.append("-" * 70)
    report.append(f"Initial Capital:      ${result.initial_capital:,.2f}")
    report.append(f"Final Capital:        ${result.final_capital:,.2f}")
    report.append(f"Net P&L:              ${result.net_pnl:,.2f} ({result.return_pct:+.2f}%)")
    report.append(f"Total Trades:         {result.total_trades}")
    report.append(f"Win Rate:             {result.win_rate:.1f}%")
    
    # Performance Metrics
    report.append("\n" + "-" * 70)
    report.append("PERFORMANCE METRICS")
    report.append("-" * 70)
    report.append(f"Profit Factor:        {result.profit_factor:.2f}")
    report.append(f"Sharpe Ratio:         {result.sharpe_ratio:.3f}")
    report.append(f"Sortino Ratio:        {result.sortino_ratio:.3f}")
    report.append(f"Max Drawdown:         ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.2f}%)")
    
    # Trade Statistics
    report.append("\n" + "-" * 70)
    report.append("TRADE STATISTICS")
    report.append("-" * 70)
    report.append(f"Winning Trades:       {result.winning_trades}")
    report.append(f"Losing Trades:        {result.losing_trades}")
    report.append(f"Average Win:          ${result.avg_win:,.2f}")
    report.append(f"Average Loss:         ${result.avg_loss:,.2f}")
    report.append(f"Average Trade:        ${result.avg_trade:,.2f}")
    report.append(f"Best Trade:           ${result.best_trade:,.2f}")
    report.append(f"Worst Trade:          ${result.worst_trade:,.2f}")
    report.append(f"Avg Holding Time:     {result.avg_holding_time}")
    report.append(f"Total Fees:           ${result.total_fees:,.2f}")
    
    # Trade Breakdown
    if result.trades:
        report.append("\n" + "-" * 70)
        report.append("TRADE BREAKDOWN BY EXIT REASON")
        report.append("-" * 70)
        
        exit_reasons = {}
        for trade in result.trades:
            reason = trade.exit_reason
            if reason not in exit_reasons:
                exit_reasons[reason] = {'count': 0, 'pnl': 0, 'wins': 0}
            exit_reasons[reason]['count'] += 1
            exit_reasons[reason]['pnl'] += trade.net_pnl
            if trade.net_pnl > 0:
                exit_reasons[reason]['wins'] += 1
        
        for reason, stats in exit_reasons.items():
            win_rate = (stats['wins'] / stats['count'] * 100) if stats['count'] > 0 else 0
            report.append(f"  {reason}:")
            report.append(f"    Count: {stats['count']} | P&L: ${stats['pnl']:,.2f} | Win Rate: {win_rate:.1f}%")
    
    # Risk Analysis
    report.append("\n" + "-" * 70)
    report.append("RISK ANALYSIS")
    report.append("-" * 70)
    
    if result.daily_returns is not None and len(result.daily_returns) > 0:
        report.append(f"Daily Return Std:     {result.daily_returns.std() * 100:.2f}%")
        report.append(f"Best Day:             {result.daily_returns.max() * 100:+.2f}%")
        report.append(f"Worst Day:            {result.daily_returns.min() * 100:+.2f}%")
        
        # Calculate VaR
        var_95 = np.percentile(result.daily_returns, 5) * 100
        report.append(f"Daily VaR (95%):      {var_95:.2f}%")
    
    report.append("\n" + "=" * 70)
    
    report_str = "\n".join(report)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report_str)
        print(f"Report saved to {output_file}")
    
    return report_str


def main():
    parser = argparse.ArgumentParser(description="Run trading strategy backtest")
    parser.add_argument("--timeframe", "-t", default="5m", 
                       choices=["1m", "5m", "15m"],
                       help="Candle timeframe")
    parser.add_argument("--days", "-d", type=int, default=30,
                       help="Number of days to backtest")
    parser.add_argument("--capital", "-c", type=float, default=10000,
                       help="Initial capital")
    parser.add_argument("--leverage", "-l", type=int, default=10,
                       help="Trading leverage")
    parser.add_argument("--optimize", "-o", action="store_true",
                       help="Run parameter optimization")
    parser.add_argument("--synthetic", "-s", action="store_true",
                       help="Use synthetic data instead of real")
    parser.add_argument("--output", default=None,
                       help="Output file for report")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("       SCALPING STRATEGY BACKTESTER")
    print("       StochRSI + MACD | BTC Perpetuals")
    print("="*60)
    
    # Fetch data
    if args.synthetic:
        df = generate_synthetic_data(days=args.days, timeframe=args.timeframe)
    else:
        try:
            df = fetch_historical_data(
                symbol="BTCUSDT",
                timeframe=args.timeframe,
                days=args.days
            )
        except Exception as e:
            print(f"Error fetching real data: {e}")
            print("Falling back to synthetic data...")
            df = generate_synthetic_data(days=args.days, timeframe=args.timeframe)
    
    if df.empty:
        print("No data available for backtest!")
        return
    
    # Run optimization or single backtest
    if args.optimize:
        opt_results = run_optimization(df, args.timeframe)
        result = opt_results['best_result']
        print(f"\nBest Parameters: {opt_results['best_params']}")
    else:
        print(f"\nRunning backtest with:")
        print(f"  Timeframe: {args.timeframe}")
        print(f"  Capital: ${args.capital:,.2f}")
        print(f"  Leverage: {args.leverage}x")
        print(f"  Data points: {len(df)}")
        
        result = run_single_backtest(
            df,
            config_name=args.timeframe,
            initial_capital=args.capital,
            leverage=args.leverage
        )
    
    # Print summary
    result.print_summary()
    
    # Generate detailed report
    report = generate_report(result, args.output)
    
    # Save trade log
    if result.trades:
        trades_df = pd.DataFrame([t.to_dict() for t in result.trades])
        trades_file = args.output.replace('.txt', '_trades.csv') if args.output else 'trades.csv'
        trades_df.to_csv(trades_file, index=False)
        print(f"Trade log saved to {trades_file}")
    
    return result


if __name__ == "__main__":
    main()
