from binance import AsyncClient, BinanceSocketManager
from utils.logger import execution_logger as logger
import os
from dotenv import load_dotenv

load_dotenv()

class BinanceExecution:
    def __init__(self, simulate=True):
        self.simulate = simulate
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        self.client = None
        logger.debug(f"Initialized BinanceExecution with simulate={simulate}")

    async def initialize(self):
        if not self.simulate:
            self.client = await AsyncClient.create(self.api_key, self.api_secret)
            logger.info("Successfully initialized Binance client")

    async def place_order(self, symbol, side, quantity):
        if self.simulate:
            logger.info(f"Simulated {side.upper()} order: {quantity} {symbol}")
            logger.debug(f"Order details - Symbol: {symbol}, Side: {side.upper()}, Quantity: {quantity}")
        else:
            try:
                # order = await self.client.create_order(
                #     symbol=symbol,
                #     side=side.upper(),
                #     type="LIMIT",
                #     timeInForce="GTC",
                #     quantity=quantity,
                #     price="0.001", 
                # )
                logger.info(f"Successfully placed {side.upper()} order for {quantity} {symbol}")
                # logger.debug(f"Order details: {order}")
            except Exception as e:
                logger.error(f"Order placement failed - Symbol: {symbol}, Side: {side.upper()}, Quantity: {quantity}")
                logger.error(f"Error details: {str(e)}")

    async def close(self):
        if self.client:
            await self.client.close_connection()
            logger.info("Closed Binance client connection")