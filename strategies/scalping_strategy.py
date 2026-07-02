"""
Scalping Strategy Implementation
Combines StochRSI and MACD for high-probability entries
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

from .indicators import Indicators, calculate_all_indicators


class Signal(Enum):
    """Trading signal types"""
    LONG = 1
    SHORT = -1
    NEUTRAL = 0


@dataclass
class TradeSignal:
    """Container for trade signal information"""
    signal: Signal
    timestamp: datetime
    price: float
    stoch_rsi_k: float
    stoch_rsi_d: float
    macd: float
    macd_signal: float
    macd_histogram: float
    confidence: float  # 0-100 score
    reason: str


class ScalpingStrategy:
    """
    Scalping strategy using StochRSI + MACD
    
    Entry Rules:
    
    LONG:
    1. StochRSI K crosses above D (bullish crossover)
    2. StochRSI K < oversold level (e.g., 20) - coming from oversold
    3. MACD histogram is increasing (momentum building)
    4. MACD line > signal line OR about to cross above
    5. (Optional) Price above trend EMA for trend filter
    6. (Optional) Volume above average
    
    SHORT:
    1. StochRSI K crosses below D (bearish crossover)
    2. StochRSI K > overbought level (e.g., 80) - coming from overbought
    3. MACD histogram is decreasing (momentum fading)
    4. MACD line < signal line OR about to cross below
    5. (Optional) Price below trend EMA for trend filter
    6. (Optional) Volume above average
    """
    
    def __init__(self, 
                 stoch_rsi_settings: dict,
                 macd_settings: dict,
                 oversold: float = 20.0,
                 overbought: float = 80.0,
                 use_trend_filter: bool = True,
                 trend_ema_period: int = 50,
                 use_volume_filter: bool = True,
                 volume_threshold: float = 1.5,
                 require_macd_confirmation: bool = True):
        """
        Initialize the scalping strategy
        
        Args:
            stoch_rsi_settings: Dict with rsi_period, stoch_period, k_period, d_period
            macd_settings: Dict with fast_period, slow_period, signal_period
            oversold: StochRSI oversold threshold
            overbought: StochRSI overbought threshold
            use_trend_filter: Whether to filter signals based on trend EMA
            trend_ema_period: EMA period for trend determination
            use_volume_filter: Whether to require above-average volume
            volume_threshold: Volume must be this multiple of average
            require_macd_confirmation: Whether MACD confirmation is required
        """
        self.stoch_rsi_settings = stoch_rsi_settings
        self.macd_settings = macd_settings
        self.oversold = oversold
        self.overbought = overbought
        self.use_trend_filter = use_trend_filter
        self.trend_ema_period = trend_ema_period
        self.use_volume_filter = use_volume_filter
        self.volume_threshold = volume_threshold
        self.require_macd_confirmation = require_macd_confirmation
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all required indicators on the data"""
        return calculate_all_indicators(
            df, 
            self.stoch_rsi_settings,
            self.macd_settings,
            self.trend_ema_period
        )
    
    def _check_stoch_rsi_long(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, float, str]:
        """
        Check StochRSI conditions for long entry
        
        Returns:
            Tuple of (condition_met, confidence_score, reason)
        """
        k = row['stoch_rsi_k']
        d = row['stoch_rsi_d']
        prev_k = prev_row['stoch_rsi_k']
        prev_d = prev_row['stoch_rsi_d']
        
        # Check for bullish crossover
        crossover = (prev_k <= prev_d) and (k > d)
        
        # Check if coming from oversold
        was_oversold = prev_k < self.oversold or k < self.oversold + 10
        
        # K rising
        k_rising = k > prev_k
        
        if crossover and was_oversold:
            confidence = 80
            reason = f"StochRSI bullish crossover from oversold (K={k:.1f}, D={d:.1f})"
            return True, confidence, reason
        elif crossover:
            confidence = 60
            reason = f"StochRSI bullish crossover (K={k:.1f}, D={d:.1f})"
            return True, confidence, reason
        elif was_oversold and k_rising and k < 30:
            confidence = 50
            reason = f"StochRSI rising from oversold (K={k:.1f})"
            return True, confidence, reason
        
        return False, 0, ""
    
    def _check_stoch_rsi_short(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, float, str]:
        """Check StochRSI conditions for short entry"""
        k = row['stoch_rsi_k']
        d = row['stoch_rsi_d']
        prev_k = prev_row['stoch_rsi_k']
        prev_d = prev_row['stoch_rsi_d']
        
        # Check for bearish crossover
        crossover = (prev_k >= prev_d) and (k < d)
        
        # Check if coming from overbought
        was_overbought = prev_k > self.overbought or k > self.overbought - 10
        
        # K falling
        k_falling = k < prev_k
        
        if crossover and was_overbought:
            confidence = 80
            reason = f"StochRSI bearish crossover from overbought (K={k:.1f}, D={d:.1f})"
            return True, confidence, reason
        elif crossover:
            confidence = 60
            reason = f"StochRSI bearish crossover (K={k:.1f}, D={d:.1f})"
            return True, confidence, reason
        elif was_overbought and k_falling and k > 70:
            confidence = 50
            reason = f"StochRSI falling from overbought (K={k:.1f})"
            return True, confidence, reason
        
        return False, 0, ""
    
    def _check_macd_long(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, float, str]:
        """Check MACD conditions for long entry"""
        macd = row['macd']
        signal = row['macd_signal']
        hist = row['macd_histogram']
        prev_hist = prev_row['macd_histogram']
        prev_macd = prev_row['macd']
        prev_signal = prev_row['macd_signal']
        
        # MACD crossover
        macd_crossover = (prev_macd <= prev_signal) and (macd > signal)
        
        # Histogram increasing (momentum building)
        hist_increasing = hist > prev_hist
        
        # Already above signal
        above_signal = macd > signal
        
        if macd_crossover:
            confidence = 90
            reason = f"MACD bullish crossover (MACD={macd:.4f}, Signal={signal:.4f})"
            return True, confidence, reason
        elif above_signal and hist_increasing:
            confidence = 70
            reason = f"MACD above signal, histogram increasing"
            return True, confidence, reason
        elif hist_increasing and hist > 0:
            confidence = 50
            reason = f"MACD histogram positive and increasing"
            return True, confidence, reason
        
        return False, 0, ""
    
    def _check_macd_short(self, row: pd.Series, prev_row: pd.Series) -> Tuple[bool, float, str]:
        """Check MACD conditions for short entry"""
        macd = row['macd']
        signal = row['macd_signal']
        hist = row['macd_histogram']
        prev_hist = prev_row['macd_histogram']
        prev_macd = prev_row['macd']
        prev_signal = prev_row['macd_signal']
        
        # MACD crossover
        macd_crossover = (prev_macd >= prev_signal) and (macd < signal)
        
        # Histogram decreasing
        hist_decreasing = hist < prev_hist
        
        # Already below signal
        below_signal = macd < signal
        
        if macd_crossover:
            confidence = 90
            reason = f"MACD bearish crossover (MACD={macd:.4f}, Signal={signal:.4f})"
            return True, confidence, reason
        elif below_signal and hist_decreasing:
            confidence = 70
            reason = f"MACD below signal, histogram decreasing"
            return True, confidence, reason
        elif hist_decreasing and hist < 0:
            confidence = 50
            reason = f"MACD histogram negative and decreasing"
            return True, confidence, reason
        
        return False, 0, ""
    
    def _check_trend_filter(self, row: pd.Series) -> Tuple[Optional[Signal], str]:
        """
        Check trend filter based on EMA
        
        Returns:
            Tuple of (allowed_signal_direction, reason)
            If None, any direction is allowed
        """
        if not self.use_trend_filter:
            return None, ""
        
        close = row['close']
        ema = row['trend_ema']
        
        if close > ema:
            return Signal.LONG, f"Price above EMA{self.trend_ema_period} (trend filter)"
        else:
            return Signal.SHORT, f"Price below EMA{self.trend_ema_period} (trend filter)"
    
    def _check_volume_filter(self, row: pd.Series) -> Tuple[bool, str]:
        """Check if volume is above threshold"""
        if not self.use_volume_filter or 'volume_sma' not in row.index:
            return True, ""
        
        volume = row['volume']
        avg_volume = row['volume_sma']
        
        if pd.isna(avg_volume) or avg_volume == 0:
            return True, ""
        
        ratio = volume / avg_volume
        
        if ratio >= self.volume_threshold:
            return True, f"Volume {ratio:.1f}x average"
        else:
            return False, f"Volume too low ({ratio:.1f}x average)"
    
    def generate_signal(self, df: pd.DataFrame, idx: int = -1) -> Optional[TradeSignal]:
        """
        Generate trading signal for the given bar
        
        Args:
            df: DataFrame with indicators calculated
            idx: Index of the bar to check (-1 for latest)
            
        Returns:
            TradeSignal if conditions are met, None otherwise
        """
        if len(df) < 2:
            return None
        
        # Get current and previous rows
        if idx == -1:
            row = df.iloc[-1]
            prev_row = df.iloc[-2]
        else:
            if idx < 1:
                return None
            row = df.iloc[idx]
            prev_row = df.iloc[idx - 1]
        
        # Skip if indicators not ready
        if pd.isna(row['stoch_rsi_k']) or pd.isna(row['macd']):
            return None
        
        # Check volume filter first
        volume_ok, volume_reason = self._check_volume_filter(row)
        if not volume_ok:
            return None
        
        # Check trend filter
        trend_direction, trend_reason = self._check_trend_filter(row)
        
        # Check LONG conditions
        stoch_long, stoch_conf, stoch_reason = self._check_stoch_rsi_long(row, prev_row)
        macd_long, macd_conf, macd_reason = self._check_macd_long(row, prev_row)
        
        # Check SHORT conditions
        stoch_short, stoch_s_conf, stoch_s_reason = self._check_stoch_rsi_short(row, prev_row)
        macd_short, macd_s_conf, macd_s_reason = self._check_macd_short(row, prev_row)
        
        # Determine final signal
        signal = Signal.NEUTRAL
        confidence = 0
        reasons = []
        
        # LONG signal check
        if stoch_long:
            if self.require_macd_confirmation and not macd_long:
                pass  # Skip - MACD confirmation required but not present
            elif trend_direction == Signal.SHORT:
                pass  # Skip - against trend
            else:
                signal = Signal.LONG
                confidence = (stoch_conf + macd_conf) / 2 if macd_long else stoch_conf * 0.7
                reasons.append(stoch_reason)
                if macd_long:
                    reasons.append(macd_reason)
                if volume_reason:
                    reasons.append(volume_reason)
                if trend_reason:
                    reasons.append(trend_reason)
        
        # SHORT signal check
        if stoch_short and signal == Signal.NEUTRAL:
            if self.require_macd_confirmation and not macd_short:
                pass
            elif trend_direction == Signal.LONG:
                pass
            else:
                signal = Signal.SHORT
                confidence = (stoch_s_conf + macd_s_conf) / 2 if macd_short else stoch_s_conf * 0.7
                reasons.append(stoch_s_reason)
                if macd_short:
                    reasons.append(macd_s_reason)
                if volume_reason:
                    reasons.append(volume_reason)
                if trend_reason:
                    reasons.append(trend_reason)
        
        if signal == Signal.NEUTRAL:
            return None
        
        # Get timestamp
        if isinstance(row.name, pd.Timestamp):
            timestamp = row.name.to_pydatetime()
        else:
            timestamp = datetime.now()
        
        return TradeSignal(
            signal=signal,
            timestamp=timestamp,
            price=row['close'],
            stoch_rsi_k=row['stoch_rsi_k'],
            stoch_rsi_d=row['stoch_rsi_d'],
            macd=row['macd'],
            macd_signal=row['macd_signal'],
            macd_histogram=row['macd_histogram'],
            confidence=confidence,
            reason=" | ".join(reasons)
        )
    
    def generate_all_signals(self, df: pd.DataFrame) -> List[TradeSignal]:
        """Generate signals for all bars in the dataframe"""
        signals = []
        
        for i in range(1, len(df)):
            signal = self.generate_signal(df, i)
            if signal:
                signals.append(signal)
        
        return signals


class AdvancedScalpingStrategy(ScalpingStrategy):
    """
    Enhanced scalping strategy with additional filters for higher win rate
    """
    
    def __init__(self, *args, 
                 min_confidence: float = 60.0,
                 use_divergence: bool = True,
                 use_momentum_filter: bool = True,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.min_confidence = min_confidence
        self.use_divergence = use_divergence
        self.use_momentum_filter = use_momentum_filter
    
    def _check_divergence(self, df: pd.DataFrame, idx: int, lookback: int = 10) -> Tuple[Optional[Signal], str]:
        """
        Check for RSI divergence
        
        Bullish divergence: Price making lower lows, RSI making higher lows
        Bearish divergence: Price making higher highs, RSI making lower highs
        """
        if idx < lookback:
            return None, ""
        
        recent_df = df.iloc[idx-lookback:idx+1]
        
        # Find price and RSI pivots
        price_min_idx = recent_df['low'].idxmin()
        price_max_idx = recent_df['high'].idxmax()
        rsi_min_idx = recent_df['rsi'].idxmin()
        rsi_max_idx = recent_df['rsi'].idxmax()
        
        # Check bullish divergence
        if price_min_idx != rsi_min_idx:
            # Compare current lows with recent lows
            current_price = df.iloc[idx]['close']
            current_rsi = df.iloc[idx]['rsi']
            prev_price_low = recent_df['low'].min()
            prev_rsi_low = recent_df['rsi'].min()
            
            if current_price <= prev_price_low and current_rsi > prev_rsi_low:
                return Signal.LONG, "Bullish RSI divergence detected"
        
        # Check bearish divergence
        if price_max_idx != rsi_max_idx:
            current_price = df.iloc[idx]['close']
            current_rsi = df.iloc[idx]['rsi']
            prev_price_high = recent_df['high'].max()
            prev_rsi_high = recent_df['rsi'].max()
            
            if current_price >= prev_price_high and current_rsi < prev_rsi_high:
                return Signal.SHORT, "Bearish RSI divergence detected"
        
        return None, ""
    
    def generate_signal(self, df: pd.DataFrame, idx: int = -1) -> Optional[TradeSignal]:
        """Generate signal with additional filters"""
        # Get base signal
        signal = super().generate_signal(df, idx)
        
        if signal is None:
            return None
        
        # Apply minimum confidence filter
        if signal.confidence < self.min_confidence:
            return None
        
        # Check divergence for additional confirmation
        if self.use_divergence and idx > 10:
            actual_idx = idx if idx != -1 else len(df) - 1
            div_signal, div_reason = self._check_divergence(df, actual_idx)
            
            if div_signal and div_signal == signal.signal:
                # Divergence confirms signal - boost confidence
                signal = TradeSignal(
                    signal=signal.signal,
                    timestamp=signal.timestamp,
                    price=signal.price,
                    stoch_rsi_k=signal.stoch_rsi_k,
                    stoch_rsi_d=signal.stoch_rsi_d,
                    macd=signal.macd,
                    macd_signal=signal.macd_signal,
                    macd_histogram=signal.macd_histogram,
                    confidence=min(100, signal.confidence + 15),
                    reason=f"{signal.reason} | {div_reason}"
                )
        
        return signal
