#!/usr/bin/env python3
"""
DIAGNOSTIC SCRIPT - Run this on YOUR machine with real Blofin data

This will:
1. Analyze your actual market data
2. Find the optimal configuration for REAL conditions
3. Show exactly why trades are winning/losing

Usage:
    python diagnose_strategy.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta


def fetch_blofin_data(symbol="BTC-USDT", timeframe="15m", days=30):
    """Fetch real data from Blofin"""
    base_url = "https://openapi.blofin.com"
    endpoint = "/api/v1/market/candles"
    
    end_time = int(datetime.now().timestamp() * 1000)
    all_candles = []
    current_end = end_time
    
    print(f"Fetching {days} days of {timeframe} data...")
    
    for _ in range(days * 10):  # Multiple requests needed
        params = {
            "instId": symbol,
            "bar": timeframe,
            "limit": 100,
            "after": str(current_end)
        }
        
        try:
            response = requests.get(f"{base_url}{endpoint}", params=params, timeout=10)
            data = response.json()
            
            if data.get('code') != '0' or not data.get('data'):
                break
            
            candles = data['data']
            all_candles.extend(candles)
            
            oldest = int(candles[-1][0])
            current_end = oldest - 1
            
            if len(candles) < 100:
                break
            
            # Check if we have enough data
            oldest_time = datetime.fromtimestamp(oldest / 1000)
            if (datetime.now() - oldest_time).days >= days:
                break
                
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
    
    if not all_candles:
        return None
    
    df = pd.DataFrame(all_candles, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'vol_ccy', 'vol_quote', 'confirm'
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
    df.set_index('timestamp', inplace=True)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    df = df[['open', 'high', 'low', 'close', 'volume']]
    return df.sort_index()


def add_indicators(df):
    """Add technical indicators"""
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Stoch RSI
    rsi_min = df['rsi'].rolling(window=14).min()
    rsi_max = df['rsi'].rolling(window=14).max()
    stoch = (df['rsi'] - rsi_min) / (rsi_max - rsi_min) * 100
    df['stoch_rsi_k'] = stoch.rolling(window=3).mean()
    df['stoch_rsi_d'] = df['stoch_rsi_k'].rolling(window=3).mean()
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    
    # EMAs
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # ATR for volatility
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    df['atr_pct'] = df['atr'] / df['close'] * 100
    
    return df


def generate_signals(df, oversold=20, overbought=80):
    """Generate trading signals"""
    signals = []
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        k = row['stoch_rsi_k']
        d = row['stoch_rsi_d']
        prev_k = prev['stoch_rsi_k']
        
        macd_hist = row['macd_histogram']
        prev_hist = prev['macd_histogram']
        
        trend_up = row['ema_20'] > row['ema_50']
        trend_down = row['ema_20'] < row['ema_50']
        
        # Long: oversold + crossover + MACD momentum + uptrend
        if k < oversold and prev_k < d and k > d and macd_hist > prev_hist and trend_up:
            signals.append({
                'idx': i, 
                'time': df.index[i],
                'type': 'LONG', 
                'price': row['close'],
                'atr_pct': row['atr_pct']
            })
        
        # Short: overbought + crossunder + MACD momentum + downtrend
        elif k > overbought and prev_k > d and k < d and macd_hist < prev_hist and trend_down:
            signals.append({
                'idx': i,
                'time': df.index[i],
                'type': 'SHORT',
                'price': row['close'],
                'atr_pct': row['atr_pct']
            })
    
    return signals


def analyze_signal_quality(df, signals):
    """Analyze what happens after each signal"""
    results = []
    
    for s in signals:
        idx = s['idx']
        entry = s['price']
        is_long = s['type'] == 'LONG'
        
        # Look at next 100 candles (about 25 hours on 15m)
        future = df.iloc[idx+1:min(idx+100, len(df))]
        
        if len(future) < 10:
            continue
        
        if is_long:
            max_profit_pct = (future['high'].max() - entry) / entry * 100
            max_loss_pct = (entry - future['low'].min()) / entry * 100
        else:
            max_profit_pct = (entry - future['low'].min()) / entry * 100
            max_loss_pct = (future['high'].max() - entry) / entry * 100
        
        # Find when various SL/TP levels were hit
        sl_hits = {}
        tp_hits = {}
        
        for sl_pct in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
            if is_long:
                sl_price = entry * (1 - sl_pct/100)
                hit = (future['low'] <= sl_price).any()
            else:
                sl_price = entry * (1 + sl_pct/100)
                hit = (future['high'] >= sl_price).any()
            
            if hit:
                if is_long:
                    hit_idx = (future['low'] <= sl_price).idxmax()
                else:
                    hit_idx = (future['high'] >= sl_price).idxmax()
                candles_to_hit = list(future.index).index(hit_idx) + 1
                sl_hits[sl_pct] = candles_to_hit
            else:
                sl_hits[sl_pct] = None
        
        for tp_pct in [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0]:
            if is_long:
                tp_price = entry * (1 + tp_pct/100)
                hit = (future['high'] >= tp_price).any()
            else:
                tp_price = entry * (1 - tp_pct/100)
                hit = (future['low'] <= tp_price).any()
            
            if hit:
                if is_long:
                    hit_idx = (future['high'] >= tp_price).idxmax()
                else:
                    hit_idx = (future['low'] <= tp_price).idxmax()
                candles_to_hit = list(future.index).index(hit_idx) + 1
                tp_hits[tp_pct] = candles_to_hit
            else:
                tp_hits[tp_pct] = None
        
        results.append({
            'type': s['type'],
            'price': entry,
            'time': s['time'],
            'atr_pct': s['atr_pct'],
            'max_profit': max_profit_pct,
            'max_loss': max_loss_pct,
            'sl_hits': sl_hits,
            'tp_hits': tp_hits
        })
    
    return results


def find_optimal_config(signal_results):
    """Find the best SL/TP combination"""
    configs = []
    
    for sl in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        for tp in [sl*2, sl*3, sl*4, sl*5]:  # R:R of 2, 3, 4, 5
            wins = 0
            losses = 0
            
            for r in signal_results:
                sl_candles = r['sl_hits'].get(sl)
                tp_candles = r['tp_hits'].get(tp)
                
                if tp_candles is not None and (sl_candles is None or tp_candles < sl_candles):
                    wins += 1
                elif sl_candles is not None:
                    losses += 1
                # If neither hit, trade still open - ignore
            
            if wins + losses > 0:
                wr = wins / (wins + losses) * 100
                # Expected value per trade (ignoring fees for now)
                ev = (wins * tp - losses * sl) / (wins + losses)
                
                configs.append({
                    'sl': sl,
                    'tp': tp,
                    'rr': tp/sl,
                    'wins': wins,
                    'losses': losses,
                    'wr': wr,
                    'ev': ev
                })
    
    return sorted(configs, key=lambda x: x['ev'], reverse=True)


def backtest_config(df, signals, leverage, sl_pct, tp_pct, capital_pct=10):
    """Backtest a specific configuration"""
    capital = 10000
    trades = []
    commission = 0.0006
    
    for s in signals:
        idx = s['idx']
        entry = s['price']
        is_long = s['type'] == 'LONG'
        
        if is_long:
            sl = entry * (1 - sl_pct/100)
            tp = entry * (1 + tp_pct/100)
        else:
            sl = entry * (1 + sl_pct/100)
            tp = entry * (1 - tp_pct/100)
        
        # Find exit
        future = df.iloc[idx+1:min(idx+200, len(df))]
        exit_price = None
        reason = None
        
        for _, row in future.iterrows():
            if is_long:
                if row['low'] <= sl:
                    exit_price, reason = sl, 'SL'
                    break
                if row['high'] >= tp:
                    exit_price, reason = tp, 'TP'
                    break
            else:
                if row['high'] >= sl:
                    exit_price, reason = sl, 'SL'
                    break
                if row['low'] <= tp:
                    exit_price, reason = tp, 'TP'
                    break
        
        if exit_price is None:
            if len(future) > 0:
                exit_price = future.iloc[-1]['close']
            else:
                exit_price = entry
            reason = 'TIMEOUT'
        
        # Calculate P&L
        margin = capital * capital_pct / 100
        if is_long:
            pnl_pct = (exit_price - entry) / entry
        else:
            pnl_pct = (entry - exit_price) / entry
        
        gross_pnl = margin * pnl_pct * leverage
        fees = margin * leverage * commission * 2
        net_pnl = gross_pnl - fees
        
        trades.append({
            'type': s['type'],
            'entry': entry,
            'exit': exit_price,
            'reason': reason,
            'gross_pnl': gross_pnl,
            'fees': fees,
            'net_pnl': net_pnl
        })
    
    return trades


def main():
    print("=" * 70)
    print("   STRATEGY DIAGNOSTIC - REAL DATA ANALYSIS")
    print("=" * 70)
    
    # Fetch data
    df = fetch_blofin_data("BTC-USDT", "15m", 30)
    
    if df is None or df.empty:
        print("\n[ERROR] Could not fetch data from Blofin")
        print("Make sure you have internet access and Blofin API is available")
        return
    
    print(f"\n[DATA SUMMARY]")
    print(f"  Period: {df.index[0]} to {df.index[-1]}")
    print(f"  Candles: {len(df)}")
    print(f"  Start Price: ${df['close'].iloc[0]:,.2f}")
    print(f"  End Price: ${df['close'].iloc[-1]:,.2f}")
    print(f"  Change: {(df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100:.2f}%")
    
    # Add indicators
    df = add_indicators(df)
    
    # Volatility analysis
    avg_atr_pct = df['atr_pct'].mean()
    print(f"\n[VOLATILITY]")
    print(f"  Avg ATR: {avg_atr_pct:.3f}% per candle")
    print(f"  This means price typically moves {avg_atr_pct:.3f}% per 15 minutes")
    print(f"  MINIMUM recommended SL: {avg_atr_pct * 2:.2f}% (2x ATR)")
    print(f"  SAFE recommended SL: {avg_atr_pct * 3:.2f}% (3x ATR)")
    
    # Generate signals
    signals = generate_signals(df)
    print(f"\n[SIGNALS]")
    print(f"  Total: {len(signals)}")
    print(f"  Longs: {len([s for s in signals if s['type'] == 'LONG'])}")
    print(f"  Shorts: {len([s for s in signals if s['type'] == 'SHORT'])}")
    
    if len(signals) == 0:
        print("\n[WARNING] No signals generated!")
        print("The strategy may be too restrictive for current market conditions")
        return
    
    # Analyze signal quality
    print(f"\n[ANALYZING SIGNAL OUTCOMES...]")
    signal_results = analyze_signal_quality(df, signals)
    
    # Show individual signal outcomes
    print(f"\n[SIGNAL OUTCOMES] (first 10)")
    print(f"{'Type':<6} {'Price':>10} {'MaxProfit':>10} {'MaxLoss':>10} {'Quality'}")
    print("-" * 55)
    
    for r in signal_results[:10]:
        quality = "GOOD" if r['max_profit'] > r['max_loss'] else "BAD"
        print(f"{r['type']:<6} ${r['price']:>9,.0f} {r['max_profit']:>9.2f}% {r['max_loss']:>9.2f}% {quality}")
    
    # Find optimal configuration
    print(f"\n[FINDING OPTIMAL CONFIGURATION...]")
    optimal_configs = find_optimal_config(signal_results)
    
    print(f"\n[TOP 10 CONFIGURATIONS] (by expected value)")
    print(f"{'SL%':>6} {'TP%':>6} {'R:R':>5} {'Wins':>6} {'Losses':>6} {'WR%':>6} {'EV':>8}")
    print("-" * 55)
    
    for c in optimal_configs[:10]:
        print(f"{c['sl']:>6.1f} {c['tp']:>6.1f} {c['rr']:>5.1f} {c['wins']:>6} {c['losses']:>6} {c['wr']:>5.1f}% {c['ev']:>7.2f}%")
    
    # Backtest top configurations
    print(f"\n[BACKTESTING TOP CONFIGS WITH FEES]")
    print(f"{'Config':<25} {'P&L':>12} {'Trades':>8} {'WR%':>8} {'Fees':>10}")
    print("-" * 70)
    
    for leverage in [5, 10, 15]:
        for c in optimal_configs[:3]:
            trades = backtest_config(df, signals, leverage, c['sl'], c['tp'])
            
            if trades:
                total_pnl = sum(t['net_pnl'] for t in trades)
                total_fees = sum(t['fees'] for t in trades)
                wins = len([t for t in trades if t['net_pnl'] > 0])
                wr = wins / len(trades) * 100
                
                name = f"{leverage}x SL{c['sl']}% TP{c['tp']}%"
                status = "[+]" if total_pnl > 0 else "[-]"
                print(f"{name:<25} {status}${total_pnl:>10,.2f} {len(trades):>8} {wr:>7.1f}% ${total_fees:>9,.2f}")
    
    # Final recommendation
    print(f"\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    
    best = optimal_configs[0] if optimal_configs else None
    if best:
        print(f"""
Based on REAL market data analysis:

1. STOP LOSS: {best['sl']}% minimum
   - ATR shows {avg_atr_pct:.2f}% avg movement per candle
   - Anything below {avg_atr_pct * 2:.1f}% will hit on normal noise

2. TAKE PROFIT: {best['tp']}% ({best['rr']:.1f}:1 R:R)
   - This compensates for lower win rate
   
3. LEVERAGE: 5-10x recommended
   - Higher leverage = higher fees
   - Fees are {0.06 * 2:.2f}% round trip × leverage
   
4. WIN RATE: Expect ~{best['wr']:.0f}% wins
   - This is NORMAL for high R:R strategies
   - Profit comes from few big wins

5. CURRENT MARKET: {"TRENDING" if abs((df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100) > 5 else "RANGING"}
   - This strategy works better in trending markets
""")
    
    # Save detailed results
    results_df = pd.DataFrame(signal_results)
    results_df.to_csv('signal_analysis.csv', index=False)
    print(f"\n[SAVED] Detailed analysis to signal_analysis.csv")


if __name__ == "__main__":
    main()
