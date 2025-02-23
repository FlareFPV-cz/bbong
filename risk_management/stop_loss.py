from utils.logger import risk_logger as logger

class TrailingStopLoss:
    def __init__(self, initial_price, trailing_percent=0.02):
        self.trailing_percent = trailing_percent
        self.highest_price = initial_price
        self.stop_loss_price = initial_price * (1 - trailing_percent)
        logger.info(f"Initialized trailing stop-loss at {self.stop_loss_price} ({trailing_percent*100}% below {initial_price})")

    def update(self, current_price):
        if current_price > self.highest_price:
            old_stop_loss = self.stop_loss_price
            self.highest_price = current_price
            self.stop_loss_price = self.highest_price * (1 - self.trailing_percent)
            logger.debug(f"Updated stop-loss from {old_stop_loss} to {self.stop_loss_price} (new high: {self.highest_price})")

        if current_price <= self.stop_loss_price:
            logger.warning(f"Stop-loss triggered at {current_price} (stop-loss price: {self.stop_loss_price})")
            return True
        return False