from enum import Enum
import json
import logging
import traceback


from poly_market_maker.orderbook_manager import OrderBookManager
from poly_market_maker.token import Token, Collateral
from poly_market_maker.constants import MAX_DECIMALS
from poly_market_maker.simulation.shadow_book import ShadowBook # NEW IMPORT

from poly_market_maker.strategies.base_strategy import BaseStrategy
from poly_market_maker.strategies.amm_strategy import AMMStrategy
from poly_market_maker.strategies.bands_strategy import BandsStrategy


class Strategy(Enum):
    AMM = "amm"
    BANDS = "bands"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for strategy in Strategy:
                if value.lower() == strategy.value.lower():
                    return strategy
        return super()._missing_(value)


class StrategyManager:
    def __init__(
        self,
        strategy: str,
        config_path: str,
        shadow_book: ShadowBook, # CHANGED PARAMETER
        order_book_manager: OrderBookManager,
    ) -> BaseStrategy:
        self.logger = logging.getLogger(self.__class__.__name__)

        with open(config_path) as fh:
            config = json.load(fh)

        self.shadow_book = shadow_book # CHANGED ASSIGNMENT
        self.order_book_manager = order_book_manager
        self.bootstrapped = False

        match Strategy(strategy):
            case Strategy.AMM:
                self.strategy = AMMStrategy(config)
            case Strategy.BANDS:
                self.strategy = BandsStrategy(config)
            case _:
                raise Exception("Invalid strategy")

    def synchronize(self, price: float = None):
        try:
            # 1. BOOTSTRAP CHECK (Keep this as is)
            if not self.bootstrapped:
                if not self.shadow_book.last_update_time:
                    self.logger.info("ShadowBook not yet synchronized (no update time). Waiting...")
                    return
                self.bootstrapped = True
                self.logger.info("ShadowBook bootstrapped!")

            # 2. SAFETY CHECK: BUSY WAIT (New!)
            # If the OrderBookManager is busy cancelling, we MUST wait.
            # Otherwise, we will calculate orders based on stale data 
            # or try to spend locked funds.
            if self.order_book_manager.has_pending_cancels:
                self.logger.debug("Pending cancels in progress. Skipping strategy cycle.")
                return

            self.logger.debug("Synchronizing strategy...")

            try:
                orderbook = self.get_order_book()
            except Exception as e:
                self.logger.error(f"{e}")
                return

            self.logger.info("DEBUG: Synchronizing strategy... checking price...")
            token_prices = self.get_token_prices(price=price)
            if token_prices is None:
                self.logger.info("DEBUG: Strategy skipped - No price available.")
                return 

            self.logger.info(f"DEBUG: Price found: {token_prices}. Getting orders...")
            (orders_to_cancel, orders_to_place) = self.strategy.get_orders(
                orderbook, token_prices
            )
            self.logger.info(f"DEBUG: Strategy calculated: Cancel {len(orders_to_cancel)}, Place {len(orders_to_place)}")

            # 3. EXECUTION LOGIC
            # If we have orders to cancel, we ONLY cancel this tick.
            # We do not place orders yet, because the funds are not freed.
            if len(orders_to_cancel) > 0:
                self.logger.info(f"Cancelling {len(orders_to_cancel)} orders.")
                self.cancel_orders(orders_to_cancel)
                # We return here. The next tick will see 'has_pending_cancels=True' 
                # and wait. The tick after that will see the funds freed and place orders.
                return 

            if len(orders_to_place) > 0:
                self.logger.info(f"Placing {len(orders_to_place)} orders.")
                self.place_orders(orders_to_place)

            self.logger.debug("Synchronized strategy!")

        except BaseException as e:
            self.logger.error(f"CRITICAL ERROR in synchronize: {type(e).__name__}: {str(e)}")
            #TODO: do I need to remove the traceback.format_exc()?
            self.logger.error(traceback.format_exc())
            # raise e  <-- Careful: Raising here might crash the whole main loop. 
            # usually you just want to log it and retry next tick.

    def get_order_book(self):
        orderbook = self.order_book_manager.get_order_book()

        if None in orderbook.balances.values():
            self.logger.debug("Balances invalid/non-existent")
            raise Exception("Balances invalid/non-existent")

        if sum(orderbook.balances.values()) == 0:
            self.logger.debug("Wallet has no balances for this market")
            raise Exception("Zero Balances")

        return orderbook

    def get_token_prices(self, price: float = None):
        """
        Determines the current market price safely.
        Priority:
        1. Override 'price' argument (if provided)
        2. ShadowBook 'last_trade_price' (if valid)
        3. ShadowBook 'mid_price' (calculated from best bid/ask)
        """
        price_a = None

        # Priority 1: Argument
        if price is not None:
             price_a = price
        #TODO: last_trade_price is not used anymore?
        elif (price := self.shadow_book.last_trade_price) is not None and False: # check freshness
             price_a = price
        else:
            mid = self.shadow_book.get_mid_price()
            if mid and mid > 0:
                price_a = mid
        
        # Validation
        if price_a is None or price_a <= 0:
            self.logger.warning("Market price missing or zero. Cannot run strategy.")
            return None

        # Rounding
        price_a = round(price_a, MAX_DECIMALS)
        price_b = round(1 - price_a, MAX_DECIMALS)
        
        return {Token.A: price_a, Token.B: price_b}

    def cancel_orders(self, orders_to_cancel):
        if len(orders_to_cancel) > 0:
            self.logger.info(
                f"About to cancel {len(orders_to_cancel)} existing orders!"
            )
            self.order_book_manager.cancel_orders(orders_to_cancel)

    def place_orders(self, orders_to_place):
        if len(orders_to_place) > 0:
            self.logger.info(f"About to place {len(orders_to_place)} new orders!")
            self.order_book_manager.place_orders(orders_to_place)
