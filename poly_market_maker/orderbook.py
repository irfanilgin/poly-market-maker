import threading
import logging
import time
from collections.abc import Callable
from poly_market_maker.order import Order
from concurrent.futures import ThreadPoolExecutor

from poly_market_maker.order import Order, Side



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


class OrderBookManager:
    """
    Manages the lifecycle of User Orders (Placing, Cancelling, Syncing).
    Fully Asynchronous.
    """

    def __init__(self, refresh_frequency: int = 10, max_workers: int = 5):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.refresh_frequency = refresh_frequency
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        
        # The Data Container
        self.order_book = OrderBook(orders=[], balances={})

        # State Tracking
        self._currently_placing_orders = 0
        self._order_ids_cancelling = set()
        
        # API Functions (injected)
        self.get_orders_function = None
        self.get_balances_function = None
        self.place_order_function = None
        self.cancel_order_function = None
        self.cancel_all_orders_function = None
        self.on_update_function = None

    # --- Configuration Methods ---
    def get_orders_with(self, func): self.get_orders_function = func
    def get_balances_with(self, func): self.get_balances_function = func
    def place_orders_with(self, func): self.place_order_function = func
    def cancel_orders_with(self, func): self.cancel_order_function = func
    def cancel_all_orders_with(self, func): self.cancel_all_orders_function = func
    def on_update(self, func): self.on_update_function = func

    # --- State Properties ---
    @property
    def has_pending_cancels(self) -> bool:
        with self._lock:
            return len(self._order_ids_cancelling) > 0

    def get_order_book(self) -> OrderBook:
        """Returns the live order book object."""
        # Update status flags before returning
        with self._lock:
            self.order_book.set_placing_status(self._currently_placing_orders > 0)
            self.order_book.set_cancelling_status(len(self._order_ids_cancelling) > 0)
        return self.order_book

    def start(self):
        """Starts the background sync loop."""
        threading.Thread(target=self._sync_loop, daemon=True).start()

    # --- Asynchronous Actions ---

    def place_orders(self, orders: list[Order]):
        """Places new orders asynchronously."""
        if not orders: return

        with self._lock:
            self._currently_placing_orders += len(orders)
        
        self._notify_update()

        for order in orders:
            future = self._executor.submit(
                self._thread_place_order, # The function to run
                self.place_order_function, # Arg 1
                order                      # Arg 2
            )
            future.add_done_callback(self._on_place_complete)

    def cancel_orders(self, orders: list[Order]):
        """Cancels orders asynchronously."""
        if not orders: return

        self.logger.info(f"Cancelling {len(orders)} orders...")
        
        with self._lock:
            for order in orders:
                self._order_ids_cancelling.add(order.id)
        
        self._notify_update()

        for order in orders:
            future = self._executor.submit(
                self._thread_cancel_order,
                self.cancel_order_function,
                order
            )
            # Use lambda to pass the order ID to the callback
            future.add_done_callback(lambda f, oid=order.id: self._on_cancel_complete(f, oid))

    def cancel_all_orders(self):
        """Cancels ALL orders."""
        orders = self.order_book.orders # Get safe copy
        if not orders:
            self.logger.info("No open orders to cancel.")
            return

        self.logger.info(f"Cancelling all {len(orders)} orders...")

        with self._lock:
            for order in orders:
                self._order_ids_cancelling.add(order.id)

        future = self._executor.submit(
            self._thread_cancel_all,
            self.cancel_all_orders_function,
            orders
        )
        future.add_done_callback(lambda f, ords=orders: self._on_cancel_all_complete(f, ords))

    # --- Background Threads (Worker Logic) ---
    # These methods run INSIDE the ThreadPool. 
    # They MUST NOT return functions; they must DO the work.

    def _thread_place_order(self, place_func, order):
        """Executes the API call to place an order."""
        try:
            # 1. Call API
            placed_order = place_func(order)
            
            # 2. Optimistic Update: Add to local book immediately
            if placed_order:
                self.order_book.add_order(placed_order)
                return placed_order
            else:
                raise Exception("API returned None for placed order")
        except Exception as e:
            self.logger.error(f"Failed to place order {order}: {e}")
            raise e

    def _thread_cancel_order(self, cancel_func, order):
        """Executes the API call to cancel an order."""
        try:
            # 1. Call API
            success = cancel_func(order)
            
            # 2. Optimistic Update: Remove from local book immediately
            if success:
                self.order_book.remove_order(order.id)
            else:
                self.logger.warning(f"API failed to cancel order {order.id}")
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order.id}: {e}")
            raise e

    def _thread_cancel_all(self, cancel_all_func, orders):
        """Executes the API call to cancel all orders."""
        try:
            cancel_all_func(orders)
            # Optimistic Update
            for order in orders:
                self.order_book.remove_order(order.id)
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            raise e

    # --- Callbacks (Cleanup) ---

    def _on_place_complete(self, future):
        try:
            future.result() # Raise exception if thread failed
        except Exception:
            pass # Already logged in thread
        finally:
            with self._lock:
                self._currently_placing_orders = max(0, self._currently_placing_orders - 1)

    def _on_cancel_complete(self, future, order_id):
        try:
            future.result()
        except Exception:
            pass
        finally:
            with self._lock:
                self._order_ids_cancelling.discard(order_id)

    def _on_cancel_all_complete(self, future, orders):
        try:
            future.result()
            self.logger.info("All orders cancelled successfully.")
        except Exception:
            pass
        finally:
            with self._lock:
                for order in orders:
                    self._order_ids_cancelling.discard(order.id)

    # --- Periodic Sync Loop (Anti-Entropy) ---
    
    def _sync_loop(self):
        """
        Background loop that fetches the 'True' state.
        Hardened against RPC failures.
        """
        self.logger.info("OrderBook Sync Loop started.")
        while True:
            current_orders = None
            current_balances = None

            # 1. Fetch Orders (Critical)
            try:
                if self.get_orders_function:
                    current_orders = self.get_orders_function()
            except Exception as e:
                self.logger.error(f"Failed to fetch orders from API: {e}")
                # If we can't get orders, we usually can't proceed with a sync
                current_orders = None

            # 2. Fetch Balances (Non-Critical / Flaky RPC)
            try:
                if self.get_balances_function:
                    current_balances = self.get_balances_function()
            except Exception as e:
                self.logger.warning(f"RPC Balance fetch failed (using stale balances): {e}")
                # We do NOT stop. We just use None, so the OrderBook keeps the old balances.
                current_balances = None

            # 3. Update the Book (Thread-Safe)
            try:
                # Only update if we successfully got orders
                if current_orders is not None:
                    # Filter out orders we are currently cancelling
                    with self._lock:
                        clean_orders = [
                            o for o in current_orders 
                            if o.id not in self._order_ids_cancelling
                        ]
                    
                    # Update orders. Only update balances if we actually got fresh ones.
                    # If current_balances is None, the OrderBook keeps its existing balances.
                    self.order_book.update(
                        clean_orders, 
                        current_balances if current_balances is not None else {}
                    )
                    
                    self._notify_update()
                    self.logger.debug(f"Synced OrderBook: {len(clean_orders)} orders.")
            except Exception as e:
                 self.logger.error(f"Error updating local OrderBook: {e}")

            time.sleep(self.refresh_frequency)

    def _notify_update(self):
        if self.on_update_function:
            try:
                self.on_update_function()
            except Exception:
                pass