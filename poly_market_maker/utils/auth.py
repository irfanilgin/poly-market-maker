import time
import hmac
import hashlib
import base64
import logging

def generate_ws_headers(api_key: str, api_secret: str, api_passphrase: str):
    """
    Generates the Signed Headers required for the User WebSocket handshake.
    Matches the logic validated in verify_user_ws_headers.py.
    """
    timestamp = str(int(time.time()))
    method = "GET"
    request_path = "/ws/user"
    
    # 1. Prepare Message
    message = timestamp + method + request_path
    
    # 2. Decode Secret (URL-Safe Base64)
    try:
        # Add padding if missing
        secret_padded = api_secret + '=' * (-len(api_secret) % 4)
        secret_bytes = base64.urlsafe_b64decode(secret_padded)
    except Exception:
        # Fallback to raw bytes
        secret_bytes = api_secret.encode('utf-8')

    # 3. Sign
    signature = hmac.new(
        secret_bytes,
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # 4. Encode Signature
    signature_b64 = base64.urlsafe_b64encode(signature).decode('utf-8')

    return {
        "Poly-Api-Key": api_key,
        "Poly-Api-Signature": signature_b64,
        "Poly-Timestamp": timestamp,
        "Poly-Api-Passphrase": api_passphrase,
    }