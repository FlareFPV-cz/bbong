import asyncio
import signal
from market_data.binance_websocket import BinanceWebSocket
from strategy.moving_average import MovingAverageCrossover
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
        self.strategy = MovingAverageCrossover(timeframe='1m')
        self.execution = BinanceExecution(simulate=True)
        self.balance = INITIAL_BALANCE
        self.position = None
        self.stop_loss = None
        self.websocket = None

    async def initialize(self):
        await self.execution.initialize()
        logger.info("Trading bot initialized")

    async def handle_trade(self, data):
        try:
            price = float(data['p'])
            logger.info(f"New trade: {price}")

            # Update strategy
            signal = self.strategy.update(price)

            # Execute order based on signal
            if signal == "buy" and not self.position:
                quantity = (self.balance * RISK_PERCENT) / price
                await self.execution.place_order(SYMBOL, "buy", quantity)
                self.position = price
                self.stop_loss = TrailingStopLoss(price)
            elif signal == "sell" and self.position:
                await self.execution.place_order(SYMBOL, "sell", quantity)
                self.position = None
                self.stop_loss = None

            # Update stop-loss
            if self.stop_loss:
                if self.stop_loss.update(price):
                    await self.execution.place_order(SYMBOL, "sell", quantity)
                    self.position = None
                    self.stop_loss = None
        except Exception as e:
            logger.error(f"Error in handle_trade: {str(e)}")

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
    
    # Add backtesting mode
    if len(sys.argv) > 1 and sys.argv[1] == '--backtest':
        from backtesting.historical_data import HistoricalData
        from backtesting.backtest_engine import BacktestEngine
        
        historical_data = HistoricalData(SYMBOL)
        data = await historical_data.get_historical_data()
        
        if data is not None:
            backtest = BacktestEngine(bot.strategy, INITIAL_BALANCE)
            results = await backtest.run(data)
            
            logger.info("Backtest Results:")
            logger.info(f"Total Trades: {results['total_trades']}")
            logger.info(f"Win Rate: {results['win_rate']:.2%}")
            logger.info(f"Total Profit: ${results['total_profit']:.2f}")
            logger.info(f"Final Balance: ${results['final_balance']:.2f}")
            logger.info(f"Return: {results['return_pct']:.2f}%")
        else:
            logger.error("Failed to fetch historical data")
    else:
        # Live trading mode
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        await bot.run()

if __name__ == "__main__":
    asyncio.run(main())