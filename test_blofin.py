#!/usr/bin/env python3
"""
Quick test script for Blofin connection
No API keys needed - uses public endpoints
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 50)
    print("  BLOFIN CONNECTION TEST")
    print("  (No API keys required)")
    print("=" * 50)
    
    try:
        from exchanges.blofin_data import BlofinDataFetcher
    except ImportError as e:
        print(f"\n[ERROR] Import failed: {e}")
        print("Make sure you're in the trading_bot directory")
        return False
    
    # Create fetcher (no API keys needed for public data)
    fetcher = BlofinDataFetcher()
    
    # Test connection
    print("\n1. Testing API connection...")
    if not fetcher.test_connection():
        print("\n[FAILED] Could not connect to Blofin API")
        print("Check your internet connection")
        return False
    
    # Fetch sample data
    print("\n2. Fetching sample candlestick data...")
    df = fetcher.get_candlesticks("BTC-USDT", "15m", 10)
    
    if df.empty:
        print("[FAILED] Could not fetch candlestick data")
        return False
    
    print(f"[OK] Got {len(df)} candles")
    print(f"\nSample data:")
    print(df)
    
    print("\n" + "=" * 50)
    print("  ALL TESTS PASSED!")
    print("  You can now run: python run_backtest_live.py")
    print("=" * 50)
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
