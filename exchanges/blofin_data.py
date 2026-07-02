"""
Blofin Exchange Data Fetcher
Uses official blofin Python SDK or direct REST API

IMPORTANT: Public endpoints (candlesticks, tickers) do NOT require API keys!
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import os
import time


class BlofinDataFetcher:
    """
    Fetch historical data from Blofin API
    
    API Docs: https://docs.blofin.com/
    
    Note: Public endpoints (candlesticks, tickers) do NOT require authentication!
    """
    
    BASE_URL = "https://openapi.blofin.com"
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 passphrase: str = None):
        """
        Initialize Blofin fetcher
        
        Args:
            api_key: Blofin API key (optional for public data)
            api_secret: Blofin API secret (optional for public data)
            passphrase: Blofin passphrase (optional for public data)
        """
        self.api_key = api_key or os.getenv('BLOFIN_API_KEY')
        self.api_secret = api_secret or os.getenv('BLOFIN_API_SECRET')
        self.passphrase = passphrase or os.getenv('BLOFIN_PASSPHRASE')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make API request"""
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Request failed: {e}")
            return {}
    
    def get_tickers(self, inst_id: str = None) -> dict:
        """
        Get ticker(s) - PUBLIC endpoint, no auth needed
        
        Args:
            inst_id: Instrument ID (e.g., "BTC-USDT"). If None, returns all.
        """
        endpoint = "/api/v1/market/tickers"
        params = {}
        if inst_id:
            params['instId'] = inst_id
        
        return self._make_request(endpoint, params)
    
    def get_candlesticks(self, inst_id: str = "BTC-USDT", 
                         bar: str = "15m",
                         limit: int = 100,
                         after: int = None,
                         before: int = None) -> pd.DataFrame:
        """
        Get candlestick data - PUBLIC endpoint, no auth needed
        
        Args:
            inst_id: Instrument ID (e.g., "BTC-USDT")
            bar: Bar size (1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 8H, 12H, 1D, 3D, 1W, 1M)
            limit: Number of candles (max 100)
            after: Pagination - return results after this timestamp
            before: Pagination - return results before this timestamp
            
        Returns:
            DataFrame with OHLCV data
        """
        endpoint = "/api/v1/market/candles"
        
        params = {
            'instId': inst_id,
            'bar': bar,
            'limit': min(limit, 100)
        }
        
        if after:
            params['after'] = after
        if before:
            params['before'] = before
        
        data = self._make_request(endpoint, params)
        
        if not data or data.get('code') != '0':
            error_msg = data.get('msg', 'Unknown error') if data else 'No response'
            print(f"[ERROR] API error: {error_msg}")
            return pd.DataFrame()
        
        candles = data.get('data', [])
        
        if not candles:
            return pd.DataFrame()
        
        # Blofin returns: [timestamp, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        columns = ['timestamp', 'open', 'high', 'low', 'close', 
                   'volume', 'vol_ccy', 'vol_quote', 'confirm']
        
        # Handle varying column counts
        df = pd.DataFrame(candles)
        if len(df.columns) >= 5:
            df.columns = columns[:len(df.columns)]
        
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        df.set_index('timestamp', inplace=True)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # Keep only OHLCV columns
        keep_cols = [c for c in ['open', 'high', 'low', 'close', 'volume'] if c in df.columns]
        df = df[keep_cols]
        df = df.sort_index()
        
        return df
    
    def fetch_historical_data(self, symbol: str = "BTC-USDT",
                              interval: str = "15m", 
                              days: int = 30) -> pd.DataFrame:
        """
        Fetch multiple days of historical data
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            interval: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D)
            days: Number of days to fetch
            
        Returns:
            DataFrame with all historical data
        """
        print(f"[DATA] Fetching {days} days of {interval} data for {symbol}...")
        
        all_data = []
        
        # Calculate how many candles we need
        interval_minutes = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1H': 60, '2H': 120, '4H': 240, '6H': 360, '8H': 480, '12H': 720,
            '1D': 1440, '3D': 4320, '1W': 10080
        }
        
        minutes = interval_minutes.get(interval, 15)
        candles_per_day = 1440 // minutes
        total_candles_needed = days * candles_per_day
        
        # Fetch in batches of 100 (API limit)
        fetched = 0
        after_ts = None  # For pagination
        
        while fetched < total_candles_needed:
            df = self.get_candlesticks(
                inst_id=symbol,
                bar=interval,
                limit=100,
                after=after_ts
            )
            
            if df.empty:
                print(f"[WARNING] No more data available")
                break
            
            all_data.append(df)
            fetched += len(df)
            
            # Get oldest timestamp for next pagination
            oldest_ts = int(df.index[0].timestamp() * 1000)
            after_ts = oldest_ts
            
            print(f"  Fetched {fetched}/{total_candles_needed} candles...")
            
            # Small delay to avoid rate limiting
            time.sleep(0.1)
            
            # Safety check - if we got less than requested, we've hit the end
            if len(df) < 100:
                break
        
        if not all_data:
            print("[ERROR] No data fetched!")
            return pd.DataFrame()
        
        # Combine all data
        result = pd.concat(all_data)
        result = result[~result.index.duplicated(keep='first')]
        result = result.sort_index()
        
        print(f"[OK] Fetched {len(result)} candles from {result.index[0]} to {result.index[-1]}")
        
        return result
    
    def test_connection(self) -> bool:
        """Test API connection using public endpoint"""
        print("[TEST] Testing Blofin connection...")
        
        try:
            data = self.get_tickers("BTC-USDT")
            
            if data and data.get('code') == '0' and data.get('data'):
                ticker = data['data'][0]
                last_price = float(ticker.get('last', 0))
                print(f"[OK] Connected to Blofin")
                print(f"     BTC-USDT Price: ${last_price:,.2f}")
                return True
            else:
                error_msg = data.get('msg', 'Unknown error') if data else 'No response'
                print(f"[ERROR] API returned: {error_msg}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False


def fetch_blofin_data(symbol: str = "BTC-USDT", 
                      interval: str = "15m",
                      days: int = 30) -> pd.DataFrame:
    """
    Convenience function to fetch Blofin data
    
    Note: Public endpoints don't require API keys!
    """
    fetcher = BlofinDataFetcher()
    return fetcher.fetch_historical_data(symbol, interval, days)


if __name__ == "__main__":
    # Test the fetcher - no API keys needed for public data!
    fetcher = BlofinDataFetcher()
    
    if fetcher.test_connection():
        print("\n[DATA] Fetching sample data...")
        df = fetcher.fetch_historical_data("BTC-USDT", "15m", 7)
        
        if not df.empty:
            print(f"\nFirst 5 candles:")
            print(df.head())
            print(f"\nLast 5 candles:")
            print(df.tail())
            print(f"\nPrice range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
