from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np
import random
from typing import Optional, Tuple, Deque, Dict

class BonkRoulette:
    def __init__(self, bb_period: int = 20, bb_std: float = 2.2, rsi_period: int = 14,
                 timeframe: str = '1m', min_volatility: float = 0.002,
                 risk_levels: list = [0.02, 0.04, 0.06], max_risk_per_trade: float = 0.015) -> None:
        # bb params
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.price_history = deque(maxlen=bb_period)
        
        # RSI parameters
        self.rsi_period = rsi_period
        self.gains = deque(maxlen=rsi_period)
        self.losses = deque(maxlen=rsi_period)
        self.rsi_values = deque(maxlen=10)  # Store recent RSI values for divergence detection
        
        # Volatility and risk parameters
        self.timeframe = timeframe
        self.min_volatility = min_volatility
        self.risk_levels = risk_levels
        self.max_risk_per_trade = max_risk_per_trade
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        # ATR for dynamic stop loss and take profit
        self.atr_period = 14
        self.atr_values = deque(maxlen=self.atr_period)
        
        # Position tracking
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_candle = None
        self.last_update = None
        
        # Performance tracking
        self.win_count = 0
        self.loss_count = 0
        self.consecutive_losses = 0
        
        logger.info(f"Initialized Enhanced BonkRoulette strategy with BB period: {bb_period}, "
                   f"RSI period: {rsi_period}, Risk levels: {risk_levels}, Max risk: {max_risk_per_trade*100}%")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000

    def calculate_bollinger_bands(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Calculate Bollinger Bands and bandwidth"""
        if len(self.price_history) < self.bb_period:
            return None, None, None, None
        
        prices = np.array(self.price_history)
        sma = np.mean(prices)
        std = np.std(prices)
        upper_band = sma + (self.bb_std * std)
        lower_band = sma - (self.bb_std * std)
        
        # Calculate bandwidth for volatility assessment
        bandwidth = (upper_band - lower_band) / sma if sma > 0 else 0
        
        return sma, upper_band, lower_band, bandwidth

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
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                
                self.rsi_values.append(rsi)
                return rsi
        return 50
    
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
    
    def detect_divergence(self, price, rsi):
        if len(self.price_history) < 5 or len(self.rsi_values) < 5:
            return False, None
            
        recent_prices = list(self.price_history)[-5:]
        recent_rsi = list(self.rsi_values)[-5:]
        
        # Bullish divergence: price making lower lows but RSI making higher lows
        if price < min(recent_prices[:-1]) and rsi > min(recent_rsi[:-1]):
            return True, "bullish"
            
        # Bearish divergence: price making higher highs but RSI making lower highs
        if price > max(recent_prices[:-1]) and rsi < max(recent_rsi[:-1]):
            return True, "bearish"
            
        return False, None

    def update(self, price: float, timestamp: Optional[float] = None,
              candle: Optional[Dict] = None, account_balance: float = 1000) -> Optional[str]:
        """
        Process market update and return trading signal
        
        Args:
            price: Current market price
            timestamp: Current timestamp in milliseconds
            candle: Complete candle data if available
            account_balance: Current account balance for position sizing
        
        Returns:
            Optional trading signal ('buy', 'sell', 'stop_loss', 'take_profit')
        """
        if candle:
            self.last_candle = self.current_candle.copy() if self.current_candle['open'] is not None else None
            self.current_candle = candle
            self.price_history.append(candle['close'])
            self.update_atr()
        else:
            if self.current_candle['open'] is None:
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
                self.last_update = timestamp
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price

        if timestamp and self.last_update and (timestamp - self.last_update >= self.timeframe_ms):
            self.last_candle = self.current_candle.copy()
            self.price_history.append(self.current_candle['close'])
            self.update_atr()
            self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
            self.last_update = timestamp

        if len(self.price_history) >= self.bb_period:
            sma, upper_band, lower_band, bandwidth = self.calculate_bollinger_bands()
            rsi = self.calculate_rsi(price)
            atr = self.calculate_atr()
            divergence_exists, divergence_type = self.detect_divergence(price, rsi)
            
            # Volatility check - only trade in sufficiently volatile markets
            volatility = bandwidth
            
            # Adjust risk based on consecutive losses
            adjusted_risk_levels = self.risk_levels
            if self.consecutive_losses > 1:
                # Reduce risk after consecutive losses
                adjusted_risk_levels = [level * 0.7 for level in self.risk_levels]
            
            if self.position is None and volatility > self.min_volatility:
                # Buy signal: price above upper band with extreme RSI and potential reversal
                if price > upper_band and rsi > 75 and divergence_exists and divergence_type == "bearish": 
                    self.position = "sell"  # Counter-trend strategy - sell when overbought
                    self.entry_price = price
                    
                    # Select risk level but cap it at max_risk_per_trade
                    risk_multiplier = min(random.choice(adjusted_risk_levels), self.max_risk_per_trade)
                    
                    # Use ATR for dynamic stop loss
                    self.stop_loss = price + (2.0 * atr)
                    self.take_profit = price - (3.5 * atr)
                    
                    logger.info(f"Opening SHORT position with {risk_multiplier*100:.2f}% risk level, ATR: {atr:.8f}")
                    return "sell"
                    
                # Sell signal: price below lower band with extreme RSI and potential reversal
                elif price < lower_band and rsi < 25 and divergence_exists and divergence_type == "bullish": 
                    self.position = "buy"  # Counter-trend strategy - buy when oversold
                    self.entry_price = price
                    
                    # Select risk level but cap it at max_risk_per_trade
                    risk_multiplier = min(random.choice(adjusted_risk_levels), self.max_risk_per_trade)
                    
                    # Use ATR for dynamic stop loss
                    self.stop_loss = price - (2.0 * atr)
                    self.take_profit = price + (3.5 * atr)
                    
                    logger.info(f"Opening LONG position with {risk_multiplier*100:.2f}% risk level, ATR: {atr:.8f}")
                    return "buy"

            # Exit logic with tracking of win/loss for risk management
            if self.position == "buy":
                if price <= self.stop_loss:
                    logger.info(f"Stop-loss triggered at {price:.8f}")
                    self.position = None
                    self.loss_count += 1
                    self.consecutive_losses += 1
                    return "stop_loss"
                elif price >= self.take_profit:
                    logger.info(f"Take-profit triggered at {price:.8f}")
                    self.position = None
                    self.win_count += 1
                    self.consecutive_losses = 0
                    return "take_profit"
            elif self.position == "sell":
                if price >= self.stop_loss:
                    logger.info(f"Stop-loss triggered at {price:.8f}")
                    self.position = None
                    self.loss_count += 1
                    self.consecutive_losses += 1
                    return "stop_loss"
                elif price <= self.take_profit:
                    logger.info(f"Take-profit triggered at {price:.8f}")
                    self.position = None
                    self.win_count += 1
                    self.consecutive_losses = 0
                    return "take_profit"

        return None

    def reset(self):
        self.price_history.clear()
        self.gains.clear()
        self.losses.clear()
        self.rsi_values.clear()
        self.atr_values.clear()
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_candle = None
        self.win_count = 0
        self.loss_count = 0
        self.consecutive_losses = 0
        logger.info("BonkRoulette strategy reset")