import asyncio
from utils.logger import logger

class BacktestEngine:
    def __init__(self, strategy, initial_balance=1000):
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = None
        self.trades = []
        self.equity_curve = []

    async def run(self, historical_data):
        logger.info(f"Starting backtest with initial balance: ${self.initial_balance}")
        
        for timestamp, row in historical_data.iterrows():
            # Convert timestamp to milliseconds for strategy
            timestamp_ms = int(timestamp.timestamp() * 1000)
            
            signal = self.strategy.update(
                price=float(row['close']),
                timestamp=timestamp_ms
            )
            
            if signal == "buy" and not self.position:
                quantity = (self.balance * 0.01) / float(row['close'])
                cost = quantity * float(row['close'])
                self.balance -= cost
                self.position = {'price': float(row['close']), 'quantity': quantity}
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'buy',
                    'price': float(row['close']),
                    'quantity': quantity,
                    'balance': self.balance
                })
                
            elif signal == "sell" and self.position:
                revenue = self.position['quantity'] * float(row['close'])
                self.balance += revenue
                profit = revenue - (self.position['quantity'] * self.position['price'])
                self.trades.append({
                    'timestamp': timestamp,
                    'type': 'sell',
                    'price': float(row['close']),
                    'quantity': self.position['quantity'],
                    'balance': self.balance,
                    'profit': profit
                })
                self.position = None
                
            self.equity_curve.append({
                'timestamp': timestamp,
                'equity': self.calculate_total_equity(float(row['close']))
            })
            
        return self.generate_report()
    
    def calculate_total_equity(self, current_price):
        equity = self.balance
        if self.position:
            equity += self.position['quantity'] * current_price
        return equity
    
    def generate_report(self):
        total_trades = len([t for t in self.trades if t['type'] == 'sell'])
        profitable_trades = len([t for t in self.trades if t['type'] == 'sell' and t['profit'] > 0])
        total_profit = sum([t['profit'] for t in self.trades if t['type'] == 'sell'])
        
        return {
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'win_rate': profitable_trades / total_trades if total_trades > 0 else 0,
            'total_profit': total_profit,
            'final_balance': self.balance,
            'return_pct': ((self.balance - self.initial_balance) / self.initial_balance) * 100
        }