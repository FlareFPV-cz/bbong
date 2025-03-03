import asyncio
import os
import sys
from utils.logger import logger

async def test_historical_data():
    """Test historical data fetching"""
    from backtesting.historical_data import HistoricalData
    
    logger.info("Testing historical data...")
    historical = HistoricalData("BTCUSDT")
    historical.set_limit(5)  # Only get 5 candles for quick testing
    
    count = 0
    async for kline in historical.simulate_streaming():
        logger.info(f"Candle: {kline['timestamp']} - Close: {kline['close']}")
        count += 1
    
    logger.info(f"Retrieved {count} candles successfully")
    return count > 0

async def test_optimizer_imports():
    """Test optimizer imports"""
    logger.info("Testing optimizer imports...")
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from optimization.optimizer import StrategyOptimizer
        logger.info("Optimizer imports successful")
        return True
    except Exception as e:
        logger.error(f"Optimizer import error: {str(e)}")
        return False

async def main():
    logger.info("Running quick tests to verify fixes...")
    
    historical_test = await test_historical_data()
    optimizer_test = await test_optimizer_imports()
    
    if historical_test and optimizer_test:
        logger.info("All quick tests passed! You can now run the full test suite.")
    else:
        logger.error("Some tests failed. Please check the logs for details.")

if __name__ == "__main__":
    asyncio.run(main())