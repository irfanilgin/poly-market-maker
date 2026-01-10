# Understanding `--refresh-frequency` and `--websocket-debounce-ms`

This document explains the usage and flow of the `--refresh-frequency` and `--websocket-debounce-ms` arguments within the Poly Market Maker codebase, particularly their roles in order execution, data pipelines, and potential interactions.

## `--refresh-frequency`

**Definition:**

The `--refresh-frequency` argument (default: 5 seconds) controls the frequency (in seconds) at which the background order book and balances refresh takes place.

**Usage and Flow:**

1.  **Argument Parsing:** Defined in `poly_market_maker/args.py` and parsed at application startup.
2.  **`OrderBookManager` Initialization:** The `poly_market_maker/app.py` passes the `refresh_frequency` value to the `OrderBookManager` during its initialization:
    ```python
    self.order_book_manager = OrderBookManager(
        args.refresh_frequency, max_workers=1
    )
    ```
3.  **Background Refresh Thread:** Inside `poly_market_maker/orderbook.py`, the `OrderBookManager` starts a daemon thread (`_thread_refresh_order_book`) that periodically fetches the latest active keeper orders and balances. The `time.sleep(self.refresh_frequency)` call within this thread dictates the pause between consecutive refreshes.
    ```python
    def _thread_refresh_order_book(self):
        while True:
            # ... (fetch orders and balances)
            time.sleep(self.refresh_frequency)
    ```
4.  **Reconciliation Mechanism:** This mechanism ensures eventual consistency with the CLOB (Central Limit Order Book) or mock exchange. Even if WebSocket updates are missed or delayed, the periodic refresh will eventually bring the local order book and balance state in sync with the external source.
5.  **Optimistic State:** The `OrderBookManager` maintains an optimistic local state by tracking orders being placed (`_orders_placed`) and orders being cancelled (`_order_ids_cancelling`, `_order_ids_cancelled`). This allows the `StrategyManager` to operate on a more immediate view of the order book, even before the background refresh confirms these operations on the exchange.

## `--websocket-debounce-ms`

**Definition:**

The `--websocket-debounce-ms` argument (default: 100 milliseconds) sets the minimum delay (in milliseconds) between WebSocket price triggers that can initiate a synchronization of the market-making strategy.

**Usage and Flow:**

1.  **Argument Parsing:** Defined in `poly_market_maker/args.py` and parsed at application startup.
2.  **`PriceListener` Initialization:** The `poly_market_maker/app.py` passes the `websocket_debounce_ms` value to the `PriceListener` during its initialization:
    ```python
    self.price_listener = PriceListener(
        # ...
        debounce_ms=args.websocket_debounce_ms,
        # ...
    )
    ```
3.  **Debounce Logic in `PriceListener`:** In `poly_market_maker/price_listener.py`, the `_handle_single_message` method implements the debounce logic. When a WebSocket message (e.g., `book` or `price_change`) is received, the `PriceListener` checks the time elapsed since the `last_trigger_time`. If the elapsed time is less than `debounce_ms`, the update is ignored.
    ```python
    # ... inside _handle_single_message(self, data):
    now = time.time() * 1000
    if (now - self.last_trigger_time) >= self.debounce_ms:
        self.last_trigger_time = now
        if self.shadow_book:
            self.shadow_book.apply_snapshot(data) # or apply_delta
        self.callback()
    else:
        self.logger.debug(f"Debouncing market data update.")
    ```
4.  **Strategy Synchronization:** If an update is *not* debounced, the `PriceListener` calls the `synchronize` method of the `StrategyManager` (via a callback). This triggers the market-making strategy to reassess the market and potentially place or cancel orders.

## Interaction and Potential Risks

**Optimistic Local State vs. Eventual Consistency:**

The system operates with two primary mechanisms for updating its view of the market:

1.  **Fast (Debounced) WebSocket Updates:** The `PriceListener` provides near real-time updates from the CLOB via WebSockets. The `websocket_debounce-ms` argument ensures that the strategy is not overwhelmed by a flood of rapid price changes, allowing for a minimum processing interval. When an update passes the debounce filter, it triggers an immediate strategy synchronization.
2.  **Slow (Periodic) Order Book Refresh:** The `OrderBookManager` periodically fetches the complete order book and balances. This `--refresh-frequency` mechanism acts as a robust reconciliation layer, ensuring that any missed WebSocket updates or discrepancies are eventually corrected.

**Simulation Desynchronization Risk:**

In simulation mode (`--simulate`), the `ShadowBook` in `poly_market_maker/simulation/shadow_book.py` is designed to maintain a local, in-memory representation of the order book by applying snapshots and deltas received from the WebSocket. However, due to the `websocket_debounce-ms` mechanism:

-   If WebSocket `price_change` deltas arrive faster than `debounce_ms`, some deltas might be ignored by the `PriceListener`.
-   Since deltas must be applied sequentially to maintain a correct order book state, skipping even a single delta can lead to the `ShadowBook` becoming desynchronized from the actual (simulated) exchange state.
-   The `OrderBookManager`'s periodic refresh can help to resynchronize the `ShadowBook` when it fetches the full order book. However, during the interval between refreshes, the `ShadowBook` might provide an inaccurate view of the market to the strategy, leading to suboptimal or incorrect decisions in a simulated environment.

This highlights a trade-off: debouncing helps prevent over-reaction to rapid, transient price fluctuations in live trading but introduces a risk of desynchronization in simulations that rely on a perfect sequence of deltas. A potential mitigation in simulation mode could be to disable or significantly reduce the `websocket_debounce-ms` to ensure all deltas are processed, or to implement more frequent full order book snapshots for the `ShadowBook`.
