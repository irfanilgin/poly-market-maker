import os
import time
from dotenv import load_dotenv
from web3 import Web3

# --- CONFIGURATION ---
# Polygon RPC
RPC_URL = "https://polygon-rpc.com"
# USDC Contract (Polygon)
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174" 
# Polymarket Exchange Contract (The one that needs permission)
EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E" 
# ---------------------

def main():
    load_dotenv("config.env")
    private_key = os.getenv("METAMASK_PRIVATE_KEY")
    
    if not private_key:
        print("❌ Error: PRIVATE_KEY not found in config.env")
        return

    # 1. Connect to Polygon
    print("🔌 Connecting to Polygon...")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ Failed to connect to Polygon RPC")
        return

    account = w3.eth.account.from_key(private_key)
    my_address = account.address
    print(f"🆔 Wallet: {my_address}")

    # 2. Check USDC Balance
    usdc_abi = [
        {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
        {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"}
    ]
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=usdc_abi)
    
    raw_balance = usdc_contract.functions.balanceOf(my_address).call()
    human_balance = raw_balance / 1_000_000 # USDC has 6 decimals
    
    print(f"💰 USDC in Wallet: ${human_balance}")

    if human_balance < 1:
        print("⚠️  You have less than 1 USDC. You need USDC to trade.")
        return

    # 3. Approve Exchange
    print("\n🚀 Approving Polymarket to trade your USDC...")
    
    # We approve a very large amount (infinite unlock) so you don't have to do this again
    max_amount = w3.to_wei(1000000, 'ether') # Just a huge number
    
    tx = usdc_contract.functions.approve(EXCHANGE_ADDRESS, max_amount).build_transaction({
        'chainId': 137,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(my_address),
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    print(f"⏳ Transaction Sent! Hash: {tx_hash.hex()}")
    print("Waiting for confirmation...")
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        print("✅ SUCCESS! Trading Enabled.")
        print("You can now run 'python run_live.py'")
    else:
        print("❌ Transaction Failed.")

if __name__ == "__main__":
    main()