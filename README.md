# 🤖 BTC Scalping Bot - StochRSI + MACD Strategy

A professional automated trading bot for BTC perpetual futures scalping on multiple centralized exchanges (MEXC, Blofin, Hyperliquid).

## 📋 Table of Contents

- [Features](#features)
- [Strategy Overview](#strategy-overview)
- [Installation](#installation)
- [Configuration](#configuration)
- [Backtesting](#backtesting)
- [Live Trading](#live-trading)
- [Risk Management](#risk-management)
- [API Reference](#api-reference)

## ✨ Features

- **Multi-Exchange Support**: MEXC, Blofin, Hyperliquid
- **Advanced Scalping Strategy**: Combines StochRSI and MACD for high-probability entries
- **Multiple Timeframes**: 1m, 5m, 15m scalping configurations
- **Comprehensive Backtesting**: Full backtester with performance metrics
- **Parameter Optimization**: Grid search for optimal settings
- **Risk Management**: Stop-loss, take-profit, daily limits, max drawdown protection
- **Position Sizing**: Configurable leverage and capital allocation

## 📈 Strategy Overview

### Entry Rules

#### LONG Entry:
1. ✅ StochRSI K crosses above D (bullish crossover)
2. ✅ StochRSI K was below oversold level (e.g., 20)
3. ✅ MACD histogram is increasing (momentum building)
4. ✅ MACD line > signal line OR about to cross above
5. ⚡ (Optional) Price above trend EMA
6. ⚡ (Optional) Volume above average

#### SHORT Entry:
1. ✅ StochRSI K crosses below D (bearish crossover)
2. ✅ StochRSI K was above overbought level (e.g., 80)
3. ✅ MACD histogram is decreasing
4. ✅ MACD line < signal line OR about to cross below
5. ⚡ (Optional) Price below trend EMA
6. ⚡ (Optional) Volume above average

### Exit Rules

- **Stop Loss**: Configurable % from entry (default: 0.5%)
- **Take Profit**: Configurable % from entry (default: 1.0%)
- **Signal Reversal**: Close on opposite signal

### Indicator Settings by Timeframe

| Setting | 1m | 5m | 15m |
|---------|----|----|-----|
| RSI Period | 7 | 10 | 14 |
| Stoch Period | 7 | 10 | 14 |
| Oversold | 15 | 18 | 20 |
| Overbought | 85 | 82 | 80 |
| MACD Fast | 6 | 8 | 12 |
| MACD Slow | 13 | 17 | 26 |
| MACD Signal | 4 | 6 | 9 |

## 🚀 Installation

```bash
# Clone or copy the trading_bot directory
cd trading_bot

# Install dependencies
pip install -r requirements.txt

# For Hyperliquid support (optional)
pip install hyperliquid-python
```

## ⚙️ Configuration

### Basic Configuration

Edit `config/settings.py` or use pre-configured scalping profiles:

```python
from config.settings import SCALPING_CONFIGS, Exchange

# Use 5-minute scalping config
settings = SCALPING_CONFIGS["5m"]
settings.exchange = Exchange.MEXC

# Customize risk settings
settings.risk.leverage = 10
settings.risk.stop_loss_pct = 0.5
settings.risk.take_profit_pct = 1.0
settings.risk.capital_percentage = 10  # % of capital per trade
```

### Risk Settings

```python
@dataclass
class RiskSettings:
    leverage: int = 10              # Position leverage
    capital_percentage: float = 10  # % of capital per trade
    stop_loss_pct: float = 0.5      # Stop loss percentage
    take_profit_pct: float = 1.0    # Take profit percentage
    max_positions: int = 1          # Max concurrent positions
    max_daily_trades: int = 20      # Daily trade limit
    max_daily_loss_pct: float = 5.0 # Max daily loss limit
```

## 📊 Backtesting

### Quick Start

```bash
# Run backtest with default settings (5m timeframe, 30 days)
python run_backtest.py

# Run with specific parameters
python run_backtest.py --timeframe 5m --days 60 --capital 10000 --leverage 10

# Run parameter optimization
python run_backtest.py --optimize --days 30

# Use synthetic data for testing
python run_backtest.py --synthetic --days 30
```

### Programmatic Backtesting

```python
from run_backtest import fetch_historical_data, run_single_backtest

# Fetch data
df = fetch_historical_data(symbol="BTCUSDT", timeframe="5m", days=30)

# Run backtest
result = run_single_backtest(
    df,
    config_name="5m",
    initial_capital=10000,
    leverage=10,
    stop_loss_pct=0.5,
    take_profit_pct=1.0
)

# Print results
result.print_summary()

# Access metrics
print(f"Win Rate: {result.win_rate}%")
print(f"Profit Factor: {result.profit_factor}")
print(f"Sharpe Ratio: {result.sharpe_ratio}")
```

### Backtest Metrics

The backtester provides comprehensive metrics:

- **Performance**: Net P&L, Return %, Profit Factor
- **Trade Stats**: Win Rate, Avg Win/Loss, Best/Worst Trade
- **Risk Metrics**: Max Drawdown, Sharpe Ratio, Sortino Ratio, VaR
- **Time Analysis**: Avg Holding Time, Trade Distribution

## 🔴 Live Trading

### Setup API Keys

```python
# For MEXC
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"

# For Blofin (requires passphrase)
PASSPHRASE = "your_passphrase"

# For Hyperliquid (uses private key)
PRIVATE_KEY = "your_private_key"
```

### Start Live Bot

```python
import asyncio
from trading_bot import TradingBot
from config.settings import SCALPING_CONFIGS, Exchange

# Configure
settings = SCALPING_CONFIGS["5m"]
settings.exchange = Exchange.MEXC

# Create and run bot
bot = TradingBot(
    settings=settings,
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    testnet=True  # Start with testnet!
)

# Run
asyncio.run(bot.start())
```

### Monitor Bot Status

```python
status = bot.get_status()
print(f"Running: {status['is_running']}")
print(f"Position: {status['position']}")
print(f"Daily P&L: {status['daily_pnl']}")
print(f"Last Signal: {status['last_signal']}")
```

## ⚠️ Risk Management

### Built-in Protections

1. **Position Sizing**: Only risk configured % of capital per trade
2. **Stop Loss**: Automatic stop-loss on every position
3. **Daily Limits**: Max trades and max loss per day
4. **Leverage Control**: Configurable leverage with sensible defaults

### Recommended Settings for Beginners

```python
settings.risk.leverage = 5          # Lower leverage
settings.risk.capital_percentage = 5  # Smaller position size
settings.risk.stop_loss_pct = 0.5    # Tight stops
settings.risk.max_daily_loss_pct = 3  # Conservative daily limit
```

### ⚠️ Important Warnings

1. **Always start with testnet** before using real funds
2. **Backtest thoroughly** before live trading
3. **Start with small capital** to validate strategy
4. **Monitor the bot** - don't leave it unattended for long periods
5. **Crypto is volatile** - only trade what you can afford to lose

## 📚 API Reference

### Strategy Classes

```python
# Basic strategy
from strategies import ScalpingStrategy

strategy = ScalpingStrategy(
    stoch_rsi_settings={...},
    macd_settings={...},
    oversold=20,
    overbought=80
)

# Advanced strategy with divergence detection
from strategies import AdvancedScalpingStrategy

strategy = AdvancedScalpingStrategy(
    ...,
    min_confidence=60,
    use_divergence=True
)
```

### Exchange Connectors

```python
from exchanges import get_connector

# MEXC
connector = get_connector("mexc", api_key="...", api_secret="...")

# Blofin  
connector = get_connector("blofin", api_key="...", api_secret="...", passphrase="...")

# Hyperliquid
connector = get_connector("hyperliquid", api_key="private_key")
```

### Backtester

```python
from backtest import Backtester

backtester = Backtester(
    initial_capital=10000,
    commission_rate=0.0006,
    slippage_pct=0.01,
    leverage=10
)

result = backtester.run(df, strategy)
```

## 📁 Project Structure

```
trading_bot/
├── __init__.py
├── trading_bot.py          # Main bot runner
├── run_backtest.py         # Backtest runner script
├── requirements.txt
├── README.md
├── config/
│   ├── __init__.py
│   └── settings.py         # Configuration settings
├── strategies/
│   ├── __init__.py
│   ├── indicators.py       # Technical indicators
│   └── scalping_strategy.py # Strategy implementation
├── exchanges/
│   ├── __init__.py
│   └── connectors.py       # Exchange API connectors
└── backtest/
    ├── __init__.py
    └── engine.py           # Backtesting engine
```

## 🔄 Updates & Improvements

Potential enhancements:
- [ ] Add more indicators (Bollinger Bands, ATR for dynamic SL/TP)
- [ ] Implement trailing stop-loss
- [ ] Add sentiment analysis integration
- [ ] WebSocket for real-time data
- [ ] Telegram/Discord alerts
- [ ] Machine learning signal confirmation

## 📜 License

This software is provided for educational purposes. Use at your own risk.

## 🙏 Disclaimer

**Trading cryptocurrencies involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. This bot is provided as-is without any warranties. Always do your own research and never trade more than you can afford to lose.**
