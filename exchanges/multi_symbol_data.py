"""
Multi-Symbol Data Fetcher
---------------------------
Fetches OHLCV for the full cross-sectional universe and aligns it into a
single price panel (rows=timestamp, columns=symbol).

PATCH NOTES:
- resolve_symbol() now branches per exchange instead of assuming the MEXC/
  CCXT unified perp format everywhere. Blofin's REST API uses dash-separated
  instIds ("BTC-USDT"), Hyperliquid uses bare coin symbols ("BTC"), and MEXC
  via ccxt uses unified linear-perp symbols ("BTC/USDT:USDT").
- fetch_price_panel() now routes Blofin through BlofinDataFetcher (REST,
  public endpoints, no auth needed) instead of BlofinConnector.fetch_ohlcv,
  because BlofinConnector silently falls back to a no-op stub when
  ccxt.blofin isn't installed -- it was returning empty data with no error.
"""
import pandas as pd
import time
import logging
import math
from typing import List, Dict

from exchanges.connectors import ExchangeConnector
from exchanges.blofin_data import BlofinDataFetcher

logger = logging.getLogger(__name__)

_BLOFIN_BAR_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "8h": "8H", "12h": "12H",
    "1d": "1D", "3d": "3D", "1w": "1W",
}
_HOURS_PER_BAR = {
    "1m": 1/60, "3m": 3/60, "5m": 5/60, "15m": 15/60, "30m": 30/60,
    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "8h": 8, "12h": 12, "1d": 24,
}


def resolve_symbol(base: str, quote: str, exchange_name: str) -> str:
    """Map a base asset (e.g. 'BTC') to the exchange-specific instrument ID."""
    ex = exchange_name.lower()
    if ex == "hyperliquid":
        return base
    if ex == "blofin":
        return f"{base}-{quote}"          # Blofin REST instId convention
    return f"{base}/{quote}:{quote}"       # CCXT unified linear-perp (MEXC etc.)


def fetch_price_panel(connector: ExchangeConnector,
                       universe: List[str],
                       quote: str = "USDT",
                       timeframe: str = "1h",
                       limit: int = 1500,
                       exchange_name: str = "mexc",
                       request_delay_s: float = 0.2) -> pd.DataFrame:
    """
    Fetch OHLCV for every symbol in `universe`, return a close-price panel
    aligned on a shared timestamp index. Missing bars are left as NaN.
    """
    series_by_symbol: Dict[str, pd.Series] = {}
    ex = exchange_name.lower()

    if ex == "blofin":
        # Route around the broken CCXT wrapper -- use the working public
        # REST client directly. No API keys required for candlestick data.
        fetcher = BlofinDataFetcher()
        bar = _BLOFIN_BAR_MAP.get(timeframe, "1H")
        hours_per_bar = _HOURS_PER_BAR.get(timeframe, 1)
        days_needed = max(1, math.ceil((limit * hours_per_bar) / 24))

        for base in universe:
            symbol = resolve_symbol(base, quote, ex)
            try:
                df = fetcher.fetch_historical_data(symbol=symbol, interval=bar, days=days_needed)
                if df.empty:
                    logger.warning(f"No Blofin data for {symbol}, skipping")
                    continue
                series_by_symbol[base] = df["close"]
            except Exception as e:
                logger.error(f"Failed to fetch {symbol} from Blofin: {e}")
            time.sleep(request_delay_s)
    else:
        for base in universe:
            symbol = resolve_symbol(base, quote, ex)
            try:
                df = connector.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
                if df is None or df.empty:
                    logger.warning(f"No data returned for {symbol}, skipping")
                    continue
                series_by_symbol[base] = df["close"]
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
            time.sleep(request_delay_s)

    if not series_by_symbol:
        raise RuntimeError("No symbols returned data — check connector/universe/timeframe")

    panel = pd.DataFrame(series_by_symbol).sort_index()
    return panel


def fetch_current_prices(connector: ExchangeConnector,
                          universe: List[str],
                          quote: str = "USDT",
                          exchange_name: str = "mexc") -> Dict[str, float]:
    """Fresh last-price snapshot per symbol, used for live risk checks."""
    prices = {}
    ex = exchange_name.lower()

    if ex == "blofin":
        fetcher = BlofinDataFetcher()
        for base in universe:
            symbol = resolve_symbol(base, quote, ex)
            try:
                data = fetcher.get_tickers(symbol)
                if data and data.get("code") == "0" and data.get("data"):
                    prices[base] = float(data["data"][0]["last"])
            except Exception as e:
                logger.error(f"Failed to fetch current price for {symbol}: {e}")
        return prices

    for base in universe:
        symbol = resolve_symbol(base, quote, ex)
        try:
            df = connector.fetch_ohlcv(symbol=symbol, timeframe="1m", limit=1)
            if not df.empty:
                prices[base] = float(df["close"].iloc[-1])
        except Exception as e:
            logger.error(f"Failed to fetch current price for {symbol}: {e}")
    return prices
