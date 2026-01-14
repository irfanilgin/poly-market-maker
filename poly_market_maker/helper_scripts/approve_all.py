import os
import time
from dotenv import load_dotenv
from web3 import Web3

# --- CONFIGURATION ---
RPC_URL = "https://polygon-rpc.com"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# The Three Polymarket Doors
SPENDERS = {
    "Standard Exchange": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
    "Neg Risk Adapter":  "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
    "CLOB Adapter":      "0xC5d563A36AE78145C45a50134d48A1215220f80a"
}

def main():
    load_dotenv("config.env")
    private_key = os.getenv("METAMASK_PRIVATE_KEY")
    if not private_key:
        print("❌ Error: PRIVATE_KEY not found")
        return

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(private_key)
    my_address = account.address
    print(f"🆔 Wallet: {my_address}")

    # Setup USDC Contract
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=[
        {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
    ])

    print("\n🚀 Checking and Approving Contracts...")
    
    for name, spender_address in SPENDERS.items():
        # Check current allowance
        current_allowance = usdc.functions.allowance(my_address, spender_address).call()
        
        if current_allowance > 1000 * 10**6:
            print(f"✅ {name}: Already Approved.")
            continue

        print(f"🔓 Approving {name} ({spender_address})...")
        try:
            # Approve Infinite
            tx = usdc.functions.approve(spender_address, w3.to_wei(1000000, 'ether')).build_transaction({
                'chainId': 137,
                'gas': 100000,
                'gasPrice': w3.eth.gas_price,
                'nonce': w3.eth.get_transaction_count(my_address),
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"   ⏳ Tx Sent: {tx_hash.hex()}... Waiting...")
            w3.eth.wait_for_transaction_receipt(tx_hash)
            print("   ✅ Confirmed.")
            # Sleep briefly to let nonce update
            time.sleep(2) 
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print("\n✨ All systems go. Try running the bot now.")

if __name__ == "__main__":
    main()