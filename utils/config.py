import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    def __init__(self, config_file=None):
        self.config_file = config_file or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'config.json'
        )
        self.config = self._load_config()
        
    def _load_config(self):
        """Load configuration from file or create default"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading config file: {str(e)}")
                return self._create_default_config()
        else:
            return self._create_default_config()
            
    def _create_default_config(self):
        """Create and save default configuration"""
        default_config = {
            "trading": {
                "symbol": "bonkusdt",
                "risk_percent": 0.01,
                "initial_balance": 1000,
                "simulate": True
            },
            "strategy": {
                "name": "momentum_surge",
                "params": {
                    "short_window": 2,
                    "long_window": 10,
                    "trend_window": 15,
                    "min_trend_strength": 0.005,
                    "rsi_period": 10,
                    "timeframe": "1m",
                    "atr_period": 10,
                    "risk_per_trade": 0.03
                }
            },
            "risk_management": {
                "trailing_stop_loss": 0.02
            },
            "api": {
                "binance_api_key": os.getenv("BINANCE_API_KEY", ""),
                "binance_api_secret": os.getenv("BINANCE_API_SECRET", "")
            }
        }
        
        # Save default config
        try:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving default config: {str(e)}")
            
        return default_config
        
    def get(self, section, key=None):
        """Get configuration value"""
        if section not in self.config:
            return None
            
        if key is None:
            return self.config[section]
            
        return self.config[section].get(key)
        
    def update(self, section, key, value):
        """Update configuration value"""
        if section not in self.config:
            self.config[section] = {}
            
        self.config[section][key] = value
        
        # Save updated config
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving updated config: {str(e)}")