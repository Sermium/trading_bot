"""
Main Trading Bot Runner
Orchestrates strategy execution and position management
"""
import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges.connectors import ExchangeConnector, get_connector, Position, OrderResult
from strategies.scalping_strategy import ScalpingStrategy, AdvancedScalpingStrategy, Signal, TradeSignal
from config.settings import TradingSettings, SCALPING_CONFIGS, Timeframe, Exchange

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TradingState:
    """Current trading state"""
    is_running: bool = False
    current_position: Optional[Position] = None
    daily_trades: int = 0
    daily_pnl: float = 0.0
    last_signal: Optional[TradeSignal] = None
    last_trade_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class TradeRecord:
    """Record of executed trade"""
    timestamp: datetime
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    status: str = "open"


class TradingBot:
    """
    Main trading bot class
    Manages strategy execution, position tracking, and risk management
    """
    
    def __init__(self, 
                 settings: TradingSettings,
                 api_key: str = "",
                 api_secret: str = "",
                 passphrase: str = "",
                 testnet: bool = True):
        """
        Initialize trading bot
        
        Args:
            settings: Trading configuration
            api_key: Exchange API key
            api_secret: Exchange API secret
            passphrase: Exchange passphrase (if required)
            testnet: Use testnet/sandbox mode
        """
        self.settings = settings
        self.testnet = testnet
        
        # Initialize exchange connector
        self.connector = get_connector(
            exchange=settings.exchange.value,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet
        )
        
        # Initialize strategy
        self.strategy = AdvancedScalpingStrategy(
            stoch_rsi_settings={
                'rsi_period': settings.stoch_rsi.rsi_period,
                'stoch_period': settings.stoch_rsi.stoch_period,
                'k_period': settings.stoch_rsi.k_period,
                'd_period': settings.stoch_rsi.d_period
            },
            macd_settings={
                'fast_period': settings.macd.fast_period,
                'slow_period': settings.macd.slow_period,
                'signal_period': settings.macd.signal_period
            },
            oversold=settings.stoch_rsi.oversold,
            overbought=settings.stoch_rsi.overbought,
            use_trend_filter=settings.use_trend_filter,
            trend_ema_period=settings.trend_ema_period,
            use_volume_filter=settings.use_volume_filter,
            volume_threshold=settings.volume_threshold,
            require_macd_confirmation=settings.require_macd_confirmation
        )
        
        # Trading state
        self.state = TradingState()
        self.trade_history: List[TradeRecord] = []
        
        # Timing
        self.timeframe_seconds = self._get_timeframe_seconds()
        
    def _get_timeframe_seconds(self) -> int:
        """Convert timeframe to seconds"""
        tf_map = {
            Timeframe.M1: 60,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.M30: 1800,
            Timeframe.H1: 3600
        }
        return tf_map.get(self.settings.timeframe, 300)
    
    def _get_symbol(self) -> str:
        """Get symbol format for exchange"""
        exchange = self.settings.exchange
        
        if exchange == Exchange.HYPERLIQUID:
            return "BTC"
        elif exchange == Exchange.BLOFIN:
            return "BTC-USDT"
        else:  # MEXC and others
            return "BTC/USDT:USDT"
    
    async def start(self):
        """Start the trading bot"""
        logger.info(f"Starting trading bot on {self.settings.exchange.value}")
        logger.info(f"Symbol: {self.settings.symbol}, Timeframe: {self.settings.timeframe.value}")
        logger.info(f"Leverage: {self.settings.risk.leverage}x")
        logger.info(f"Testnet: {self.testnet}")
        
        try:
            # Connect to exchange
            self.connector.connect()
            
            # Set leverage
            symbol = self._get_symbol()
            self.connector.set_leverage(symbol, self.settings.risk.leverage)
            
            # Get initial balance
            balance = self.connector.get_balance()
            logger.info(f"Account balance: ${balance.get('total', 0):,.2f}")
            
            self.state.is_running = True
            
            # Main trading loop
            await self._trading_loop()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            self.state.errors.append(str(e))
            raise
    
    async def stop(self):
        """Stop the trading bot"""
        logger.info("Stopping trading bot...")
        self.state.is_running = False
        
        # Close any open position
        if self.state.current_position:
            logger.info("Closing open position...")
            symbol = self._get_symbol()
            self.connector.close_position(symbol)
    
    async def _trading_loop(self):
        """Main trading loop"""
        symbol = self._get_symbol()
        
        while self.state.is_running:
            try:
                # Check daily limits
                if self._check_daily_limits():
                    logger.warning("Daily limits reached, pausing trading")
                    await asyncio.sleep(60)
                    continue
                
                # Fetch latest data
                df = self.connector.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=self.settings.timeframe.value,
                    limit=200
                )
                
                if df.empty:
                    logger.warning("No data received, retrying...")
                    await asyncio.sleep(5)
                    continue
                
                # Prepare data with indicators
                df = self.strategy.prepare_data(df)
                
                # Check current position
                self.state.current_position = self.connector.get_position(symbol)
                
                # Generate signal
                signal = self.strategy.generate_signal(df)
                
                if signal:
                    self.state.last_signal = signal
                    await self._process_signal(signal, symbol)
                
                # Check for position management (SL/TP)
                if self.state.current_position:
                    await self._manage_position(df.iloc[-1])
                
                # Wait for next candle
                await self._wait_for_next_candle()
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                self.state.errors.append(str(e))
                await asyncio.sleep(10)
    
    async def _process_signal(self, signal: TradeSignal, symbol: str):
        """Process trading signal"""
        logger.info(f"Signal received: {signal.signal.name} | Confidence: {signal.confidence:.1f}% | {signal.reason}")
        
        # Skip if we already have a position in same direction
        if self.state.current_position:
            current_side = self.state.current_position.side
            signal_side = 'long' if signal.signal == Signal.LONG else 'short'
            
            if current_side == signal_side:
                logger.info("Already in position, skipping signal")
                return
            else:
                # Close opposite position first
                logger.info(f"Closing {current_side} position for reversal")
                self.connector.close_position(symbol)
                self.state.current_position = None
        
        # Open new position
        await self._open_position(signal, symbol)
    
    async def _open_position(self, signal: TradeSignal, symbol: str):
        """Open a new position"""
        try:
            # Calculate position size
            balance = self.connector.get_balance()
            capital = balance.get('free', 0)
            
            if capital <= 0:
                logger.error("Insufficient balance")
                return
            
            # Position sizing
            capital_to_use = capital * (self.settings.risk.capital_percentage / 100)
            position_value = capital_to_use * self.settings.risk.leverage
            position_size = position_value / signal.price
            
            # Determine side
            side = 'buy' if signal.signal == Signal.LONG else 'sell'
            
            logger.info(f"Opening {side.upper()} position | Size: {position_size:.6f} | Price: ${signal.price:,.2f}")
            
            # Place order
            result = self.connector.place_market_order(symbol, side, position_size)
            
            if result.status in ['filled', 'closed']:
                logger.info(f"Position opened successfully | Order ID: {result.order_id}")
                
                # Record trade
                self.trade_history.append(TradeRecord(
                    timestamp=datetime.now(),
                    side=side,
                    entry_price=result.price or signal.price
                ))
                
                self.state.daily_trades += 1
                self.state.last_trade_time = datetime.now()
            else:
                logger.warning(f"Order not filled: {result.status}")
                
        except Exception as e:
            logger.error(f"Error opening position: {e}")
    
    async def _manage_position(self, current_bar):
        """Manage open position - check SL/TP"""
        if not self.state.current_position:
            return
        
        pos = self.state.current_position
        current_price = current_bar['close']
        
        # Calculate SL/TP levels
        if pos.side == 'long':
            stop_loss = pos.entry_price * (1 - self.settings.risk.stop_loss_pct / 100)
            take_profit = pos.entry_price * (1 + self.settings.risk.take_profit_pct / 100)
            
            if current_price <= stop_loss:
                logger.info(f"Stop loss triggered at ${current_price:,.2f}")
                await self._close_position("Stop Loss")
            elif current_price >= take_profit:
                logger.info(f"Take profit triggered at ${current_price:,.2f}")
                await self._close_position("Take Profit")
        else:  # Short
            stop_loss = pos.entry_price * (1 + self.settings.risk.stop_loss_pct / 100)
            take_profit = pos.entry_price * (1 - self.settings.risk.take_profit_pct / 100)
            
            if current_price >= stop_loss:
                logger.info(f"Stop loss triggered at ${current_price:,.2f}")
                await self._close_position("Stop Loss")
            elif current_price <= take_profit:
                logger.info(f"Take profit triggered at ${current_price:,.2f}")
                await self._close_position("Take Profit")
    
    async def _close_position(self, reason: str):
        """Close current position"""
        symbol = self._get_symbol()
        
        try:
            result = self.connector.close_position(symbol)
            
            if result:
                logger.info(f"Position closed | Reason: {reason}")
                
                # Update last trade record
                if self.trade_history:
                    last_trade = self.trade_history[-1]
                    if last_trade.status == "open":
                        last_trade.exit_price = result.price
                        last_trade.status = "closed"
                        
                        # Calculate PnL
                        if last_trade.side == 'buy':
                            pnl = (result.price - last_trade.entry_price) / last_trade.entry_price * 100
                        else:
                            pnl = (last_trade.entry_price - result.price) / last_trade.entry_price * 100
                        
                        pnl *= self.settings.risk.leverage
                        last_trade.pnl = pnl
                        self.state.daily_pnl += pnl
                        
                        logger.info(f"Trade P&L: {pnl:+.2f}%")
                
                self.state.current_position = None
                
        except Exception as e:
            logger.error(f"Error closing position: {e}")
    
    def _check_daily_limits(self) -> bool:
        """Check if daily limits are exceeded"""
        # Reset at midnight
        if self.state.last_trade_time:
            if self.state.last_trade_time.date() < datetime.now().date():
                self.state.daily_trades = 0
                self.state.daily_pnl = 0.0
        
        # Check trade limit
        if self.state.daily_trades >= self.settings.risk.max_daily_trades:
            return True
        
        # Check daily loss limit
        if self.state.daily_pnl <= -self.settings.risk.max_daily_loss_pct:
            return True
        
        return False
    
    async def _wait_for_next_candle(self):
        """Wait until next candle"""
        now = datetime.now()
        
        # Calculate seconds until next candle
        seconds_into_candle = (now.minute * 60 + now.second) % self.timeframe_seconds
        seconds_until_next = self.timeframe_seconds - seconds_into_candle
        
        # Add small buffer
        wait_time = max(1, seconds_until_next + 2)
        
        logger.debug(f"Waiting {wait_time}s for next candle")
        await asyncio.sleep(wait_time)
    
    def get_status(self) -> Dict:
        """Get current bot status"""
        return {
            'is_running': self.state.is_running,
            'exchange': self.settings.exchange.value,
            'symbol': self.settings.symbol,
            'timeframe': self.settings.timeframe.value,
            'leverage': self.settings.risk.leverage,
            'position': {
                'side': self.state.current_position.side if self.state.current_position else None,
                'size': self.state.current_position.size if self.state.current_position else 0,
                'entry_price': self.state.current_position.entry_price if self.state.current_position else 0,
                'unrealized_pnl': self.state.current_position.unrealized_pnl if self.state.current_position else 0
            } if self.state.current_position else None,
            'daily_trades': self.state.daily_trades,
            'daily_pnl': f"{self.state.daily_pnl:+.2f}%",
            'last_signal': {
                'type': self.state.last_signal.signal.name if self.state.last_signal else None,
                'confidence': self.state.last_signal.confidence if self.state.last_signal else None,
                'price': self.state.last_signal.price if self.state.last_signal else None
            } if self.state.last_signal else None,
            'total_trades': len(self.trade_history),
            'errors': self.state.errors[-5:] if self.state.errors else []
        }


async def run_bot(settings: TradingSettings, 
                  api_key: str = "",
                  api_secret: str = "",
                  passphrase: str = "",
                  testnet: bool = True):
    """Run the trading bot"""
    bot = TradingBot(
        settings=settings,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        testnet=testnet
    )
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    # Example usage
    from config.settings import SCALPING_CONFIGS, Exchange
    
    # Use 5-minute scalping config
    settings = SCALPING_CONFIGS["5m"]
    settings.exchange = Exchange.MEXC
    
    # Run bot (requires API keys)
    asyncio.run(run_bot(
        settings=settings,
        api_key="YOUR_API_KEY",
        api_secret="YOUR_API_SECRET",
        testnet=True
    ))
