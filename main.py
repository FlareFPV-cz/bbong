import asyncio
import signal
from market_data.binance_websocket import BinanceWebSocket
from strategy.momentum_surge import MomentumSurge
from execution.binance_execution import BinanceExecution
from risk_management.stop_loss import TrailingStopLoss
from utils.logger import logger
import sys

# Configuration
SYMBOL = "bonkusdt"
RISK_PERCENT = 0.01  # 1% of account balance
INITIAL_BALANCE = 1000  # Simulated account balance

class TradingBot:
    def __init__(self):
        self.strategy = MomentumSurge(timeframe='1m')
        self.execution = BinanceExecution(simulate=True)
        self.balance = INITIAL_BALANCE
        self.position = None
        self.stop_loss = None
        self.websocket = None
        self.total_trades = 0
        self.winning_trades = 0
        self.initial_balance = INITIAL_BALANCE

    async def handle_trade(self, data):
        try:
            price = float(data['p'])
            logger.info(f"New trade: {price}")

            signal = self.strategy.update(price)

            if signal == "buy" and not self.position:
                self.quantity = (self.balance * RISK_PERCENT) / price
                await self.execution.place_order(SYMBOL, "buy", self.quantity)
                self.position = price
                self.stop_loss = TrailingStopLoss(price)
                
            elif signal == "sell" and self.position:
                pl = (price - self.position) * self.quantity
                self.balance += pl
                
                await self.execution.place_order(SYMBOL, "sell", self.quantity)
                self.total_trades += 1
                if price > self.position:
                    self.winning_trades += 1
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

def handle_shutdown(signum, frame):
    logger.info("Shutting down...")
    bot.stop()
    exit(0)

async def main():
    bot = TradingBot()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--backtest':
        from backtesting.historical_data import HistoricalData
        
        historical_data = HistoricalData(SYMBOL)
        await bot.initialize()
        
        async for kline in historical_data.simulate_streaming():
            trade_data = {
                'p': float(kline['close']),
                't': kline['timestamp'].timestamp() * 1000,
                'q': float(kline['volume'])
            }
            
            signal = bot.strategy.update(
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
            
            if signal:
                await bot.handle_trade(trade_data)
        
        final_balance = bot.balance
        total_return = ((final_balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        win_rate = (bot.winning_trades / bot.total_trades * 100) if bot.total_trades > 0 else 0
        
        logger.info("\n=== Backtest Results ===")
        logger.info(f"Total Trades: {bot.total_trades}")
        logger.info(f"Winning Trades: {bot.winning_trades}")
        logger.info(f"Win Rate: {win_rate:.2f}%")
        logger.info(f"Initial Balance: ${INITIAL_BALANCE:.2f}")
        logger.info(f"Final Balance: ${final_balance:.2f}")
        logger.info(f"Total Return: {total_return:.2f}%")
        logger.info("=====================")
        logger.info(f"Return: {total_return:.2f}%")
        
    else:
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        await bot.run()

if __name__ == "__main__":
    asyncio.run(main())