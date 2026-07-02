"""
Exchange Connectors for CEX Integration
Supports: Blofin, MEXC, Hyperliquid
"""
import ccxt
import asyncio
import pandas as pd
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Order execution result"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    amount: float
    filled: float
    status: str
    timestamp: datetime
    fee: Optional[float] = None


@dataclass
class Position:
    """Current position info"""
    symbol: str
    side: str  # 'long' or 'short'
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    liquidation_price: float


class ExchangeConnector(ABC):
    """Abstract base class for exchange connectors"""
    
    def __init__(self, api_key: str = "", api_secret: str = "", 
                 passphrase: str = "", testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self.exchange = None
    
    @abstractmethod
    def connect(self):
        """Establish connection to exchange"""
        pass
    
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, 
                    limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV data"""
        pass
    
    @abstractmethod
    def place_market_order(self, symbol: str, side: str, 
                          amount: float) -> OrderResult:
        """Place market order"""
        pass
    
    @abstractmethod
    def place_limit_order(self, symbol: str, side: str, 
                         amount: float, price: float) -> OrderResult:
        """Place limit order"""
        pass
    
    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int):
        """Set position leverage"""
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position"""
        pass
    
    @abstractmethod
    def close_position(self, symbol: str) -> OrderResult:
        """Close entire position"""
        pass
    
    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """Get account balance"""
        pass
    
    def _ohlcv_to_dataframe(self, ohlcv: list) -> pd.DataFrame:
        """Convert OHLCV list to DataFrame"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df


class MEXCConnector(ExchangeConnector):
    """MEXC Futures connector"""
    
    def connect(self):
        """Connect to MEXC"""
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'sandbox': self.testnet,
            'options': {
                'defaultType': 'swap',  # For perpetual futures
            }
        }
        
        if self.testnet:
            # MEXC testnet
            config['urls'] = {
                'api': {
                    'public': 'https://contract.mexc.com',
                    'private': 'https://contract.mexc.com',
                }
            }
        
        self.exchange = ccxt.mexc(config)
        logger.info(f"Connected to MEXC {'testnet' if self.testnet else 'mainnet'}")
    
    def fetch_ohlcv(self, symbol: str = "BTC/USDT:USDT", 
                    timeframe: str = "5m", limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV candles"""
        if not self.exchange:
            self.connect()
        
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return self._ohlcv_to_dataframe(ohlcv)
    
    def place_market_order(self, symbol: str, side: str, 
                          amount: float) -> OrderResult:
        """Place market order"""
        order = self.exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount
        )
        
        return OrderResult(
            order_id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            order_type=order['type'],
            price=order.get('average', order.get('price', 0)),
            amount=order['amount'],
            filled=order.get('filled', 0),
            status=order['status'],
            timestamp=datetime.now(),
            fee=order.get('fee', {}).get('cost')
        )
    
    def place_limit_order(self, symbol: str, side: str, 
                         amount: float, price: float) -> OrderResult:
        """Place limit order"""
        order = self.exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=price
        )
        
        return OrderResult(
            order_id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            order_type=order['type'],
            price=price,
            amount=order['amount'],
            filled=order.get('filled', 0),
            status=order['status'],
            timestamp=datetime.now()
        )
    
    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for symbol"""
        self.exchange.set_leverage(leverage, symbol)
        logger.info(f"Set leverage to {leverage}x for {symbol}")
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position"""
        positions = self.exchange.fetch_positions([symbol])
        
        for pos in positions:
            if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                return Position(
                    symbol=pos['symbol'],
                    side=pos['side'],
                    size=float(pos['contracts']),
                    entry_price=float(pos.get('entryPrice', 0)),
                    mark_price=float(pos.get('markPrice', 0)),
                    unrealized_pnl=float(pos.get('unrealizedPnl', 0)),
                    leverage=int(pos.get('leverage', 1)),
                    liquidation_price=float(pos.get('liquidationPrice', 0))
                )
        return None
    
    def close_position(self, symbol: str) -> Optional[OrderResult]:
        """Close current position"""
        position = self.get_position(symbol)
        if not position:
            return None
        
        side = 'sell' if position.side == 'long' else 'buy'
        return self.place_market_order(symbol, side, position.size)
    
    def get_balance(self) -> Dict[str, float]:
        """Get account balance"""
        balance = self.exchange.fetch_balance()
        return {
            'total': balance.get('USDT', {}).get('total', 0),
            'free': balance.get('USDT', {}).get('free', 0),
            'used': balance.get('USDT', {}).get('used', 0)
        }


class BlofinConnector(ExchangeConnector):
    """Blofin Futures connector"""
    
    def connect(self):
        """Connect to Blofin"""
        # Blofin uses similar API structure
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.passphrase,  # Blofin requires passphrase
            'options': {
                'defaultType': 'swap',
            }
        }
        
        # Using generic ccxt for Blofin-like exchanges
        # Note: You may need blofin-specific SDK for full functionality
        self.exchange = ccxt.blofin(config) if hasattr(ccxt, 'blofin') else None
        
        if not self.exchange:
            logger.warning("Blofin not directly supported in ccxt, using custom implementation")
            # Fallback to custom implementation if needed
            self._setup_custom_blofin()
        
        logger.info(f"Connected to Blofin {'testnet' if self.testnet else 'mainnet'}")
    
    def _setup_custom_blofin(self):
        """Setup custom Blofin API calls"""
        # Placeholder for custom implementation
        pass
    
    def fetch_ohlcv(self, symbol: str = "BTC-USDT", 
                    timeframe: str = "5m", limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV candles"""
        if self.exchange:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return self._ohlcv_to_dataframe(ohlcv)
        return pd.DataFrame()
    
    def place_market_order(self, symbol: str, side: str, 
                          amount: float) -> OrderResult:
        """Place market order"""
        if not self.exchange:
            raise Exception("Exchange not connected")
        
        order = self.exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount
        )
        
        return OrderResult(
            order_id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            order_type=order['type'],
            price=order.get('average', 0),
            amount=order['amount'],
            filled=order.get('filled', 0),
            status=order['status'],
            timestamp=datetime.now()
        )
    
    def place_limit_order(self, symbol: str, side: str, 
                         amount: float, price: float) -> OrderResult:
        """Place limit order"""
        order = self.exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=price
        )
        
        return OrderResult(
            order_id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            order_type=order['type'],
            price=price,
            amount=order['amount'],
            filled=order.get('filled', 0),
            status=order['status'],
            timestamp=datetime.now()
        )
    
    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage"""
        if self.exchange:
            self.exchange.set_leverage(leverage, symbol)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position"""
        if not self.exchange:
            return None
        
        positions = self.exchange.fetch_positions([symbol])
        for pos in positions:
            if float(pos.get('contracts', 0)) > 0:
                return Position(
                    symbol=pos['symbol'],
                    side=pos['side'],
                    size=float(pos['contracts']),
                    entry_price=float(pos.get('entryPrice', 0)),
                    mark_price=float(pos.get('markPrice', 0)),
                    unrealized_pnl=float(pos.get('unrealizedPnl', 0)),
                    leverage=int(pos.get('leverage', 1)),
                    liquidation_price=float(pos.get('liquidationPrice', 0))
                )
        return None
    
    def close_position(self, symbol: str) -> Optional[OrderResult]:
        """Close position"""
        position = self.get_position(symbol)
        if not position:
            return None
        
        side = 'sell' if position.side == 'long' else 'buy'
        return self.place_market_order(symbol, side, position.size)
    
    def get_balance(self) -> Dict[str, float]:
        """Get balance"""
        if not self.exchange:
            return {}
        
        balance = self.exchange.fetch_balance()
        return {
            'total': balance.get('USDT', {}).get('total', 0),
            'free': balance.get('USDT', {}).get('free', 0),
            'used': balance.get('USDT', {}).get('used', 0)
        }


class HyperliquidConnector(ExchangeConnector):
    """
    Hyperliquid connector
    Note: Hyperliquid is a DEX with unique API structure
    """
    
    def connect(self):
        """Connect to Hyperliquid"""
        # Hyperliquid uses different connection method
        # You'll need the hyperliquid-python SDK
        try:
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange as HLExchange
            from hyperliquid.utils import constants
            
            self.info = Info(constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL)
            
            if self.api_key:  # Private key for signing
                self.hl_exchange = HLExchange(
                    self.api_key,  # This is actually the private key
                    constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
                )
            
            logger.info(f"Connected to Hyperliquid {'testnet' if self.testnet else 'mainnet'}")
        except ImportError:
            logger.error("hyperliquid-python not installed. Install with: pip install hyperliquid-python")
            self.info = None
            self.hl_exchange = None
    
    def fetch_ohlcv(self, symbol: str = "BTC", 
                    timeframe: str = "5m", limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV from Hyperliquid"""
        if not self.info:
            return pd.DataFrame()
        
        # Convert timeframe to Hyperliquid format
        tf_map = {
            '1m': '1m', '5m': '5m', '15m': '15m', 
            '30m': '30m', '1h': '1h', '4h': '4h', '1d': '1d'
        }
        
        try:
            # Hyperliquid candle fetch
            end_time = int(datetime.now().timestamp() * 1000)
            
            # Calculate start time based on limit and timeframe
            tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
            minutes = tf_minutes.get(timeframe, 5)
            start_time = end_time - (limit * minutes * 60 * 1000)
            
            candles = self.info.candles_snapshot(
                coin=symbol,
                interval=tf_map.get(timeframe, '5m'),
                start_time=start_time,
                end_time=end_time
            )
            
            if candles:
                df = pd.DataFrame(candles)
                df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
                df = df.rename(columns={
                    'o': 'open', 'h': 'high', 'l': 'low', 
                    'c': 'close', 'v': 'volume'
                })
                df.set_index('timestamp', inplace=True)
                df = df[['open', 'high', 'low', 'close', 'volume']]
                return df.astype(float)
            
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid OHLCV: {e}")
        
        return pd.DataFrame()
    
    def place_market_order(self, symbol: str, side: str, 
                          amount: float) -> OrderResult:
        """Place market order on Hyperliquid"""
        if not self.hl_exchange:
            raise Exception("Exchange not connected or no private key")
        
        is_buy = side.lower() == 'buy'
        
        try:
            result = self.hl_exchange.market_open(
                coin=symbol,
                is_buy=is_buy,
                sz=amount,
                slippage=0.01  # 1% slippage tolerance
            )
            
            return OrderResult(
                order_id=str(result.get('response', {}).get('data', {}).get('statuses', [{}])[0].get('resting', {}).get('oid', '')),
                symbol=symbol,
                side=side,
                order_type='market',
                price=0,  # Market order
                amount=amount,
                filled=amount,
                status='filled',
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error placing Hyperliquid order: {e}")
            raise
    
    def place_limit_order(self, symbol: str, side: str, 
                         amount: float, price: float) -> OrderResult:
        """Place limit order on Hyperliquid"""
        if not self.hl_exchange:
            raise Exception("Exchange not connected")
        
        is_buy = side.lower() == 'buy'
        
        result = self.hl_exchange.order(
            coin=symbol,
            is_buy=is_buy,
            sz=amount,
            limit_px=price,
            order_type={'limit': {'tif': 'Gtc'}}
        )
        
        return OrderResult(
            order_id=str(result.get('response', {}).get('data', {}).get('statuses', [{}])[0].get('resting', {}).get('oid', '')),
            symbol=symbol,
            side=side,
            order_type='limit',
            price=price,
            amount=amount,
            filled=0,
            status='open',
            timestamp=datetime.now()
        )
    
    def set_leverage(self, symbol: str, leverage: int):
        """Set leverage on Hyperliquid"""
        if self.hl_exchange:
            self.hl_exchange.update_leverage(leverage, symbol)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from Hyperliquid"""
        if not self.info or not self.api_key:
            return None
        
        try:
            # Get user state
            user_state = self.info.user_state(self.api_key)  # address
            
            for pos in user_state.get('assetPositions', []):
                if pos['position']['coin'] == symbol:
                    position = pos['position']
                    szi = float(position['szi'])
                    if szi != 0:
                        return Position(
                            symbol=symbol,
                            side='long' if szi > 0 else 'short',
                            size=abs(szi),
                            entry_price=float(position['entryPx']),
                            mark_price=float(position.get('markPx', 0)),
                            unrealized_pnl=float(position['unrealizedPnl']),
                            leverage=int(position.get('leverage', {}).get('value', 1)),
                            liquidation_price=float(position.get('liquidationPx', 0))
                        )
        except Exception as e:
            logger.error(f"Error getting Hyperliquid position: {e}")
        
        return None
    
    def close_position(self, symbol: str) -> Optional[OrderResult]:
        """Close position on Hyperliquid"""
        if not self.hl_exchange:
            return None
        
        position = self.get_position(symbol)
        if not position:
            return None
        
        try:
            result = self.hl_exchange.market_close(coin=symbol)
            return OrderResult(
                order_id='close',
                symbol=symbol,
                side='sell' if position.side == 'long' else 'buy',
                order_type='market',
                price=position.mark_price,
                amount=position.size,
                filled=position.size,
                status='filled',
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Error closing Hyperliquid position: {e}")
            return None
    
    def get_balance(self) -> Dict[str, float]:
        """Get balance from Hyperliquid"""
        if not self.info or not self.api_key:
            return {}
        
        try:
            user_state = self.info.user_state(self.api_key)
            margin = user_state.get('marginSummary', {})
            return {
                'total': float(margin.get('accountValue', 0)),
                'free': float(margin.get('availableBalance', 0)),
                'used': float(margin.get('totalMarginUsed', 0))
            }
        except:
            return {}


def get_connector(exchange: str, **kwargs) -> ExchangeConnector:
    """Factory function to get exchange connector"""
    connectors = {
        'mexc': MEXCConnector,
        'blofin': BlofinConnector,
        'hyperliquid': HyperliquidConnector
    }
    
    connector_class = connectors.get(exchange.lower())
    if not connector_class:
        raise ValueError(f"Unsupported exchange: {exchange}")
    
    return connector_class(**kwargs)
