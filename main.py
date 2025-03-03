import asyncio
import signal
import sys
from market_data.binance_websocket import BinanceWebSocket
from strategy.strategy_factory import StrategyFactory
from execution.binance_execution import BinanceExecution
from risk_management.stop_loss import TrailingStopLoss
from utils.logger import logger
from utils.config import Config
import os

config = Config()
SYMBOL = config.get("trading", "symbol")
RISK_PERCENT = config.get("trading", "risk_percent")
INITIAL_BALANCE = config.get("trading", "initial_balance")
SIMULATE = config.get("trading", "simulate")

class TradingBot:
    def __init__(self):
        strategy_config = config.get("strategy")
        self.strategy = StrategyFactory.create_strategy(
            strategy_config["name"], 
            **strategy_config["params"]
        )
        self.execution = BinanceExecution(simulate=SIMULATE)
        self.balance = INITIAL_BALANCE
        self.position = None
        self.stop_loss = None
        self.websocket = None
        self.total_trades = 0
        self.winning_trades = 0
        self.initial_balance = INITIAL_BALANCE
        self.trades = [] 
        self.quantity = 0

    async def handle_trade(self, data):
        try:
            price = float(data['p'])
            timestamp = data.get('t', None) 
            logger.info(f"New trade: {price}")

            signal = self.strategy.update(price)

            if signal == "buy" and not self.position:
                self.quantity = (self.balance * RISK_PERCENT) / price
                await self.execution.place_order(SYMBOL, "buy", self.quantity)
                self.position = price
                self.stop_loss = TrailingStopLoss(price)
                
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'buy',
                    'price': price,
                    'quantity': self.quantity,
                    'balance': self.balance
                })
                
            elif signal == "sell" and self.position:
                pl = (price - self.position) * self.quantity
                self.balance += pl
                
                await self.execution.place_order(SYMBOL, "sell", self.quantity)
                self.total_trades += 1
                if price > self.position:
                    self.winning_trades += 1
                
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'sell',
                    'price': price,
                    'quantity': self.quantity,
                    'balance': self.balance,
                    'profit': pl
                })
                
                self.position = None
                self.stop_loss = None

            if self.stop_loss and self.position:
                if self.stop_loss.update(price):
                    pl = (price - self.position) * self.quantity
                    self.balance += pl
                    
                    await self.execution.place_order(SYMBOL, "sell", self.quantity)
                    self.total_trades += 1
                    if price > self.position:
                        self.winning_trades += 1
                    
                    self.trades.append({
                        'timestamp': timestamp,
                        'type': 'sell',
                        'price': price,
                        'quantity': self.quantity,
                        'balance': self.balance,
                        'profit': pl,
                        'reason': 'stop_loss'
                    })
                    
                    self.position = None
                    self.stop_loss = None
                    
        except Exception as e:
            logger.error(f"Error in handle_trade: {str(e)}")

    async def initialize(self):
        await self.execution.initialize()
        logger.info("Trading bot initialized")

    async def run(self):
        await self.initialize()
        self.websocket = BinanceWebSocket(SYMBOL, self.handle_trade)
        await self.websocket.connect()

    async def stop(self):
        if self.websocket:
            self.websocket.stop()
        await self.execution.close()
        logger.info("Trading bot stopped.")

bot = None

def handle_shutdown(signum, frame):
    logger.info("Shutting down...")
    if bot:
        asyncio.create_task(bot.stop())
    exit(0)

async def main():
    global bot
    bot = TradingBot()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--backtest':
            from backtesting.historical_data import HistoricalData
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            historical_data = HistoricalData(
                symbol=SYMBOL,
                interval='1m',  
                start_date=start_date,
                end_date=end_date
            )
            await bot.initialize()
            
            timestamp = None
            
            async for kline in historical_data.simulate_streaming():
                timestamp_str = kline['timestamp']
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
                
                trade_data = {
                    'p': float(kline['close']),
                    't': timestamp.timestamp() * 1000,
                    'q': float(kline['volume'])
                }
                
                signal = bot.strategy.update(
                    price=float(kline['close']),
                    timestamp=timestamp.timestamp() * 1000,
                    candle={
                        'open': float(kline['open']),
                        'high': float(kline['high']),
                        'low': float(kline['low']),
                        'close': float(kline['close']),
                        'volume': float(kline['volume'])
                    }
                )
                
                if signal:
                    await bot.handle_trade(trade_data)
            
            final_balance = bot.balance
            total_return = ((final_balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
            win_rate = (bot.winning_trades / bot.total_trades * 100) if bot.total_trades > 0 else 0
            
        elif sys.argv[1] == '--optimize':
            from optimization.cli import StrategyOptimizer
            
            strategy_config = config.get("strategy")
            strategy_name = strategy_config["name"]
            
            logger.info(f"Starting optimization for {strategy_name} on {SYMBOL}")
            
            optimizer = StrategyOptimizer(
                strategy_name,
                SYMBOL,
                INITIAL_BALANCE
            )
            
            if strategy_name == 'momentum_surge':
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
            elif strategy_name == 'moving_average':
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
            
            best_params, best_return, results_file = await optimizer.optimize(param_grid)
            
            if best_params:
                config.update("strategy", "params", best_params)
                logger.info(f"Applied optimized parameters: {best_params}")
                logger.info(f"Best return: {best_return:.2f}%")
                logger.info(f"Detailed results saved to: {results_file}")
            
            return
    else:
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        await bot.run()
        
        while True:
            if dashboard_thread:
                update_bot_status({
                    "running": True,
                    "symbol": SYMBOL,
                    "balance": bot.balance,
                    "position": bot.position,
                    "total_trades": bot.total_trades,
                    "winning_trades": bot.winning_trades,
                    "profit_loss": bot.balance - INITIAL_BALANCE
                })
                
                with open(os.path.join(data_dir, 'trades.json'), 'w') as f:
                    json.dump(bot.trades, f)
                
                with open(os.path.join(data_dir, 'equity.json'), 'w') as f:
                    json.dump([{
                        'timestamp': datetime.now().isoformat(),
                        'equity': bot.balance + (bot.quantity * bot.position if bot.position else 0)
                    }], f)
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())