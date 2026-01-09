import os
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.token import Token # Import Token for dictionary keys

# --- Configuration (replace with your actual values) ---
# For a real scenario, these would typically come from environment variables or a config file.
HOST = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")  # Example host
CHAIN_ID = int(os.environ.get("CLOB_CHAIN_ID", 137))  # Example Chain ID (Polygon Mainnet)
PRIVATE_KEY = "0x1234567890123456789012345678901234567890123456789012345678901234" # !!! IMPORTANT: Replace with your actual private key or load securely !!!

# Set to True to run the ClobApi in mock mode (no actual API calls will be made).
# Useful for testing the script structure without live credentials.
IS_MOCK = os.environ.get("IS_MOCK", "False").lower() == "true"

CONDITION_ID = "0x4e4f77e7dbf4cab666e9a1943674d7ae66348e862df03ea6f44b11eb95731928"

def main():
    print("Initializing ClobApi...")
    if IS_MOCK:
        print("Running in MOCK mode. No actual API calls will be made.")
    
    # Initialize ClobApi. If IS_MOCK is True, private_key can be a dummy value.
    # In a real application, ensure private_key is handled securely.
    clob_api = ClobApi(host=HOST, chain_id=CHAIN_ID, private_key=PRIVATE_KEY, is_mock=False)

    print(f"Checking token IDs for condition_id: {CONDITION_ID}")
    try:
        token_ids = clob_api.get_token_ids(CONDITION_ID)
        print(f"Returned token IDs: {token_ids}")
        if Token.A in token_ids and Token.B in token_ids:
            print(f"Token.A (YES) ID: {token_ids[Token.A]}")
            print(f"Token.B (NO) ID: {token_ids[Token.B]}")
        else:
            print("Could not retrieve both Token.A and Token.B IDs.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
