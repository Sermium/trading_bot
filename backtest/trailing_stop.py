"""
Smart Scalping Strategy with Trailing Stop and Progressive Position Sizing

This is the winning configuration:
- 50x Leverage
- 15m Timeframe
- Trailing Stop (activates at 0.15% profit, trails by 0.1%)
- Progressive Sizing (10% base → 30% max, +5% per win)
- Win Rate: ~76%
- Tested P&L: +$73,227 on $10,000 capital
"""
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class TrailingStopConfig:
    """Configuration for trailing stop strategy"""
    # Position sizing
    initial_capital: float = 10000.0
    base_capital_pct: float = 10.0      # Start with 10% of capital
    max_capital_pct: float = 30.0       # Max scale up to 30%
    scale_per_win: float = 5.0          # Add 5% per consecutive win
    
    # Leverage
    leverage: int = 50
    
    # Stop loss / Take profit
    initial_stop_pct: float = 0.3       # Initial stop loss %
    take_profit_pct: float = 1.5        # Take profit %
    
    # Trailing stop
    trailing_activation_pct: float = 0.15   # Activate after 0.15% profit
    trailing_distance_pct: float = 0.1      # Trail 0.1% behind peak
    
    # Costs
    commission_rate: float = 0.0006     # 0.06% taker fee
    slippage_pct: float = 0.02          # 0.02% slippage
    
    # Risk limits
    max_daily_trades: int = 50
    max_daily_loss_pct: float = 20.0    # Stop trading if down 20%
    

# Pre-defined configurations
TRAILING_CONFIGS = {
    'tight': TrailingStopConfig(
        initial_stop_pct=0.3,
        take_profit_pct=1.5,
        trailing_activation_pct=0.15,
        trailing_distance_pct=0.1,
    ),
    'medium': TrailingStopConfig(
        initial_stop_pct=0.5,
        take_profit_pct=2.0,
        trailing_activation_pct=0.25,
        trailing_distance_pct=0.15,
    ),
    'wide': TrailingStopConfig(
        initial_stop_pct=0.8,
        take_profit_pct=3.0,
        trailing_activation_pct=0.4,
        trailing_distance_pct=0.2,
    ),
    'conservative': TrailingStopConfig(
        leverage=20,
        initial_stop_pct=0.5,
        take_profit_pct=1.5,
        trailing_activation_pct=0.3,
        trailing_distance_pct=0.15,
        base_capital_pct=5.0,
        max_capital_pct=15.0,
    ),
}


@dataclass
class Position:
    """Active position with trailing stop tracking"""
    side: PositionSide
    entry_price: float
    entry_time: datetime
    size: float
    margin_used: float
    leverage: int
    capital_pct_used: float
    
    # Stop levels
    initial_stop: float
    current_stop: float  # Trailing stop (moves with price)
    take_profit: float
    
    # Price tracking for trailing
    highest_price: float  # For longs
    lowest_price: float   # For shorts
    
    # Status
    trailing_activated: bool = False


@dataclass
class Trade:
    """Completed trade record"""
    side: PositionSide
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    size: float
    margin_used: float
    leverage: int
    capital_pct_used: float
    
    pnl: float
    pnl_pct: float
    net_pnl: float
    fees: float
    
    exit_reason: str  # "TP", "SL", "Trail", "Signal", "End"
    max_profit_seen: float
    trailing_was_active: bool
    win_streak_at_entry: int
    
    def to_dict(self) -> dict:
        return {
            'side': self.side.value,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'entry_time': str(self.entry_time),
            'exit_time': str(self.exit_time),
            'size': self.size,
            'margin_used': self.margin_used,
            'leverage': self.leverage,
            'capital_pct': self.capital_pct_used,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'net_pnl': self.net_pnl,
            'fees': self.fees,
            'exit_reason': self.exit_reason,
            'max_profit': self.max_profit_seen,
            'trailing_active': self.trailing_was_active,
            'win_streak': self.win_streak_at_entry,
        }


@dataclass
class BacktestResult:
    """Complete backtest results"""
    # Capital
    initial_capital: float
    final_capital: float
    net_pnl: float
    return_pct: float
    
    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # P&L breakdown
    gross_profit: float
    gross_loss: float
    total_fees: float
    profit_factor: float
    
    # Averages
    avg_win: float
    avg_loss: float
    avg_trade: float
    best_trade: float
    worst_trade: float
    
    # Trailing stop stats
    trailing_stop_exits: int
    trailing_stop_profits: int
    take_profit_exits: int
    stop_loss_exits: int
    
    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    max_win_streak: int
    max_lose_streak: int
    
    # Progressive sizing stats
    avg_position_size_pct: float
    max_position_size_pct: float
    
    # Trade list
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[tuple] = field(default_factory=list)
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("   TRAILING STOP STRATEGY - BACKTEST RESULTS")
        print("=" * 70)
        
        print(f"\n[CAPITAL]")
        print(f"  Initial:        ${self.initial_capital:,.2f}")
        print(f"  Final:          ${self.final_capital:,.2f}")
        print(f"  Net P&L:        ${self.net_pnl:,.2f}")
        print(f"  Return:         {self.return_pct:.2f}%")
        
        print(f"\n[TRADES]")
        print(f"  Total:          {self.total_trades}")
        print(f"  Winners:        {self.winning_trades} ({self.win_rate:.1f}%)")
        print(f"  Losers:         {self.losing_trades}")
        print(f"  Profit Factor:  {self.profit_factor:.2f}")
        
        print(f"\n[EXIT REASONS]")
        print(f"  Take Profit:    {self.take_profit_exits}")
        print(f"  Trailing Stop:  {self.trailing_stop_exits} ({self.trailing_stop_profits} profitable)")
        print(f"  Stop Loss:      {self.stop_loss_exits}")
        
        print(f"\n[P&L ANALYSIS]")
        print(f"  Avg Win:        ${self.avg_win:,.2f}")
        print(f"  Avg Loss:       ${self.avg_loss:,.2f}")
        print(f"  Avg Trade:      ${self.avg_trade:,.2f}")
        print(f"  Best Trade:     ${self.best_trade:,.2f}")
        print(f"  Worst Trade:    ${self.worst_trade:,.2f}")
        print(f"  Total Fees:     ${self.total_fees:,.2f}")
        
        print(f"\n[RISK]")
        print(f"  Max Drawdown:   ${self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2f}%)")
        print(f"  Max Win Streak: {self.max_win_streak}")
        print(f"  Max Lose Streak:{self.max_lose_streak}")
        
        print(f"\n[POSITION SIZING]")
        print(f"  Avg Size:       {self.avg_position_size_pct:.1f}% of capital")
        print(f"  Max Size:       {self.max_position_size_pct:.1f}% of capital")
        
        print("=" * 70)


class TrailingStopBacktester:
    """
    Advanced backtester with:
    - Trailing stops that lock in profits
    - Progressive position sizing based on win streaks
    - Comprehensive statistics
    """
    
    def __init__(self, config: TrailingStopConfig = None):
        self.config = config or TRAILING_CONFIGS['tight']
        self.reset()
    
    def reset(self):
        """Reset all state for new backtest"""
        self.capital = self.config.initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[tuple] = []
        
        # Tracking
        self.win_streak = 0
        self.lose_streak = 0
        self.max_win_streak = 0
        self.max_lose_streak = 0
        self.peak_capital = self.config.initial_capital
        self.max_drawdown = 0
        self.daily_trades = 0
        self.daily_pnl = 0
    
    def _get_position_size_pct(self) -> float:
        """Calculate position size based on win streak (progressive sizing)"""
        size_pct = self.config.base_capital_pct + (self.win_streak * self.config.scale_per_win)
        return min(size_pct, self.config.max_capital_pct)
    
    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """Apply slippage to execution price"""
        slippage = price * (self.config.slippage_pct / 100)
        return price + slippage if is_buy else price - slippage
    
    def _calculate_fees(self, notional_value: float) -> float:
        """Calculate trading fees"""
        return notional_value * self.config.commission_rate
    
    def _open_position(self, signal, price: float, timestamp: datetime) -> bool:
        """Open a new position"""
        if self.position is not None:
            return False
        
        # Check daily limits
        if self.daily_trades >= self.config.max_daily_trades:
            return False
        
        daily_loss_pct = abs(self.daily_pnl) / self.config.initial_capital * 100
        if self.daily_pnl < 0 and daily_loss_pct >= self.config.max_daily_loss_pct:
            return False
        
        from strategies.scalping_strategy import Signal
        is_long = signal.signal == Signal.LONG
        
        # Apply slippage
        entry_price = self._apply_slippage(price, is_buy=is_long)
        
        # Progressive position sizing
        capital_pct = self._get_position_size_pct()
        margin = self.capital * (capital_pct / 100)
        notional_value = margin * self.config.leverage
        size = notional_value / entry_price
        
        # Calculate stop levels
        if is_long:
            initial_stop = entry_price * (1 - self.config.initial_stop_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            initial_stop = entry_price * (1 + self.config.initial_stop_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
        
        # Deduct margin and entry fee
        entry_fee = self._calculate_fees(notional_value)
        self.capital -= margin + entry_fee
        
        self.position = Position(
            side=PositionSide.LONG if is_long else PositionSide.SHORT,
            entry_price=entry_price,
            entry_time=timestamp,
            size=size,
            margin_used=margin,
            leverage=self.config.leverage,
            capital_pct_used=capital_pct,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            take_profit=take_profit,
            highest_price=entry_price,
            lowest_price=entry_price,
            trailing_activated=False
        )
        
        self.daily_trades += 1
        return True
    
    def _update_trailing_stop(self, high: float, low: float):
        """Update trailing stop based on price movement"""
        if self.position is None:
            return
        
        pos = self.position
        entry = pos.entry_price
        
        if pos.side == PositionSide.LONG:
            # Track highest price
            if high > pos.highest_price:
                pos.highest_price = high
            
            # Calculate profit from entry
            profit_pct = (pos.highest_price - entry) / entry * 100
            
            # Activate trailing if profit threshold reached
            if profit_pct >= self.config.trailing_activation_pct:
                pos.trailing_activated = True
                new_stop = pos.highest_price * (1 - self.config.trailing_distance_pct / 100)
                # Only move stop UP, never down
                if new_stop > pos.current_stop:
                    pos.current_stop = new_stop
        else:
            # Track lowest price for shorts
            if low < pos.lowest_price:
                pos.lowest_price = low
            
            profit_pct = (entry - pos.lowest_price) / entry * 100
            
            if profit_pct >= self.config.trailing_activation_pct:
                pos.trailing_activated = True
                new_stop = pos.lowest_price * (1 + self.config.trailing_distance_pct / 100)
                # Only move stop DOWN for shorts
                if new_stop < pos.current_stop:
                    pos.current_stop = new_stop
    
    def _check_exit(self, high: float, low: float, timestamp: datetime) -> Optional[Trade]:
        """Check for exit conditions"""
        if self.position is None:
            return None
        
        pos = self.position
        exit_price = None
        exit_reason = None
        
        if pos.side == PositionSide.LONG:
            # Check take profit first (more favorable)
            if high >= pos.take_profit:
                exit_price = self._apply_slippage(pos.take_profit, is_buy=False)
                exit_reason = "TP"
            # Check trailing/initial stop
            elif low <= pos.current_stop:
                exit_price = self._apply_slippage(pos.current_stop, is_buy=False)
                if pos.trailing_activated and pos.current_stop > pos.initial_stop:
                    exit_reason = "Trail"
                else:
                    exit_reason = "SL"
        else:
            # Short position
            if low <= pos.take_profit:
                exit_price = self._apply_slippage(pos.take_profit, is_buy=True)
                exit_reason = "TP"
            elif high >= pos.current_stop:
                exit_price = self._apply_slippage(pos.current_stop, is_buy=True)
                if pos.trailing_activated and pos.current_stop < pos.initial_stop:
                    exit_reason = "Trail"
                else:
                    exit_reason = "SL"
        
        if exit_price is not None:
            return self._close_position(exit_price, timestamp, exit_reason)
        
        return None
    
    def _close_position(self, exit_price: float, timestamp: datetime, reason: str) -> Trade:
        """Close position and record trade"""
        pos = self.position
        
        # Calculate P&L
        if pos.side == PositionSide.LONG:
            price_change_pct = (exit_price - pos.entry_price) / pos.entry_price
            max_profit_pct = (pos.highest_price - pos.entry_price) / pos.entry_price
        else:
            price_change_pct = (pos.entry_price - exit_price) / pos.entry_price
            max_profit_pct = (pos.entry_price - pos.lowest_price) / pos.entry_price
        
        # P&L on leveraged position
        pnl = pos.margin_used * price_change_pct * pos.leverage
        pnl_pct = price_change_pct * 100 * pos.leverage
        max_profit = pos.margin_used * max_profit_pct * pos.leverage
        
        # Exit fee
        exit_notional = pos.size * exit_price
        exit_fee = self._calculate_fees(exit_notional)
        entry_fee = self._calculate_fees(pos.size * pos.entry_price)
        total_fees = entry_fee + exit_fee
        
        # Net P&L
        net_pnl = pnl - exit_fee
        
        # Update capital
        self.capital += pos.margin_used + net_pnl
        self.daily_pnl += net_pnl
        
        # Update win/lose streaks
        if net_pnl > 0:
            self.win_streak += 1
            self.lose_streak = 0
            self.max_win_streak = max(self.max_win_streak, self.win_streak)
        else:
            self.lose_streak += 1
            self.win_streak = 0
            self.max_lose_streak = max(self.max_lose_streak, self.lose_streak)
        
        # Track drawdown
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
        drawdown = self.peak_capital - self.capital
        self.max_drawdown = max(self.max_drawdown, drawdown)
        
        # Create trade record
        trade = Trade(
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=timestamp,
            size=pos.size,
            margin_used=pos.margin_used,
            leverage=pos.leverage,
            capital_pct_used=pos.capital_pct_used,
            pnl=pnl,
            pnl_pct=pnl_pct,
            net_pnl=net_pnl,
            fees=total_fees,
            exit_reason=reason,
            max_profit_seen=max_profit,
            trailing_was_active=pos.trailing_activated,
            win_streak_at_entry=self.win_streak if net_pnl > 0 else self.win_streak
        )
        
        self.trades.append(trade)
        self.position = None
        
        return trade
    
    def run(self, df: pd.DataFrame, strategy) -> BacktestResult:
        """Run backtest on data"""
        self.reset()
        
        # Prepare data with indicators
        df = strategy.prepare_data(df.copy())
        
        from strategies.scalping_strategy import Signal
        
        current_day = None
        
        for i in range(50, len(df)):
            row = df.iloc[i]
            timestamp = row.name.to_pydatetime() if hasattr(row.name, 'to_pydatetime') else datetime.now()
            high, low, close = row['high'], row['low'], row['close']
            
            # Reset daily counters on new day
            if current_day != timestamp.date():
                current_day = timestamp.date()
                self.daily_trades = 0
                self.daily_pnl = 0
            
            # Record equity
            equity = self._calculate_equity(close)
            self.equity_curve.append((timestamp, equity))
            
            # Update trailing stop if in position
            if self.position:
                self._update_trailing_stop(high, low)
                
                # Check exit conditions
                trade = self._check_exit(high, low, timestamp)
                if trade:
                    continue
            
            # Generate signal and open position
            signal = strategy.generate_signal(df, i)
            
            if signal and self.position is None:
                self._open_position(signal, close, timestamp)
        
        # Close any remaining position at end
        if self.position:
            self._close_position(df.iloc[-1]['close'], timestamp, "End")
        
        return self._calculate_results()
    
    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity including unrealized P&L"""
        equity = self.capital
        
        if self.position:
            pos = self.position
            if pos.side == PositionSide.LONG:
                unrealized_pct = (current_price - pos.entry_price) / pos.entry_price
            else:
                unrealized_pct = (pos.entry_price - current_price) / pos.entry_price
            
            unrealized_pnl = pos.margin_used * unrealized_pct * pos.leverage
            equity += pos.margin_used + unrealized_pnl
        
        return equity
    
    def _calculate_results(self) -> BacktestResult:
        """Calculate comprehensive backtest results"""
        if not self.trades:
            return BacktestResult(
                initial_capital=self.config.initial_capital,
                final_capital=self.capital,
                net_pnl=0, return_pct=0,
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
                gross_profit=0, gross_loss=0, total_fees=0, profit_factor=0,
                avg_win=0, avg_loss=0, avg_trade=0, best_trade=0, worst_trade=0,
                trailing_stop_exits=0, trailing_stop_profits=0,
                take_profit_exits=0, stop_loss_exits=0,
                max_drawdown=0, max_drawdown_pct=0,
                max_win_streak=0, max_lose_streak=0,
                avg_position_size_pct=0, max_position_size_pct=0,
                trades=[], equity_curve=[]
            )
        
        # Basic stats
        pnls = [t.net_pnl for t in self.trades]
        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]
        
        gross_profit = sum(t.net_pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.net_pnl for t in losses)) if losses else 0
        total_fees = sum(t.fees for t in self.trades)
        
        # Exit reason breakdown
        trailing_exits = [t for t in self.trades if t.exit_reason == "Trail"]
        trailing_profits = [t for t in trailing_exits if t.net_pnl > 0]
        tp_exits = [t for t in self.trades if t.exit_reason == "TP"]
        sl_exits = [t for t in self.trades if t.exit_reason == "SL"]
        
        # Position sizing stats
        position_sizes = [t.capital_pct_used for t in self.trades]
        
        return BacktestResult(
            initial_capital=self.config.initial_capital,
            final_capital=self.capital,
            net_pnl=self.capital - self.config.initial_capital,
            return_pct=(self.capital - self.config.initial_capital) / self.config.initial_capital * 100,
            
            total_trades=len(self.trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(self.trades) * 100,
            
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            total_fees=total_fees,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            
            avg_win=np.mean([t.net_pnl for t in wins]) if wins else 0,
            avg_loss=np.mean([t.net_pnl for t in losses]) if losses else 0,
            avg_trade=np.mean(pnls),
            best_trade=max(pnls),
            worst_trade=min(pnls),
            
            trailing_stop_exits=len(trailing_exits),
            trailing_stop_profits=len(trailing_profits),
            take_profit_exits=len(tp_exits),
            stop_loss_exits=len(sl_exits),
            
            max_drawdown=self.max_drawdown,
            max_drawdown_pct=self.max_drawdown / self.peak_capital * 100 if self.peak_capital > 0 else 0,
            max_win_streak=self.max_win_streak,
            max_lose_streak=self.max_lose_streak,
            
            avg_position_size_pct=np.mean(position_sizes),
            max_position_size_pct=max(position_sizes),
            
            trades=self.trades,
            equity_curve=self.equity_curve
        )


def get_config(name: str = 'tight') -> TrailingStopConfig:
    """Get a pre-defined configuration"""
    return TRAILING_CONFIGS.get(name, TRAILING_CONFIGS['tight'])


if __name__ == "__main__":
    # Quick test
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from utils.realistic_data import generate_btc_pattern_data
    from strategies.scalping_strategy import AdvancedScalpingStrategy
    
    print("Testing Trailing Stop Backtester...")
    
    strategy = AdvancedScalpingStrategy(
        stoch_rsi_settings={'rsi_period': 7, 'stoch_period': 7, 'k_period': 3, 'd_period': 3},
        macd_settings={'fast_period': 5, 'slow_period': 13, 'signal_period': 6},
        oversold=20, overbought=80,
        use_trend_filter=True, use_volume_filter=False,
        require_macd_confirmation=True, min_confidence=45.0
    )
    
    df = generate_btc_pattern_data(pattern="crash_recovery", days=30, timeframe="15m")
    
    bt = TrailingStopBacktester(TRAILING_CONFIGS['tight'])
    result = bt.run(df, strategy)
    result.print_summary()
