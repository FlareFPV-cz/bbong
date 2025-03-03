import logging
import os
from logging.handlers import RotatingFileHandler

log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'trading_bot.log')

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
console_handler = logging.StreamHandler()

log_format = logging.Formatter(
    '%(asctime)s - %(name)s - [%(levelname)s] - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

# Create root logger
logger = logging.getLogger('trading_bot')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False

# Create child loggers with proper propagation
def create_child_logger(name):
    child_logger = logger.getChild(name)
    child_logger.propagate = False  # Prevent duplicate logs
    child_logger.addHandler(file_handler)
    child_logger.addHandler(console_handler)
    return child_logger

# Create child loggers for different components
market_data_logger = create_child_logger('market_data')
execution_logger = create_child_logger('execution')
risk_logger = create_child_logger('risk')
strategy_logger = create_child_logger('strategy')

# Add rotating file handler for error logs
error_log_file = os.path.join(log_dir, 'error.log')
error_file_handler = RotatingFileHandler(
    error_log_file,
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3
)
error_file_handler.setLevel(logging.ERROR)
error_file_handler.setFormatter(log_format)
logger.addHandler(error_file_handler)

# Add performance logger
performance_logger = create_child_logger('performance')