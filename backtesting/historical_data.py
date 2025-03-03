import pandas as pd
import asyncio
from binance.client import Client
from datetime import datetime, timedelta
from utils.logger import logger
import aiohttp

class HistoricalData:
    def __init__(self, symbol, interval='1m', start_date=None, end_date=None, limit=1000):
        self.symbol = symbol.upper() 
        self.interval = interval
        self.end_date = end_date if end_date else datetime.now()
        self.start_date = start_date if start_date else self.end_date - timedelta(days=30) 
        self.limit = min(limit, 1000) 
        self.data = []
        self.client = Client()
        
        self.interval_map = {
            '1m': Client.KLINE_INTERVAL_1MINUTE,
            '3m': Client.KLINE_INTERVAL_3MINUTE,
            '5m': Client.KLINE_INTERVAL_5MINUTE,
            '15m': Client.KLINE_INTERVAL_15MINUTE,
            '30m': Client.KLINE_INTERVAL_30MINUTE,
            '1h': Client.KLINE_INTERVAL_1HOUR,
            '2h': Client.KLINE_INTERVAL_2HOUR,
            '4h': Client.KLINE_INTERVAL_4HOUR,
            '1d': Client.KLINE_INTERVAL_1DAY,
        }
        
    async def get_historical_data(self):
        try:
            binance_interval = self.interval_map.get(self.interval, Client.KLINE_INTERVAL_1MINUTE)
            
            start_str = self.start_date.strftime("%d %b %Y %H:%M:%S")
            end_str = self.end_date.strftime("%d %b %Y %H:%M:%S")
            
            logger.info(f"Fetching {self.symbol} data from {start_str} to {end_str} with interval {binance_interval}")
            
            all_klines = []
            temp_start = self.start_date
            
            while temp_start < self.end_date:
                temp_start_str = temp_start.strftime("%d %b %Y %H:%M:%S")
                
                klines = self.client.get_historical_klines(
                    self.symbol,
                    binance_interval,
                    temp_start_str,
                    end_str,
                    limit=1000
                )
                
                if not klines:
                    break
                    
                all_klines.extend(klines)
                logger.info(f"Retrieved {len(klines)} candles, total now: {len(all_klines)}")
                
                last_timestamp = int(klines[-1][0])
                
                interval_ms = {
                    '1m': 60000,
                    '3m': 180000,
                    '5m': 300000,
                    '15m': 900000,
                    '30m': 1800000,
                    '1h': 3600000,
                    '2h': 7200000,
                    '4h': 14400000,
                    '1d': 86400000
                }.get(self.interval, 60000)
                
                temp_start = datetime.fromtimestamp((last_timestamp + interval_ms) / 1000)
                
                if hasattr(self, '_limit') and len(all_klines) >= self._limit:
                    all_klines = all_klines[:self._limit]
                    break
            
            if not all_klines:
                logger.warning(f"No data returned for {self.symbol} from {start_str} to {end_str}")
                return None
                
            logger.info(f"Retrieved total of {len(all_klines)} candles for {self.symbol}")
            
            df = pd.DataFrame(all_klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {str(e)}")
            return None
            
    def set_limit(self, limit):
        self._limit = limit
        self.limit = limit 
        
    async def simulate_streaming(self):
        df = await self.get_historical_data()
        if df is None or df.empty:
            logger.error(f"No historical data available for {self.symbol}")
            return
            
        logger.info(f"Starting to stream {len(df)} historical candles")
        
        for index, row in df.iterrows():
            candle = {
                'timestamp': index,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            }
            yield candle
            
            await asyncio.sleep(0.001)