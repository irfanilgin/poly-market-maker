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
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}. Reconnecting in 5 seconds...")
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
        if data.get("type") == "book":
            book_data = data.get("market")
            if book_data and str(book_data.get("asset_id")) == str(self.asset_id):
                best_bid = float(book_data["bids"][0][0]) if book_data["bids"] else 0.0
                best_ask = float(book_data["asks"][0][0]) if book_data["asks"] else float("inf")
                
                self.logger.info(f"Updating market data: Bid={best_bid}, Ask={best_ask}")
                # Debounce Logic
                now = time.time() * 1000
                if (now - self.last_trigger_time) >= self.debounce_ms:
                    self.last_trigger_time = now
                    if self.shadow_book:
                        self.shadow_book.update_market_data(best_bid=best_bid, best_ask=best_ask)
                    self.callback()
                else:
                    self.logger.debug(f"Debouncing market data update: Bid={best_bid}, Ask={best_ask}")
            else:
                self.logger.debug(f"Ignoring irrelevant book update: {data}")
        elif data.get("type") == "price_change":
            price_change_data = data.get("market")
            if price_change_data and str(price_change_data.get("asset_id")) == str(self.asset_id):
                best_bid = float(price_change_data.get("bid"))
                best_ask = float(price_change_data.get("ask"))

                self.logger.info(f"Updating market data: Bid={best_bid}, Ask={best_ask}")
                # Debounce Logic
                now = time.time() * 1000
                if (now - self.last_trigger_time) >= self.debounce_ms:
                    self.last_trigger_time = now
                    if self.shadow_book:
                        self.shadow_book.update_market_data(best_bid=best_bid, best_ask=best_ask)
                    self.callback()
                else:
                    self.logger.debug(f"Debouncing price change update: Bid={best_bid}, Ask={best_ask}")
        else:
            self.logger.debug(f"Ignoring unknown WS message type: {data.get("type")}")