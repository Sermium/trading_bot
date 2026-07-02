#!/usr/bin/env python3
"""
NEW STRATEGIES - Based on REAL Blofin trade analysis

Strategy 1: Trend Following Breakout
Strategy 2: ML-Filtered Signals

Both include time/day filters that showed profit in real data.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum


class Signal(Enum):
    LONG = 1
    SHORT = -1
    NONE = 0


@dataclass
class TradeSignal:
    signal: Signal
    confidence: float
    reason: str
    filters_passed: List[str]


# ============================================================
# STRATEGY 1: TREND FOLLOWING BREAKOUT
# ============================================================
class TrendBreakoutStrategy:
    """
    Simple trend-following strategy:
    - Uses EMA crossover for trend direction
    - Enters on breakout of recent range
    - Time-filtered based on profitable hours
    """
    
    def __init__(
        self,
        ema_fast: int = 10,
        ema_slow: int = 30,
        breakout_periods: int = 20,
        atr_periods: int = 14,
        profitable_hours: List[int] = None,
        skip_days: List[int] = None
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.breakout_periods = breakout_periods
        self.atr_periods = atr_periods
        
        # From real data analysis
        self.profitable_hours = profitable_hours or [6, 7, 8, 15, 16, 17, 18, 19]
        self.skip_days = skip_days or [5]  # Skip Saturday (worst day)
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicators"""
        df = df.copy()
        
        # EMAs for trend
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        
        # Trend direction
        df['trend'] = np.where(df['ema_fast'] > df['ema_slow'], 1, -1)
        
        # Breakout levels
        df['high_breakout'] = df['high'].rolling(self.breakout_periods).max()
        df['low_breakout'] = df['low'].rolling(self.breakout_periods).min()
        
        # ATR for volatility
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(self.atr_periods).mean()
        
        # Momentum
        df['momentum'] = df['close'].pct_change(5)
        
        return df
    
    def check_time_filter(self, timestamp) -> Tuple[bool, str]:
        """Check if current time is in profitable trading window"""
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        
        hour = timestamp.hour
        day = timestamp.dayofweek
        
        if day in self.skip_days:
            return False, f"Skipping day {day}"
        
        if hour not in self.profitable_hours:
            return False, f"Hour {hour} not profitable"
        
        return True, f"Time filter passed (hour={hour}, day={day})"
    
    def generate_signal(self, df: pd.DataFrame, idx: int) -> Optional[TradeSignal]:
        """Generate trading signal"""
        if idx < self.breakout_periods + 5:
            return None
        
        row = df.iloc[idx]
        prev = df.iloc[idx - 1]
        timestamp = df.index[idx]
        
        # Time filter first
        time_ok, time_reason = self.check_time_filter(timestamp)
        if not time_ok:
            return None
        
        filters_passed = [time_reason]
        
        trend = row['trend']
        close = row['close']
        high_break = prev['high_breakout']  # Previous bar's level
        low_break = prev['low_breakout']
        atr = row['atr']
        
        # Skip if ATR is too low (no volatility)
        if atr < close * 0.002:  # Less than 0.2%
            return None
        
        signal = Signal.NONE
        confidence = 0
        reason = ""
        
        # LONG: Uptrend + breakout above range
        if trend == 1 and close > high_break:
            signal = Signal.LONG
            confidence = 60 + min(20, row['momentum'] * 500)
            reason = f"Bullish breakout above {high_break:.0f}"
            filters_passed.append("Uptrend confirmed")
            filters_passed.append("High breakout")
        
        # SHORT: Downtrend + breakdown below range
        elif trend == -1 and close < low_break:
            signal = Signal.SHORT
            confidence = 60 + min(20, abs(row['momentum']) * 500)
            reason = f"Bearish breakdown below {low_break:.0f}"
            filters_passed.append("Downtrend confirmed")
            filters_passed.append("Low breakdown")
        
        if signal == Signal.NONE:
            return None
        
        return TradeSignal(
            signal=signal,
            confidence=confidence,
            reason=reason,
            filters_passed=filters_passed
        )


# ============================================================
# STRATEGY 2: ML-FILTERED SIGNALS
# ============================================================
class MLFilteredStrategy:
    """
    Uses the original StochRSI/MACD signals but filters them
    using patterns learned from real trade data.
    
    ML Features:
    - Hour of day
    - Day of week  
    - Price relative to moving average
    - Recent volatility
    - Trend strength
    """
    
    def __init__(self):
        # Learned from real data analysis
        self.good_hours = [6, 7, 8, 15, 16, 17, 18, 19]
        self.bad_days = [5, 6]  # Saturday, Sunday
        self.min_trend_strength = 0.001  # 0.1% EMA difference
        
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all indicators"""
        df = df.copy()
        
        # Original indicators
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Stoch RSI
        rsi_min = df['rsi'].rolling(window=14).min()
        rsi_max = df['rsi'].rolling(window=14).max()
        stoch = (df['rsi'] - rsi_min) / (rsi_max - rsi_min + 0.0001) * 100
        df['stoch_k'] = stoch.rolling(window=3).mean()
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # ML Features
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['price_vs_ema'] = (df['close'] - df['ema_20']) / df['ema_20']
        df['trend_strength'] = (df['ema_20'] - df['ema_50']) / df['ema_50']
        
        # Volatility
        df['volatility'] = df['close'].pct_change().rolling(20).std()
        
        # Recent performance
        df['recent_return'] = df['close'].pct_change(10)
        
        return df
    
    def ml_filter(self, row, timestamp, signal_type: str) -> Tuple[bool, float, List[str]]:
        """
        ML-style filtering based on learned patterns
        Returns: (should_trade, confidence_adjustment, reasons)
        """
        score = 50  # Base score
        reasons = []
        
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        
        hour = timestamp.hour
        day = timestamp.dayofweek
        
        # Hour filter (strongest signal from data)
        if hour in self.good_hours:
            score += 15
            reasons.append(f"Good hour ({hour})")
        else:
            score -= 20
            reasons.append(f"Bad hour ({hour})")
        
        # Day filter
        if day in self.bad_days:
            score -= 15
            reasons.append(f"Weekend")
        elif day == 0:  # Monday was best
            score += 10
            reasons.append("Monday bonus")
        elif day == 3:  # Thursday was good
            score += 5
            reasons.append("Thursday")
        
        # Trend alignment
        trend_strength = row['trend_strength']
        if signal_type == 'SHORT' and trend_strength < -self.min_trend_strength:
            score += 10
            reasons.append("Aligned with downtrend")
        elif signal_type == 'LONG' and trend_strength > self.min_trend_strength:
            score += 10
            reasons.append("Aligned with uptrend")
        else:
            score -= 10
            reasons.append("Counter-trend")
        
        # Price position (shorts at higher prices worked better)
        price_vs_ema = row['price_vs_ema']
        if signal_type == 'SHORT' and price_vs_ema > 0:
            score += 5
            reasons.append("Price above EMA (good for short)")
        elif signal_type == 'LONG' and price_vs_ema < 0:
            score += 5
            reasons.append("Price below EMA (good for long)")
        
        # Volatility check
        vol = row['volatility']
        if vol > 0.005:  # High volatility
            score += 5
            reasons.append("High volatility")
        elif vol < 0.002:  # Low volatility
            score -= 10
            reasons.append("Low volatility")
        
        # Minimum score to trade
        should_trade = score >= 60
        
        return should_trade, score, reasons
    
    def generate_signal(self, df: pd.DataFrame, idx: int) -> Optional[TradeSignal]:
        """Generate ML-filtered signal"""
        if idx < 50:
            return None
        
        row = df.iloc[idx]
        prev = df.iloc[idx - 1]
        timestamp = df.index[idx]
        
        k = row['stoch_k']
        d = row['stoch_d']
        prev_k = prev['stoch_k']
        
        macd_hist = row['macd_hist']
        prev_hist = prev['macd_hist']
        
        signal = Signal.NONE
        base_reason = ""
        
        # Original signal logic (SHORT only based on data)
        if k > 80 and prev_k > d and k < d:  # Overbought crossdown
            if macd_hist < prev_hist:  # MACD momentum down
                signal = Signal.SHORT
                base_reason = "StochRSI overbought + MACD down"
        
        # We could add LONG but data showed it loses
        # elif k < 20 and prev_k < d and k > d:
        #     if macd_hist > prev_hist:
        #         signal = Signal.LONG
        #         base_reason = "StochRSI oversold + MACD up"
        
        if signal == Signal.NONE:
            return None
        
        # Apply ML filter
        signal_type = 'SHORT' if signal == Signal.SHORT else 'LONG'
        should_trade, ml_score, ml_reasons = self.ml_filter(row, timestamp, signal_type)
        
        if not should_trade:
            return None
        
        return TradeSignal(
            signal=signal,
            confidence=ml_score,
            reason=base_reason,
            filters_passed=ml_reasons
        )


# ============================================================
# COMBINED STRATEGY
# ============================================================
class CombinedStrategy:
    """
    Combines both strategies:
    - Trend breakout for entries
    - ML filtering for confirmation
    - SHORT only (based on real data)
    """
    
    def __init__(self):
        self.trend_strategy = TrendBreakoutStrategy()
        self.ml_strategy = MLFilteredStrategy()
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Combine both strategy indicators"""
        df = self.trend_strategy.prepare_data(df)
        df = self.ml_strategy.prepare_data(df)
        return df
    
    def generate_signal(self, df: pd.DataFrame, idx: int) -> Optional[TradeSignal]:
        """Generate signal using both strategies"""
        
        # Try trend breakout first
        trend_signal = self.trend_strategy.generate_signal(df, idx)
        
        if trend_signal and trend_signal.signal == Signal.SHORT:
            # Apply ML filter
            row = df.iloc[idx]
            timestamp = df.index[idx]
            should_trade, ml_score, ml_reasons = self.ml_strategy.ml_filter(
                row, timestamp, 'SHORT'
            )
            
            if should_trade and ml_score >= 60:
                trend_signal.confidence = (trend_signal.confidence + ml_score) / 2
                trend_signal.filters_passed.extend(ml_reasons)
                return trend_signal
        
        # Fallback to ML-filtered StochRSI
        ml_signal = self.ml_strategy.generate_signal(df, idx)
        if ml_signal:
            return ml_signal
        
        return None


if __name__ == "__main__":
    print("New strategies created:")
    print("  1. TrendBreakoutStrategy - Trend following with breakout entries")
    print("  2. MLFilteredStrategy - Original signals with ML filtering")
    print("  3. CombinedStrategy - Best of both")
    print("\nUse run_new_strategies.py to backtest")
