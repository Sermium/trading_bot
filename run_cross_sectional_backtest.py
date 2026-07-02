"""
Cross-Sectional Momentum Backtest Runner
-------------------------------------------
python run_cross_sectional_backtest.py --exchange mexc --bars 1500
python run_cross_sectional_backtest.py --exchange blofin --bars 1500 --sweep
python run_cross_sectional_backtest.py --exchange mexc --ml --compare
"""
import argparse
import pandas as pd

from exchanges.connectors import get_connector
from exchanges.multi_symbol_data import fetch_price_panel
from config.cross_sectional_config import DEFAULT_CONFIG
from strategies.cross_sectional_momentum import StrategyParams
from strategies.cross_sectional_risk import RiskStackConfig
from strategies.ml_pair_selector import MLFilterConfig
from backtest.cross_sectional_engine import (
    CrossSectionalBacktest, BacktestConfig, rebalance_phase_sweep
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", default="mexc")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--bars", type=int, default=1500)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--ml", action="store_true", help="Enable ML pair-reliability filter")
    parser.add_argument("--compare", action="store_true", help="Run with and without ML filter, side by side")
    args = parser.parse_args()

    cfg = DEFAULT_CONFIG
    connector = get_connector(args.exchange, testnet=False)
    connector.connect()

    print(f"Fetching {len(cfg.universe)} symbols @ {cfg.bar_timeframe} from {args.exchange}...")
    panel = fetch_price_panel(
        connector, cfg.universe, quote=cfg.quote_asset,
        timeframe=cfg.bar_timeframe, limit=args.bars, exchange_name=args.exchange,
    )
    print(f"Panel shape: {panel.shape}, from {panel.index[0]} to {panel.index[-1]}")

    strategy_params = StrategyParams(
        universe=list(panel.columns),
        formation_window_hours=cfg.formation_window_days * 24,
        rebalance_hours=cfg.rebalance_days * 24,
        n_long=cfg.n_long, n_short=cfg.n_short,
        taker_fee_bps=cfg.taker_fee_bps, base_leverage=cfg.base_leverage,
    )
    risk_config = RiskStackConfig(
        profit_lock_arm_pct=cfg.profit_lock_arm_pct,
        profit_lock_giveback_pct=cfg.profit_lock_giveback_pct,
        per_leg_stop_pct=cfg.per_leg_stop_pct,
        target_book_vol_annualized=cfg.target_book_vol_annualized,
        vol_lookback_hours=cfg.vol_lookback_days * 24,
        account_max_drawdown_pct=cfg.account_max_drawdown_pct,
    )

    if args.sweep:
        ml_cfg = MLFilterConfig(enabled=args.ml)
        sweep_df = rebalance_phase_sweep(panel, strategy_params, risk_config, ml_config=ml_cfg)
        print(f"\nRebalance-phase sweep (ml={'ON' if args.ml else 'OFF'}):")
        print(sweep_df.to_string(index=False))
        return

    if args.compare:
        for label, ml_enabled in [("WITHOUT ML filter", False), ("WITH ML filter", True)]:
            bt = CrossSectionalBacktest(BacktestConfig(
                initial_capital=args.capital,
                strategy_params=strategy_params,
                risk_config=risk_config,
                ml_config=MLFilterConfig(enabled=ml_enabled),
                use_risk_stack=True,
            ))
            result = bt.run(panel)
            print(f"\n--- {label} ---")
            print(f"Net return:   {result['net_return']:.2%}")
            print(f"Max drawdown: {result['max_drawdown']:.2%}")
            print(f"Sharpe:       {result['sharpe']:.2f}")
            print(f"# Rebalances: {result['n_rebalances']}")
        return

    bt = CrossSectionalBacktest(BacktestConfig(
        initial_capital=args.capital,
        strategy_params=strategy_params,
        risk_config=risk_config,
        ml_config=MLFilterConfig(enabled=args.ml),
        use_risk_stack=True,
    ))
    result = bt.run(panel)
    print(f"\nNet return:     {result['net_return']:.2%}")
    print(f"Max drawdown:   {result['max_drawdown']:.2%}")
    print(f"Sharpe:         {result['sharpe']:.2f}")
    print(f"# Rebalances:   {result['n_rebalances']}")


if __name__ == "__main__":
    main()
