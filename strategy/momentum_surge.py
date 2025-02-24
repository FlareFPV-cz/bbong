from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np

class MomentumSurge:
    def __init__(self, short_window=2, long_window=10, trend_window=15, min_trend_strength=0.005, rsi_period=10, timeframe='1m', atr_period=10, risk_per_trade=0.03):
        self.short_window = short_window
        self.long_window = long_window
        self.trend_window = trend_window
        self.min_trend_strength = min_trend_strength
        self.rsi_period = rsi_period
        self.timeframe = timeframe
        self.atr_period = atr_period
        self.risk_per_trade = risk_per_trade
        
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_update = None
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        self.short_ma = deque(maxlen=short_window)
        self.long_ma = deque(maxlen=long_window)
        self.trend_ma = deque(maxlen=trend_window)
        self.price_history = deque(maxlen=trend_window)
        self.gains = deque(maxlen=rsi_period)
        self.losses = deque(maxlen=rsi_period)
        self.atr_values = deque(maxlen=atr_period)
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        
        logger.info(f"Initialized MomentumSurge with aggressive parameters")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000 

    def update(self, price, timestamp=None, candle=None):
        if candle:
            self.current_candle = candle
            candle_price = candle['close']
            self.short_ma.append(candle_price)
            self.long_ma.append(candle_price)
            self.trend_ma.append(candle_price)
            self.price_history.append(candle_price)
            self.update_atr(candle_price)
        else:
            if self.current_candle['open'] is None:
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
                self.last_update = timestamp
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price

        if timestamp and self.last_update and (timestamp - self.last_update >= self.timeframe_ms):
            candle_price = self.current_candle['close']
            self.short_ma.append(candle_price)
            self.long_ma.append(candle_price)
            self.trend_ma.append(candle_price)
            self.price_history.append(candle_price)
            self.update_atr(candle_price)

            self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
            self.last_update = timestamp

        if (len(self.short_ma) == self.short_window and 
            len(self.long_ma) == self.long_window and 
            len(self.trend_ma) == self.trend_window):

            short_avg = self.calculate_ma(self.short_ma)
            long_avg = self.calculate_ma(self.long_ma)
            trend_strength = self.calculate_trend_strength()
            rsi = self.calculate_rsi(price)
            atr = self.calculate_atr()

            logger.debug(f"MAs - Short: {short_avg:.8f}, Long: {long_avg:.8f}, "
                        f"Trend Strength: {trend_strength:.4%}, RSI: {rsi:.2f}, ATR: {atr:.8f}")

            if abs(trend_strength) >= self.min_trend_strength:
                if (short_avg > long_avg and trend_strength > 0 and 
                    self.position != "buy" and rsi > 50):
                    self.entry_price = price
                    self.stop_loss = price - 1 * atr 
                    self.take_profit = price + 2 * atr  
                    logger.info(f"Buy signal - MA cross with RSI: {rsi:.2f}, ATR: {atr:.8f}")
                    self.position = "buy"
                    return "buy"
                elif (short_avg < long_avg and trend_strength < 0 and 
                      self.position != "sell" and rsi < 50): 
                    self.entry_price = price
                    self.stop_loss = price + 1 * atr  
                    self.take_profit = price - 2 * atr
                    logger.info(f"Sell signal - MA cross with RSI: {rsi:.2f}, ATR: {atr:.8f}")
                    self.position = "sell"
                    return "sell"

        if self.position == "buy" and price <= self.stop_loss:
            logger.info(f"Stop-loss triggered at {price:.8f}")
            self.position = None
            return "stop_loss"
        elif self.position == "buy" and price >= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            return "take_profit"
        elif self.position == "sell" and price >= self.stop_loss:
            logger.info(f"Stop-loss triggered at {price:.8f}")
            self.position = None
            return "stop_loss"
        elif self.position == "sell" and price <= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            return "take_profit"

        return None

    def calculate_ma(self, data):
        return sum(data) / len(data) if len(data) > 0 else None

    def calculate_rsi(self, price):
        if len(self.price_history) > 1:
            change = price - self.price_history[-1]
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

    def calculate_trend_strength(self):
        if len(self.trend_ma) == self.trend_window:
            trend_start = self.calculate_ma(list(self.trend_ma)[:3]) 
            trend_end = self.calculate_ma(list(self.trend_ma)[-3:])
            return (trend_end - trend_start) / trend_start if trend_start and trend_start > 0 else 0
        return 0

    def update_atr(self, price):
        if len(self.price_history) > 1:
            tr = max(self.current_candle['high'] - self.current_candle['low'], 
                     abs(self.current_candle['high'] - self.price_history[-1]), 
                     abs(self.current_candle['low'] - self.price_history[-1]))
            self.atr_values.append(tr)

    def calculate_atr(self):
        if len(self.atr_values) == self.atr_period:
            return sum(self.atr_values) / self.atr_period
        return 0

    def reset(self):
        self.short_ma.clear()
        self.long_ma.clear()
        self.trend_ma.clear()
        self.price_history.clear()
        self.gains.clear()
        self.losses.clear()
        self.atr_values.clear()
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        logger.info("Strategy reset for new session")