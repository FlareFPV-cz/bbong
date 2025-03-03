from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np
import random

class BonkRoulette:
    def __init__(self, bb_period=20, bb_std=2, rsi_period=14, timeframe='1m',
             min_volatility=0.003, risk_levels=[0.05, 0.10, 0.15]):
        # bb params
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.price_history = deque(maxlen=bb_period)
        
        self.rsi_period = rsi_period
        self.gains = deque(maxlen=rsi_period)
        self.losses = deque(maxlen=rsi_period)
        
        self.timeframe = timeframe
        self.min_volatility = min_volatility
        self.risk_levels = risk_levels
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None}
        self.last_update = None
        
        logger.info(f"Initialized BonkRoulette strategy with BB period: {bb_period}, "
                   f"RSI period: {rsi_period}, Risk levels: {risk_levels}")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000

    def calculate_bollinger_bands(self):
        if len(self.price_history) < self.bb_period:
            return None, None, None
        
        prices = np.array(self.price_history)
        sma = np.mean(prices)
        std = np.std(prices)
        upper_band = sma + (self.bb_std * std)
        lower_band = sma - (self.bb_std * std)
        return sma, upper_band, lower_band

    def calculate_rsi(self, price):
        if len(self.price_history) > 1:
            change = price - list(self.price_history)[-1]
            gain = max(change, 0)
            loss = abs(min(change, 0))
            
            self.gains.append(gain)
            self.losses.append(loss)
            
            if len(self.gains) == self.rsi_period:
                avg_gain = sum(self.gains) / self.rsi_period
                avg_loss = sum(self.losses) / self.rsi_period
                
                if avg_loss == 0:
                    return 100
                rs = avg_gain / avg_loss
                return 100 - (100 / (1 + rs))
        return 50

    def update(self, price, timestamp=None, candle=None):
        if candle:
            self.current_candle = candle
            self.price_history.append(candle['close'])
        else:
            if self.current_candle['open'] is None:
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price}
                self.last_update = timestamp
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price

            if timestamp and self.last_update and (timestamp - self.last_update >= self.timeframe_ms):
                self.price_history.append(self.current_candle['close'])
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price}
                self.last_update = timestamp

        if len(self.price_history) >= self.bb_period:
            sma, upper_band, lower_band = self.calculate_bollinger_bands()
            rsi = self.calculate_rsi(price)
            
            #volaaaaa
            volatility = (upper_band - lower_band) / sma if sma else 0
            
            if self.position is None and volatility > self.min_volatility:
                if price > upper_band and rsi > 70: 
                    self.position = "buy"
                    self.entry_price = price
                    risk_multiplier = random.choice(self.risk_levels)
                    self.stop_loss = price * 0.95 
                    self.take_profit = price * (1 + (0.2 * risk_multiplier)) 
                    logger.info(f"Opening LONG position with {risk_multiplier*100}% risk level")
                    return "buy"
                elif price < lower_band and rsi < 30: 
                    self.position = "sell"
                    self.entry_price = price
                    risk_multiplier = random.choice(self.risk_levels)
                    self.stop_loss = price * 1.05 
                    self.take_profit = price * (1 - (0.2 * risk_multiplier)) 
                    logger.info(f"Opening SHORT position with {risk_multiplier*100}% risk level")
                    return "sell"

            if self.position == "buy":
                if price <= self.stop_loss:
                    self.position = None
                    return "stop_loss"
                elif price >= self.take_profit:
                    self.position = None
                    return "take_profit"
            elif self.position == "sell":
                if price >= self.stop_loss:
                    self.position = None
                    return "stop_loss"
                elif price <= self.take_profit:
                    self.position = None
                    return "take_profit"

        return None

    def reset(self):
        self.price_history.clear()
        self.gains.clear()
        self.losses.clear()
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        logger.info("BonkRoulette strategy reset")