import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait

from poly_market_maker.order import Order, Side


class OrderBook:
    """Represents the current snapshot of the order book.

    Attributes:
        -orders: Current list of active orders.
        -balances: Current balances state.
        -orders_being_placed: `True` if at least one order is currently being placed. `False` otherwise.
        -orders_being_cancelled: `True` if at least one orders is currently being cancelled. `False` otherwise.
    """

    def __init__(
        self,
        orders: list[Order],
        balances: dict,
        orders_being_placed: bool,
        orders_being_cancelled: bool,
    ):
        assert isinstance(orders_being_placed, bool)
        assert isinstance(orders_being_cancelled, bool)

        self.orders = orders
        self.balances = balances
        self.orders_being_placed = orders_being_placed
        self.orders_being_cancelled = orders_being_cancelled


class OrderBookManager:
    """Tracks state of the order book without constantly querying it.

    Attributes:
        refresh_frequency: Frequency (in seconds) of how often background order book (and balances)
            refresh takes place.
    """

    def __init__(self, refresh_frequency: int, max_workers: int = 5):
        self.logger = logging.getLogger(self.__class__.__name__)

        assert isinstance(refresh_frequency, int)
        assert isinstance(max_workers, int)

        self.refresh_frequency = refresh_frequency
        self.get_orders_function = None
        self.get_balances_function = None
        self.place_order_function = None
        self.cancel_order_function = None
        self.cancel_all_orders_function = None
        self.on_update_function = None

        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._state = None
        self._refresh_count = 0
        self._currently_placing_orders = 0
        self._orders_placed = list()
        self._order_ids_cancelling = set()
        self._order_ids_cancelled = set()

    def get_orders_with(self, get_orders_function: Callable[[], list[Order]]):
        """
        Configures the function used to fetch active keeper orders.
        """
        assert callable(get_orders_function)

        self.get_orders_function = get_orders_function

    def get_balances_with(self, get_balances_function: Callable):
        """
        Configures the (optional) function used to fetch current keeper balances.
        Args:
            get_balances_function: The function which will be periodically called by the order book manager
                in order to get current keeper balances. This is optional, is not configured balances
                will not be fetched.
        """
        assert callable(get_balances_function)

        self.get_balances_function = get_balances_function

    def place_orders_with(self, place_order_function: Callable):
        """
        Configures the function used to place orders.
        Args:
            place_order_function: The function which will be called in order to place new orders.
        """
        assert callable(place_order_function)

        self.place_order_function = place_order_function

    def cancel_orders_with(self, cancel_order_function: Callable):
        """
        Configures the function used to cancel orders.
        Args:
            cancel_order_function: The function which will be called in order to cancel orders.
        """
        assert callable(cancel_order_function)

        self.cancel_order_function = cancel_order_function

    def cancel_all_orders_with(self, cancel_all_orders_function: Callable):
        """
        Configures the function used to cancel all keeper orders.
        Args:
            cancel_all_orders_function: The function which will be called in order to cancel orders.
        """
        assert callable(cancel_all_orders_function)

        self.cancel_all_orders_function = cancel_all_orders_function

    # Add this inside OrderBookManager class
    @property
    def has_pending_cancels(self) -> bool:
        """Returns True if there are orders currently being cancelled."""
        with self._lock:
            return len(self._order_ids_cancelling) > 0

    def on_update(self, on_update_function: Callable):
        assert callable(on_update_function)

        self.on_update_function = on_update_function

    def start(self):
        """Start the background refresh of active keeper orders."""
        threading.Thread(target=self._thread_refresh_order_book, daemon=True).start()

    def get_order_book(self) -> OrderBook:
        """
        Returns the current snapshot of the active keeper orders and balances.
        """
        while self._state is None:
            self.logger.info("Waiting for the order book to become available...")
            time.sleep(0.5)

        with self._lock:
            self.logger.debug("Getting the order book...")
            if self._state.get("orders") is not None:
                self.logger.debug(
                    f"Orders retrieved last time: {[order.id for order in self._state["orders"]]}"
                )
            self.logger.debug(
                f"Orders placed since then: {[order.id for order in self._orders_placed]}"
            )
            self.logger.debug(
                f"Orders cancelled since then: {[order_id for order_id in self._order_ids_cancelled]}"
            )
            self.logger.debug(
                f"Orders being cancelled: {[order_id for order_id in self._order_ids_cancelling]}"
            )
            self.logger.debug(
                f"Orders being placed: {self._currently_placing_orders} order(s)"
            )

            orders = []

            # Add orders which have been placed if they exist
            if self._state.get("orders") is not None:
                orders = list(self._state["orders"])
                for order in self._orders_placed:
                    if order.id not in list(map(lambda order: order.id, orders)):
                        orders.append(order)

                # Remove orders being cancelled and already cancelled.
                orders = list(
                    filter(
                        lambda order: order.id not in self._order_ids_cancelling
                        and order.id not in self._order_ids_cancelled,
                        orders,
                    )
                )

                self.logger.debug(
                    f"Open keeper orders: {[order.id for order in orders]}"
                )

        return OrderBook(
            orders=orders,
            balances=self._state["balances"],
            orders_being_placed=self._currently_placing_orders > 0,
            orders_being_cancelled=len(self._order_ids_cancelling) > 0,
        )

    def place_order(self, place_order_function: Callable[[Order], Order], order: Order):
        """Places new order. Order placement will happen in a background thread.

        Args:
            place_order_function: Function used to place the order.
        """
        assert callable(place_order_function)

        with self._lock:
            self._currently_placing_orders += 1

        self._report_order_book_updated()

        result = self._executor.submit(
            self._thread_place_order(place_order_function, order)
        )
        wait([result])

    def place_orders(self, orders: list[Order]):
        """Places new orders asynchronously.
        
        Args:
            orders: List of new orders to place.
        """
        assert isinstance(orders, list)
        assert callable(self.place_order_function)

        # 1. Increment counter safely
        with self._lock:
            self._currently_placing_orders += len(orders)

        self._report_order_book_updated()

        for order in orders:
            # 2. FIXED SYNTAX: Pass the function and args separately
            # Do NOT use parenthesis () after _thread_place_order
            future = self._executor.submit(
                self._thread_place_order,   # Function reference
                self.place_order_function,  # Arg 1
                order                       # Arg 2
            )
            
            # 3. Add Callback: This runs automatically when the thread finishes
            # It replaces 'wait(results)' so we don't block the main loop
            future.add_done_callback(self._on_order_complete)

    def _on_order_complete(self, future):
        """
        Callback handler. Runs in a background thread when an order finishes.
        """
        try:
            # Check if the thread raised an exception (e.g. API Error)
            future.result() 
        except Exception as e:
            self.logger.error(f"Order placement failed in background: {e}", exc_info=True)
        finally:
            # 4. Cleanup: Always decrement the counter, success or fail
            with self._lock:
                self._currently_placing_orders = max(0, self._currently_placing_orders - 1)

    def cancel_orders(self, orders: list[Order]):
        """
        Cancels existing orders asynchronously.
        
        Args:
            orders: List of orders to cancel.
        """
        self.logger.info("Cancelling orders...")
        assert isinstance(orders, list)
        assert callable(self.cancel_order_function)

        # 1. Mark orders as 'cancelling' so we don't try to double-cancel
        with self._lock:
            for order in orders:
                self._order_ids_cancelling.add(order.id)

        self._report_order_book_updated()

        for order in orders:
            # 2. FIXED SYNTAX: Pass function and args separately
            future = self._executor.submit(
                self._thread_cancel_order,    # Function reference
                self.cancel_order_function,   # Arg 1
                order                         # Arg 2
            )
            
            # 3. Add Callback with Closure
            # We must pass the specific order.id to the callback so we know which one to clean up.
            # "oid=order.id" captures the current ID safely.
            future.add_done_callback(lambda f, oid=order.id: self._on_cancel_complete(f, oid))

    def _on_cancel_complete(self, future, order_id):
        """
        Callback handler. Runs when a cancel thread finishes.
        """
        try:
            # Check for exceptions (e.g., Network Error during cancel)
            future.result()
        except Exception as e:
            self.logger.error(f"Order cancellation failed for {order_id}: {e}", exc_info=True)
        finally:
            # 4. Cleanup: CRITICAL
            # We MUST remove the ID from the set, otherwise the bot thinks
            # it is still cancelling this order forever.
            with self._lock:
                self._order_ids_cancelling.discard(order_id)

    def cancel_all_orders(self):
        """
        Cancels all existing orders asynchronously.
        """
        # 1. Get current orders
        orders = self.get_order_book().orders
        if len(orders) == 0:
            self.logger.info("No open orders on order book.")
            return

        self.logger.info(f"Cancelling {len(orders)} open orders...")

        # 2. Mark all as cancelling immediately so we don't try to touch them
        with self._lock:
            for order in orders:
                self._order_ids_cancelling.add(order.id)

        # 3. FIXED SYNTAX: Submit to background thread properly
        future = self._executor.submit(
            self._thread_cancel_all_orders,   # Function reference
            self.cancel_all_orders_function,  # Arg 1
            orders                            # Arg 2
        )

        # 4. Add Callback for cleanup
        # We pass the list of orders to the callback so we can clear their IDs 
        # from the 'cancelling' set once the job is done.
        future.add_done_callback(lambda f, ords=orders: self._on_cancel_all_complete(f, ords))

    def _on_cancel_all_complete(self, future, orders):
        """
        Callback handler. Runs when the 'cancel all' thread finishes.
        """
        try:
            future.result() # Check for exceptions
            self.logger.info("Cancel All signal sent successfully.")
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}", exc_info=True)
        finally:
            # 5. Cleanup: Remove the IDs from the tracking set
            with self._lock:
                for order in orders:
                    self._order_ids_cancelling.discard(order.id)

    def wait_for_order_cancellation(self):
        """Wait until no background order cancellation takes place."""
        while len(self._order_ids_cancelling) > 0:
            time.sleep(0.1)

    def wait_for_order_book_refresh(self):
        """Wait until at least one background order book refresh happens since now."""
        with self._lock:
            old_counter = self._refresh_count

        while True:
            with self._lock:
                new_counter = self._refresh_count

            if new_counter > old_counter:
                break

            time.sleep(0.1)

    def wait_for_stable_order_book(self):
        """Wait until no background order placement nor cancellation takes place."""
        while True:
            order_book = self.get_order_book()
            if (
                not order_book.orders_being_cancelled
                and not order_book.orders_being_placed
            ):
                break
            time.sleep(0.1)

    def _report_order_book_updated(self):
        if self.on_update_function is not None:
            self.on_update_function()

    def _run_get_orders(self):
        try:
            orders = self.get_orders_function()
            return orders
        except Exception as e:
            self.logger.error(f"Exception fetching orderbook! Error: {e}")
            return None

    def _run_get_balances(self):
        try:
            balances = (
                self.get_balances_function()
                if self.get_balances_function is not None
                else None
            )
            self.logger.debug(f"Balances: {balances}")
            return balances
        except Exception as e:
            self.logger.error(f"Exception fetching onchain balances! Error: {e}")
            return None

    def _thread_refresh_order_book(self):
        while True:
            try:
                with self._lock:
                    orders_already_cancelled_before = set(self._order_ids_cancelled)
                    orders_already_placed_before = set(self._orders_placed)

                # get orders
                orders = self._run_get_orders()

                # get balances
                balances = self._run_get_balances()

                with self._lock:
                    self._order_ids_cancelled = (
                        self._order_ids_cancelled - orders_already_cancelled_before
                    )
                    for order in orders_already_placed_before:
                        self._orders_placed.remove(order)

                    if self._state is None:
                        self.logger.info("Order book became available")

                    # Issue: RPC endpoints are sometimes unreliable and fetching the onchain balances for the keeper sometimes
                    # fails. This kills the whole refresh orderbook process which is clearly undesirable.
                    # Fix should be to ensure the process doesn't fail if any specific internal function fails
                    if self._state is None:
                        self._state = {}

                    if orders is not None:
                        # If either the orderbook or balance check fails, the state stays as it was before the refresh
                        self._state["orders"] = orders
                    if balances is not None:
                        self._state["balances"] = balances
                    # self._state = {"orders": orders, "balances": balances}
                    self._refresh_count += 1

                self._report_order_book_updated()
                
                if orders is None:
                    self.logger.error("Failed to fetch order book: orders is None")
                    return # Skip this refresh cycle
                else:
                    # Dynamically access shadow_book from the app instance via the bound method
                    shadow_book = None
                    try:
                        # self.get_orders_function is bound to app.get_orders
                        # self.get_orders_function.__self__ is the app instance
                        if hasattr(self.get_orders_function.__self__, 'shadow_book'):
                            shadow_book = self.get_orders_function.__self__.shadow_book
                    except AttributeError:
                        self.logger.debug("Could not access shadow_book from get_orders_function.__self__")
    
                    self.logger.debug(
                        f"Fetched the order book"
                        f" (orders: {[order.id for order in orders]}, "
                        f" buys: {len([order for order in orders if order.side == Side.BUY])}, "
                        f" sells: {len([order for order in orders if order.side == Side.SELL])})"
                    )
            except ValueError as e:
                self.logger.error(f"Failed to fetch the order book or balances ({e})!")

            time.sleep(self.refresh_frequency)

    def _thread_place_order(
        self, place_order_function: Callable[[Order], Order], order: Order
    ):
        assert callable(place_order_function)

        def func():
            try:
                new_order = place_order_function(order)

                if new_order is not None:
                    with self._lock:
                        self._orders_placed.append(new_order)
            except BaseException as exception:
                self.logger.exception(exception)
            finally:
                with self._lock:
                    self._currently_placing_orders -= 1
                self._report_order_book_updated()

        return func

    def _thread_cancel_order(
        self, cancel_order_function: Callable[[Order], None], order: Order
    ):
        assert callable(cancel_order_function)

        def func():
            order_id = order.id
            try:
                if cancel_order_function(order):
                    with self._lock:
                        self._order_ids_cancelled.add(order_id)
                        self._order_ids_cancelling.remove(order_id)
            except BaseException as e:
                self.logger.exception(f"Failed to cancel {order_id}")
                self.logger.exception(f"Exception: {e}")
            finally:
                with self._lock:
                    try:
                        self._order_ids_cancelling.remove(order_id)
                    except KeyError:
                        pass
                self._report_order_book_updated()

        return func

    def _thread_cancel_all_orders(
        self, 
        cancel_all_orders_function: Callable[[list[Order]], bool],
        orders: list[Order],
    ):
        assert callable(cancel_all_orders_function)

        def func():
            order_ids = [order.id for order in orders]
            try:
                if cancel_all_orders_function(orders):
                    with self._lock:
                        for order_id in order_ids:
                            self._order_ids_cancelled.add(order_id)
                            self._order_ids_cancelling.remove(order_id)
            except BaseException:
                self.logger.exception("Failed to cancel all")
            finally:
                with self._lock:
                    for order_id in order_ids:
                        try:
                            self._order_ids_cancelling.remove(order_id)
                        except KeyError:
                            pass
                self._report_order_book_updated()

        return func
