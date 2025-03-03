import asyncio
import itertools
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import logger
from utils.config import Config
from strategy.strategy_factory import StrategyFactory
from backtesting.historical_data import HistoricalData

class StrategyOptimizer:
    def __init__(self, strategy_name, symbol, initial_balance=1000):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.results = []
        self.best_params = None
        self.best_return = -float('inf')
        
        self.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'optimization_results'
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
    async def run_backtest(self, params):
        strategy = StrategyFactory.create_strategy(self.strategy_name, **params)
        
        balance = self.initial_balance
        position = None
        quantity = 0
        total_trades = 0
        winning_trades = 0
        
        historical_data = HistoricalData(self.symbol)
        
        async for kline in historical_data.simulate_streaming():
            signal = strategy.update(
                price=float(kline['close']),
                timestamp=kline['timestamp'].timestamp() * 1000,
                candle={
                    'open': float(kline['open']),
                    'high': float(kline['high']),
                    'low': float(kline['low']),
                    'close': float(kline['close']),
                    'volume': float(kline['volume'])
                }
            )
            
            if signal == "buy" and not position:
                quantity = (balance * 0.01) / float(kline['close'])
                position = float(kline['close'])
                
            elif signal == "sell" and position:
                pl = (float(kline['close']) - position) * quantity
                balance += pl
                total_trades += 1
                if float(kline['close']) > position:
                    winning_trades += 1
                position = None
                
            if position and (signal == "stop_loss" or signal == "take_profit"):
                pl = (float(kline['close']) - position) * quantity
                balance += pl
                total_trades += 1
                if float(kline['close']) > position:
                    winning_trades += 1
                position = None
        
        final_balance = balance
        total_return = ((final_balance - self.initial_balance) / self.initial_balance) * 100
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'params': params,
            'final_balance': final_balance,
            'total_return': total_return,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate
        }
    
    async def optimize(self, param_grid):
        keys = param_grid.keys()
        combinations = itertools.product(*param_grid.values())
        param_combinations = [dict(zip(keys, combo)) for combo in combinations]
        
        logger.info(f"Starting optimization with {len(param_combinations)} parameter combinations")
        
        for i, params in enumerate(param_combinations):
            logger.info(f"Testing combination {i+1}/{len(param_combinations)}: {params}")
            result = await self.run_backtest(params)
            self.results.append(result)
            
            if result['total_return'] > self.best_return:
                self.best_return = result['total_return']
                self.best_params = params
                logger.info(f"New best parameters found: {params} with return: {self.best_return:.2f}%")
        
        self.results.sort(key=lambda x: x['total_return'], reverse=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.strategy_name}_{self.symbol}_optimization_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump({
                'strategy': self.strategy_name,
                'symbol': self.symbol,
                'timestamp': timestamp,
                'best_params': self.best_params,
                'best_return': self.best_return,
                'results': self.results[:10] 
            }, f, indent=4)
        
        logger.info(f"Optimization complete. Results saved to {filepath}")
        logger.info(f"Best parameters: {self.best_params}")
        logger.info(f"Best return: {self.best_return:.2f}%")
        
        return self.best_params, self.best_return, filepath