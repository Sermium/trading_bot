"""
Backtesting Engine for Trading Strategy Evaluation
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Represents an open position"""
    side: PositionSide
    entry_price: float
    entry_time: datetime
    size: float
    leverage: int
    stop_loss: float
    take_profit: float
    signal_confidence: float
    signal_reason: str


@dataclass
class Trade:
    """Completed trade record"""
    side: PositionSide
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    size: float
    leverage: int
    pnl: float
    pnl_pct: float
    fee: float
    net_pnl: float
    exit_reason: str
    signal_confidence: float
    signal_reason: str
    
    def to_dict(self) -> dict:
        return {
            'side': self.side.value,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': self.entry_time.isoformat() if isinstance(self.entry_time, datetime) else str(self.entry_time),
            'exit_time': self.exit_time.isoformat() if isinstance(self.exit_time, datetime) else str(self.exit_time),
            'size': self.size,
            'leverage': self.leverage,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'fee': self.fee,
            'net_pnl': self.net_pnl,
            'exit_reason': self.exit_reason,
            'signal_confidence': self.signal_confidence,
            'signal_reason': self.signal_reason
        }


@dataclass
class BacktestResult:
    """Container for backtest results"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_fees: float
    net_pnl: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_trade: float
    best_trade: float
    worst_trade: float
    avg_holding_time: str
    initial_capital: float
    final_capital: float
    return_pct: float
    trades: List[Trade]
    equity_curve: pd.Series
    daily_returns: pd.Series
    
    def to_dict(self) -> dict:
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 2),
            'total_pnl': round(self.total_pnl, 2),
            'total_fees': round(self.total_fees, 2),
            'net_pnl': round(self.net_pnl, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'sortino_ratio': round(self.sortino_ratio, 3),
            'profit_factor': round(self.profit_factor, 3),
            'avg_win': round(self.avg_win, 2),
            'avg_loss': round(self.avg_loss, 2),
            'avg_trade': round(self.avg_trade, 2),
            'best_trade': round(self.best_trade, 2),
            'worst_trade': round(self.worst_trade, 2),
            'avg_holding_time': self.avg_holding_time,
            'initial_capital': round(self.initial_capital, 2),
            'final_capital': round(self.final_capital, 2),
            'return_pct': round(self.return_pct, 2),
        }
    
    def print_summary(self):
        """Print formatted backtest summary"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS SUMMARY")
        print("="*60)
        print(f"\n[DATA] PERFORMANCE METRICS")
        print(f"  Initial Capital:    ${self.initial_capital:,.2f}")
        print(f"  Final Capital:      ${self.final_capital:,.2f}")
        print(f"  Net P&L:            ${self.net_pnl:,.2f}")
        print(f"  Return:             {self.return_pct:.2f}%")
        print(f"\n[STATS] TRADE STATISTICS")
        print(f"  Total Trades:       {self.total_trades}")
        print(f"  Winning Trades:     {self.winning_trades}")
        print(f"  Losing Trades:      {self.losing_trades}")
        print(f"  Win Rate:           {self.win_rate:.1f}%")
        print(f"\n[PROFIT] PROFIT ANALYSIS")
        print(f"  Profit Factor:      {self.profit_factor:.2f}")
        print(f"  Avg Win:            ${self.avg_win:,.2f}")
        print(f"  Avg Loss:           ${self.avg_loss:,.2f}")
        print(f"  Avg Trade:          ${self.avg_trade:,.2f}")
        print(f"  Best Trade:         ${self.best_trade:,.2f}")
        print(f"  Worst Trade:        ${self.worst_trade:,.2f}")
        print(f"\n[WARNING] RISK METRICS")
        print(f"  Max Drawdown:       ${self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2f}%)")
        print(f"  Sharpe Ratio:       {self.sharpe_ratio:.3f}")
        print(f"  Sortino Ratio:      {self.sortino_ratio:.3f}")
        print(f"\n[TIME] TIME ANALYSIS")
        print(f"  Avg Holding Time:   {self.avg_holding_time}")
        print(f"  Total Fees:         ${self.total_fees:,.2f}")
        print("="*60 + "\n")


class Backtester:
    """
    Backtesting engine for the scalping strategy
    """
    
    def __init__(self,
                 initial_capital: float = 10000.0,
                 commission_rate: float = 0.0006,  # 0.06% taker fee
                 slippage_pct: float = 0.01,  # 0.01% slippage
                 leverage: int = 10,
                 capital_percentage: float = 10.0,
                 stop_loss_pct: float = 0.5,
                 take_profit_pct: float = 1.0,
                 max_positions: int = 1):
        """
        Initialize backtester
        
        Args:
            initial_capital: Starting capital in USDT
            commission_rate: Trading fee rate (maker/taker)
            slippage_pct: Expected slippage percentage
            leverage: Position leverage
            capital_percentage: % of capital to use per trade
            stop_loss_pct: Stop loss percentage from entry
            take_profit_pct: Take profit percentage from entry
            max_positions: Maximum concurrent positions
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_pct = slippage_pct
        self.leverage = leverage
        self.capital_percentage = capital_percentage
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_positions = max_positions
        
        self.capital = initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_history: List[Tuple[datetime, float]] = []
    
    def reset(self):
        """Reset backtester state"""
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_history = []
    
    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """Apply slippage to execution price"""
        slippage = price * (self.slippage_pct / 100)
        if is_buy:
            return price + slippage
        else:
            return price - slippage
    
    def _calculate_fee(self, position_value: float) -> float:
        """Calculate trading fee"""
        return position_value * self.commission_rate
    
    def _calculate_position_size(self, price: float) -> float:
        """Calculate position size based on capital and leverage"""
        capital_to_use = self.capital * (self.capital_percentage / 100)
        position_value = capital_to_use * self.leverage
        return position_value / price
    
    def _open_position(self, signal, price: float, timestamp: datetime) -> bool:
        """Open a new position"""
        if self.position is not None:
            return False
        
        from strategies.scalping_strategy import Signal, TradeSignal
        
        is_long = signal.signal == Signal.LONG
        
        # Apply slippage
        entry_price = self._apply_slippage(price, is_buy=is_long)
        
        # Calculate position size based on capital to risk
        capital_to_use = self.capital * (self.capital_percentage / 100)
        position_value = capital_to_use * self.leverage
        size = position_value / entry_price
        
        # Calculate SL/TP
        if is_long:
            stop_loss = entry_price * (1 - self.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + self.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.take_profit_pct / 100)
        
        # Deduct margin (capital used) from available capital
        margin_used = capital_to_use
        self.capital -= margin_used
        
        # Deduct entry fee
        entry_fee = self._calculate_fee(position_value)
        self.capital -= entry_fee
        
        self.position = Position(
            side=PositionSide.LONG if is_long else PositionSide.SHORT,
            entry_price=entry_price,
            entry_time=timestamp,
            size=size,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_confidence=signal.confidence,
            signal_reason=signal.reason
        )
        
        # Store the margin used for later
        self._margin_used = margin_used
        self._entry_fee = entry_fee
        
        return True
    
    def _close_position(self, price: float, timestamp: datetime, reason: str) -> Trade:
        """Close current position and record trade"""
        if self.position is None:
            return None
        
        is_long = self.position.side == PositionSide.LONG
        
        # Apply slippage
        exit_price = self._apply_slippage(price, is_buy=not is_long)
        
        # Calculate P&L on the position
        position_value = self.position.size * self.position.entry_price
        
        if is_long:
            # Long: profit when price goes up
            price_change_pct = (exit_price - self.position.entry_price) / self.position.entry_price
        else:
            # Short: profit when price goes down
            price_change_pct = (self.position.entry_price - exit_price) / self.position.entry_price
        
        # P&L on the leveraged position (based on margin used)
        margin_used = getattr(self, '_margin_used', position_value / self.leverage)
        pnl = margin_used * price_change_pct * self.leverage
        
        # P&L percentage (on margin)
        pnl_pct = price_change_pct * 100 * self.leverage
        
        # Calculate exit fee
        exit_position_value = self.position.size * exit_price
        exit_fee = self._calculate_fee(exit_position_value)
        
        # Net P&L after fees
        net_pnl = pnl - exit_fee
        
        # Return margin + net P&L to capital
        self.capital += margin_used + net_pnl
        
        trade = Trade(
            side=self.position.side,
            entry_price=self.position.entry_price,
            exit_price=exit_price,
            entry_time=self.position.entry_time,
            exit_time=timestamp,
            size=self.position.size,
            leverage=self.leverage,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fee=exit_fee + getattr(self, '_entry_fee', 0),
            net_pnl=net_pnl,
            exit_reason=reason,
            signal_confidence=self.position.signal_confidence,
            signal_reason=self.position.signal_reason
        )
        
        self.trades.append(trade)
        self.position = None
        self._margin_used = 0
        self._entry_fee = 0
        
        return trade
    
    def _check_stop_loss_take_profit(self, high: float, low: float, 
                                     timestamp: datetime) -> Optional[Trade]:
        """Check if SL or TP is hit"""
        if self.position is None:
            return None
        
        is_long = self.position.side == PositionSide.LONG
        
        if is_long:
            # Check stop loss (price went below SL)
            if low <= self.position.stop_loss:
                return self._close_position(
                    self.position.stop_loss, timestamp, "Stop Loss"
                )
            # Check take profit (price went above TP)
            if high >= self.position.take_profit:
                return self._close_position(
                    self.position.take_profit, timestamp, "Take Profit"
                )
        else:  # Short
            # Check stop loss (price went above SL)
            if high >= self.position.stop_loss:
                return self._close_position(
                    self.position.stop_loss, timestamp, "Stop Loss"
                )
            # Check take profit (price went below TP)
            if low <= self.position.take_profit:
                return self._close_position(
                    self.position.take_profit, timestamp, "Take Profit"
                )
        
        return None
    
    def run(self, df: pd.DataFrame, strategy) -> BacktestResult:
        """
        Run backtest on historical data
        
        Args:
            df: DataFrame with OHLCV data
            strategy: Trading strategy instance
            
        Returns:
            BacktestResult with all metrics
        """
        self.reset()
        
        # Prepare data with indicators
        df = strategy.prepare_data(df)
        
        from strategies.scalping_strategy import Signal
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            
            # Get timestamp
            if isinstance(row.name, pd.Timestamp):
                timestamp = row.name.to_pydatetime()
            else:
                timestamp = datetime.now()
            
            # Record equity
            current_equity = self._calculate_current_equity(row['close'])
            self.equity_history.append((timestamp, current_equity))
            
            # Check SL/TP first
            if self.position:
                trade = self._check_stop_loss_take_profit(
                    row['high'], row['low'], timestamp
                )
                if trade:
                    continue  # Position was closed
            
            # Generate signal
            signal = strategy.generate_signal(df, i)
            
            if signal:
                if self.position is None:
                    # Open new position
                    self._open_position(signal, row['close'], timestamp)
                elif signal.signal == Signal.LONG and self.position.side == PositionSide.SHORT:
                    # Close short and open long
                    self._close_position(row['close'], timestamp, "Signal Reversal")
                    self._open_position(signal, row['close'], timestamp)
                elif signal.signal == Signal.SHORT and self.position.side == PositionSide.LONG:
                    # Close long and open short
                    self._close_position(row['close'], timestamp, "Signal Reversal")
                    self._open_position(signal, row['close'], timestamp)
        
        # Close any remaining position at the end
        if self.position:
            final_row = df.iloc[-1]
            if isinstance(final_row.name, pd.Timestamp):
                timestamp = final_row.name.to_pydatetime()
            else:
                timestamp = datetime.now()
            self._close_position(final_row['close'], timestamp, "End of Backtest")
        
        return self._calculate_results()
    
    def _calculate_current_equity(self, current_price: float) -> float:
        """Calculate current equity including unrealized P&L"""
        equity = self.capital
        
        if self.position:
            # Get the margin we have locked in the position
            margin_used = getattr(self, '_margin_used', 0)
            
            # Calculate unrealized P&L
            if self.position.side == PositionSide.LONG:
                price_change_pct = (current_price - self.position.entry_price) / self.position.entry_price
            else:
                price_change_pct = (self.position.entry_price - current_price) / self.position.entry_price
            
            unrealized_pnl = margin_used * price_change_pct * self.leverage
            
            # Total equity = available capital + margin + unrealized P&L
            equity += margin_used + unrealized_pnl
        
        return equity
    
    def _calculate_results(self) -> BacktestResult:
        """Calculate all backtest metrics"""
        if not self.trades:
            return self._empty_result()
        
        # Basic stats
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.net_pnl > 0])
        losing_trades = len([t for t in self.trades if t.net_pnl <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L stats
        pnls = [t.net_pnl for t in self.trades]
        total_pnl = sum([t.pnl for t in self.trades])
        total_fees = sum([t.fee for t in self.trades])
        net_pnl = sum(pnls)
        
        wins = [t.net_pnl for t in self.trades if t.net_pnl > 0]
        losses = [t.net_pnl for t in self.trades if t.net_pnl <= 0]
        
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        avg_trade = np.mean(pnls)
        best_trade = max(pnls)
        worst_trade = min(pnls)
        
        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Equity curve
        equity_df = pd.DataFrame(self.equity_history, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)
        equity_curve = equity_df['equity']
        
        # Drawdown
        rolling_max = equity_curve.expanding().max()
        drawdown = equity_curve - rolling_max
        max_drawdown = abs(drawdown.min())
        max_drawdown_pct = (max_drawdown / rolling_max[drawdown.idxmin()]) * 100 if len(drawdown) > 0 else 0
        
        # Daily returns for Sharpe/Sortino
        daily_equity = equity_curve.resample('D').last().dropna()
        daily_returns = daily_equity.pct_change().dropna()
        
        # Sharpe ratio (annualized, assuming 365 trading days for crypto)
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
        else:
            sharpe_ratio = 0
        
        # Sortino ratio
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 1 and negative_returns.std() > 0:
            sortino_ratio = (daily_returns.mean() / negative_returns.std()) * np.sqrt(365)
        else:
            sortino_ratio = sharpe_ratio
        
        # Average holding time
        holding_times = [(t.exit_time - t.entry_time) for t in self.trades 
                        if isinstance(t.exit_time, datetime) and isinstance(t.entry_time, datetime)]
        if holding_times:
            avg_holding = sum(holding_times, timedelta()) / len(holding_times)
            hours, remainder = divmod(avg_holding.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            avg_holding_time = f"{avg_holding.days}d {hours}h {minutes}m"
        else:
            avg_holding_time = "N/A"
        
        # Return
        final_capital = self.capital
        return_pct = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade=avg_trade,
            best_trade=best_trade,
            worst_trade=worst_trade,
            avg_holding_time=avg_holding_time,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            return_pct=return_pct,
            trades=self.trades,
            equity_curve=equity_curve,
            daily_returns=daily_returns
        )
    
    def _empty_result(self) -> BacktestResult:
        """Return empty result when no trades"""
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            total_pnl=0,
            total_fees=0,
            net_pnl=0,
            max_drawdown=0,
            max_drawdown_pct=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            profit_factor=0,
            avg_win=0,
            avg_loss=0,
            avg_trade=0,
            best_trade=0,
            worst_trade=0,
            avg_holding_time="N/A",
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            return_pct=0,
            trades=[],
            equity_curve=pd.Series(),
            daily_returns=pd.Series()
        )


class WalkForwardOptimizer:
    """
    Walk-forward optimization for strategy parameters
    Helps prevent overfitting by using out-of-sample testing
    """
    
    def __init__(self, 
                 in_sample_pct: float = 0.7,
                 num_windows: int = 5):
        self.in_sample_pct = in_sample_pct
        self.num_windows = num_windows
    
    def optimize(self, df: pd.DataFrame, param_grid: dict, 
                 strategy_class, backtester: Backtester) -> dict:
        """
        Run walk-forward optimization
        
        Args:
            df: Full historical data
            param_grid: Dict of parameters to optimize
            strategy_class: Strategy class to instantiate
            backtester: Backtester instance
            
        Returns:
            Best parameters found
        """
        window_size = len(df) // self.num_windows
        results = []
        
        for window in range(self.num_windows):
            start_idx = window * window_size
            end_idx = start_idx + window_size
            
            window_data = df.iloc[start_idx:end_idx]
            
            in_sample_size = int(len(window_data) * self.in_sample_pct)
            in_sample = window_data.iloc[:in_sample_size]
            out_sample = window_data.iloc[in_sample_size:]
            
            # Find best params on in-sample
            best_params = None
            best_score = -float('inf')
            
            # Simple grid search (can be expanded)
            for oversold in param_grid.get('oversold', [20]):
                for overbought in param_grid.get('overbought', [80]):
                    strategy = strategy_class(
                        stoch_rsi_settings={'rsi_period': 14, 'stoch_period': 14, 
                                           'k_period': 3, 'd_period': 3},
                        macd_settings={'fast_period': 12, 'slow_period': 26, 
                                      'signal_period': 9},
                        oversold=oversold,
                        overbought=overbought
                    )
                    
                    result = backtester.run(in_sample, strategy)
                    
                    # Score by profit factor * win rate
                    score = result.profit_factor * (result.win_rate / 100)
                    
                    if score > best_score:
                        best_score = score
                        best_params = {'oversold': oversold, 'overbought': overbought}
            
            # Test on out-of-sample
            if best_params:
                strategy = strategy_class(
                    stoch_rsi_settings={'rsi_period': 14, 'stoch_period': 14,
                                       'k_period': 3, 'd_period': 3},
                    macd_settings={'fast_period': 12, 'slow_period': 26,
                                  'signal_period': 9},
                    **best_params
                )
                out_result = backtester.run(out_sample, strategy)
                results.append({
                    'params': best_params,
                    'in_sample_score': best_score,
                    'out_sample_pnl': out_result.net_pnl,
                    'out_sample_win_rate': out_result.win_rate
                })
        
        # Return most consistent params
        if results:
            # Average out-of-sample performance
            param_scores = {}
            for r in results:
                key = str(r['params'])
                if key not in param_scores:
                    param_scores[key] = []
                param_scores[key].append(r['out_sample_win_rate'])
            
            best_key = max(param_scores.keys(), key=lambda k: np.mean(param_scores[k]))
            return eval(best_key)
        
        return {}
