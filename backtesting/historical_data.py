import pandas as pd
from binance.client import Client
from datetime import datetime, timedelta
from utils.logger import logger

class HistoricalData:
    def __init__(self, symbol, interval='1m', start_date=None, end_date=None):
        self.symbol = symbol.upper()
        self.interval = interval
        self.start_date = start_date or (datetime.now() - timedelta(days=10))
        self.end_date = end_date or datetime.now()
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
    async def simulate_streaming(self):
        df = await self.get_historical_data()
        if df is None:
            return
        
        for timestamp, row in df.iterrows():
            kline_data = {
                'timestamp': timestamp,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']),
                'trades': int(row['trades']),
                'interval': self.interval
            }
            yield kline_data
            
    async def get_historical_data(self):
        try:
            binance_interval = self.interval_map.get(self.interval, Client.KLINE_INTERVAL_1MINUTE)
            klines = self.client.get_historical_klines(
                self.symbol,
                binance_interval,
                self.start_date.strftime("%d %b %Y %H:%M:%S"),
                self.end_date.strftime("%d %b %Y %H:%M:%S")
            )
            
            df = pd.DataFrame(klines, columns=[
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