# Runtime Flow: Lifecycle to Strategy in Poly Market Maker

This document outlines the runtime flow of the `poly-market-maker` application, focusing on how the `Lifecycle` class orchestrates the market-making strategy, particularly concerning limit order management and data requests during order replacement. The system operates on a polling architecture, with no WebSocket usage for real-time updates.

## Architecture Overview

The `poly-market-maker` application's core logic is managed by the `App` class, which initializes and integrates various components like the `ClobApi`, `GasStation`, `Contracts`, `Market`, `PriceFeedClob`, `OrderBookManager`, and `StrategyManager`. The overall execution is controlled by a `Lifecycle` instance, which schedules periodic synchronization tasks.

*   `App`: The entry point and orchestrator, responsible for setting up all necessary services and components.
*   `Lifecycle`: Manages the application's startup, periodic execution (synchronization), and shutdown phases.
*   `OrderBookManager`: Manages the local order book state, fetching orders and balances in a background thread.
*   `StrategyManager`: Selects and executes the chosen market-making strategy (e.g., `BandsStrategy`).

**Note**: The system uses a polling architecture to fetch data, rather than real-time updates via WebSockets.

## Two-Timer Architecture

The `poly-market-maker` utilizes two distinct timers, each with a specific role in maintaining market positions and data freshness:

1.  **Sync Interval (default: 30 seconds)**:
    *   **Role**: This is the **"Decision Cycle"** of the bot (the brain). It dictates how often the market-making strategy is evaluated and actions are taken.
    *   **Action**: Every `sync-interval` seconds, the main `App.synchronize()` function is called by the `Lifecycle`. During this call, the bot fetches the **current market price** and compares it against its desired strategy (e.g., `BandsStrategy`). Based on this evaluation, it decides which limit orders to cancel and which new orders to place.
    *   **Reactivity**: The bot **only** makes changes to the order book at these fixed intervals. If the market price moves between two sync intervals, the bot's existing orders will remain at their previous prices and will not react until the next sync interval.

2.  **Refresh Frequency (default: 5 seconds)**:
    *   **Role**: This is the **"Background Memory Update"** (the memory). It focuses on keeping the bot's internal view of its open orders and balances up-to-date.
    *   **Action**: Every `refresh-frequency` seconds, the `OrderBookManager`'s background thread (`_thread_refresh_order_book`) queries the CLOB API for all of the keeper's active orders and fetches its on-chain balances. This data is then cached internally by the `OrderBookManager`.
    *   **Purpose**: This asynchronous refresh ensures that when the `sync-interval` decision cycle occurs, the strategy has access to a reasonably fresh (at most `refresh-frequency` seconds old) list of its own open orders and current balances, without delaying the main decision-making process.

## Data Fetching Strategy

Data retrieval is split between an asynchronous background process for order book and balance information, and synchronous calls for price data.

### Asynchronous Background Loop (OrderBookManager)

The `OrderBookManager` operates in a dedicated background thread, constantly refreshing the keeper's active orders and balances.

1.  **Initialization**: When `App` starts, `OrderBookManager.start()` is called, which launches a daemon thread `_thread_refresh_order_book`.
2.  **Periodic Refresh**: This thread enters an infinite loop (`while True`) that pauses for `refresh_frequency` seconds between cycles.
3.  **Order Fetching**: It calls `self.get_orders_function()`, which is configured in `App` to be `self.clob_api.get_orders(self.market.condition_id)`. This makes a REST API call to the CLOB to retrieve all open orders for the given market.
4.  **Balance Fetching**: It calls `self.get_balances_function()`, configured in `App` as `self.get_balances()`. This method fetches on-chain balances for collateral and conditional tokens by interacting with smart contracts via `web3` and the `Contracts` utility.
5.  **State Update**: The fetched orders and balances update the `OrderBookManager`'s internal `_state` attribute. Importantly, if either fetching orders or balances fails, the `_state` is not updated with `None` values, ensuring data consistency.
6.  **Order Status Management**: The `OrderBookManager` also tracks orders that are `_currently_placing_orders`, `_orders_placed`, `_order_ids_cancelling`, and `_order_ids_cancelled` to provide an accurate representation of the order book, even before API confirmations.

### Synchronous Price Fetch (PriceFeed)

Market prices, crucial for strategy decisions, are fetched synchronously as part of the main synchronization loop.

1.  **Call by StrategyManager**: During `StrategyManager.synchronize()`, `self.get_token_prices()` is invoked.
2.  **PriceFeedClob**: This method, in turn, calls `self.price_feed.get_price(token)`, which is an instance of `PriceFeedClob`.
3.  **CLOB API Call**: `PriceFeedClob.get_price()` makes a direct REST API call to `self.clob_api.get_midpoint(token_id)` to retrieve the current midpoint price for a specific token.

## Limit Order Management Flow

The core of the market-making strategy involves continuously evaluating and adjusting limit orders based on the current market price and defined bands. This process is driven by the `Lifecycle`'s periodic `synchronize` call.

1.  **Lifecycle Trigger**: The `Lifecycle` class's `_main_loop` calls `self.synchronize()` on an `every` interval (e.g., every `sync_interval` seconds).
2.  **StrategyManager Synchronization**: `App.synchronize()` delegates to `self.strategy_manager.synchronize()`.
3.  **Order Book Snapshot**: `StrategyManager.synchronize()` first retrieves the latest order book state from `self.order_book_manager.get_order_book()`. This provides a snapshot of current open orders, balances, and in-progress order actions.
4.  **Token Price Retrieval**: It then fetches the target prices for Token A and Token B using `self.get_token_prices()`, which internally uses `PriceFeedClob` to query the CLOB API for midpoint prices.
5.  **Strategy Execution (e.g., BandsStrategy)**: The `StrategyManager` then calls `self.strategy.get_orders(orderbook, token_prices)` (e.g., `BandsStrategy.get_orders`).
    *   **Identify Orders to Cancel**: The strategy (e.g., `BandsStrategy.cancellable_orders`) evaluates existing `orderbook.orders` against the `target_prices` and its defined `bands`.
        *   Orders that are outside the defined bands or exceed the maximum amount for a band are identified for cancellation.
    *   **Identify New Orders to Place**: The strategy (e.g., `BandsStrategy.new_orders`) then determines where new orders need to be placed to fill under-represented bands, considering available collateral and token balances.
6.  **Order Execution**: `StrategyManager` calls `self.order_book_manager.cancel_orders(orders_to_cancel)` and `self.order_book_manager.place_orders(orders_to_place)`.
    *   **Asynchronous Operations**: Both cancellation and placement are handled asynchronously by the `OrderBookManager` using a `ThreadPoolExecutor`.
    *   `_thread_place_order`: Submits orders to `self.clob_api.place_order()` which makes a REST API call to `create_and_post_order` on the CLOB. The `order_id` is then used to track the order.
    *   `_thread_cancel_order`: Submits orders to `self.clob_api.cancel_order()` which makes a REST API call to `cancel` on the CLOB. The `order_id` is then added to `_order_ids_cancelled`.

## Data Request during Order Replacement

When orders are replaced (cancelled and new ones placed), the system performs the following data requests:

1.  **Price Data**: A synchronous REST API call to `clob_api.get_midpoint(token_id)` is made via `PriceFeedClob` to get the latest market price, which is critical for calculating new order prices and evaluating existing orders against the bands.
2.  **Order Book Data**: The `OrderBookManager`'s background thread continuously fetches all open keeper orders using `clob_api.get_orders(condition_id)`. This ensures that the strategy has an up-to-date view of the current open orders when determining which orders to cancel or place.
3.  **Balance Data**: The `OrderBookManager`'s background thread also continuously fetches on-chain balances using `contracts.token_balance_of` and `contracts.gas_balance`. This is used by the strategy to determine how much capital is available for new orders.

In essence, order replacement involves using the latest price data (synchronously fetched) and the continuously updated order book and balance data (asynchronously fetched) to make informed decisions about canceling old and placing new orders. The actual API calls for canceling and placing orders are REST API calls to the CLOB backend.

## Benefits of Asynchronous Architecture

Asynchronous operations are crucial in this market maker for **speed** and **efficiency**. Here is why they are needed and their benefits:

1.  **Non-Blocking Strategy Execution**: Network requests (like fetching orders or balances) can be slow. If the main strategy loop had to wait for every single request to finish one by one, the bot would react very slowly to market changes. By fetching data in the background, the main strategy loop always has instant access to the latest *cached* data. It doesn't have to wait for the network, allowing it to make decisions much faster.

2.  **Parallel Order Management**: A strategy might need to cancel multiple orders and place multiple new ones. Doing this sequentially would be slow. The `OrderBookManager` uses a thread pool to submit these requests in parallel. This means multiple orders can be placed or cancelled simultaneously, drastically reducing the time it takes to update the bot's position in the market.

3.  **Continuous Data Refresh**: The background thread acts like a "heartbeat," constantly pulling fresh data. This ensures that whenever the strategy runs, it's working with a snapshot of the market that is kept as fresh as possible without delaying the decision-making process.

## Risk of Stale Orders

Given the fixed `sync-interval` for strategy execution, there is an inherent risk of stale orders being present on the order book:

*   **Fixed-Time Reactivity**: The bot **only** makes changes to its limit orders at the precise moments dictated by the `sync-interval`. For example, if `sync-interval` is 30 seconds, the bot will evaluate its strategy and potentially update orders at 0s, 30s, 60s, and so on.
*   **Vulnerability Window**: If the market price experiences significant movement (e.g., a crash or spike) *between* these fixed sync intervals (e.g., at second 10 in a 30-second interval), the bot's existing limit orders will remain at their pre-movement prices. They will not react to the new market conditions.
*   **Stale Orders**: During this vulnerability window, the bot's orders are considered "stale." They no longer accurately reflect the desired strategy based on the current market price. This creates an opportunity for other faster market participants (arbitrageurs) to exploit these mispriced orders, leading to potential losses for the market maker.

In summary, while the asynchronous data fetching provides a reasonably fresh *view* of the bot's own orders and balances *at the moment of decision*, the fixed `sync-interval` introduces a latency in *acting* on new market prices, making orders susceptible to becoming stale. This design choice prioritizes operational simplicity and resource efficiency over instant, real-time reactivity to all market fluctuations.))
