from prometheus_client import Counter, Gauge, Histogram

chain_requests_counter = Counter(
    "chain_requests_counter",
    "Counts the chain executions",
    labelnames=["method", "status"],
    namespace="market_maker",
)
keeper_balance_amount = Gauge(
    "balance_amount",
    "Balance of the bot",
    labelnames=["accountaddress", "assetaddress", "tokenid"],
    namespace="market_maker",
)
clob_requests_latency = Histogram(
    "clob_requests_latency",
    "Latency of the clob requests",
    labelnames=["method", "status"],
    namespace="market_maker",
)
gas_station_latency = Histogram(
    "gas_station_latency",
    "Latency of the gas station",
    labelnames=["strategy", "status"],
    namespace="market_maker",
)

order_fill_latency = Histogram(
    "order_fill_latency_seconds",
    "Time from internal strategy signal to confirmed fill",
    labelnames=["side", "token"],  # breakdown by Buy/Sell and TokenA/B
    namespace="market_maker",
    # Custom buckets for HFT: 10ms to 10 seconds
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))
)

order_slippage = Histogram(
    "order_slippage",
    "Difference between Decision Price and Fill Price (Positive = Good, Negative = Bad)",
    labelnames=["side"], 
    namespace="market_maker",
    # Buckets for slippage: from -5 cents to +5 cents
    buckets=(-0.05, -0.01, -0.005, -0.001, 0, 0.001, 0.005, 0.01, 0.05, float("inf"))
)

# NEW: Strategy Effectiveness (Fill Count)
fill_counter = Counter(
    "order_fills_total",
    "Total number of orders filled",
    labelnames=["side", "token"],
    namespace="market_maker",
)

placed_orders_counter = Counter(
    "orders_placed_total",
    "Total number of orders sent to the exchange",
    labelnames=["side", "token"],
    namespace="market_maker",
)