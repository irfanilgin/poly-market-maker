import asyncio
import json
import logging
import threading
import websockets
import time

from poly_market_maker.utils.metrics_tracker import MetricsTracker
from poly_market_maker.utils.auth import generate_ws_headers

class UserListener:
    def __init__(self, api_key, api_secret, api_passphrase, manager=None, ws_url="wss://ws-subscriptions-clob.polymarket.com/ws/user"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_url = ws_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.order_book_manager = manager
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._listen())

    async def _listen(self):
        while self.running:
            try:
                headers = generate_ws_headers(self.api_key, self.api_secret, self.api_passphrase)
                self.logger.info(f"Connecting to User WebSocket...")
                
                async with websockets.connect(self.ws_url, extra_headers=headers) as ws:
                    self.logger.info("User WebSocket Connected & Authenticated.")
                    
                    async for message in ws:
                        if not self.running: break
                        self._handle_message(json.loads(message))

            except Exception as e:
                self.logger.error(f"User WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
        self.logger.info("UserListener stopped.")

    def _handle_message(self, data):
        if isinstance(data, list):
            for item in data: self._process_event(item)
        else:
            self._process_event(data)

    def _process_event(self, event):
        if event.get("type") == "FILL":
            self._handle_fill(event)

    def _handle_fill(self, fill_event):
        order_id = fill_event.get("orderID") or fill_event.get("order_id")
        price = float(fill_event.get("price", 0))
        size = float(fill_event.get("size", 0))
        
        self.logger.info(f"*** FILL DETECTED *** Order {order_id}: {size} @ {price}")

        if self.order_book_manager:
            # We call the new get_order method we are about to add
            original_order = self.order_book_manager.get_order(order_id)
            if original_order:
                MetricsTracker.record_fill(original_order, fill_time=time.time())
                self.logger.info(f"Recorded fill metrics for {order_id}")