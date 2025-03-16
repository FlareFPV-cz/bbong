from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple, Deque, Dict, List

class BonkQuant:    
    def __init__(self, ema_period: int = 50, bb_period: int = 20, bb_std: float = 2.0, 
                 atr_period: int = 14, rsi_period: int = 14, macd_fast: int = 12, 
                 macd_slow: int = 26, macd_signal: int = 9, volume_ma_period: int = 20, 
                 timeframe: str = '1m', risk_per_trade: float = 0.05,
                 trailing_stop: bool = True, dynamic_tp: bool = True,
                 adx_period: int = 14, adx_threshold: int = 25,
                 volatility_period: int = 20, max_daily_loss: float = 40) -> None:
        self.ema_period = ema_period
        self.ema_alpha = 2 / (ema_period + 1)
        self.ema_value = None
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bb_squeeze_threshold = 0.09  # Reduced to be more selective in low volatility
        
        self.atr_period = atr_period
        self.atr_values = deque(maxlen=atr_period)
        self.atr_multiplier_sl = 1.5  # Tighter stops to minimize losses
        self.atr_multiplier_tp = 3.0  # Increased for better reward/risk ratio
        self.risk_per_trade = risk_per_trade
        self.trailing_stop = trailing_stop
        self.dynamic_tp = dynamic_tp
        # Trade tracking
        self.max_loss_streak = 0
        self.current_loss_streak = 0
        self.win_count = 0
        self.loss_count = 0
        self.daily_pnl = 0.0
        self.max_daily_loss = max_daily_loss
        self.last_trade_time = None
        self.cooldown_end_time = None
        self.cooldown_period_minutes = 45  # Increased cooldown after losses
        
        # Market session filters
        self.trading_hours = {
            'start': 2,  # UTC hours (avoid low liquidity)
            'end': 22
        }
        self.min_volatility_threshold = 0.0015  # Minimum volatility required
        self.max_volatility_threshold = 0.05  # Maximum volatility allowed
        
        self.rsi_period = rsi_period
        self.rsi_values = deque(maxlen=rsi_period)
        self.gains = deque(maxlen=rsi_period)
        self.losses = deque(maxlen=rsi_period)
        
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.macd_values = deque(maxlen=macd_slow)
        self.macd_signal_values = deque(maxlen=macd_signal)
        
        self.volume_ma_period = volume_ma_period
        self.volume_history = deque(maxlen=volume_ma_period)
        self.volume_ma = None
        
        # Market regime detection parameters
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.adx_values = deque(maxlen=adx_period)
        self.plus_di_values = deque(maxlen=adx_period)
        self.minus_di_values = deque(maxlen=adx_period)
        self.volatility_period = volatility_period
        self.volatility_values = deque(maxlen=volatility_period)
        self.market_state = "unknown"  # "trending", "ranging", "volatile"
        
        # Price and candle history
        self.price_history = deque(maxlen=max(ema_period, bb_period, macd_slow + macd_signal, adx_period + 1))
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_candle = None
        self.candle_history = deque(maxlen=bb_period)
        
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.position_size = 1.0
        self.trailing_stop_price = None
        self.entry_time = None
        self.trade_duration = 0
        self.partial_exit_executed = False
        self.max_trade_duration_minutes = 60  # Maximum trade duration in minutes
        
        # Signal strength scoring system
        self.signal_strength_threshold = 8  # Increased threshold for stronger signals
        
        # Timeframe settings
        self.timeframe = timeframe
        self.last_update = None
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        logger.info(f"Initialized Enhanced BonkQuant strategy with EMA: {ema_period}, "
                   f"BB: {bb_period}/{bb_std}, ATR: {atr_period}, RSI: {rsi_period}, "
                   f"MACD: {macd_fast}/{macd_slow}/{macd_signal}, Risk: {risk_per_trade*100}%")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000

    def calculate_ema(self, price: float) -> Optional[float]:
        """Calculate Exponential Moving Average (EMA)"""
        if self.ema_value is None and len(self.price_history) >= self.ema_period:
            self.ema_value = sum(self.price_history) / len(self.price_history)
        elif self.ema_value is not None:
            self.ema_value = (price * self.ema_alpha) + (self.ema_value * (1 - self.ema_alpha))
        return self.ema_value
        
    def calculate_ema_from_data(self, data, period):
        if len(data) < period:
            return None
            
        alpha = 2 / (period + 1)
        ema = sum(data[:period]) / period
        
        for i in range(period, len(data)):
            ema = data[i] * alpha + ema * (1 - alpha)
            
        return ema

    def calculate_bollinger_bands(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Calculate Bollinger Bands and bandwidth"""
        if len(self.price_history) < self.bb_period:
            return None, None, None, None
        
        prices = list(self.price_history)[-self.bb_period:]
        sma = sum(prices) / len(prices)
        std = np.std(prices)
        upper_band = sma + (self.bb_std * std)
        lower_band = sma - (self.bb_std * std)
        
        # Calculate bandwidth for squeeze detection
        bandwidth = (upper_band - lower_band) / sma if sma > 0 else 0
        
        return sma, upper_band, lower_band, bandwidth

    def update_atr(self) -> None:
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
        
    def calculate_rsi(self):
        if len(self.gains) < self.rsi_period or len(self.losses) < self.rsi_period:
            return 50
            
        avg_gain = sum(self.gains) / self.rsi_period
        avg_loss = sum(self.losses) / self.rsi_period
        
        if avg_loss == 0:
            return 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        self.rsi_values.append(rsi)
        return rsi
        
    def calculate_macd(self):
        if len(self.price_history) < self.macd_slow + self.macd_signal:
            return None, None, None
            
        # Calculate MACD line
        ema_fast = self.calculate_ema_from_data(list(self.price_history), self.macd_fast)
        ema_slow = self.calculate_ema_from_data(list(self.price_history), self.macd_slow)
        
        if ema_fast is None or ema_slow is None:
            return None, None, None
            
        macd_line = ema_fast - ema_slow
        self.macd_values.append(macd_line)
        
        # Calculate signal line
        if len(self.macd_values) >= self.macd_signal:
            signal_line = self.calculate_ema_from_data(list(self.macd_values), self.macd_signal)
            self.macd_signal_values.append(signal_line)
            histogram = macd_line - signal_line
            return macd_line, signal_line, histogram
            
        return macd_line, None, None
        
    def calculate_volume_ma(self):
        if len(self.volume_history) < self.volume_ma_period:
            return None
            
        return sum(self.volume_history) / len(self.volume_history)

    def calculate_adx(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate Average Directional Index (ADX) to measure trend strength"""
        if len(self.candle_history) < self.adx_period + 1:
            return None, None, None
            
        # Calculate +DI and -DI
        candles = list(self.candle_history)[-self.adx_period-1:]
        plus_dm_list = []
        minus_dm_list = []
        tr_list = []
        
        for i in range(1, len(candles)):
            high_diff = candles[i]['high'] - candles[i-1]['high']
            low_diff = candles[i-1]['low'] - candles[i]['low']
            
            plus_dm = max(high_diff, 0) if high_diff > low_diff else 0
            minus_dm = max(low_diff, 0) if low_diff > high_diff else 0
            
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            
            tr = max(
                candles[i]['high'] - candles[i]['low'],
                abs(candles[i]['high'] - candles[i-1]['close']),
                abs(candles[i]['low'] - candles[i-1]['close'])
            )
            tr_list.append(tr)
        
        # Calculate smoothed values
        tr_sum = sum(tr_list)
        plus_dm_sum = sum(plus_dm_list)
        minus_dm_sum = sum(minus_dm_list)
        
        if tr_sum == 0:
            return None, None, None
            
        plus_di = 100 * plus_dm_sum / tr_sum
        minus_di = 100 * minus_dm_sum / tr_sum
        
        self.plus_di_values.append(plus_di)
        self.minus_di_values.append(minus_di)
        
        # Calculate ADX
        if len(self.plus_di_values) < 2 or len(self.minus_di_values) < 2:
            return plus_di, minus_di, None
            
        dx_values = []
        for i in range(min(len(self.plus_di_values), len(self.minus_di_values))):
            di_diff = abs(self.plus_di_values[i] - self.minus_di_values[i])
            di_sum = self.plus_di_values[i] + self.minus_di_values[i]
            dx = 100 * di_diff / di_sum if di_sum > 0 else 0
            dx_values.append(dx)
        
        adx = sum(dx_values) / len(dx_values)
        self.adx_values.append(adx)
        
        return plus_di, minus_di, adx

    def calculate_volatility(self) -> Optional[float]:
        """Calculate market volatility based on ATR relative to price"""
        if len(self.atr_values) < self.volatility_period or len(self.price_history) < self.volatility_period:
            return None
            
        atr = self.calculate_atr()
        avg_price = sum(list(self.price_history)[-self.volatility_period:]) / self.volatility_period
        
        if avg_price == 0:
            return None
            
        volatility = atr / avg_price * 100  # Volatility as percentage of price
        self.volatility_values.append(volatility)
        
        return volatility

    def determine_market_state(self, adx: Optional[float], volatility: Optional[float]) -> str:
        """Classify market state as trending, ranging, or volatile"""
        if adx is None or volatility is None:
            return "unknown"
            
        avg_volatility = sum(self.volatility_values) / len(self.volatility_values) if self.volatility_values else 0
        
        # More granular market state classification
        if adx > self.adx_threshold:
            if volatility <= avg_volatility * 0.8:
                return "trending_low_vol"  # Strong trend with low volatility
            elif volatility <= avg_volatility * 1.3:
                return "trending_normal_vol"  # Strong trend with normal volatility
            else:
                return "trending_high_vol"  # Strong trend with high volatility
        elif volatility > avg_volatility * 1.5:
            return "volatile"  # High volatility market
        elif volatility < avg_volatility * 0.5:
            return "dead_zone"  # Very low volatility, avoid trading
        else:
            if adx < self.adx_threshold * 0.5:
                return "ranging_stable"  # Stable ranging market
            else:
                return "ranging_unstable"  # Unstable ranging market

    def calculate_signal_strength(self, price: float, trend: str, rsi: float, histogram: Optional[float],
                                volume_confirms: bool, divergence_exists: bool, divergence_type: Optional[str],
                                adx: Optional[float], volatility: Optional[float]) -> int:
        """Calculate signal strength score (0-12) based on multiple factors"""
        score = 0
        
        # Market regime alignment (0-2 points)
        market_state = self.determine_market_state(adx, volatility)
        if market_state.startswith("trending") and adx and adx > self.adx_threshold:
            score += 2
        elif market_state.startswith("ranging") and adx and adx < self.adx_threshold:
            score += 1
        elif market_state == "dead_zone" or market_state == "volatile":
            score -= 1  # Penalty for unfavorable market conditions
        
        # Trend strength and alignment (0-2 points)
        if trend == "bullish" and price > self.ema_value:
            score += 1
            if histogram and histogram > 0 and histogram > self.macd_values[-2] if len(self.macd_values) > 1 else False:
                score += 1  # Increasing momentum
        elif trend == "bearish" and price < self.ema_value:
            score += 1
            if histogram and histogram < 0 and histogram < self.macd_values[-2] if len(self.macd_values) > 1 else False:
                score += 1  # Increasing momentum
        
        # RSI confirmation (0-2 points)
        if trend == "bullish" and rsi < 40:
            score += 2
        elif trend == "bearish" and rsi > 60:
            score += 2
        elif trend == "bullish" and rsi < 50:
            score += 1
        elif trend == "bearish" and rsi > 50:
            score += 1
        
        # Volume confirmation (0-2 points)
        if volume_confirms:
            score += 2
        
        # Divergence bonus (0-2 points)
        if divergence_exists:
            if (trend == "bullish" and divergence_type == "bullish") or \
               (trend == "bearish" and divergence_type == "bearish"):
                score += 2
        
        # Price action pattern recognition (0-2 points)
        if len(self.candle_history) >= 3:
            recent_candles = list(self.candle_history)[-3:]
            
            # Check for bullish patterns
            if trend == "bullish":
                # Check for bullish engulfing or strong bullish candle
                if (recent_candles[-1]['close'] > recent_candles[-1]['open'] and 
                    recent_candles[-1]['close'] > recent_candles[-2]['high'] and
                    recent_candles[-2]['close'] < recent_candles[-2]['open']):
                    score += 2  # Bullish engulfing
                # Check for three white soldiers (3 consecutive bullish candles)
                elif all(c['close'] > c['open'] for c in recent_candles) and \
                     all(recent_candles[i]['close'] > recent_candles[i-1]['close'] for i in range(1, 3)):
                    score += 2  # Three white soldiers
            
            # Check for bearish patterns
            elif trend == "bearish":
                # Check for bearish engulfing or strong bearish candle
                if (recent_candles[-1]['close'] < recent_candles[-1]['open'] and 
                    recent_candles[-1]['close'] < recent_candles[-2]['low'] and
                    recent_candles[-2]['close'] > recent_candles[-2]['open']):
                    score += 2  # Bearish engulfing
                # Check for three black crows (3 consecutive bearish candles)
                elif all(c['close'] < c['open'] for c in recent_candles) and \
                     all(recent_candles[i]['close'] < recent_candles[i-1]['close'] for i in range(1, 3)):
                    score += 2  # Three black crows
        
        # Time of day filter (0-1 points)
        if self.entry_time:
            entry_hour = datetime.fromtimestamp(self.entry_time / 1000).hour
            if self.trading_hours['start'] <= entry_hour <= self.trading_hours['end']:
                score += 1  # Bonus for trading during favorable hours
            else:
                score -= 1  # Penalty for trading during unfavorable hours
        
        # Mean reversion logic for sideways markets (0-1 points)
        if market_state.startswith("ranging"):
            # In ranging markets, buy near support and sell near resistance
            if trend == "bullish" and price <= lower_band * 1.02:
                score += 1
            elif trend == "bearish" and price >= upper_band * 0.98:
                score += 1
        
        return score

    def calculate_position_size(self, account_balance):
        atr = self.calculate_atr()
        if atr == 0:
            return 1.0
        
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss * account_balance:
            logger.info("Daily loss limit reached. No new trades allowed.")
            return 0.0
        
        # Check cooldown period
        # if self.cooldown_end_time and datetime.now() < self.cooldown_end_time:
        #     logger.info("In cooldown period. No new trades allowed.")
        #     return 0.0
        
        # Base risk adjustment based on win/loss streak
        adjusted_risk = self.risk_per_trade
        if self.current_loss_streak > 2:
            adjusted_risk = max(self.risk_per_trade * 0.4, 0.002)  # More aggressive risk reduction
            self.cooldown_end_time = datetime.now() + timedelta(minutes=self.cooldown_period_minutes)
        elif self.current_loss_streak > 1:
            adjusted_risk = max(self.risk_per_trade * 0.6, 0.003)  # Moderate risk reduction
        elif self.win_count > self.loss_count and self.win_count > 3:
            adjusted_risk = min(self.risk_per_trade * 1.1, 0.015)  # More conservative increase
        
        # Market state based adjustments
        volatility = self.calculate_volatility()
        if volatility and len(self.volatility_values) > 0:
            avg_volatility = sum(self.volatility_values) / len(self.volatility_values)
            market_state = self.determine_market_state(self.adx_values[-1] if self.adx_values else None, volatility)
            
            # Adjust risk based on market state
            if market_state == "dead_zone":
                adjusted_risk *= 0.5  # Significantly reduce risk in low volatility
            elif market_state == "volatile":
                adjusted_risk *= 0.6  # Reduce risk in high volatility
            elif market_state == "trending_high_vol":
                adjusted_risk *= 0.8  # Moderate reduction in trending but volatile markets
            elif market_state == "trending_normal_vol":
                adjusted_risk *= 1.0  # Normal risk in ideal conditions
            elif market_state == "ranging_unstable":
                adjusted_risk *= 0.7  # Reduce risk in unstable ranging markets
            
            # Additional volatility-based adjustment
            if volatility > avg_volatility * 1.5:
                adjusted_risk *= 0.8  # Further reduce risk in high volatility
            elif volatility < avg_volatility * 0.5:
                adjusted_risk *= 0.7  # Reduce risk in very low volatility
        
        # Time-based risk adjustment
        if self.entry_time:
            entry_hour = datetime.fromtimestamp(self.entry_time / 1000).hour
            if entry_hour < self.trading_hours['start'] or entry_hour > self.trading_hours['end']:
                adjusted_risk *= 0.6  # Reduce risk during off-hours
        
        # Calculate final position size with adjusted risk
        risk_amount = account_balance * adjusted_risk
        position_size = risk_amount / (atr * self.atr_multiplier_sl)
        
        # Log risk adjustments
        logger.info(f"Position sizing - Base risk: {self.risk_per_trade:.4f}, Adjusted risk: {adjusted_risk:.4f}")
        
        return position_size
        
    def detect_divergence(self, price, rsi):
        """Detect potential RSI divergence"""
        if len(self.price_history) < 10 or len(self.rsi_values) < 10:
            return False, None
            
        # Get recent price and RSI values
        recent_prices = list(self.price_history)[-10:]
        recent_rsi = list(self.rsi_values)[-10:]
        
        # Check for bullish divergence (price making lower lows, RSI making higher lows)
        # Relaxed condition: price near recent lows and RSI showing strength
        if price <= min(recent_prices[:-1]) * 1.02 and rsi >= min(recent_rsi[:-1]):
            return True, "bullish"
            
        # Check for bearish divergence (price making higher highs, RSI making lower highs)
        # Relaxed condition: price near recent highs and RSI showing weakness
        if price >= max(recent_prices[:-1]) * 0.98 and rsi <= max(recent_rsi[:-1]):
            return True, "bearish"
            
        return False, None
        
    def is_volume_confirming(self, trend):
        """Check if volume confirms the trend"""
        if len(self.volume_history) < self.volume_ma_period or self.volume_ma is None:
            return True  # Default to true when not enough data to avoid blocking trades
            
        current_volume = self.volume_history[-1]
        prev_volumes = list(self.volume_history)[-5:]
        
        # Volume should be above average for trend confirmation, with more relaxed requirements
        volume_increasing = current_volume > sum(prev_volumes[:-1]) / len(prev_volumes[:-1])
        return current_volume > self.volume_ma * 0.8 or volume_increasing  # Significantly relaxed volume requirement

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
        # try:
        if candle:
            self.last_candle = self.current_candle.copy() if self.current_candle['open'] is not None else None
            self.current_candle = candle
            self.price_history.append(candle['close'])
            self.volume_history.append(candle['volume'])
            self.candle_history.append(candle)
            self.update_atr()
            
            # Update gains/losses for RSI
            if len(self.price_history) > 1:
                change = candle['close'] - self.price_history[-2]
                self.gains.append(max(change, 0))
                self.losses.append(abs(min(change, 0)))
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

        # Calculate indicators
        ema = self.calculate_ema(price)
        sma, upper_band, lower_band, bandwidth = self.calculate_bollinger_bands()
        atr = self.calculate_atr()
        rsi = self.calculate_rsi()
        macd_line, signal_line, histogram = self.calculate_macd()
        self.volume_ma = self.calculate_volume_ma()
        
        if ema is None or sma is None or atr == 0:
            return None
        
        trend = "bullish" if price > ema else "bearish"
        divergence_exists, divergence_type = self.detect_divergence(price, rsi)
        
        # Update trailing stop if active - more aggressive trailing
        if self.position and self.trailing_stop and self.trailing_stop_price:
            if self.position == "buy" and price > self.trailing_stop_price + (1.2 * atr):
                self.trailing_stop_price = price - (1.2 * atr)
                self.stop_loss = max(self.stop_loss, self.trailing_stop_price)
            elif self.position == "sell" and price < self.trailing_stop_price - (1.2 * atr):
                self.trailing_stop_price = price + (1.2 * atr)
                self.stop_loss = min(self.stop_loss, self.trailing_stop_price)
        
        if self.position is None:
            self.position_size = self.calculate_position_size(account_balance)
            
            # If position size is 0, we're in cooldown or hit daily loss limit
            if self.position_size == 0:
                return None
            
            # Get market regime information
            plus_di, minus_di, adx = self.calculate_adx()
            volatility = self.calculate_volatility()
            market_state = self.determine_market_state(adx, volatility)
            
            # Stricter entry conditions with volume confirmation
            volume_confirms = self.is_volume_confirming(trend)
            bb_squeeze = bandwidth < self.bb_squeeze_threshold if bandwidth is not None else False
            price_action_strength = abs(price - sma) / sma if sma > 0 else 0
            divergence_exists, divergence_type = self.detect_divergence(price, rsi)
            
            # Calculate signal strength score (0-10)
            signal_strength = self.calculate_signal_strength(
                price, trend, rsi, histogram, volume_confirms, 
                divergence_exists, divergence_type, adx, volatility
            )
            
            # Only enter if signal strength meets threshold
            if signal_strength < self.signal_strength_threshold:
                return None
            
            # Enhanced buy condition with market regime filtering
            if (trend == "bullish" and 
                price <= lower_band * 1.03 and  # Tighter entry near band
                rsi < 45 and rsi > 20 and      # More selective RSI range
                volume_confirms):
                
                # Skip trades in unfavorable market regimes
                if market_state == "dead_zone" or market_state == "volatile":
                    logger.info(f"Skipping BUY in unfavorable market regime: {market_state}")
                    return None
                    
                # Apply specific rules based on market regime
                if market_state.startswith("trending"):
                    # In trending markets, ensure price is above EMA for bullish trend
                    if price < self.ema_value * 0.98:
                        logger.info("Skipping BUY: Price below EMA in trending market")
                        return None
                elif market_state.startswith("ranging"):
                    # In ranging markets, ensure we're near support (lower band)
                    if price > lower_band * 1.02:
                        logger.info("Skipping BUY: Not close enough to support in ranging market")
                        return None
                        
                # Check for consecutive candles confirming the trend - require at least 2 out of 3 candles
                if len(self.candle_history) >= 3 and self.last_candle:
                    recent_candles = list(self.candle_history)[-3:]
                    bullish_candles = sum(1 for c in recent_candles if c['close'] > c['open'])
                    if bullish_candles < 2:  # At least 2 out of 3 should be bullish
                        logger.info("Skipping BUY: Insufficient bullish candle confirmation")
                        return None
                
                # Check volatility thresholds
                if volatility:
                    if volatility < self.min_volatility_threshold:
                        logger.info(f"Skipping BUY: Volatility too low ({volatility:.4f})")
                        return None
                    if volatility > self.max_volatility_threshold:
                        logger.info(f"Skipping BUY: Volatility too high ({volatility:.4f})")
                        return None
                
                # Adjust take profit based on market regime and volatility
                tp_multiplier = self.atr_multiplier_tp
                if volatility and len(self.volatility_values) > 0:
                    avg_volatility = sum(self.volatility_values) / len(self.volatility_values)
                    
                    # Higher targets in trending markets with normal volatility
                    if market_state == "trending_normal_vol":
                        tp_multiplier = self.atr_multiplier_tp * 1.2
                    # Even higher targets in trending markets with low volatility
                    elif market_state == "trending_low_vol":
                        tp_multiplier = self.atr_multiplier_tp * 1.4
                    # More conservative targets in ranging markets
                    elif market_state.startswith("ranging"):
                        tp_multiplier = self.atr_multiplier_tp * 0.8
                
                self.position = "buy"
                self.entry_price = price
                self.entry_time = timestamp
                self.stop_loss = price - (self.atr_multiplier_sl * atr)
                self.take_profit = price + (tp_multiplier * atr)
                self.trailing_stop_price = self.stop_loss
                self.partial_exit_executed = False
                
                logger.info(f"BUY signal - Signal strength: {signal_strength}/10, Market: {market_state}. Entry: {price:.8f}, SL: {self.stop_loss:.8f}, TP: {self.take_profit:.8f}")
                return "buy"
                
            # Enhanced sell condition with market regime filtering
            elif (trend == "bearish" and 
                  price >= upper_band * 0.97 and  # Tighter entry near band
                  rsi > 55 and rsi < 80 and      # More selective RSI range
                  volume_confirms):
                  
                # Skip trades in unfavorable market regimes
                if market_state == "dead_zone" or market_state == "volatile":
                    logger.info(f"Skipping SELL in unfavorable market regime: {market_state}")
                    return None
                    
                # Apply specific rules based on market regime
                if market_state.startswith("trending"):
                    # In trending markets, ensure price is below EMA for bearish trend
                    if price > self.ema_value * 1.02:
                        logger.info("Skipping SELL: Price above EMA in trending market")
                        return None
                elif market_state.startswith("ranging"):
                    # In ranging markets, ensure we're near resistance (upper band)
                    if price < upper_band * 0.98:
                        logger.info("Skipping SELL: Not close enough to resistance in ranging market")
                        return None
                        
                # Check for consecutive candles confirming the trend - require at least 2 out of 3 candles
                if len(self.candle_history) >= 3 and self.last_candle:
                    recent_candles = list(self.candle_history)[-3:]
                    bearish_candles = sum(1 for c in recent_candles if c['close'] < c['open'])
                    if bearish_candles < 2:  # At least 2 out of 3 should be bearish
                        logger.info("Skipping SELL: Insufficient bearish candle confirmation")
                        return None
                
                # Check volatility thresholds
                if volatility:
                    if volatility < self.min_volatility_threshold:
                        logger.info(f"Skipping SELL: Volatility too low ({volatility:.4f})")
                        return None
                    if volatility > self.max_volatility_threshold:
                        logger.info(f"Skipping SELL: Volatility too high ({volatility:.4f})")
                        return None
                
                # Adjust take profit based on market regime and volatility
                tp_multiplier = self.atr_multiplier_tp
                if volatility and len(self.volatility_values) > 0:
                    avg_volatility = sum(self.volatility_values) / len(self.volatility_values)
                    
                    # Higher targets in trending markets with normal volatility
                    if market_state == "trending_normal_vol":
                        tp_multiplier = self.atr_multiplier_tp * 1.2
                    # Even higher targets in trending markets with low volatility
                    elif market_state == "trending_low_vol":
                        tp_multiplier = self.atr_multiplier_tp * 1.4
                    # More conservative targets in ranging markets
                    elif market_state.startswith("ranging"):
                        tp_multiplier = self.atr_multiplier_tp * 0.8
                
                self.position = "sell"
                self.entry_price = price
                self.entry_time = timestamp
                self.stop_loss = price + (self.atr_multiplier_sl * atr)
                self.take_profit = price - (tp_multiplier * atr)
                self.trailing_stop_price = self.stop_loss
                self.partial_exit_executed = False
                
                logger.info(f"SELL signal - Signal strength: {signal_strength}/10, Market: {market_state}. Entry: {price:.8f}, SL: {self.stop_loss:.8f}, TP: {self.take_profit:.8f}")
                return "sell"
        else:
            # Update trade duration
            if self.entry_time and timestamp:
                self.trade_duration = (timestamp - self.entry_time) / 1000  # Convert to seconds
            
            # Enhanced time-based exit strategy
            max_duration_ms = self.max_trade_duration_minutes * 60 * 1000
            if self.entry_time and timestamp:
                # Progressive time-based exits
                time_elapsed_pct = (timestamp - self.entry_time) / max_duration_ms
                
                # Exit non-profitable trades after 75% of max duration
                if time_elapsed_pct > 0.75 and (
                    (self.position == "buy" and price < self.entry_price * 1.01) or 
                    (self.position == "sell" and price > self.entry_price * 0.99)):
                    logger.info(f"Time-based exit triggered after {self.trade_duration/60:.1f} minutes - non-profitable trade")
                    self.position = None
                    # Count as a loss but with reduced impact
                    self.current_loss_streak += 1
                    self.loss_count += 1
                    return "stop_loss"
                    
                # Force exit all trades at max duration regardless of profit
                elif timestamp - self.entry_time > max_duration_ms:
                    logger.info(f"Maximum time exit triggered after {self.trade_duration/60:.1f} minutes")
                    self.position = None
                    
                    # Determine if it was a win or loss
                    if (self.position == "buy" and price > self.entry_price) or \
                       (self.position == "sell" and price < self.entry_price):
                        self.current_loss_streak = 0
                        self.win_count += 1
                        return "take_profit"
                    else:
                        self.current_loss_streak += 1
                        self.loss_count += 1
                        return "stop_loss"
            
            # Enhanced partial profit taking with multiple levels
            atr = self.calculate_atr()
            if not self.partial_exit_executed:
                # First partial at 1.5R
                if (self.position == "buy" and price >= self.entry_price + (1.5 * self.atr_multiplier_sl * atr)) or \
                   (self.position == "sell" and price <= self.entry_price - (1.5 * self.atr_multiplier_sl * atr)):
                    # Mark partial exit as executed
                    self.partial_exit_executed = True
                    logger.info(f"Partial profit taking at 1.5R - {price:.8f}")
                    
                    # Move stop loss to breakeven plus small buffer
                    if self.position == "buy":
                        self.stop_loss = max(self.stop_loss, self.entry_price + (0.2 * atr))
                    else:
                        self.stop_loss = min(self.stop_loss, self.entry_price - (0.2 * atr))
                    logger.info(f"Moving stop loss to breakeven+buffer: {self.stop_loss:.8f}")
                    
                    # Adjust take profit to be more aggressive
                    if self.position == "buy":
                        new_tp = price + (1.5 * atr)
                        self.take_profit = min(self.take_profit, new_tp) if self.take_profit else new_tp
                    else:
                        new_tp = price - (1.5 * atr)
                        self.take_profit = max(self.take_profit, new_tp) if self.take_profit else new_tp
                    logger.info(f"Adjusting take profit to: {self.take_profit:.8f}")
            
            # Enhanced trailing stop and dynamic take profit
            if self.trailing_stop and self.partial_exit_executed:
                # More aggressive trailing once in profit
                if self.position == "buy":
                    # Calculate trailing stop distance based on price movement
                    trail_distance = min(1.0 * atr, (price - self.entry_price) * 0.4)  # 40% of current profit
                    new_stop = price - trail_distance
                    if new_stop > self.stop_loss:
                        self.stop_loss = new_stop
                        logger.info(f"Trailing stop updated to: {self.stop_loss:.8f}")
                elif self.position == "sell":
                    trail_distance = min(1.0 * atr, (self.entry_price - price) * 0.4)  # 40% of current profit
                    new_stop = price + trail_distance
                    if new_stop < self.stop_loss:
                        self.stop_loss = new_stop
                        logger.info(f"Trailing stop updated to: {self.stop_loss:.8f}")
            
            # Dynamic take profit adjustment based on market conditions
            if self.dynamic_tp:
                # Adjust take profit based on time in trade and price action
                time_factor = min(1.5, 1.0 + (self.trade_duration / (self.max_trade_duration_minutes * 60) * 0.5))
                
                if self.position == "buy" and price > self.entry_price + (1.2 * atr):
                    # Calculate new take profit with time-based scaling
                    new_tp = price + (time_factor * atr)
                    self.take_profit = max(self.take_profit, new_tp)
                    logger.info(f"Dynamic TP adjusted to: {self.take_profit:.8f} (time factor: {time_factor:.2f})")
                    
                elif self.position == "sell" and price < self.entry_price - (1.2 * atr):
                    new_tp = price - (time_factor * atr)
                    self.take_profit = min(self.take_profit, new_tp)
                    logger.info(f"Dynamic TP adjusted to: {self.take_profit:.8f} (time factor: {time_factor:.2f})")
            
            # Exit conditions
            if self.position == "buy":
                if price <= self.stop_loss:
                    # Calculate PnL for daily tracking
                    pnl_pct = (price / self.entry_price - 1) * 100
                    self.daily_pnl += pnl_pct * self.risk_per_trade  # Approximate impact on account
                    
                    logger.info(f"Stop-loss triggered at {price:.8f} after {self.trade_duration:.1f}s, PnL: {pnl_pct:.2f}%")
                    self.position = None
                    self.current_loss_streak += 1
                    self.loss_count += 1
                    return "stop_loss"
                elif price >= self.take_profit:
                    # Calculate PnL for daily tracking
                    pnl_pct = (price / self.entry_price - 1) * 100
                    self.daily_pnl += pnl_pct * self.risk_per_trade  # Approximate impact on account
                    
                    logger.info(f"Take-profit triggered at {price:.8f} after {self.trade_duration:.1f}s, PnL: {pnl_pct:.2f}%")
                    self.position = None
                    self.current_loss_streak = 0
                    self.win_count += 1
                    return "take_profit"
            elif self.position == "sell":
                if price >= self.stop_loss:
                    # Calculate PnL for daily tracking
                    pnl_pct = (1 - price / self.entry_price) * 100
                    self.daily_pnl += pnl_pct * self.risk_per_trade  # Approximate impact on account
                    
                    logger.info(f"Stop-loss triggered at {price:.8f} after {self.trade_duration:.1f}s, PnL: {pnl_pct:.2f}%")
                    self.position = None
                    self.current_loss_streak += 1
                    self.loss_count += 1
                    return "stop_loss"
                elif price <= self.take_profit:
                    # Calculate PnL for daily tracking
                    pnl_pct = (1 - price / self.entry_price) * 100
                    self.daily_pnl += pnl_pct * self.risk_per_trade  # Approximate impact on account
                    
                    logger.info(f"Take-profit triggered at {price:.8f} after {self.trade_duration:.1f}s, PnL: {pnl_pct:.2f}%")
                    self.position = None
                    self.current_loss_streak = 0
                    self.win_count += 1
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
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_candle = None
        self.volume_history.clear()
        self.gains.clear()
        self.losses.clear()
        self.rsi_values.clear()
        self.macd_values.clear()
        self.macd_signal_values.clear()
        self.candle_history.clear()
        self.trailing_stop_price = None
        self.entry_time = None
        self.trade_duration = 0
        self.partial_exit_executed = False
        
        # Reset market regime detection data
        self.adx_values.clear()
        self.plus_di_values.clear()
        self.minus_di_values.clear()
        self.volatility_values.clear()
        self.market_state = "unknown"
        
        # Keep track of performance metrics
        self.max_loss_streak = max(self.max_loss_streak, self.current_loss_streak)
        self.current_loss_streak = 0
        self.daily_pnl = 0.0  # Reset daily P&L
        self.cooldown_end_time = None
        
        logger.info("BonkQuant strategy reset")