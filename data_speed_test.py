import asyncio
import websockets
import json
from datetime import datetime

# --- CONFIGURATION ---
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"
POLY_RTDS_URL = "wss://ws-live-data.polymarket.com"

async def binance_listener():
    """Listens to direct Binance feed."""
    async with websockets.connect(BINANCE_WS_URL) as websocket:
        print(f"\033[92m[BINANCE] Connected.\033[0m")
        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                price = float(data['p'])
                now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{now}] BINANCE     | {price:.2f}")
        except Exception as e:
            print(f"[BINANCE] Error: {e}")

async def polymarket_listener():
    """Listens to Polymarket RTDS."""
    # Custom headers
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # FIX: Use 'additional_headers' instead of 'extra_headers' for newer websockets versions
    async with websockets.connect(POLY_RTDS_URL, additional_headers=headers) as websocket:
        print(f"\033[94m[POLYMARKET] Connected.\033[0m")
        
        # Subscribe to crypto_prices
        sub_msg = {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": "crypto_prices", 
                    "type": "update"
                }
            ]
        }
        await websocket.send(json.dumps(sub_msg))
        print("[POLYMARKET] Subscription sent.")

        # Heartbeat task
        async def keep_alive():
            while True:
                await asyncio.sleep(10)
                try:
                    await websocket.ping()
                except:
                    break
        asyncio.create_task(keep_alive())
        
        try:
            while True:
                message = await websocket.recv()
                
                # Handle possible empty messages
                if not message: continue

                try:
                    data = json.loads(message)
                except:
                    continue

                if isinstance(data, list): 
                    for item in data: process_poly_message(item)
                else:
                    process_poly_message(data)
                        
        except Exception as e:
            print(f"[POLYMARKET] Connection Error: {e}")

def process_poly_message(data):
    """Helper to parse the nested Polymarket payload"""
    if data.get("topic") == "crypto_prices":
        payload = data.get("payload", {})
        symbol = payload.get("symbol", "")
        price = payload.get("price") or payload.get("value")
        
        # Filter for BTC
        if "btc" in symbol.lower() and price:
            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{now}]                                   POLYMARKET  | {float(price):.2f}")

async def main():
    print("Starting latency race (v5 - Fixed Headers)...")
    print("-----------------------------------------------------------------------")
    print("TIME            SOURCE      | PRICE")
    print("-----------------------------------------------------------------------")
    await asyncio.gather(binance_listener(), polymarket_listener())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest stopped.")