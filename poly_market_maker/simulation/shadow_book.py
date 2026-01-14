import logging
import uuid
from collections import defaultdict
import random
import time
from poly_market_maker.order import Order, Side
from poly_market_maker.market import Token
from poly_market_maker.token import Collateral


class ShadowBook:
    """
    The core engine for simulating an in-memory order book and tracking virtual inventory.
    """

    def __init__(self, token_id: int):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.token_id = token_id
        self.bids = {} # { 0.20: 7588.26, ... }
        self.asks = {} # { 0.22: 3856.79, ... }
        self._orders: dict[str, Order] = {}
        self.last_update_time = None
        self.last_trade_price = None
        self._best_bid_cache = None
        self._best_ask_cache = None

    def apply_snapshot(self, snapshot_data):
        self._best_bid_cache = None
        self._best_ask_cache = None
        self.bids = {
            float(x['price']): s
            for x in snapshot_data.get('bids', [])
            if (s := float(x['size'])) > 0
        }

        self.asks = {
            float(x['price']): s
            for x in snapshot_data.get('asks', [])
            if (s := float(x['size'])) > 0
        }
        self.last_update_time = time.time()

    def apply_delta(self, delta_item: dict) -> bool:
        """
        Updates a single price level and maintains smart caches.
        Returns True if the book is healthy, False if a desync is detected.
        """
        try:
            side = delta_item.get('side')
            price = float(delta_item.get('price'))
            size = float(delta_item.get('size'))

            # 1. Update the Local Book & Manage Cache
            if side == 'buy':
                if size == 0:
                    self.bids.pop(price, None)
                    # Cache Invalidation: Only if we removed the top bid
                    if self._best_bid_cache == price:
                        self._best_bid_cache = None
                else:
                    self.bids[price] = size
                    # Cache Update: Only if new price is BETTER (Higher) than current
                    if self._best_bid_cache is not None and price > self._best_bid_cache:
                        self._best_bid_cache = price
            else:
                # Sell Side
                if size == 0:
                    self.asks.pop(price, None)
                    # Cache Invalidation: Only if we removed the top ask
                    if self._best_ask_cache == price:
                        self._best_ask_cache = None
                else:
                    self.asks[price] = size
                    # Cache Update: Only if new price is BETTER (Lower) than current
                    if self._best_ask_cache is not None and price < self._best_ask_cache:
                        self._best_ask_cache = price

            # 2. Sanity Check (Optimized: Random Sampling)
            if random.random() < 0.01: 
                server_best = float(delta_item.get('best_bid' if side == 'buy' else 'best_ask', 0))
                
                if server_best > 0:
                    # NOW we pay the cost of finding the max/min using our optimized getters
                    my_best = self.get_best_bid() if side == 'buy' else self.get_best_ask()
                    
                    if my_best is None or abs(my_best - server_best) > 0.001:
                        # Log warning if needed
                        return False # Desync detected 

            self.last_update_time = time.time()
            return True

        except Exception as e:
            # It's good practice to catch parsing errors to avoid crashing the thread
            print(f"Error applying delta: {e}")
            return False

    def get_best_bid(self):
        """
        Returns best bid with O(1) access 90% of the time.
        """
        # Return cached value if it exists
        if self._best_bid_cache is not None:
            return self._best_bid_cache

        # Fallback: Calculate, Cache, and Return
        if not self.bids:
            return None
        self._best_bid_cache = max(self.bids.keys())
        return self._best_bid_cache
    
    def get_best_ask(self):
        """
        Returns best ask with O(1) access.
        """
        if self._best_ask_cache is not None:
            return self._best_ask_cache

        if not self.asks:
            return None
            
        self._best_ask_cache = min(self.asks.keys())
        return self._best_ask_cache

    def get_mid_price(self):
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        # SAFETY CHECK: If one side is missing, the market is broken.
        if best_bid is None or best_ask is None:
            return None  # Signal to Strategy: "DO NOT TRADE"
            
        return (best_bid + best_ask) / 2

    def add_virtual_order(self, order: Order) -> str:
        """Adds a virtual order to the in-memory book and returns a simulated order_id."""
        order_id = str(uuid.uuid4())
        order.id = order_id
        self._orders[order_id] = order
        self.logger.info(f"Added virtual order: {order}")
        return order_id

    def cancel_virtual_order(self, order_id: str) -> bool:
        """Removes a virtual order from the in-memory book."""
        if order_id in self._orders:
            order = self._orders.pop(order_id)
            self.logger.info(f"Cancelled virtual order: {order_id}")
            return True
        self.logger.warning(f"Attempted to cancel non-existent order: {order_id}")
        return False

    def get_open_orders(self) -> list[Order]:
        """Returns a list of all active virtual orders."""
        return list(self._orders.values())

    def get_balances(self) -> dict:
        """
        Returns the current virtual balances.
        """
        # TODO: Implement actual balance tracking in ShadowBook for simulation
        # For now, returning a dummy value as per MockExchange's current implementation
        return {Collateral: 10000.0, Token.A: 0.0, Token.B: 0.0} # Return a dict with balances

    def check_fills(self):
        """
        Simulates order fills based on strict crossing logic and updates virtual inventory.
        Assumes we are last in the queue, so fills only occur when the price moves THROUGH our level.
        """
        filled_order_ids = []
        # TODO: optimize bid ask request save it to a cache
        for order_id, order in self._orders.items():
            market_bid = self.get_best_bid()
            market_ask = self.get_best_ask()

            filled = False
            # Only fill if both sides of the market exist
            if market_bid is not None and market_ask is not None:
                if order.side == Side.BUY:
                    # Buy order at P fills if market_ask drops BELOW P
                    if market_ask < order.price:
                        filled = True
                elif order.side == Side.SELL:
                    # Sell order at P fills if market_bid rises ABOVE P
                    if market_bid > order.price:
                        filled = True
            
            if filled:
                self.logger.info(f"Virtual Fill: Order {order_id} ({order.side.value} {order.size} @ {order.price}) FILLED!")
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            self._orders.pop(order_id)

    
    @property
    def last_trade_price(self) -> float | None:
        return self._last_trade_price

    @last_trade_price.setter
    def last_trade_price(self, value: float | None):
        self._last_trade_price = self._parse_safe_float(value)

    @classmethod
    def _parse_safe_float(cls, value) -> float | None:
            """Helper to convert API strings to float, handling '' and None."""
            # 1. Handle explicit None
            if value is None:
                return None
            
            # 2. Handle empty strings (e.g. from API: "last_trade_price": "")
            if isinstance(value, str) and value.strip() == "":
                return None
                
            # 3. Try conversion
            try:
                return float(value)
            except ValueError:
                return None