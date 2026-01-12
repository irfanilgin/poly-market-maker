import time
from poly_market_maker.order import Order, Side
from poly_market_maker.metrics import (order_fill_latency, fill_counter, placed_orders_counter)

class MetricsTracker:
    """
    Centralized utility for recording business logic metrics.
    Uses @classmethod to be safe for inheritance/mocking.
    """

    @classmethod
    def record_fill(cls, order: Order, fill_time: float = None):
        """
        Records metrics when an order is filled.
        """
        if fill_time is None:
            fill_time = time.time()

        # 1. Calculate and Record Latency
        # Ensure the order has 'created_at'. If not, we can't measure latency.
        if hasattr(order, 'created_at') and order.created_at is not None:
            latency = fill_time - order.created_at
            
            # Sanity check: Latency cannot be negative
            if latency > 0:
                order_fill_latency.labels(
                    side=order.side.name, 
                    token=order.token.name
                ).observe(latency)

        # 2. Increment Fill Counter
        fill_counter.labels(
            side=order.side.name, 
            token=order.token.name
        ).inc()

    @classmethod
    def record_placement(cls, order: Order):
        """
        Optional: Record when an order is successfully placed on the book.
        """
        # Increment the placement counter
        placed_orders_counter.labels(
            side=order.side.name, 
            token=order.token.name
        ).inc()