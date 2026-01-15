import os
import sys
import logging
from web3 import Web3
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

# --- CONFIGURATION ---
# ⚠️ REPLACE THIS WITH YOUR PERSONAL WALLET ADDRESS
DESTINATION_ADDRESS = "0xabe0340E894113DF0E4047bF5EC013d1fa7ee2d2" 
AMOUNT_TO_SEND = 10.0 # Sending just 10 shares as a test
# ---------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("TestTransfer")

def main():
    load_dotenv(".env")
    
    if "PASTE_YOUR" in DESTINATION_ADDRESS:
        logger.error("❌ STOP: You must edit the script and add your DESTINATION_ADDRESS first.")
        return

    # 1. Setup
    rpc_url = os.getenv("RPC_URL", "https://polygon-rpc.com")
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("METAMASK_PRIVATE_KEY")
    condition_id = os.getenv("CONDITION_ID")
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)
    my_address = account.address
    logger.info(f"Source Wallet: {my_address}")

    # 2. Get Token ID
    # We use the client just to look up the correct ID for 'YES'
    client = ClobClient("https://clob.polymarket.com/", 137, private_key)
    try:
        resp = client.get_market(condition_id)
        # Usually index 0 is YES, index 1 is NO. 
        # Adjust if you hold NO shares.
        token_id = resp.get("tokens", [])[0].get("token_id") 
        logger.info(f"Token ID: {token_id}")
    except:
        logger.error("Could not find Token ID. Check condition_id in .env")
        return

    # 3. CTF Contract (The official ledger)
    ctf = w3.eth.contract(
        address=w3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"), 
        abi=[
            {"constant":True,"inputs":[{"name":"owner","type":"address"},{"name":"id","type":"uint256"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
            {"constant":False,"inputs":[{"name":"from","type":"address"},{"name":"to","type":"address"},{"name":"id","type":"uint256"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"}],"name":"safeTransferFrom","outputs":[],"type":"function"}
        ]
    )

    # 4. Check Balance
    raw_balance = ctf.functions.balanceOf(my_address, int(token_id)).call()
    human_balance = raw_balance / 10**6
    logger.info(f"Current Balance: {human_balance}")

    if human_balance < AMOUNT_TO_SEND:
        logger.error(f"Not enough balance to send {AMOUNT_TO_SEND}. You only have {human_balance}.")
        return

    # 5. Execute Transfer
    dest = w3.to_checksum_address(DESTINATION_ADDRESS)
    amount_atomic = int(AMOUNT_TO_SEND * 10**6)
    
    logger.info(f"🚀 Sending {AMOUNT_TO_SEND} shares to {dest}...")
    
    try:
        # safeTransferFrom(from, to, id, value, data)
        tx = ctf.functions.safeTransferFrom(
            my_address, 
            dest, 
            int(token_id), 
            amount_atomic, 
            b"" # Data must be empty bytes
        ).build_transaction({
            'from': my_address,
            'nonce': w3.eth.get_transaction_count(my_address),
            'gas': 150000,
            'gasPrice': int(w3.eth.gas_price * 1.5)
        })

        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        
        logger.info(f"✅ TX Sent! Hash: {w3.to_hex(tx_hash)}")
        logger.info("Waiting for confirmation...")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("🎉 Confirmed! Check your other wallet on Polymarket.")

    except Exception as e:
        logger.error(f"Transfer failed: {e}")

if __name__ == "__main__":
    main()