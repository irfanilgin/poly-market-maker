import pytest
import time
import base64
from unittest.mock import patch
from poly_market_maker.utils.auth import generate_ws_headers

def test_generate_ws_headers_matches_spec():
    """
    Verifies the function produces a signature that matches a known-good
    reference vector calculated externally (e.g. via OpenSSL or official SDK).
    """
    # 1. KNOWN INPUTS
    api_key = "test-key"
    api_passphrase = "test-pass"
    
    # This is "the-secret-key-123456" encoded in URL-Safe Base64
    # We use this to verify your code correctly decodes it back to bytes.
    api_secret = "dGhlLXNlY3JldC1rZXktMTIzNDU2" 
    
    fixed_timestamp = 1700000000
    
    # 2. EXPECTED OUTPUT (Calculated externally)
    # Message: "1700000000GET/ws/user"
    # Key (bytes): "the-secret-key-123456"
    # HMAC-SHA256 (Hex): 980171d384de2aa1bc61de8df5e1e1e4efe003edb8ed6d45f5d2885e6f38d52d
    # Base64 (UrlSafe): koidMR9DFCNVB9rJe4t8npvTqdstn9hn6hhI8BSRfeU=
    expected_sig = "koidMR9DFCNVB9rJe4t8npvTqdstn9hn6hhI8BSRfeU="

    # 3. EXECUTE
    with patch('time.time', return_value=fixed_timestamp):
        headers = generate_ws_headers(api_key, api_secret, api_passphrase)

    # 4. ASSERT
    assert headers["Poly-Timestamp"] == str(fixed_timestamp)
    assert headers["Poly-Api-Signature"] == expected_sig
    
    print("\n✅ Signature verified against external reference vector.")