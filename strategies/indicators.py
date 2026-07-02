"""
Technical Indicators Module
Implements StochRSI, MACD and supporting indicators for scalping strategy
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class StochRSIResult:
    """Container for StochRSI calculation results"""
    k: pd.Series
    d: pd.Series
    rsi: pd.Series


@dataclass
class MACDResult:
    """Container for MACD calculation results"""
    macd_line: pd.Series
    signal_line: pd.Series
    histogram: pd.Series


class Indicators:
    """Technical indicators for trading strategy"""
    
    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            close: Series of closing prices
            period: RSI lookback period
            
        Returns:
            RSI values as pandas Series
        """
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # Use exponential moving average for smoothing
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def stochastic(series: pd.Series, k_period: int = 14, 
                   d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic Oscillator
        
        Args:
            series: Input series (typically RSI for StochRSI)
            k_period: %K lookback period
            d_period: %D smoothing period
            
        Returns:
            Tuple of (%K, %D) series
        """
        lowest_low = series.rolling(window=k_period).min()
        highest_high = series.rolling(window=k_period).max()
        
        # Calculate %K
        k = 100 * (series - lowest_low) / (highest_high - lowest_low)
        k = k.replace([np.inf, -np.inf], np.nan)
        
        # Calculate %D (smoothed %K)
        d = k.rolling(window=d_period).mean()
        
        return k, d
    
    @staticmethod
    def stoch_rsi(close: pd.Series, 
                  rsi_period: int = 14,
                  stoch_period: int = 14,
                  k_period: int = 3,
                  d_period: int = 3) -> StochRSIResult:
        """
        Calculate Stochastic RSI
        
        The StochRSI applies the Stochastic formula to RSI values instead of price.
        This creates a more sensitive oscillator that can generate more signals.
        
        Args:
            close: Series of closing prices
            rsi_period: RSI calculation period
            stoch_period: Stochastic lookback period
            k_period: %K smoothing period
            d_period: %D smoothing period
            
        Returns:
            StochRSIResult with K, D, and RSI values
        """
        # First calculate RSI
        rsi = Indicators.rsi(close, rsi_period)
        
        # Apply stochastic to RSI
        lowest_rsi = rsi.rolling(window=stoch_period).min()
        highest_rsi = rsi.rolling(window=stoch_period).max()
        
        stoch_rsi_raw = 100 * (rsi - lowest_rsi) / (highest_rsi - lowest_rsi)
        stoch_rsi_raw = stoch_rsi_raw.replace([np.inf, -np.inf], np.nan)
        
        # Smooth with K period
        k = stoch_rsi_raw.rolling(window=k_period).mean()
        
        # D is smoothed K
        d = k.rolling(window=d_period).mean()
        
        return StochRSIResult(k=k, d=d, rsi=rsi)
    
    @staticmethod
    def macd(close: pd.Series,
             fast_period: int = 12,
             slow_period: int = 26,
             signal_period: int = 9) -> MACDResult:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            close: Series of closing prices
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line EMA period
            
        Returns:
            MACDResult with MACD line, signal line, and histogram
        """
        # Calculate EMAs
        ema_fast = close.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=slow_period, adjust=False).mean()
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # Histogram
        histogram = macd_line - signal_line
        
        return MACDResult(
            macd_line=macd_line,
            signal_line=signal_line,
            histogram=histogram
        )
    
    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return series.rolling(window=period).mean()
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, 
            period: int = 14) -> pd.Series:
        """
        Calculate Average True Range
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ATR period
            
        Returns:
            ATR values
        """
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.ewm(span=period, adjust=False).mean()
        
        return atr
    
    @staticmethod
    def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Volume Simple Moving Average"""
        return volume.rolling(window=period).mean()
    
    @staticmethod
    def bollinger_bands(close: pd.Series, period: int = 20, 
                        std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands
        
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower


def calculate_all_indicators(df: pd.DataFrame, 
                            stoch_rsi_settings: dict,
                            macd_settings: dict,
                            trend_ema_period: int = 50) -> pd.DataFrame:
    """
    Calculate all indicators needed for the strategy
    
    Args:
        df: DataFrame with OHLCV data
        stoch_rsi_settings: StochRSI parameters
        macd_settings: MACD parameters
        trend_ema_period: EMA period for trend filter
        
    Returns:
        DataFrame with indicator columns added
    """
    df = df.copy()
    
    # StochRSI
    stoch_result = Indicators.stoch_rsi(
        df['close'],
        rsi_period=stoch_rsi_settings.get('rsi_period', 14),
        stoch_period=stoch_rsi_settings.get('stoch_period', 14),
        k_period=stoch_rsi_settings.get('k_period', 3),
        d_period=stoch_rsi_settings.get('d_period', 3)
    )
    df['stoch_rsi_k'] = stoch_result.k
    df['stoch_rsi_d'] = stoch_result.d
    df['rsi'] = stoch_result.rsi
    
    # MACD
    macd_result = Indicators.macd(
        df['close'],
        fast_period=macd_settings.get('fast_period', 12),
        slow_period=macd_settings.get('slow_period', 26),
        signal_period=macd_settings.get('signal_period', 9)
    )
    df['macd'] = macd_result.macd_line
    df['macd_signal'] = macd_result.signal_line
    df['macd_histogram'] = macd_result.histogram
    
    # Trend EMA
    df['trend_ema'] = Indicators.ema(df['close'], trend_ema_period)
    
    # Volume SMA for volume filter
    if 'volume' in df.columns:
        df['volume_sma'] = Indicators.volume_sma(df['volume'], 20)
    
    # ATR for dynamic stop loss
    df['atr'] = Indicators.atr(df['high'], df['low'], df['close'], 14)
    
    return df
