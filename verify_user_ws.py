import asyncio
import json
import logging
import websockets
import time
import hmac
import hashlib
import base64
import sys
# --- CONFIGURATION LOADER ---
# We use your existing config so we don't paste keys here
try:
    with open("config/config.json", "r") as f:
        config = json.load(f)
        credentials = config["clob_client"]["credentials"]
        API_KEY = credentials["api_key"]
        API_SECRET = credentials["api_secret"]
        API_PASSPHRASE = credentials["api_passphrase"]
except Exception as e:
    print(f"Could not load credentials from config/config.json: {e}")
    sys.exit(1)

# --- THE TEST ---
def generate_headers():
    """Generates the required Auth Headers for the Handshake"""
    timestamp = str(int(time.time()))
    method = "GET"
    request_path = "/ws/user"
    
    # 1. Prepare Message
    message = timestamp + method + request_path
    
    # 2. Decode Secret (URL-Safe Base64)
    try:
        # Add padding if missing to avoid errors
        secret_padded = API_SECRET + '=' * (-len(API_SECRET) % 4)
        secret_bytes = base64.urlsafe_b64decode(secret_padded)
    except Exception:
        secret_bytes = API_SECRET.encode('utf-8')

    # 3. Sign
    signature = hmac.new(
        secret_bytes,
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # 4. Encode Signature
    signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8')

    return {
        "Poly-Api-Key": API_KEY,
        "Poly-Api-Signature": signature_b64,
        "Poly-Timestamp": timestamp,
        "Poly-Api-Passphrase": API_PASSPHRASE,
    }

async def test_auth_headers():
    uri = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
    print(f"\nTEST: Connecting to {uri} with SIGNED HEADERS...")

    try:
        # Generate headers locally
        headers = generate_headers()
        
        # Connect WITH headers
        async with websockets.connect(uri, extra_headers=headers) as ws:
            print("Connected! (Handshake Accepted)")
            print("Listening for 'connected' confirmation...")
            
            # If the headers worked, the server will immediately send a confirmation
            try:
                async for message in ws:
                    data = json.loads(message)
                    print(f"RESPONSE: {data}")
                    
                    if data.get("type") == "connected":
                        print("\n SUCCESS: The Signed Headers method works!")
                        return
                    if data.get("type") == "error":
                        print(f"\nFAILURE: Server rejected signature: {data.get('message')}")
                        return
                        
            except asyncio.TimeoutError:
                print("TIMEOUT: Server silent.")
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"\n HANDSHAKE REJECTED (401/403): {e}")
        print("This usually means the Signature Math or Keys are incorrect.")
    except Exception as e:
        print(f"\n CONNECTION ERROR: {e}")

if __name__ == "__main__":
    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("PLEASE PASTE YOUR KEYS AT THE TOP!")
    else:
        asyncio.run(test_auth_headers())