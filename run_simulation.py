import logging
import argparse
import time

from poly_market_maker.app import App
from poly_market_maker.strategy import Strategy
from poly_market_maker.order import Order, Side
from poly_market_maker.market import Token

# Configure basic logging for the simulation script
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_simulation():
    logger.info("Starting simulation...")

    # Prepare mock arguments as a list of strings, similar to sys.argv
    mock_args_list = [
        "--private-key", "0x1234567890123456789012345678901234567890123456789012345678901234",
        "--rpc-url", "http://mock-rpc.com",
        "--clob-api-url", "http://mock-clob-api.com",
        "--clob-ws-url", "wss://ws-subscriptions-clob.polymarket.com/ws/market", # Real Polymarket WebSocket URL
        "--websocket-debounce-ms", "100",
        "--min-size", "10.0", # Reduced for easier testing
        "--min-tick", "0.01",
        "--refresh-frequency", "1",
        "--gas-strategy", "fixed",
        "--fixed-gas-price", "1",
        "--metrics-server-port", "9008",
        "--condition-id", "0x6e9f08625902094285915d9061030e2c21949511a2f4705051a37c0f1647413c", # Actual condition_id for demonstration
        "--strategy", "bands", # Using string representation
        "--strategy-config", "./config/bands.json",
        "--simulate", "True"
    ]

    # Initialize the App in simulation mode. get_args will parse this list.
    app = App(args=mock_args_list)

    # Access the shadow book and mock exchange directly for demonstration
    shadow_book = app.shadow_book
    mock_exchange = app.clob_api

    logger.info(f"Initial Virtual Balances: {shadow_book.get_balances()}")

    # Simulate placing a buy order
    buy_order = Order(size=10.0, price=0.49, side=Side.BUY, token=Token.A)
    buy_order_id = mock_exchange.place_order(buy_order.price, buy_order.size, buy_order.side.value, shadow_book.token_id)
    logger.info(f"Placed virtual buy order with ID: {buy_order_id}")

    # Simulate placing a sell order
    sell_order = Order(size=10.0, price=0.51, side=Side.SELL, token=Token.B)
    sell_order_id = mock_exchange.place_order(sell_order.price, sell_order.size, sell_order.side.value, shadow_book.token_id)
    logger.info(f"Placed virtual sell order with ID: {sell_order_id}")

    logger.info(f"Open Virtual Orders: {shadow_book.get_open_orders()}")
    logger.info(f"Current Market State: {shadow_book._market_state}")
    
    logger.info(f"Derived Token ID for YES outcome (Token.A): {app.market.token_ids[Token.A]}")

    logger.info("Simulation running in Shadow Mode. Waiting for real market data...")
    try:
        while True:
            time.sleep(1) # Keep the script alive to listen for WebSocket updates
    except KeyboardInterrupt:
        logger.info("Simulation stopped by user.")
    
    logger.info("\n--- Simulation Complete ---")
    logger.info(f"Final Virtual Balances: {shadow_book.get_balances()}")
    logger.info(f"Final Open Virtual Orders: {shadow_book.get_open_orders()}")

if __name__ == "__main__":
    run_simulation()

