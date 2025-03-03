import asyncio
import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optimizer import StrategyOptimizer
from utils.logger import logger
from utils.config import Config

async def main():
    parser = argparse.ArgumentParser(description='Optimize trading strategy parameters')
    parser.add_argument('--strategy', type=str, default='momentum_surge', 
                        help='Strategy name to optimize')
    parser.add_argument('--symbol', type=str, default='bonkusdt',
                        help='Symbol to backtest on')
    parser.add_argument('--balance', type=float, default=1000.0,
                        help='Initial balance for backtesting')
    parser.add_argument('--params', type=str, default=None,
                        help='JSON file with parameter grid')
    parser.add_argument('--apply', action='store_true',
                        help='Apply best parameters to config')
    
    args = parser.parse_args()
    
    if args.params:
        with open(args.params, 'r') as f:
            param_grid = json.load(f)
    else:
        if args.strategy == 'momentum_surge':
            param_grid = {
                'short_window': [2, 3, 4],
                'long_window': [8, 10, 12],
                'trend_window': [12, 15, 18],
                'min_trend_strength': [0.003, 0.005, 0.007],
                'rsi_period': [8, 10, 12],
                'timeframe': ['1m'],
                'atr_period': [8, 10, 12],
                'risk_per_trade': [0.02, 0.03, 0.04]
            }
        # Default parameter grid for moving_average
        elif args.strategy == 'moving_average':
            param_grid = {
                'short_window': [6, 8, 10],
                'long_window': [18, 21, 24],
                'trend_window': [40, 50, 60],
                'min_trend_strength': [0.001, 0.002, 0.003],
                'rsi_period': [12, 14, 16],
                'timeframe': ['1m'],
                'atr_period': [12, 14, 16],
                'risk_per_trade': [0.01, 0.015, 0.02]
            }
        else:
            logger.error(f"No default parameter grid for strategy: {args.strategy}")
            return
    
    logger.info(f"Optimizing {args.strategy} on {args.symbol} with initial balance ${args.balance}")
    logger.info(f"Parameter grid: {param_grid}")
    
    optimizer = StrategyOptimizer(args.strategy, args.symbol, args.balance)
    best_params, best_return, results_file = await optimizer.optimize(param_grid)
    
    if args.apply:
        config = Config()
        strategy_config = config.get("strategy")
        
        if strategy_config["name"] == args.strategy:
            logger.info(f"Applying best parameters to config: {best_params}")
            config.update("strategy", "params", best_params)
            logger.info("Parameters applied successfully")
        else:
            logger.warning(f"Config strategy ({strategy_config['name']}) doesn't match optimized strategy ({args.strategy})")
            logger.warning("Parameters not applied")

if __name__ == "__main__":
    asyncio.run(main())