from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np

class BonkQuant:
    def __init__(self, ema_period=200, bb_period=20, bb_std=2, atr_period=14, 
                 timeframe='1m', risk_per_trade=0.01): 
        self.ema_period = ema_period
        self.ema_alpha = 2 / (ema_period + 1)
        self.ema_value = None
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        
        self.atr_period = atr_period
        self.atr_values = deque(maxlen=atr_period)
        
        self.risk_per_trade = risk_per_trade
        
        self.price_history = deque(maxlen=max(ema_period, bb_period))
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None}
        self.last_candle = None
        
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.position_size = 1.0
        
        self.timeframe = timeframe
        self.last_update = None
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        logger.info(f"Initialized BonkQuant strategy with EMA period: {ema_period}, "
                   f"BB period: {bb_period}, ATR period: {atr_period}")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000

    def calculate_ema(self, price):
        if self.ema_value is None and len(self.price_history) >= self.ema_period:
            self.ema_value = sum(self.price_history) / len(self.price_history)
        elif self.ema_value is not None:
            self.ema_value = (price * self.ema_alpha) + (self.ema_value * (1 - self.ema_alpha))
        return self.ema_value

    def calculate_bollinger_bands(self):
        if len(self.price_history) < self.bb_period:
            return None, None, None
        
        prices = list(self.price_history)[-self.bb_period:]
        sma = sum(prices) / len(prices)
        std = np.std(prices)
        upper_band = sma + (self.bb_std * std)
        lower_band = sma - (self.bb_std * std)
        return sma, upper_band, lower_band

    def update_atr(self):
        if self.last_candle is not None:
            tr = max(
                self.current_candle['high'] - self.current_candle['low'],
                abs(self.current_candle['high'] - self.last_candle['close']),
                abs(self.current_candle['low'] - self.last_candle['close'])
            )
            self.atr_values.append(tr)

    def calculate_atr(self):
        if len(self.atr_values) == self.atr_period:
            return sum(self.atr_values) / self.atr_period
        elif len(self.atr_values) > 0:
            return sum(self.atr_values) / len(self.atr_values)
        return 0

    def calculate_position_size(self, account_balance):
        atr = self.calculate_atr()
        if atr == 0:
            return 1.0
        
        risk_amount = account_balance * self.risk_per_trade
        position_size = risk_amount / (atr * 1.5)
        return position_size

    def update(self, price, timestamp=None, candle=None, account_balance=1000):
        if candle:
            self.last_candle = self.current_candle.copy() if self.current_candle['open'] is not None else None
            self.current_candle = candle
            self.price_history.append(candle['close'])
            self.update_atr()
        else:
            if self.current_candle['open'] is None:
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price}
                self.last_update = timestamp
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price

            if timestamp and self.last_update and (timestamp - self.last_update >= self.timeframe_ms):
                self.last_candle = self.current_candle.copy()
                self.price_history.append(self.current_candle['close'])
                self.update_atr()
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price}
                self.last_update = timestamp

        ema = self.calculate_ema(price)
        sma, upper_band, lower_band = self.calculate_bollinger_bands()
        atr = self.calculate_atr()
        
        if ema is None or sma is None or atr == 0:
            return None
        
        trend = "bullish" if price > ema else "bearish"
        
        if self.position is None:
            self.position_size = self.calculate_position_size(account_balance)
            
            if trend == "bullish" and price <= lower_band:
                self.position = "buy"
                self.entry_price = price
                self.stop_loss = price - (1.5 * atr)
                self.take_profit = price + (3 * atr)
                logger.info(f"BUY signal - Bullish trend, price at lower BB. Entry: {price:.8f}, SL: {self.stop_loss:.8f}, TP: {self.take_profit:.8f}")
                return "buy"
            elif trend == "bearish" and price >= upper_band:
                self.position = "sell"
                self.entry_price = price
                self.stop_loss = price + (1.5 * atr)
                self.take_profit = price - (3 * atr)
                logger.info(f"SELL signal - Bearish trend, price at upper BB. Entry: {price:.8f}, SL: {self.stop_loss:.8f}, TP: {self.take_profit:.8f}")
                return "sell"
        else:
            if self.position == "buy":
                if price <= self.stop_loss:
                    logger.info(f"Stop-loss triggered at {price:.8f}")
                    self.position = None
                    return "stop_loss"
                elif price >= self.take_profit:
                    logger.info(f"Take-profit triggered at {price:.8f}")
                    self.position = None
                    return "take_profit"
            elif self.position == "sell":
                if price >= self.stop_loss:
                    logger.info(f"Stop-loss triggered at {price:.8f}")
                    self.position = None
                    return "stop_loss"
                elif price <= self.take_profit:
                    logger.info(f"Take-profit triggered at {price:.8f}")
                    self.position = None
                    return "take_profit"

        return None

    def reset(self):
        self.price_history.clear()
        self.atr_values.clear()
        self.ema_value = None
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None}
        self.last_candle = None
        logger.info("BonkQuant strategy reset")