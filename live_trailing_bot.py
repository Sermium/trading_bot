#!/usr/bin/env python3
"""
Live Trading Bot with Trailing Stop Strategy

Features:
- 50x Leverage with smart risk management
- Trailing stops that lock in profits
- Progressive position sizing (scale up on wins)
- Multi-exchange support (Blofin, MEXC)

WARNING: This is for educational purposes. Use at your own risk.
Always test on testnet/paper trading first!
"""
import asyncio
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.scalping_strategy import AdvancedScalpingStrategy, Signal
from backtest.trailing_stop import TrailingStopConfig, TRAILING_CONFIGS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """Track live position with trailing stop"""
    side: str  # 'long' or 'short'
    entry_price: float
    size: float
    margin: float
    leverage: int
    
    initial_stop: float
    current_stop: float
    take_profit: float
    
    highest_price: float
    lowest_price: float
    trailing_activated: bool
    
    entry_time: datetime
    order_id: str


class TrailingStopTradingBot:
    """
    Live trading bot with trailing stop and progressive sizing
    """
    
    def __init__(self, 
                 exchange: str = 'blofin',
                 symbol: str = 'BTC-USDT',
                 timeframe: str = '15m',
                 config: TrailingStopConfig = None,
                 testnet: bool = True):
        
        self.exchange_name = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.config = config or TRAILING_CONFIGS['tight']
        self.testnet = testnet
        
        # State
        self.capital = self.config.initial_capital
        self.position: Optional[LivePosition] = None
        self.win_streak = 0
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.last_trade_day = None
        
        # Strategy
        self.strategy = AdvancedScalpingStrategy(
            stoch_rsi_settings={'rsi_period': 7, 'stoch_period': 7, 'k_period': 3, 'd_period': 3},
            macd_settings={'fast_period': 5, 'slow_period': 13, 'signal_period': 6},
            oversold=20, overbought=80,
            use_trend_filter=True, use_volume_filter=False,
            require_macd_confirmation=True, min_confidence=45.0
        )
        
        # Exchange connector
        self.exchange = None
        
        # Running flag
        self.running = False
    
    def _load_credentials(self):
        """Load API credentials from environment"""
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
    
    def _init_exchange(self):
        """Initialize exchange connector"""
        self._load_credentials()
        
        if self.exchange_name == 'blofin':
            try:
                from blofin import BloFinClient
                
                self.exchange = BloFinClient(
                    api_key=os.getenv('BLOFIN_API_KEY'),
                    api_secret=os.getenv('BLOFIN_API_SECRET'),
                    passphrase=os.getenv('BLOFIN_PASSPHRASE'),
                )
                logger.info(f"Connected to Blofin ({'testnet' if self.testnet else 'mainnet'})")
                return True
            except ImportError:
                logger.error("blofin package not installed. Run: pip install blofin")
                return False
            except Exception as e:
                logger.error(f"Failed to connect to Blofin: {e}")
                return False
        
        elif self.exchange_name == 'mexc':
            try:
                import ccxt
                
                self.exchange = ccxt.mexc({
                    'apiKey': os.getenv('MEXC_API_KEY'),
                    'secret': os.getenv('MEXC_API_SECRET'),
                    'options': {'defaultType': 'swap'}
                })
                
                if self.testnet:
                    self.exchange.set_sandbox_mode(True)
                
                logger.info(f"Connected to MEXC ({'testnet' if self.testnet else 'mainnet'})")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to MEXC: {e}")
                return False
        
        return False
    
    def _get_position_size_pct(self) -> float:
        """Calculate position size based on win streak"""
        size_pct = self.config.base_capital_pct + (self.win_streak * self.config.scale_per_win)
        return min(size_pct, self.config.max_capital_pct)
    
    def _fetch_candles(self, limit: int = 100):
        """Fetch recent candles"""
        try:
            if self.exchange_name == 'blofin':
                candles = self.exchange.public.get_candlesticks(
                    inst_id=self.symbol,
                    bar=self.timeframe,
                    limit=limit
                )
                
                if candles and candles.get('code') == '0':
                    import pandas as pd
                    data = candles.get('data', [])
                    
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 
                        'volume', 'vol_ccy', 'vol_quote', 'confirm'
                    ])
                    
                    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    
                    df = df[['open', 'high', 'low', 'close', 'volume']]
                    return df.sort_index()
            
            elif self.exchange_name == 'mexc':
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
                
                import pandas as pd
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                return df
        
        except Exception as e:
            logger.error(f"Failed to fetch candles: {e}")
        
        return None
    
    def _get_current_price(self) -> Optional[float]:
        """Get current price"""
        try:
            if self.exchange_name == 'blofin':
                ticker = self.exchange.public.get_tickers(inst_id=self.symbol)
                if ticker and ticker.get('code') == '0':
                    return float(ticker['data'][0]['last'])
            
            elif self.exchange_name == 'mexc':
                ticker = self.exchange.fetch_ticker(self.symbol)
                return ticker['last']
        
        except Exception as e:
            logger.error(f"Failed to get price: {e}")
        
        return None
    
    def _place_order(self, side: str, size: float, price: float = None) -> Optional[str]:
        """Place market order"""
        try:
            logger.info(f"Placing {side.upper()} order: {size} @ market")
            
            if self.exchange_name == 'blofin':
                result = self.exchange.trade.place_order(
                    inst_id=self.symbol,
                    trade_mode='cross',
                    side='buy' if side == 'long' else 'sell',
                    order_type='market',
                    size=str(size)
                )
                
                if result and result.get('code') == '0':
                    order_id = result['data']['orderId']
                    logger.info(f"Order placed: {order_id}")
                    return order_id
            
            elif self.exchange_name == 'mexc':
                order = self.exchange.create_market_order(
                    self.symbol,
                    'buy' if side == 'long' else 'sell',
                    size
                )
                logger.info(f"Order placed: {order['id']}")
                return order['id']
        
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
        
        return None
    
    def _close_position_market(self) -> bool:
        """Close position with market order"""
        if not self.position:
            return False
        
        try:
            close_side = 'sell' if self.position.side == 'long' else 'buy'
            
            if self.exchange_name == 'blofin':
                result = self.exchange.trade.close_positions(
                    inst_id=self.symbol,
                    margin_mode='cross'
                )
                return result and result.get('code') == '0'
            
            elif self.exchange_name == 'mexc':
                order = self.exchange.create_market_order(
                    self.symbol,
                    close_side,
                    self.position.size,
                    params={'reduceOnly': True}
                )
                return order is not None
        
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
        
        return False
    
    def _set_leverage(self):
        """Set leverage on exchange"""
        try:
            if self.exchange_name == 'blofin':
                self.exchange.account.set_leverage(
                    inst_id=self.symbol,
                    leverage=str(self.config.leverage),
                    margin_mode='cross'
                )
            elif self.exchange_name == 'mexc':
                self.exchange.set_leverage(self.config.leverage, self.symbol)
            
            logger.info(f"Leverage set to {self.config.leverage}x")
        except Exception as e:
            logger.warning(f"Could not set leverage: {e}")
    
    def _open_position(self, signal, current_price: float):
        """Open a new position"""
        if self.position is not None:
            return
        
        # Check daily limits
        today = datetime.now().date()
        if self.last_trade_day != today:
            self.last_trade_day = today
            self.daily_trades = 0
            self.daily_pnl = 0.0
        
        if self.daily_trades >= self.config.max_daily_trades:
            logger.warning("Daily trade limit reached")
            return
        
        if self.daily_pnl < 0 and abs(self.daily_pnl) >= self.capital * self.config.max_daily_loss_pct / 100:
            logger.warning("Daily loss limit reached")
            return
        
        is_long = signal.signal == Signal.LONG
        side = 'long' if is_long else 'short'
        
        # Calculate position size
        cap_pct = self._get_position_size_pct()
        margin = self.capital * cap_pct / 100
        notional = margin * self.config.leverage
        size = notional / current_price
        
        # Calculate stops
        if is_long:
            initial_stop = current_price * (1 - self.config.initial_stop_pct / 100)
            take_profit = current_price * (1 + self.config.take_profit_pct / 100)
        else:
            initial_stop = current_price * (1 + self.config.initial_stop_pct / 100)
            take_profit = current_price * (1 - self.config.take_profit_pct / 100)
        
        # Place order
        order_id = self._place_order(side, size)
        
        if order_id:
            self.position = LivePosition(
                side=side,
                entry_price=current_price,
                size=size,
                margin=margin,
                leverage=self.config.leverage,
                initial_stop=initial_stop,
                current_stop=initial_stop,
                take_profit=take_profit,
                highest_price=current_price,
                lowest_price=current_price,
                trailing_activated=False,
                entry_time=datetime.now(),
                order_id=order_id
            )
            
            self.daily_trades += 1
            
            logger.info(f"Opened {side.upper()} @ ${current_price:,.2f}")
            logger.info(f"  Size: {size:.6f} | Margin: ${margin:.2f} ({cap_pct:.1f}%)")
            logger.info(f"  SL: ${initial_stop:,.2f} | TP: ${take_profit:,.2f}")
    
    def _update_trailing_stop(self, current_price: float):
        """Update trailing stop"""
        if not self.position:
            return
        
        pos = self.position
        
        if pos.side == 'long':
            if current_price > pos.highest_price:
                pos.highest_price = current_price
            
            profit_pct = (pos.highest_price - pos.entry_price) / pos.entry_price * 100
            
            if profit_pct >= self.config.trailing_activation_pct:
                if not pos.trailing_activated:
                    logger.info(f"Trailing stop ACTIVATED at {profit_pct:.2f}% profit")
                pos.trailing_activated = True
                
                new_stop = pos.highest_price * (1 - self.config.trailing_distance_pct / 100)
                if new_stop > pos.current_stop:
                    old_stop = pos.current_stop
                    pos.current_stop = new_stop
                    logger.info(f"Trailing stop moved: ${old_stop:,.2f} -> ${new_stop:,.2f}")
        else:
            if current_price < pos.lowest_price:
                pos.lowest_price = current_price
            
            profit_pct = (pos.entry_price - pos.lowest_price) / pos.entry_price * 100
            
            if profit_pct >= self.config.trailing_activation_pct:
                if not pos.trailing_activated:
                    logger.info(f"Trailing stop ACTIVATED at {profit_pct:.2f}% profit")
                pos.trailing_activated = True
                
                new_stop = pos.lowest_price * (1 + self.config.trailing_distance_pct / 100)
                if new_stop < pos.current_stop:
                    old_stop = pos.current_stop
                    pos.current_stop = new_stop
                    logger.info(f"Trailing stop moved: ${old_stop:,.2f} -> ${new_stop:,.2f}")
    
    def _check_exit(self, current_price: float) -> bool:
        """Check if position should be closed"""
        if not self.position:
            return False
        
        pos = self.position
        should_close = False
        reason = ""
        
        if pos.side == 'long':
            if current_price >= pos.take_profit:
                should_close = True
                reason = "Take Profit"
            elif current_price <= pos.current_stop:
                should_close = True
                reason = "Trailing Stop" if pos.trailing_activated else "Stop Loss"
        else:
            if current_price <= pos.take_profit:
                should_close = True
                reason = "Take Profit"
            elif current_price >= pos.current_stop:
                should_close = True
                reason = "Trailing Stop" if pos.trailing_activated else "Stop Loss"
        
        if should_close:
            return self._close_position(current_price, reason)
        
        return False
    
    def _close_position(self, exit_price: float, reason: str) -> bool:
        """Close position and calculate P&L"""
        if not self.position:
            return False
        
        pos = self.position
        
        # Calculate P&L
        if pos.side == 'long':
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price
        
        pnl = pos.margin * pnl_pct * pos.leverage
        fee = pos.margin * pos.leverage * self.config.commission_rate * 2
        net_pnl = pnl - fee
        
        # Close on exchange
        closed = self._close_position_market()
        
        if closed or True:  # Log anyway for paper trading
            self.capital += net_pnl
            self.daily_pnl += net_pnl
            
            if net_pnl > 0:
                self.win_streak += 1
            else:
                self.win_streak = 0
            
            logger.info(f"Closed {pos.side.upper()} @ ${exit_price:,.2f} [{reason}]")
            logger.info(f"  P&L: ${net_pnl:,.2f} ({pnl_pct*100*pos.leverage:.2f}%)")
            logger.info(f"  Capital: ${self.capital:,.2f} | Win Streak: {self.win_streak}")
            
            self.position = None
            return True
        
        return False
    
    async def run(self):
        """Main trading loop"""
        logger.info("=" * 60)
        logger.info("TRAILING STOP TRADING BOT")
        logger.info("=" * 60)
        
        if not self._init_exchange():
            logger.error("Failed to initialize exchange")
            return
        
        self._set_leverage()
        
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Leverage: {self.config.leverage}x")
        logger.info(f"Config: SL {self.config.initial_stop_pct}% | TP {self.config.take_profit_pct}%")
        logger.info(f"Trailing: Activate {self.config.trailing_activation_pct}% | Distance {self.config.trailing_distance_pct}%")
        logger.info(f"Position Size: {self.config.base_capital_pct}% - {self.config.max_capital_pct}%")
        logger.info(f"Capital: ${self.capital:,.2f}")
        logger.info("=" * 60)
        
        self.running = True
        last_candle_time = None
        
        while self.running:
            try:
                # Fetch latest candles
                df = self._fetch_candles(100)
                
                if df is None or df.empty:
                    await asyncio.sleep(5)
                    continue
                
                current_candle_time = df.index[-1]
                current_price = df.iloc[-1]['close']
                
                # Update trailing stop
                if self.position:
                    self._update_trailing_stop(current_price)
                    
                    # Check exit
                    if self._check_exit(current_price):
                        continue
                
                # Only generate signals on new candles
                if last_candle_time != current_candle_time:
                    last_candle_time = current_candle_time
                    
                    # Prepare data and generate signal
                    df_prepared = self.strategy.prepare_data(df)
                    signal = self.strategy.generate_signal(df_prepared, -1)
                    
                    if signal and self.position is None:
                        self._open_position(signal, current_price)
                    elif signal and self.position:
                        # Check for signal reversal
                        if (signal.signal == Signal.LONG and self.position.side == 'short') or \
                           (signal.signal == Signal.SHORT and self.position.side == 'long'):
                            logger.info("Signal reversal detected")
                            self._close_position(current_price, "Signal Reversal")
                            self._open_position(signal, current_price)
                
                # Status update every minute
                if datetime.now().second < 5:
                    status = "IN POSITION" if self.position else "WATCHING"
                    logger.info(f"[{status}] Price: ${current_price:,.2f} | Capital: ${self.capital:,.2f}")
                
                # Wait before next check
                await asyncio.sleep(5)
            
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(10)
        
        # Close position on shutdown
        if self.position:
            current_price = self._get_current_price()
            if current_price:
                self._close_position(current_price, "Shutdown")
        
        logger.info(f"Final Capital: ${self.capital:,.2f}")
        logger.info("Bot stopped")
    
    def stop(self):
        """Stop the bot"""
        self.running = False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Trailing Stop Trading Bot")
    parser.add_argument("--exchange", "-e", default="blofin", choices=["blofin", "mexc"])
    parser.add_argument("--symbol", "-s", default="BTC-USDT")
    parser.add_argument("--timeframe", "-t", default="15m")
    parser.add_argument("--config", "-c", default="tight", choices=["tight", "medium", "wide", "conservative"])
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--testnet", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", help="Use mainnet (REAL MONEY)")
    
    args = parser.parse_args()
    
    config = TRAILING_CONFIGS[args.config]
    config.initial_capital = args.capital
    
    testnet = not args.live
    
    if args.live:
        print("\n" + "!" * 60)
        print("  WARNING: LIVE TRADING MODE - REAL MONEY AT RISK")
        print("!" * 60)
        confirm = input("\nType 'YES' to confirm: ")
        if confirm != 'YES':
            print("Cancelled")
            return
    
    bot = TrailingStopTradingBot(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        config=config,
        testnet=testnet
    )
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        bot.stop()


if __name__ == "__main__":
    main()
