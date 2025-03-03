# BBONG - lets waste some money trading bot
## Trading Strategies

### Moving Average Crossover

This strategy uses the classic moving average crossover technique with enhanced risk management. It works by:

- Tracking two moving averages: a short-term (8 periods) and a long-term (21 periods)
- Identifying trend direction and strength using a 50-period trend window
- Entering BUY positions when the short MA crosses above the long MA in an uptrend
- Entering SELL positions when the short MA crosses below the long MA in a downtrend
- Using RSI (Relative Strength Index) as a filter to avoid overbought/oversold conditions
- Setting stop-loss at 2x ATR (Average True Range) and take-profit at 4x ATR
- Adjusting position size based on account balance and market volatility

### Momentum Surge

A more aggressive strategy designed to capture short-term momentum moves. It operates by:

- Using very short moving averages (2 and 5 periods) to quickly identify momentum shifts
- Measuring trend strength over a 10-period window
- Entering positions when short-term momentum aligns with the trend direction
- Using a moderate RSI filter (45-55) to confirm momentum
- Setting tighter stop-loss (1x ATR) and take-profit (1.5x ATR) levels
- Taking more frequent trades with higher risk per trade (3%)

### Bonk Roulette

A high-risk, high-reward strategy that incorporates randomness to mimic the unpredictable nature of meme coins. It:

- Uses Bollinger Bands to identify extreme price movements
- Enters contrarian positions when price reaches band extremes (upper/lower)
- Confirms entries with RSI indicators (overbought/oversold)
- Randomly selects risk levels (5%, 10%, or 15%) for each trade
- Sets fixed percentage-based stop-loss (5%) and variable take-profit targets
- Only trades when market volatility exceeds a minimum threshold

### Bonk Quant

A more sophisticated quantitative approach combining trend-following with mean reversion. It:

- Uses a 200-period EMA (Exponential Moving Average) to determine the long-term trend
- Applies Bollinger Bands to identify overbought/oversold conditions
- Enters BUY positions when price touches the lower band during bullish trends
- Enters SELL positions when price touches the upper band during bearish trends
- Calculates position size based on ATR volatility (higher volatility = smaller position)
- Sets stop-loss at 1.5x ATR and take-profit at 3x ATR
- Maintains a 1:2 risk-reward ratio to ensure profitable trades outweigh losses

