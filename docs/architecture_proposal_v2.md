# Architecture Proposal V2: Hybrid Event-Driven Market Maker

This document proposes an architectural upgrade for the `poly-market-maker` to address the "stale orders" vulnerability identified in the current polling-based system. The proposed solution is a **Hybrid Event-Driven Architecture** that integrates WebSocket-based price updates for rapid reaction while maintaining the robustness of periodic polling.

## 1. Problem Statement Revisited

The current market maker operates on a fixed `sync-interval` (default 30 seconds) for strategy evaluation and order placement/cancellation. While `OrderBookManager` refreshes its view of active orders and balances more frequently (default 5 seconds), the core trading decisions are only made at these coarse intervals. This creates a significant **vulnerability window** during which the bot's on-book orders can become stale (mispriced) in a volatile market, making them susceptible to arbitrage.

## 2. Proposed Hybrid Architecture

The Hybrid Event-Driven Architecture combines the strengths of real-time WebSocket feeds with the reliability of periodic polling.

### Core Components & Modifications:

*   **Existing `Lifecycle` & `App`**: Remain largely the same, but the `Lifecycle.every(sync_interval, synchronize)` call will become a **fallback/reconciliation mechanism** rather than the primary trigger.
*   **`OrderBookManager`**: Continues its background polling (`refresh-frequency`) for owned orders and balances. This acts as a robust safety net to ensure the bot's internal state eventually aligns with the exchange, even if WebSocket events are missed.
*   **New `PriceListener` Module**: A new component responsible for establishing and maintaining a WebSocket connection to the CLOB API for real-time market price updates.
*   **Event-Driven Strategy Trigger**: The `App.synchronize()` method will primarily be triggered by price events from the `PriceListener`, instead of (or in addition to) the fixed `sync-interval`.

### Architectural Diagram (Conceptual):

```
+-----------------------+
|       CLOB Exchange   |
| +-------------------+ |
| | WebSocket Price   | |
| | Feed              | |
| +---------+---------+ |
|           |           |
+-----------|-----------+
            |
            | (Real-time Price Ticks)
            |
+-----------v-----------+
|    `PriceListener`    |
|   (WebSocket Client)  |
|                       |
|   - Connects to CLOB  |
|   - Receives price    |
|     updates           |
|   - Applies debounce  |
|     logic             |
+-----------+-----------+
            |
            | (Debounced Price Events)
            |
+-----------v-----------+
|       `App`           |
|  - StrategyManager    |
|  - OrderBookManager   |
|  - Lifecycle          |
+-----------+-----------+
            |
            | (Calls `App.synchronize()`)
            | (Periodically, as fallback)
+-----------v-----------+
|    `Lifecycle`        |
|    (Fallback Sync)    |
+-----------------------+
```

## 3. Configurable Debounce Logic

To prevent "thrashing" and respect API rate limits, a debounce mechanism will be implemented within the `PriceListener`. This debounce will be a **configurable parameter**.

*   **Parameter**: `--websocket-debounce-ms` (e.g., default 100ms, configurable via command-line or config file).
*   **Mechanism**: The `PriceListener` will receive continuous price updates from the WebSocket. However, it will only emit a `synchronize` trigger to the `App` if:
    1.  The `new_price` differs from the `last_synced_price` by a significant `threshold` (e.g., a configurable percentage or minimum tick size).
    2.  And, at least `websocket-debounce-ms` has passed since the *last time* `App.synchronize()` was triggered by a price event.
*   **Benefits**: Allows the bot to react quickly to meaningful price changes while avoiding excessive API calls for minor fluctuations or during periods of high market volatility.

## 4. Enhanced Reactivity & Risk Mitigation

### A. Improved Reactivity

*   **Immediate Response**: The primary trigger for `App.synchronize()` shifts from a fixed `sync-interval` to event-driven price updates. The bot will react to significant price changes within `network_latency + processing_time + debounce_interval_ms`.
*   **Reduced Vulnerability Window**: The exposure to stale orders is drastically reduced from seconds (e.g., 30s) to milliseconds or a configured debounce interval (e.g., 100-500ms), making the bot significantly more competitive against faster market movements.

### B. Risk Mitigation & Robustness

*   **WebSocket Disconnects**: The `PriceListener` must implement robust reconnection logic (exponential backoff, retries).
*   **Fallback to Polling**: The existing `Lifecycle.every(sync_interval, synchronize)` will be kept. If the WebSocket connection fails persistently, or if for any reason price events are missed, the periodic `sync-interval` will act as a crucial fallback, ensuring the bot's strategy is eventually reconciled with the market.
*   **State Reconciliation**: The `OrderBookManager`'s continuous background refresh of owned orders and balances remains essential for validating the bot's internal state against the exchange, regardless of the price trigger mechanism.
*   **API Rate Limiting**: The configurable debounce interval directly addresses potential API rate limit issues by preventing an overwhelming number of `create_and_post_order` and `cancel_order` requests during extreme volatility.

## 5. Python Latency Analysis

Python's overhead is **not** the bottleneck for this architecture.

*   **I/O Bound**: Trading bots are primarily I/O-bound (waiting for network, not CPU crunching). Python's `asyncio` framework is exceptionally well-suited for efficient handling of concurrent network operations (WebSockets and REST APIs).
*   **Processing Speed**: The logic to receive a WebSocket message, check the price threshold, and trigger the `synchronize` function is computationally light. The latency added by Python's interpreter in this path will be negligible (sub-millisecond) compared to network latencies (tens to hundreds of milliseconds).
*   **Concurrency for Orders**: The `OrderBookManager`'s `ThreadPoolExecutor` efficiently handles parallel API calls for placing and canceling orders, further minimizing the impact of Python's GIL on this critical path.

## 6. Implementation Considerations

*   **Dependency**: Introduction of a WebSocket client library (e.g., `websockets` or similar) if `py_clob_client` doesn't natively support WS streams.
*   **Configuration**: Add `--websocket-debounce-ms` (int, default e.g., 100-500) to `args.py`.
*   **Modification**: Rework `App` and `Lifecycle` to integrate the `PriceListener`'s event-driven triggers.

This hybrid approach offers a significant improvement in reactivity and robustness, directly tackling the stale order problem while maintaining a resilient operational framework.
