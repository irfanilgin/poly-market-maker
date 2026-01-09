import asyncio
import json
import logging
import threading
import time
import websockets

from poly_market_maker.app import App
from poly_market_maker.market import Token
from poly_market_maker.simulation.shadow_book import ShadowBook
from poly_market_maker.price_listener import PriceListener

logging.basicConfig(level=logging.INFO, format=">>> %(message)s")
logger = logging.getLogger(__name__)

async def check_websocket_connection():
    TEST_CONDITION_ID = "0x4e4f77e7dbf4cab666e9a1943674d7ae66348e862df03ea6f44b11eb95731928"
    TEST_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    logger.info("Initializing App in simulation mode to derive token_id...")
    # Mock args needed for App initialization
    mock_args_list = [
        "--private-key", "0x1234567890123456789012345678901234567890123456789012345678901234",
        "--rpc-url", "http://mock-rpc.com",
        "--clob-api-url", "https://clob.polymarket.com",
        "--clob-ws-url", TEST_WS_URL,
        "--websocket-debounce-ms", "100",
        "--min-size", "10.0",
        "--min-tick", "0.01",
        "--refresh-frequency", "1",
        "--gas-strategy", "fixed",
        "--fixed-gas-price", "1",
        "--metrics-server-port", "9008",
        "--condition-id", TEST_CONDITION_ID,
        "--strategy", "bands",
        "--strategy-config", "./config/bands.json",
        "--simulate", "True"
    ]

    app = App(args=mock_args_list)
    
    # The shadow_book is created within App in simulation mode
    shadow_book = app.shadow_book

    if shadow_book is None:
        logger.error("ShadowBook not initialized. Exiting.")
        return

    derived_token_id = app.market.token_ids[Token.A]
    derived_token_id = '65139230827417363158752884968303867495725894165574887635816574090175320800482'

    logger.info(f"Derived Token ID for YES outcome (Token.A): {derived_token_id}")
    logger.info(f"Using WebSocket URL: {TEST_WS_URL}")

    # Instantiate PriceListener directly, bypassing App's threading for simplicity in this example
    # In the actual app, PriceListener is started in a separate thread.
    price_listener = PriceListener(
        ws_url=TEST_WS_URL,
        condition_id=TEST_CONDITION_ID,
        callback=lambda: logger.info("Callback triggered by PriceListener!"), # Simple callback for demonstration
        debounce_ms=100,
        shadow_book=shadow_book,
        asset_id=derived_token_id
    )
    price_listener.start()

    logger.info("Listening for WebSocket market data... Press Ctrl+C to stop.")
    try:
        while True:
            # Periodically check shadow book for updates (optional, PriceListener updates it directly)
            best_bid = shadow_book.get_best_bid()
            best_ask = shadow_book.get_best_ask()
            if best_bid != 0.0 or best_ask != float("inf"):
                logger.info(f"Current ShadowBook Market State: Bid={best_bid}, Ask={best_ask}")
            await asyncio.sleep(5) # Keep the script alive
    except asyncio.CancelledError:
        logger.info("WebSocket connection check stopped.")
    except KeyboardInterrupt:
        logger.info("Script interrupted by user.")
    finally:
        price_listener.stop()
        logger.info("PriceListener stopped.")

if __name__ == "__main__":
    asyncio.run(check_websocket_connection())
