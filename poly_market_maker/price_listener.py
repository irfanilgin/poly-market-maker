import asyncio
import json
import logging
import threading
import time
import websockets


class PriceListener:
    def __init__(self, ws_url: str, condition_id: str, callback: callable, debounce_ms: int):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_url = ws_url
        self.condition_id = condition_id # Using condition_id for market identification
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.last_trigger_time = 0
        self.running = False

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
                    # TODO: Confirm specific subscription JSON format with user
                    # Placeholder subscription for price updates related to the condition_id
                    subscription_message = {
                        "type": "subscribe",
                        "channels": [
                            {
                                "name": "price_updates", # Placeholder channel name
                                "market_id": self.condition_id # Using condition_id as market_id
                            }
                        ]
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
        """Parses price and applies debounce"""
        # TODO: Implement actual price extraction logic based on CLOB WS message format
        # Placeholder: Assuming 'price' field exists in the data
        new_price = data.get("price")
        market_id = data.get("market_id")

        if new_price is None or market_id != self.condition_id:
            self.logger.debug(f"Ignoring irrelevant WS message: {data}")
            return

        self.logger.debug(f"Received price update for {market_id}: {new_price}")

        # Debounce Logic
        now = time.time() * 1000
        if (now - self.last_trigger_time) >= self.debounce_ms:
            self.last_trigger_time = now
            self.logger.info(f"Debounce triggered for price {new_price}. Calling callback.")
            self.callback() # Trigger App.synchronize
        else:
            self.logger.debug(f"Debouncing price update for {market_id}: {new_price}")

