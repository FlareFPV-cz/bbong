import asyncio
import os
import sys
import json
from datetime import datetime, timedelta
from dateutil import parser  # Add this import
from utils.logger import logger
from utils.config import Config
from strategy.strategy_factory import StrategyFactory
from backtesting.historical_data import HistoricalData

async def backtest_strategy(strategy_name, symbol='BTCUSDT', timeframe='1h', days=3, candle_limit=1000, mode='big'):
    if mode == 'big':
        days = 365
        candle_limit = 525600
    else: 
        days = 100
        candle_limit = 144000
        
    logger.info(f"Backtesting {strategy_name} strategy on {symbol} {timeframe} for {days} days (max {candle_limit} candles) - Mode: {mode}")
    
    strategy = StrategyFactory.create_strategy(strategy_name, timeframe=timeframe)
    if not strategy:
        logger.error(f"Strategy {strategy_name} not found")
        return None
    
    trades = []
    initial_balance = 1000 
    equity_curve = [{'timestamp': datetime.now().isoformat(), 'equity': initial_balance}]
    current_position = None
    highest_balance = initial_balance
    lowest_balance = initial_balance
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    try:
        logger.info(f"Fetching historical data from {start_date} to {end_date}")
        
        historical_data = HistoricalData(symbol, interval=timeframe, start_date=start_date, end_date=end_date, limit=candle_limit)
        historical_data.set_limit(candle_limit)
        
        count = 0
        async for kline in historical_data.simulate_streaming():
            try:
                count += 1
                
                if count <= 5:
                    logger.info(f"Processing candle {count}: {kline}")
                
                for key in ['open', 'high', 'low', 'close', 'volume']:
                    if key in kline:
                        kline[key] = float(kline[key])
                
                if isinstance(kline['timestamp'], str):
                    if 'T' in kline['timestamp'] and '.' not in kline['timestamp']:
                        kline['timestamp'] = f"{kline['timestamp']}.000000"
                
                signal = strategy.update(kline['close'], candle=kline)
                
                if signal:
                    logger.info(f"Signal generated: {signal} at price {kline['close']}")
                
                if (signal == 'BUY' or signal == 'buy') and current_position is None:
                    current_position = {
                        'entry_price': float(kline['close']),
                        'entry_time': kline['timestamp'],
                        'size': 1.0 
                    }
                    logger.info(f"BUY signal at {kline['timestamp']} - Price: {kline['close']}")
                    
                elif ((signal == 'SELL' or signal == 'sell' or 
                      signal == 'stop_loss' or signal == 'take_profit') and 
                      current_position is not None):
                    exit_price = float(kline['close'])
                    entry_price = float(current_position['entry_price'])
                    profit_pct = (exit_price - entry_price) / entry_price * 100
                    
                    trade = {
                        'entry_time': current_position['entry_time'],
                        'entry_price': entry_price,
                        'exit_time': kline['timestamp'],
                        'exit_price': exit_price,
                        'profit_pct': profit_pct,
                        'exit_reason': signal  
                    }
                    trades.append(trade)
                    last_equity = equity_curve[-1]['equity']
                    new_equity = last_equity * (1 + profit_pct / 100)
                    
                    highest_balance = max(highest_balance, new_equity)
                    lowest_balance = min(lowest_balance, new_equity)
                    
                    timestamp_str = ""
                    if hasattr(kline['timestamp'], 'strftime'):
                        timestamp_str = kline['timestamp'].strftime("%Y-%m-%dT%H:%M:%S")
                    elif isinstance(kline['timestamp'], str):
                        try:
                            dt = parser.parse(kline['timestamp'])
                            timestamp_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
                        except:
                            timestamp_str = kline['timestamp']
                    else:
                        try:
                            dt = datetime.fromtimestamp(float(kline['timestamp']))
                            timestamp_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
                        except:
                            timestamp_str = str(kline['timestamp'])
                    
                    equity_curve.append({
                        'timestamp': timestamp_str,
                        'equity': new_equity
                    })
                    
                    logger.info(f"{signal.upper()} signal at {kline['timestamp']} - Price: {exit_price}, Profit: {profit_pct:.2f}%")
                    current_position = None
            except Exception as inner_e:
                logger.warning(f"Error processing candle: {str(inner_e)}, skipping to next candle")
        
        if not trades:
            logger.warning(f"No trades executed for {strategy_name}")
            return {
                'strategy': strategy_name,
                'symbol': symbol,
                'timeframe': timeframe,
                'candles_processed': count,
                'trades': 0,
                'total_return': 0,
                'win_rate': 0,
                'initial_balance': initial_balance,
                'final_balance': initial_balance,
                'highest_balance': highest_balance,
                'lowest_balance': lowest_balance,
                'equity_curve': equity_curve
            }
        
        winning_trades = [t for t in trades if t['profit_pct'] > 0]
        final_balance = equity_curve[-1]['equity']
        total_return = (final_balance / initial_balance - 1) * 100
        win_rate = len(winning_trades) / len(trades) * 100
        
        results = {
            'strategy': strategy_name,
            'symbol': symbol,
            'timeframe': timeframe,
            'candles_processed': count,
            'trades': len(trades),
            'total_return': total_return,
            'win_rate': win_rate,
            'initial_balance': initial_balance,
            'final_balance': final_balance,
            'highest_balance': highest_balance,
            'lowest_balance': lowest_balance,
            'equity_curve': equity_curve
        }
        
        logger.info(f"Backtest completed for {strategy_name}: {len(trades)} trades, {total_return:.2f}% return, {win_rate:.2f}% win rate")
        logger.info(f"Balance: Initial ${initial_balance:.2f}, Final ${final_balance:.2f}, Highest ${highest_balance:.2f}, Lowest ${lowest_balance:.2f}")
        return results
        
    except Exception as e:
        logger.error(f"Error in backtest_strategy: {str(e)}")
        return {
            'strategy': strategy_name,
            'symbol': symbol,
            'timeframe': timeframe,
            'candles_processed': 0,
            'trades': 0,
            'total_return': 0,
            'win_rate': 0,
            'initial_balance': initial_balance,
            'final_balance': initial_balance,
            'highest_balance': initial_balance,
            'lowest_balance': initial_balance,
            'equity_curve': [{'timestamp': datetime.now().isoformat(), 'equity': initial_balance}]
        }
        
async def run_all_backtests(mode='big'):
    strategies = ['bonk_quant']
    symbols = ['BONKUSDT', 'ETHUSDT', 'BTCUSDT', 'SOLUSDT']
    timeframes = ['1m']
    
    results = []
    
    results_dir = os.path.join(os.path.dirname(__file__), 'backtest_results')
    os.makedirs(results_dir, exist_ok=True)
    
    for strategy in strategies:
        for symbol in symbols:
            for timeframe in timeframes:
                try:
                    logger.info(f"Starting backtest for {strategy} on {symbol} {timeframe} - Mode: {mode}")
                    result = await backtest_strategy(
                        strategy, 
                        symbol=symbol,
                        timeframe=timeframe,
                        mode=mode  # Pass the mode parameter
                    )
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error backtesting {strategy} on {symbol} {timeframe}: {str(e)}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_suffix = f"_{mode}" if mode != 'big' else ""
    
    json_file = os.path.join(results_dir, f"json/backtest_results{mode_suffix}_{timestamp}.json")
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    report_file = os.path.join(results_dir, f"md/backtest_report{mode_suffix}_{timestamp}.md")
    generate_markdown_report(results, report_file, mode)
    
    return report_file

def generate_markdown_report(results, report_file, mode='big'):
    markdown = f"""# Backtest Results - {mode.upper()} Mode
Generated on: {datetime.now().isoformat()}

## Summary

"""
    sorted_results = sorted(results, key=lambda x: float(x.get('total_return', 0)), reverse=True)
    
    for result in sorted_results:
        # Calculate additional statistics
        trades = result.get('trades', 0)
        win_rate = result.get('win_rate', 0)
        total_return = result.get('total_return', 0)
        initial_balance = result.get('initial_balance', 1000)
        final_balance = result.get('final_balance', 1000)
        highest_balance = result.get('highest_balance', 1000)
        lowest_balance = result.get('lowest_balance', 1000)
        candles_processed = result.get('candles_processed', 0)
        
        # Calculate drawdown percentage
        max_drawdown_pct = ((highest_balance - lowest_balance) / highest_balance * 100) if highest_balance > 0 else 0
        
        # Calculate profit factor if possible
        equity_curve = result.get('equity_curve', [])
        if len(equity_curve) > 1:
            daily_returns = []
            for i in range(1, len(equity_curve)):
                prev_equity = equity_curve[i-1].get('equity', 0)
                curr_equity = equity_curve[i].get('equity', 0)
                if prev_equity > 0:
                    daily_return = (curr_equity - prev_equity) / prev_equity * 100
                    daily_returns.append(daily_return)
            
            # Calculate volatility (standard deviation of returns)
            if daily_returns:
                import numpy as np
                volatility = np.std(daily_returns) if len(daily_returns) > 1 else 0
                sharpe_ratio = (np.mean(daily_returns) / volatility) if volatility > 0 else 0
            else:
                volatility = 0
                sharpe_ratio = 0
        else:
            volatility = 0
            sharpe_ratio = 0
        
        markdown += f"""### {result.get('strategy', 'Unknown')} - {result.get('symbol', 'Unknown')} {result.get('timeframe', 'Unknown')}

        #### Performance Metrics
        - **Trades**: {trades}
        - **Win Rate**: {win_rate:.2f}%
        - **Total Return**: {total_return:.2f}%
        - **Max Drawdown**: {max_drawdown_pct:.2f}%
        - **Volatility**: {volatility:.2f}%
        - **Sharpe Ratio**: {sharpe_ratio:.2f}
        
        #### Account Statistics
        - **Initial Balance**: ${initial_balance:.2f}
        - **Final Balance**: ${final_balance:.2f}
        - **Highest Balance**: ${highest_balance:.2f}
        - **Lowest Balance**: ${lowest_balance:.2f}
        
        #### Backtest Information
        - **Candles Processed**: {candles_processed}
        - **Mode**: {mode.upper()}
        - **Timeframe**: {result.get('timeframe', 'Unknown')}
        - **Symbol**: {result.get('symbol', 'Unknown')}
        
        """
        
        with open(report_file, 'w') as f:
            f.write(markdown)

if __name__ == "__main__":
    mode = 'big' 
    
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'small':
        mode = 'small'
        
    report_file = asyncio.run(run_all_backtests(mode))
    print(f"\nBacktest completed in {mode.upper()} mode! Results saved to: {report_file}")