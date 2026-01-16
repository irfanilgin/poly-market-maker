import asyncio
import json
import logging
import threading
import time
import websockets
from typing import Optional

from poly_market_maker.simulation.shadow_book import ShadowBook


class PriceListener:
    def __init__(self, ws_url: str, condition_id: str, callback: callable, debounce_ms: int, shadow_book: Optional[ShadowBook] = None, asset_id: Optional[int] = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_url = ws_url
        self.condition_id = condition_id # Using condition_id for market identification
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.last_trigger_time = 0
        self.running = False
        self.shadow_book = shadow_book
        self.asset_id = asset_id # The specific asset_id (token_id) to subscribe to.

    def start(self):
        """Starts the async listener in a daemon thread"""
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()

    def stop(self):
        """Stops the listener"""
        self.running = False

    def _run_loop(self):
        """Sets up asyncio loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._listen())

    async def _listen(self):
        """Connects, subscribes, and listens for updates"""
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.logger.info(f"Connected to WebSocket at {self.ws_url}")
                    subscription_message = {
                            
                            "type": "market",
                            "assets_ids": [str(self.asset_id)] # Corrected to assets_ids (plural)
                        
                        }
                    await ws.send(json.dumps(subscription_message))
                    self.logger.info(f"Sent subscription: {subscription_message}")

                    async for message in ws:
                        if not self.running:
                            break
                        self._handle_message(json.loads(message))
            except websockets.exceptions.ConnectionClosedOK:
                self.logger.info("WebSocket connection closed cleanly.")
            except BaseException as e:
                self.logger.error(f"WebSocket error in loop: {type(e).__name__}: {str(e)}. Reconnecting in 5 seconds...", exc_info=True)
                await asyncio.sleep(5) # Reconnect on error
        self.logger.info("PriceListener stopped.")

    def _handle_message(self, data):
        """Parses price and applies debounce. Handles both single messages and lists of messages."""
        if isinstance(data, list):
            for item in data:
                self._handle_single_message(item)
        else:
            self._handle_single_message(data)

    def _handle_single_message(self, data):
        """Processes a single WebSocket message."""
        event_type = data.get("event_type")

        # --- CASE 1: SNAPSHOT (Book) ---
        if event_type == "book":
            # Check asset/condition ID match
            if data.get("market") == self.condition_id and str(data.get("asset_id")) == str(self.asset_id):
                
                # 1. ALWAYS Update State (Data Integrity)
                raw_price = data.get("last_trade_price", "")
                
                # Update ShadowBook
                self.shadow_book.last_trade_price = raw_price
                self.logger.info(f"Updating market data: last traded price={self.shadow_book.last_trade_price}")
                
                self.logger.debug("Applying snapshot to ShadowBook...")
                self.shadow_book.apply_snapshot(data)
                
                self.logger.debug("Checking fills in ShadowBook...")
                self.shadow_book.check_fills()

                # 2. Debounce Action (Strategy Execution)
                self._try_trigger_strategy()

            else:
                self.logger.debug(f"Ignoring irrelevant book update: {data}")

        # --- CASE 2: DELTA (Price Change) ---
        elif event_type == "price_change":
            price_changes = data.get("price_changes")
            if isinstance(price_changes, list):
                for change in price_changes:
                    asset_id = change.get("asset_id")
                    # Filter by Asset ID to prevent applying deltas from other tokens
                    if asset_id == str(self.asset_id):
                        self.shadow_book.apply_delta(change) 

                    else:
                        self.logger.debug(f"Ignoring irrelevant price_change for asset: {asset_id}")
                # 2. Debounce Action
                self._try_trigger_strategy()
            else:
                self.logger.debug(f"Ignoring unknown WS message type: {event_type}")

    def _try_trigger_strategy(self):
        """Helper to debounce the expensive strategy callback."""
        now = time.time() * 1000
        if (now - self.last_trigger_time) >= self.debounce_ms:
            self.last_trigger_time = now
            try:
                self.logger.debug("Triggering strategy callback...")
                self.callback()
            except BaseException as e:
                self.logger.error(f"Error in strategy processing: {e}", exc_info=True)
        else:
            self.logger.debug("Debouncing strategy trigger.")