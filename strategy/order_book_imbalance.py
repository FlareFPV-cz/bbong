from collections import deque
from utils.logger import strategy_logger as logger
import numpy as np
import time

class OrderBookImbalance:
    def __init__(self, rsi_period=4, macd_fast=12, macd_slow=26, macd_signal=9, 
        delta_window=20, imbalance_threshold=0.005, timeframe='1m',  # Reduced threshold for more signals
        risk_per_trade=0.02, slippage_tolerance=0.001):
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.delta_window = delta_window
        self.imbalance_threshold = imbalance_threshold
        self.timeframe = timeframe
        self.risk_per_trade = risk_per_trade
        self.slippage_tolerance = slippage_tolerance
        
        # Initialize data structures
        self.price_history = deque(maxlen=max(self.macd_slow, 50))
        self.volume_history = deque(maxlen=self.delta_window)
        self.buy_volume_history = deque(maxlen=self.delta_window)
        self.sell_volume_history = deque(maxlen=self.delta_window)
        self.rsi_values = deque(maxlen=self.rsi_period)
        self.gains = deque(maxlen=self.rsi_period)
        self.losses = deque(maxlen=self.rsi_period)
        self.macd_histogram = deque(maxlen=5)
        
        # Order book tracking
        self.market_depth = {}
        self.last_depth_update = 0
        self.depth_changes = deque(maxlen=10)
        
        # Trading state
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.execution_time = None
        self.win_count = 0
        self.loss_count = 0
        
        # Candle data
        self.current_candle = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.last_update = None
        self.timeframe_ms = self._get_timeframe_ms(timeframe)
        
        logger.info(f"Initialized OrderBookImbalance strategy with RSI period: {rsi_period}, "
                   f"imbalance threshold: {imbalance_threshold*100}%")

    def _get_timeframe_ms(self, timeframe):
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        return 60 * 1000

    def update(self, price, timestamp=None, candle=None, order_book=None):
        start_time = time.time()
        
        # Process candle data
        if candle:
            self.current_candle = candle
            self.price_history.append(candle['close'])
            self.volume_history.append(candle['volume'])
            
            # Estimate buy/sell volume based on price action
            if candle['close'] > candle['open']:
                buy_volume = candle['volume'] * 0.7
                sell_volume = candle['volume'] * 0.3
            else:
                buy_volume = candle['volume'] * 0.3
                sell_volume = candle['volume'] * 0.7
                
            self.buy_volume_history.append(buy_volume)
            self.sell_volume_history.append(sell_volume)
            
        else:
            if self.current_candle['open'] is None:
                self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
                self.last_update = timestamp
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price
        
        # Process order book data if available
        if order_book:
            self.update_market_depth(order_book)
        
        # Check for sufficient data
        if len(self.price_history) < 2:
            return None
            
        # Calculate indicators
        rsi = self.calculate_rsi(price)
        macd, signal, histogram = self.calculate_macd()
        cumulative_delta = self.calculate_cumulative_delta()
        
        # Store MACD histogram for crossover detection
        if histogram is not None:
            self.macd_histogram.append(histogram)
        
        # Check for emergency exit based on MACD histogram crossover
        if self.position and len(self.macd_histogram) >= 2:
            if self.position == "buy" and self.macd_histogram[-1] < 0 and self.macd_histogram[-2] > 0:
                logger.info(f"Emergency exit: MACD histogram crossed below zero in long position")
                self.position = None
                return "sell"
            elif self.position == "sell" and self.macd_histogram[-1] > 0 and self.macd_histogram[-2] < 0:
                logger.info(f"Emergency exit: MACD histogram crossed above zero in short position")
                self.position = None
                return "buy"
        
        # Check for order book imbalance
        imbalance_detected, imbalance_direction = self.detect_order_book_imbalance()
        
        if not self.position:
            # Buy signal: RSI oversold + positive delta divergence + buy imbalance
            if (rsi < 40 and cumulative_delta > 0 and imbalance_detected and 
                imbalance_direction == "buy"):  # Less restrictive RSI condition
                self.entry_price = price
                self.position = "buy"
                self.stop_loss = price * (1 - self.slippage_tolerance * 2.5)  # Wider stop loss
                self.take_profit = self.calculate_take_profit(price, "buy")
                self.execution_time = time.time() - start_time
                logger.info(f"BUY signal - RSI: {rsi:.2f}, Delta: {cumulative_delta:.2f}, "
                           f"Execution time: {self.execution_time*1000:.2f}ms")
                return "buy"
                
            # Sell signal: RSI overbought + negative delta divergence + sell imbalance
            elif (rsi > 60 and cumulative_delta < 0 and imbalance_detected and 
                  imbalance_direction == "sell"):  # Less restrictive RSI condition
                self.entry_price = price
                self.position = "sell"
                self.stop_loss = price * (1 + self.slippage_tolerance * 2.5)  # Wider stop loss
                self.take_profit = self.calculate_take_profit(price, "sell")
                self.execution_time = time.time() - start_time
                logger.info(f"SELL signal - RSI: {rsi:.2f}, Delta: {cumulative_delta:.2f}, "
                           f"Execution time: {self.execution_time*1000:.2f}ms")
                return "sell"
                
        # Exit logic for stop loss
        if self.position == "buy" and price <= self.stop_loss:
            logger.info(f"Stop-loss triggered at {price:.8f}")
            self.position = None
            self.loss_count += 1
            return "stop_loss"
        elif self.position == "sell" and price >= self.stop_loss:
            logger.info(f"Stop-loss triggered at {price:.8f}")
            self.position = None
            self.loss_count += 1
            return "stop_loss"
        
        # Exit logic for take profit
        if self.position == "buy" and price >= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            self.win_count += 1
            return "take_profit"
        elif self.position == "sell" and price <= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            self.win_count += 1
            return "take_profit"
        
        return None

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
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
                
                self.rsi_values.append(rsi)
                return rsi
        return 50

    def calculate_macd(self):
        if len(self.price_history) >= self.macd_slow:
            # Calculate EMA values
            ema_fast = self.calculate_ema(self.price_history, self.macd_fast)
            ema_slow = self.calculate_ema(self.price_history, self.macd_slow)
            
            if ema_fast is not None and ema_slow is not None:
                macd_line = ema_fast - ema_slow
                
                # Calculate signal line (EMA of MACD)
                macd_history = []
                for i in range(self.macd_slow-1, len(self.price_history)):
                    price_subset = list(self.price_history)[:i+1]
                    fast_ema = self.calculate_ema(price_subset, self.macd_fast)
                    slow_ema = self.calculate_ema(price_subset, self.macd_slow)
                    if fast_ema is not None and slow_ema is not None:
                        macd_history.append(fast_ema - slow_ema)
                
                if len(macd_history) >= self.macd_signal:
                    signal_line = self.calculate_ema(macd_history, self.macd_signal)
                    histogram = macd_line - signal_line
                    return macd_line, signal_line, histogram
        
        return None, None, None

    def calculate_ema(self, data, period):
        if len(data) < period:
            return None
            
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        
        for i in range(period, len(data)):
            ema = data[i] * k + ema * (1 - k)
            
        return ema

    def calculate_cumulative_delta(self):
        if len(self.buy_volume_history) == self.delta_window and len(self.sell_volume_history) == self.delta_window:
            total_buy_volume = sum(self.buy_volume_history)
            total_sell_volume = sum(self.sell_volume_history)
            
            if total_sell_volume > 0:
                return (total_buy_volume - total_sell_volume) / total_sell_volume
            else:
                return 1.0  # Avoid division by zero
        return 0

    def update_market_depth(self, order_book):
        try:
            current_time = time.time()
            
            # Calculate total market depth
            total_bids = sum(float(bid[1]) for bid in order_book.get('bids', []))
            total_asks = sum(float(ask[1]) for ask in order_book.get('asks', []))
            
            new_depth = {
                'bids': total_bids,
                'asks': total_asks,
                'timestamp': current_time
            }
            
            # Calculate change in market depth
            if self.market_depth:
                bid_change = (new_depth['bids'] - self.market_depth['bids']) / self.market_depth['bids'] if self.market_depth['bids'] > 0 else 0
                ask_change = (new_depth['asks'] - self.market_depth['asks']) / self.market_depth['asks'] if self.market_depth['asks'] > 0 else 0
                
                self.depth_changes.append({
                    'bid_change': bid_change,
                    'ask_change': ask_change,
                    'timestamp': current_time
                })
            
            self.market_depth = new_depth
            self.last_depth_update = current_time
        except Exception as e:
            logger.warning(f"Error updating market depth: {str(e)}")
            self.last_depth_update = current_time
            return None
            self.position = None
            return "stop_loss"
        
        # Exit logic for take profit
        if self.position == "buy" and price >= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            return "take_profit"
        elif self.position == "sell" and price <= self.take_profit:
            logger.info(f"Take-profit triggered at {price:.8f}")
            self.position = None
            return "take_profit"
        
        return None

    def detect_order_book_imbalance(self):
        # Check if we have recent order book data - extended time window
        if not self.market_depth or time.time() - self.last_depth_update > 10:  # Extended from 5 to 10 seconds
            return False, None
            
        # Check for significant imbalance
        if self.market_depth['bids'] > 0 and self.market_depth['asks'] > 0:
            bid_ask_ratio = self.market_depth['bids'] / self.market_depth['asks']
            
            if bid_ask_ratio > (1 + self.imbalance_threshold):
                return True, "buy"
            elif bid_ask_ratio < (1 - self.imbalance_threshold):
                return True, "sell"
                
        # Check for sudden disappearance of liquidity
        if len(self.depth_changes) > 1:
            last_change = self.depth_changes[-1]
            
            if abs(last_change['bid_change']) > self.imbalance_threshold:
                return True, "sell" if last_change['bid_change'] < 0 else "buy"
                
            if abs(last_change['ask_change']) > self.imbalance_threshold:
                return True, "buy" if last_change['ask_change'] < 0 else "sell"
                
        return False, None

    def calculate_take_profit(self, price, position):
        # Find liquidity clusters in the order book
        if not self.market_depth:
            # Default take profit if no order book data
            return price * 1.02 if position == "buy" else price * 0.98
            
        # For a more sophisticated approach, we would analyze the order book
        # to find liquidity clusters, but for now we'll use a simple approach
        if position == "buy":
            return price * (1 + self.slippage_tolerance * 5)
        else:
            return price * (1 - self.slippage_tolerance * 5)

    def reset(self):
        self.price_history.clear()
        self.volume_history.clear()
        self.buy_volume_history.clear()
        self.sell_volume_history.clear()
        self.rsi_values.clear()
        self.gains.clear()
        self.losses.clear()
        self.macd_histogram.clear()
        self.depth_changes.clear()
        self.market_depth = {}
        self.position = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.win_count = 0
        self.loss_count = 0
        logger.info("OrderBookImbalance strategy reset")