# Task: Implement Local "Shadow Book" and "Mock Exchange" for Strategy Simulation

**Objective:**
We are prioritizing a "Simulation-First" approach. You must design and implement a simulation layer that allows the market maker to run entirely in-memory, mimicking the behavior of the Polymarket CLOB.

**Context:**
Before we risk real capital or hit rate limits on the Polygon RPC, we must validate our strategies against live market data in a safe, local environment. This requires a "Mock Exchange" that acts as a drop-in replacement for the real CLOB client.

**Detailed Requirements:**

1.  **Architecture & Directory Structure**
    *   Create a new directory: `poly_market_maker/simulation/`.
    *   This directory will contain:
        *   `shadow_book.py`: The core engine tracking state and simulating fills.
        *   `mock_exchange.py`: The interface class mimicking the CLOB client.

2.  **Component 1: ShadowBook (`shadow_book.py`)**
    *   **Responsibilities**:
        *   Maintain local state of the market (Best Bid/Ask).
        *   Manage "Virtual Orders" (our simulated orders).
        *   Track "Virtual Inventory" and "Virtual Balances".
        *   **Fill Engine**: Simulate execution based on market data updates.
    *   **Fill Logic (The Engine)**:
        *   Implement `check_fills(new_market_data)` logic.
        *   **Quant Constraint**: Assume we are last in the queue. Only fill if the price moves *through* our level (strict crossing).
            *   Buy Order @ $P$ fills if Best Ask drops to $< P$.
            *   Sell Order @ $P$ fills if Best Bid rises to $> P$.

3.  **Component 2: MockExchange (`mock_exchange.py`)**
    *   **Responsibilities**:
        *   Act as a drop-in replacement for the real `ClobApi` (or `py_clob_client`).
        *   Implement the **exact same interface** as the client it replaces (e.g., `place_order`, `cancel_order`, `get_orders`, `get_balances`).
        *   Route all actions to the internal `ShadowBook` instance instead of the network.
    *   **Interface**:
        *   `place_order(...)`: Calls `shadow_book.add_virtual_order`.
        *   `cancel_order(...)`: Calls `shadow_book.cancel_virtual_order`.
        *   `get_orders(...)`: Calls `shadow_book.get_open_orders`.
        *   `get_balances(...)`: Calls `shadow_book.get_balances`.

4.  **Integration Hook (Code Trace)**
    *   **Market Data Feed**: Explain where in `price_listener.py` (or equivalent) we hook the `ShadowBook` to receive real-time updates.
    *   **Strategy Execution**: The `App` (or `Strategy`) will use `MockExchange` instead of `ClobApi`.

**Constraints:**
*   **Strictly Local**: No calls to Polygon RPC or Relayer in simulation mode.
*   **No Database**: In-memory state only.
*   **Output**: Log "Virtual Fill" events with price and inventory updates.
