from strategy.momentum_surge import MomentumSurge
from strategy.moving_average import MovingAverageCrossover
from strategy.bonk_roulette import BonkRoulette
from strategy.bonk_quant import BonkQuant
from strategy.order_book_imbalance import OrderBookImbalance
from utils.logger import strategy_logger as logger

class StrategyFactory:
    @staticmethod
    def create_strategy(strategy_name, **params):
        logger.info(f"Creating strategy: {strategy_name} with parameters: {params}")
        if strategy_name.lower() == "bonk_quant":
            strategy = BonkQuant(**params)
            logger.info("BonkQuant strategy created successfully")
            return strategy
        # elif strategy_name.lower() == "moving_average":
        #     logger.info(f"Creating MovingAverageCrossover strategy with params: {params}")
        #     return MovingAverageCrossover(**params)
        # elif strategy_name.lower() == "bonk_roulette":
        #     logger.info(f"Creating BonkRoulette strategy with params: {params}")
        #     return BonkRoulette(**params)
        elif strategy_name.lower() == "bonk_quant":
            logger.info(f"Creating BonkQuant strategy with params: {params}")
            return BonkQuant(**params)
        # elif strategy_name.lower() == "order_book_imbalance":
        #     logger.info(f"Creating OrderBookImbalance strategy with params: {params}")
        #     return OrderBookImbalance(**params)
        # else:
        #     logger.warning(f"Unknown strategy: {strategy_name}, defaulting to MomentumSurge")
        #     return MomentumSurge(**params)