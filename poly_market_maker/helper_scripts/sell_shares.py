import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs

def main():
    load_dotenv(".env")

    # --- SETTINGS ---
    AMOUNT = 50.0       # Number of shares
    PRICE  = 0.50       # Price per share
    OUTCOME = "YES"     # "YES" or "NO"
    # ----------------

    # 1. Initialize Client (L1 Auth - Private Key)
    print("Connecting...")
    client = ClobClient(
        "https://clob.polymarket.com/", 
        137, 
        os.getenv("METAMASK_PRIVATE_KEY"), 
        signature_type=0, 
        funder=os.getenv("USER_ADDRESS") 
    )

    # 2. AUTO-SET API CREDENTIALS (The missing link)
    # This creates new keys if you don't have them, or finds existing ones.
    try:
        print("Setting API Credentials...")
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        print("✅ Credentials Set!")
    except Exception as e:
        print(f"❌ Credential Error: {e}")
        return

    # 3. Get Token ID
    condition_id = os.getenv("CONDITION_ID")
    resp = client.get_market(condition_id)
    tokens = resp.get("tokens", [])
    token_id = tokens[0].get("token_id") if OUTCOME == "YES" else tokens[1].get("token_id")

    # 4. Set Exchange (NegRisk Specific)
    # Comment this out for standard Yes/No markets
    client.exchange_address = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

    # 5. Place Order
    print(f"Selling {AMOUNT} shares at {PRICE}...")
    
    order_args = OrderArgs(
        price=PRICE,
        size=AMOUNT, # Corrected: No manual * 10**6
        side="SELL",
        token_id=str(token_id)
    )

    try:
        resp = client.create_and_post_order(order_args)
        if resp and resp.get("success"):
            print(f"✅ Sold! Order ID: {resp.get('orderID')}")
        else:
            print(f"❌ Error: {resp.get('errorMsg')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()