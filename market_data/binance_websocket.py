import asyncio
import websockets
import json
from utils.logger import market_data_logger as logger
import inspect

class BinanceWebSocket:
    def __init__(self, symbol, callback):
        self.symbol = symbol
        self.callback = callback
        self.websocket_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
        self.running = False

    async def connect(self):
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    logger.info(f"Successfully connected to Binance WebSocket for {self.symbol}")
                    while self.running:
                        message = await websocket.recv()
                        data = json.loads(message)
                        logger.debug(f"Received raw trade data: {data}")
                        if inspect.iscoroutinefunction(self.callback):
                            await self.callback(data) 
                        else:
                            self.callback(data) 
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"WebSocket connection closed for {self.symbol}. Attempting to reconnect...")
                await asyncio.sleep(5)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse WebSocket message for {self.symbol}")
            except Exception as e:
                logger.error(f"WebSocket error for {self.symbol}: {str(e)}. Reconnecting...")
                await asyncio.sleep(5) 

    def start(self):
        logger.info(f"Starting WebSocket connection for {self.symbol}")
        asyncio.run(self.connect())

    def stop(self):
        self.running = False
        logger.info(f"Stopping WebSocket connection for {self.symbol}")