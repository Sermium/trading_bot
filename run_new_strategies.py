#!/usr/bin/env python3
"""
Run and backtest the new strategies

Usage:
    python run_new_strategies.py --strategy trend
    python run_new_strategies.py --strategy ml
    python run_new_strategies.py --strategy combined
    python run_new_strategies.py --all
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import argparse
from datetime import datetime

from strategies.new_strategies import (
    TrendBreakoutStrategy,
    MLFilteredStrategy, 
    CombinedStrategy,
    Signal
)
from exchanges.blofin_data import BlofinDataFetcher


def backtest(df: pd.DataFrame, strategy, config: dict) -> dict:
    """Run backtest with given strategy"""
    
    df_prep = strategy.prepare_data(df.copy())
    
    capital = 10000
    initial_capital = capital
    trades = []
    position = None
    
    leverage = config.get('leverage', 5)
    sl_pct = config.get('stop_loss_pct', 0.8)
    tp_pct = config.get('take_profit_pct', 1.5)
    pos_size = config.get('position_size_pct', 10)
    
    for i in range(50, len(df_prep)):
        row = df_prep.iloc[i]
        high, low, close = row['high'], row['low'], row['close']
        time = df_prep.index[i]
        
        # Check position exit
        if position is not None:
            exit_price = None
            reason = None
            
            if position['side'] == 'short':
                if low <= position['tp']:
                    exit_price = position['tp']
                    reason = 'TP'
                elif high >= position['sl']:
                    exit_price = position['sl']
                    reason = 'SL'
            elif position['side'] == 'long':
                if high >= position['tp']:
                    exit_price = position['tp']
                    reason = 'TP'
                elif low <= position['sl']:
                    exit_price = position['sl']
                    reason = 'SL'
            
            if exit_price:
                if position['side'] == 'short':
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                else:
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                
                pnl = position['margin'] * pnl_pct * leverage
                fee = position['margin'] * leverage * 0.0006 * 2
                net = pnl - fee
                
                capital += position['margin'] + net
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': time,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'reason': reason,
                    'pnl': net,
                    'capital': capital,
                    'confidence': position.get('confidence', 0),
                    'filters': position.get('filters', [])
                })
                position = None
        
        # Look for new entry
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
                    'entry_time': time,
                    'sl': sl,
                    'tp': tp,
                    'margin': margin,
                    'confidence': sig.confidence,
                    'filters': sig.filters_passed
                }
                capital -= margin
    
    # Close open position
    if position:
        close_price = df_prep.iloc[-1]['close']
        if position['side'] == 'short':
            pnl_pct = (position['entry'] - close_price) / position['entry']
        else:
            pnl_pct = (close_price - position['entry']) / position['entry']
        
        pnl = position['margin'] * pnl_pct * leverage
        fee = position['margin'] * leverage * 0.0006 * 2
        net = pnl - fee
        capital += position['margin'] + net
        trades.append({
            'entry_time': position['entry_time'],
            'exit_time': df_prep.index[-1],
            'side': position['side'],
            'entry': position['entry'],
            'exit': close_price,
            'reason': 'END',
            'pnl': net,
            'capital': capital
        })
    
    return {
        'trades': trades,
        'final_capital': capital,
        'initial_capital': initial_capital,
        'total_pnl': capital - initial_capital,
        'pnl_pct': (capital - initial_capital) / initial_capital * 100
    }


def print_results(name: str, results: dict):
    """Print backtest results"""
    trades = results['trades']
    
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    
    if not trades:
        print("  No trades executed")
        return
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    
    print(f"\n  Trades: {len(trades)}")
    print(f"  Wins: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"  Losses: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    
    print(f"\n  Starting Capital: ${results['initial_capital']:,.2f}")
    print(f"  Final Capital: ${results['final_capital']:,.2f}")
    print(f"  Total P&L: ${results['total_pnl']:,.2f} ({results['pnl_pct']:+.1f}%)")
    
    if wins:
        print(f"\n  Avg Win: ${sum(t['pnl'] for t in wins)/len(wins):.2f}")
    if losses:
        print(f"  Avg Loss: ${sum(t['pnl'] for t in losses)/len(losses):.2f}")
    
    # Show first few trades
    print(f"\n  Recent trades:")
    for t in trades[-5:]:
        result = "WIN " if t['pnl'] > 0 else "LOSS"
        print(f"    {t['entry_time']} | {t['side']:5} | {result} ${t['pnl']:+.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', choices=['trend', 'ml', 'combined', 'all'], 
                       default='all')
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--timeframe', default='15m')
    parser.add_argument('--sl', type=float, default=0.8, help='Stop loss %')
    parser.add_argument('--tp', type=float, default=1.5, help='Take profit %')
    parser.add_argument('--leverage', type=int, default=5)
    args = parser.parse_args()
    
    config = {
        'leverage': args.leverage,
        'stop_loss_pct': args.sl,
        'take_profit_pct': args.tp,
        'position_size_pct': 10
    }
    
    print("=" * 60)
    print("   NEW STRATEGIES BACKTEST")
    print("=" * 60)
    print(f"\nConfig: {args.leverage}x leverage, {args.sl}% SL, {args.tp}% TP")
    
    # Fetch data
    print(f"\nFetching {args.days} days of {args.timeframe} data...")
    fetcher = BlofinDataFetcher()
    
    if not fetcher.test_connection():
        print("ERROR: Cannot connect to Blofin")
        return
    
    df = fetcher.fetch_historical_data("BTC-USDT", args.timeframe, args.days)
    
    if df is None or df.empty:
        print("ERROR: No data received")
        return
    
    print(f"Data: {df.index[0]} to {df.index[-1]} ({len(df)} candles)")
    
    strategies = {}
    
    if args.strategy in ['trend', 'all']:
        strategies['Trend Breakout'] = TrendBreakoutStrategy()
    
    if args.strategy in ['ml', 'all']:
        strategies['ML Filtered'] = MLFilteredStrategy()
    
    if args.strategy in ['combined', 'all']:
        strategies['Combined'] = CombinedStrategy()
    
    # Run backtests
    all_results = {}
    for name, strategy in strategies.items():
        results = backtest(df, strategy, config)
        all_results[name] = results
        print_results(name, results)
    
    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"\n  {'Strategy':<20} {'Trades':>8} {'Win%':>8} {'P&L':>12}")
    print(f"  {'-' * 50}")
    
    for name, results in all_results.items():
        trades = results['trades']
        if trades:
            wins = len([t for t in trades if t['pnl'] > 0])
            wr = wins / len(trades) * 100
            pnl = results['total_pnl']
            status = "✓" if pnl > 0 else "✗"
            print(f"  {status} {name:<18} {len(trades):>8} {wr:>7.1f}% ${pnl:>10,.2f}")
        else:
            print(f"  ✗ {name:<18} {'No trades':>8}")
    
    # Save best results
    best = max(all_results.items(), key=lambda x: x[1].get('total_pnl', -99999))
    if best[1]['trades']:
        trades_df = pd.DataFrame(best[1]['trades'])
        filename = f"trades_{best[0].lower().replace(' ', '_')}.csv"
        trades_df.to_csv(filename, index=False)
        print(f"\n  Best strategy trades saved to {filename}")


if __name__ == "__main__":
    main()
