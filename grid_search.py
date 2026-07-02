#!/usr/bin/env python3
"""
Grid search to find optimal SL/TP/Leverage for new strategies

This tests many combinations and finds what actually works.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from itertools import product

from strategies.new_strategies import (
    TrendBreakoutStrategy,
    MLFilteredStrategy,
    CombinedStrategy,
    Signal
)
from exchanges.blofin_data import BlofinDataFetcher


def quick_backtest(df_prep, strategy, leverage, sl_pct, tp_pct):
    """Fast backtest for grid search"""
    
    capital = 10000
    trades = []
    position = None
    pos_size = 10
    
    for i in range(50, len(df_prep)):
        row = df_prep.iloc[i]
        high, low, close = row['high'], row['low'], row['close']
        
        if position is not None:
            exit_price = None
            
            if position['side'] == 'short':
                if low <= position['tp']:
                    exit_price = position['tp']
                elif high >= position['sl']:
                    exit_price = position['sl']
            else:
                if high >= position['tp']:
                    exit_price = position['tp']
                elif low <= position['sl']:
                    exit_price = position['sl']
            
            if exit_price:
                if position['side'] == 'short':
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                else:
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                
                pnl = position['margin'] * pnl_pct * leverage
                fee = position['margin'] * leverage * 0.0006 * 2
                trades.append(pnl - fee)
                capital += position['margin'] + (pnl - fee)
                position = None
        
        if position is None:
            sig = strategy.generate_signal(df_prep, i)
            
            if sig:
                margin = capital * pos_size / 100
                
                if sig.signal == Signal.SHORT:
                    sl = close * (1 + sl_pct / 100)
                    tp = close * (1 - tp_pct / 100)
                    side = 'short'
                elif sig.signal == Signal.LONG:
                    sl = close * (1 - sl_pct / 100)
                    tp = close * (1 + tp_pct / 100)
                    side = 'long'
                else:
                    continue
                
                position = {
                    'side': side,
                    'entry': close,
                    'sl': sl,
                    'tp': tp,
                    'margin': margin
                }
                capital -= margin
    
    if not trades:
        return None
    
    wins = len([t for t in trades if t > 0])
    return {
        'trades': len(trades),
        'wins': wins,
        'wr': wins / len(trades) * 100,
        'pnl': sum(trades),
        'pnl_pct': (capital - 10000) / 100
    }


def main():
    print("=" * 70)
    print("   GRID SEARCH - Finding Optimal Parameters")
    print("=" * 70)
    
    # Fetch data
    print("\nFetching data...")
    fetcher = BlofinDataFetcher()
    
    if not fetcher.test_connection():
        print("ERROR: Cannot connect to Blofin")
        return
    
    df = fetcher.fetch_historical_data("BTC-USDT", "15m", 30)
    
    if df is None or df.empty:
        print("ERROR: No data")
        return
    
    print(f"Data: {len(df)} candles")
    
    # Parameters to test
    leverages = [3, 5, 7, 10]
    stop_losses = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
    take_profits = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
    
    strategies = {
        'Trend': TrendBreakoutStrategy(),
        'ML': MLFilteredStrategy(),
        'Combined': CombinedStrategy()
    }
    
    # Prepare data once per strategy
    prepared_data = {}
    for name, strat in strategies.items():
        prepared_data[name] = strat.prepare_data(df.copy())
    
    print(f"\nTesting {len(leverages) * len(stop_losses) * len(take_profits) * len(strategies)} combinations...")
    
    results = []
    
    for strat_name, strategy in strategies.items():
        df_prep = prepared_data[strat_name]
        
        for lev, sl, tp in product(leverages, stop_losses, take_profits):
            # Skip illogical combinations
            if tp < sl * 0.5:  # TP should be at least half of SL
                continue
            
            result = quick_backtest(df_prep, strategy, lev, sl, tp)
            
            if result:
                results.append({
                    'strategy': strat_name,
                    'leverage': lev,
                    'sl': sl,
                    'tp': tp,
                    'rr': tp / sl,
                    **result
                })
    
    if not results:
        print("No results!")
        return
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    # Filter profitable
    profitable = results_df[results_df['pnl'] > 0].sort_values('pnl', ascending=False)
    
    print(f"\n{'=' * 70}")
    print(f"PROFITABLE CONFIGURATIONS: {len(profitable)} / {len(results_df)}")
    print(f"{'=' * 70}")
    
    if len(profitable) == 0:
        print("\n⚠️  No profitable configurations found!")
        print("\nBest losing configurations:")
        best_losing = results_df.nlargest(10, 'pnl')
        print(best_losing[['strategy', 'leverage', 'sl', 'tp', 'trades', 'wr', 'pnl']].to_string(index=False))
    else:
        print(f"\n{'Strategy':<10} {'Lev':>4} {'SL%':>5} {'TP%':>5} {'R:R':>5} {'Trades':>7} {'WR%':>6} {'P&L':>10}")
        print("-" * 70)
        
        for _, row in profitable.head(20).iterrows():
            print(f"{row['strategy']:<10} {row['leverage']:>4}x {row['sl']:>5.1f} {row['tp']:>5.1f} {row['rr']:>5.2f} {row['trades']:>7} {row['wr']:>5.1f}% ${row['pnl']:>9.2f}")
    
    # Best by strategy
    print(f"\n{'=' * 70}")
    print("BEST CONFIG PER STRATEGY")
    print(f"{'=' * 70}")
    
    for strat in strategies.keys():
        strat_results = results_df[results_df['strategy'] == strat]
        if len(strat_results) > 0:
            best = strat_results.loc[strat_results['pnl'].idxmax()]
            status = "✓" if best['pnl'] > 0 else "✗"
            print(f"\n{status} {strat}:")
            print(f"    Leverage: {best['leverage']}x")
            print(f"    Stop Loss: {best['sl']}%")
            print(f"    Take Profit: {best['tp']}%")
            print(f"    Trades: {best['trades']}, Win Rate: {best['wr']:.1f}%")
            print(f"    P&L: ${best['pnl']:.2f} ({best['pnl_pct']:.1f}%)")
    
    # Save results
    results_df.to_csv('grid_search_results.csv', index=False)
    print(f"\nFull results saved to grid_search_results.csv")
    
    # Recommendations
    if len(profitable) > 0:
        best = profitable.iloc[0]
        print(f"\n{'=' * 70}")
        print("RECOMMENDED CONFIG")
        print(f"{'=' * 70}")
        print(f"""
Strategy: {best['strategy']}
Leverage: {best['leverage']}x
Stop Loss: {best['sl']}%
Take Profit: {best['tp']}%
R:R Ratio: {best['rr']:.2f}:1

Expected Results:
  Trades: ~{best['trades']} per month
  Win Rate: ~{best['wr']:.0f}%
  Monthly P&L: ~${best['pnl']:.0f} ({best['pnl_pct']:.1f}%)
""")


if __name__ == "__main__":
    main()
