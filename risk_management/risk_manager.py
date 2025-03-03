from utils.logger import risk_logger as logger
from datetime import datetime, timedelta
from collections import deque

class RiskManager:
    def __init__(self, config):
        self.config = config
        self.max_daily_loss = config.get("risk_management", "max_daily_loss") or 0.05
        self.max_open_trades = config.get("risk_management", "max_open_trades") or 3
        self.trailing_stop_loss = config.get("risk_management", "trailing_stop_loss") or 0.02
        
        self.initial_balance = config.get("trading", "initial_balance")
        self.daily_low = self.initial_balance
        self.open_trades = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.trade_history = deque(maxlen=100)
        
        # Add tracking for consecutive losses
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
        logger.info(f"Risk Manager initialized with max daily loss: {self.max_daily_loss*100}%, "
                   f"max open trades: {self.max_open_trades}")
                   
    def can_open_trade(self, current_balance):
        """Check if a new trade can be opened based on risk parameters"""
        # Check if we've hit max open trades
        if self.open_trades >= self.max_open_trades:
            logger.warning(f"Maximum open trades ({self.max_open_trades}) reached, cannot open new position")
            return False
            
        # Check if we need to reset daily metrics
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self.daily_low = current_balance
            logger.info("Daily risk metrics reset")
            
        # Check if we've hit max daily loss
        daily_loss_pct = (self.daily_low - self.initial_balance) / self.initial_balance
        if daily_loss_pct <= -self.max_daily_loss:
            logger.warning(f"Maximum daily loss ({self.max_daily_loss*100}%) reached, cannot open new position")
            return False
            
        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(f"Maximum consecutive losses ({self.max_consecutive_losses}) reached, cannot open new position")
            return False
            
        return True
        
    def update_metrics(self, current_balance):
        """Update risk metrics with current balance"""
        if current_balance < self.daily_low:
            self.daily_low = current_balance
            
    def trade_opened(self):
        """Record that a trade was opened"""
        self.open_trades += 1
        self.trade_history.append({
            'timestamp': datetime.now(),
            'action': 'open',
            'open_trades': self.open_trades
        })
        logger.info(f"Trade opened, current open trades: {self.open_trades}")
        
    def trade_closed(self, profit_loss):
        """Record that a trade was closed"""
        self.open_trades = max(0, self.open_trades - 1)
        
        # Update consecutive losses tracking
        if profit_loss < 0:
            self.consecutive_losses += 1
            logger.warning(f"Trade closed with loss. Consecutive losses: {self.consecutive_losses}")
        else:
            self.consecutive_losses = 0
            
        self.trade_history.append({
            'timestamp': datetime.now(),
            'action': 'close',
            'open_trades': self.open_trades,
            'profit_loss': profit_loss
        })
        logger.info(f"Trade closed with P/L: {profit_loss}, current open trades: {self.open_trades}")
        
    def get_risk_metrics(self):
        """Return current risk metrics for dashboard display"""
        return {
            'max_daily_loss': self.max_daily_loss,
            'max_open_trades': self.max_open_trades,
            'current_open_trades': self.open_trades,
            'daily_low': self.daily_low,
            'consecutive_losses': self.consecutive_losses,
            'max_consecutive_losses': self.max_consecutive_losses
        }