"""
Realistic BTC Price Data Generator
Based on actual 2025 market movements gathered from web research:
- BTC hit ATH above $126,000 in July 2025
- Currently trading around $92,000 in December 2025
- Recent range: $80,000 - $126,000
- High volatility with significant pullbacks
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_realistic_btc_data(days: int = 30, timeframe: str = "5m") -> pd.DataFrame:
    """
    Generate realistic BTC OHLCV data based on actual 2025 market conditions
    
    This creates price action that reflects:
    - Real BTC volatility patterns (2-4% daily moves common)
    - Trending and ranging periods
    - Volume spikes during large moves
    - Realistic intraday patterns
    """
    # Calculate number of candles
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
    minutes = tf_minutes.get(timeframe, 5)
    num_candles = (days * 24 * 60) // minutes
    
    # Based on recent BTC price action (Nov-Dec 2025)
    # Start from ~$100,000 and model the decline to ~$92,000
    initial_price = 100000
    
    # Real BTC characteristics
    daily_volatility = 0.025  # 2.5% daily volatility (realistic for BTC)
    candle_volatility = daily_volatility / np.sqrt(1440 / minutes)
    
    np.random.seed(int(datetime.now().timestamp()) % 10000)  # Variable seed
    
    # Generate realistic price movements with trends
    data = []
    current_price = initial_price
    
    # Create trend phases (like real BTC)
    trend_phases = []
    candles_per_day = 1440 // minutes
    
    for day in range(days):
        # Simulate different market phases
        if day < 5:
            drift = -0.005  # Initial downtrend
        elif day < 10:
            drift = 0.003   # Bounce
        elif day < 18:
            drift = -0.008  # Larger downtrend (like Nov 2025 crash)
        elif day < 23:
            drift = 0.002   # Recovery attempt
        else:
            drift = -0.003  # Consolidation/slight decline
        
        trend_phases.extend([drift] * candles_per_day)
    
    # Generate price data
    for i in range(num_candles):
        # Get trend for this candle
        trend = trend_phases[i] / candles_per_day if i < len(trend_phases) else 0
        
        # Add realistic noise with occasional spikes
        noise = np.random.normal(0, candle_volatility)
        
        # Add occasional large moves (like real crypto)
        if np.random.random() < 0.02:  # 2% chance of large move
            noise *= np.random.uniform(2, 4)
        
        # Calculate return
        ret = trend + noise
        
        # Generate OHLC
        open_price = current_price
        
        # Intraday volatility
        intraday_vol = abs(noise) * current_price * 1.5
        
        if ret > 0:  # Bullish candle
            low = open_price - intraday_vol * np.random.uniform(0.2, 0.5)
            high = open_price + intraday_vol * np.random.uniform(0.5, 1.2)
            close = open_price * (1 + ret)
        else:  # Bearish candle
            high = open_price + intraday_vol * np.random.uniform(0.2, 0.5)
            low = open_price - intraday_vol * np.random.uniform(0.5, 1.2)
            close = open_price * (1 + ret)
        
        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        # Volume: higher on larger moves
        base_volume = 500  # Base BTC volume per 5min
        volatility_factor = abs(ret) / candle_volatility if candle_volatility > 0 else 1
        volume = base_volume * (1 + volatility_factor) * np.random.uniform(0.5, 1.5)
        
        data.append({
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': round(volume, 2)
        })
        
        current_price = close
    
    # Create DataFrame
    start_date = datetime.now() - timedelta(days=days)
    timestamps = pd.date_range(start=start_date, periods=num_candles, freq=f"{minutes}min")
    
    df = pd.DataFrame(data, index=timestamps)
    
    # Print summary
    print(f"\n[DATA] Generated Realistic BTC Data:")
    print(f"   Period: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   Timeframe: {timeframe}")
    print(f"   Candles: {len(df)}")
    print(f"   Price Range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    print(f"   Start Price: ${df['open'].iloc[0]:,.2f}")
    print(f"   End Price: ${df['close'].iloc[-1]:,.2f}")
    print(f"   Total Return: {((df['close'].iloc[-1] / df['open'].iloc[0]) - 1) * 100:.2f}%")
    
    return df


# Additional function to create data based on specific historical patterns
def generate_btc_pattern_data(pattern: str = "volatile_decline", 
                               days: int = 30, 
                               timeframe: str = "5m") -> pd.DataFrame:
    """
    Generate BTC data matching specific market patterns
    
    Patterns:
    - volatile_decline: Like Nov 2025 ($100k -> $80k with bounces)
    - bull_run: Strong uptrend with pullbacks
    - choppy_range: Sideways with high volatility
    - crash_recovery: Sharp drop followed by V-shaped recovery
    """
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
    minutes = tf_minutes.get(timeframe, 5)
    num_candles = (days * 24 * 60) // minutes
    
    np.random.seed(42)  # Reproducible for testing
    
    # Pattern-specific parameters
    patterns = {
        "volatile_decline": {
            "start": 100000,
            "daily_moves": [-0.02, -0.01, 0.03, -0.03, -0.02, 
                           0.01, -0.025, -0.015, 0.02, -0.01,
                           -0.035, -0.02, 0.015, -0.01, -0.025,
                           0.03, 0.02, -0.015, -0.02, 0.01,
                           -0.01, -0.02, 0.025, -0.015, -0.01,
                           0.02, -0.03, 0.015, -0.01, -0.02],
            "volatility": 0.025
        },
        "bull_run": {
            "start": 80000,
            "daily_moves": [0.03, 0.02, -0.01, 0.025, 0.015,
                           0.02, -0.015, 0.03, 0.01, 0.02,
                           0.025, -0.02, 0.015, 0.03, 0.01,
                           -0.01, 0.02, 0.025, -0.005, 0.02,
                           0.015, 0.01, 0.025, -0.015, 0.02,
                           0.03, -0.01, 0.015, 0.02, 0.01],
            "volatility": 0.02
        },
        "choppy_range": {
            "start": 92000,
            "daily_moves": [0.02, -0.025, 0.015, -0.02, 0.025,
                           -0.015, 0.01, -0.02, 0.025, -0.01,
                           0.02, -0.025, 0.01, -0.015, 0.02,
                           -0.02, 0.015, -0.01, 0.025, -0.02,
                           0.01, -0.025, 0.02, -0.015, 0.01,
                           -0.02, 0.025, -0.01, 0.015, -0.02],
            "volatility": 0.028
        },
        "crash_recovery": {
            "start": 100000,
            "daily_moves": [-0.05, -0.08, -0.06, -0.04, -0.02,
                           0.01, 0.03, 0.05, 0.04, 0.035,
                           0.025, 0.02, -0.015, 0.02, 0.015,
                           0.01, 0.025, -0.01, 0.02, 0.015,
                           0.01, 0.02, -0.005, 0.015, 0.01,
                           0.02, -0.01, 0.015, 0.02, 0.01],
            "volatility": 0.035
        }
    }
    
    config = patterns.get(pattern, patterns["volatile_decline"])
    
    current_price = config["start"]
    daily_moves = config["daily_moves"]
    base_volatility = config["volatility"]
    candles_per_day = 1440 // minutes
    
    data = []
    
    for day in range(min(days, len(daily_moves))):
        daily_return = daily_moves[day]
        
        for candle in range(candles_per_day):
            # Distribute daily return across candles with noise
            candle_drift = daily_return / candles_per_day
            candle_noise = np.random.normal(0, base_volatility / np.sqrt(candles_per_day))
            
            ret = candle_drift + candle_noise
            
            open_price = current_price
            intraday_vol = abs(candle_noise) * current_price * 1.5
            
            if ret > 0:
                low = open_price - intraday_vol * np.random.uniform(0.2, 0.5)
                high = open_price + intraday_vol * np.random.uniform(0.5, 1.2)
            else:
                high = open_price + intraday_vol * np.random.uniform(0.2, 0.5)
                low = open_price - intraday_vol * np.random.uniform(0.5, 1.2)
            
            close = open_price * (1 + ret)
            high = max(high, open_price, close)
            low = min(low, open_price, close)
            
            volume = 500 * (1 + abs(ret) * 50) * np.random.uniform(0.5, 1.5)
            
            data.append({
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': round(volume, 2)
            })
            
            current_price = close
    
    start_date = datetime.now() - timedelta(days=days)
    timestamps = pd.date_range(start=start_date, periods=len(data), freq=f"{minutes}min")
    
    df = pd.DataFrame(data, index=timestamps)
    
    print(f"\n[DATA] Generated {pattern.upper()} Pattern Data:")
    print(f"   Period: {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"   Candles: {len(df)}")
    print(f"   Price Range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    print(f"   Start: ${df['open'].iloc[0]:,.2f} → End: ${df['close'].iloc[-1]:,.2f}")
    print(f"   Total Return: {((df['close'].iloc[-1] / df['open'].iloc[0]) - 1) * 100:.2f}%")
    
    return df


if __name__ == "__main__":
    # Test data generation
    df = generate_realistic_btc_data(days=30, timeframe="5m")
    print(df.head(10))
    print(df.tail(10))
