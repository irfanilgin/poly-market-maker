import threading

from poly_market_maker.order import Order


class OrderBook:
    """
    Thread-safe container for the user's active orders and balances.
    Acts as the 'Source of Truth' for the Strategy.
    """

    def __init__(self, orders: list[Order] = None, balances: dict = None):
        self._lock = threading.RLock()
        
        # Store as dict for O(1) access: {order_id: Order}
        self._orders: dict[str, Order] = {o.id: o for o in orders} if orders else {}
        self._balances = balances if balances else {}
        
        # Status flags
        self.orders_being_placed = False
        self.orders_being_cancelled = False

    @property
    def orders(self) -> list[Order]:
        """Returns a safe copy of the order list."""
        with self._lock:
            return list(self._orders.values())

    @property
    def balances(self) -> dict:
        """Returns a safe copy of balances."""
        with self._lock:
            return self._balances.copy()

    def update(self, orders: list[Order], balances: dict):
        """Replaces the entire state (used by the periodic sync)."""
        with self._lock:
            self._orders = {o.id: o for o in orders}
            if balances:
                self._balances = balances

    def add_order(self, order: Order):
        """Optimistic update: Add a single order."""
        with self._lock:
            self._orders[order.id] = order

    def remove_order(self, order_id: str):
        """Optimistic update: Remove a single order."""
        with self._lock:
            self._orders.pop(order_id, None)

    def set_placing_status(self, is_placing: bool):
        with self._lock:
            self.orders_being_placed = is_placing

    def set_cancelling_status(self, is_cancelling: bool):
        with self._lock:
            self.orders_being_cancelled = is_cancelling
