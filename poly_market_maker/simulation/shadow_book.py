import logging
import uuid
from collections import defaultdict

from poly_market_maker.order import Order, Side
from poly_market_maker.market import Token
from poly_market_maker.token import Collateral


class ShadowBook:
    """
    The core engine for simulating an in-memory order book and tracking virtual inventory.
    """

    def __init__(self, token_id: int, initial_collateral_balance: float = 1000.0):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.token_id = token_id
        self._market_state = {"best_bid": 0.0, "best_ask": float("inf")}
        self._orders: dict[str, Order] = {}
        self._balances = defaultdict(float)
        self._balances[Collateral] = initial_collateral_balance
        self._balances[Token.A] = 0.0
        self._balances[Token.B] = 0.0

    def update_market_data(self, best_bid: float, best_ask: float):
        """Updates the live market best bid and ask."""
        self.logger.debug(f"Updating market data: Bid={best_bid}, Ask={best_ask}")
        self._market_state["best_bid"] = best_bid
        self._market_state["best_ask"] = best_ask
        self.check_fills() # Check for fills immediately after market data update

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
        """Returns the current virtual balances."""
        return dict(self._balances)

    def check_fills(self):
        """
        Simulates order fills based on strict crossing logic and updates virtual inventory.
        Assumes we are last in the queue, so fills only occur when the price moves THROUGH our level.
        """
        filled_order_ids = []
        for order_id, order in self._orders.items():
            market_bid = self._market_state["best_bid"]
            market_ask = self._market_state["best_ask"]

            filled = False
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
                
                # Update virtual balances based on fill
                if order.side == Side.BUY:
                    # Decrement collateral, increment token A/B
                    self._balances[Collateral] -= order.size * order.price # Assuming collateral is used for buys
                    self._balances[order.token] += order.size
                elif order.side == Side.SELL:
                    # Increment collateral, decrement token A/B
                    self._balances[Collateral] += order.size * order.price # Assuming collateral received for sells
                    self._balances[order.token] -= order.size
                
                self.logger.info(f"New Virtual Inventory: {self.get_balances()}")
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            self._orders.pop(order_id)
