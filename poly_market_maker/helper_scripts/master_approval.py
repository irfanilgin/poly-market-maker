import os
import sys
import logging
import time
from web3 import Web3
from dotenv import load_dotenv

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Approvals")

# --- CONSTANTS ---
# 1. The Tokens we need to approve
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_ADDRESS  = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045" # The "Shares" contract

# 2. The "Shotgun" List of Spenders (Who gets permission?)
# We approve ALL of them so your bot works on ANY market type.
SPENDERS = [
    ("Standard Exchange", "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"), # For Yes/No Markets
    ("NegRisk Exchange",  "0xC5d563A36AE78145C45a50134d48A1215220f80a"), # For Election/Multi Markets
    ("NegRisk Adapter",   "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"), # For Converting Shares
    ("Old Adapter",       "0xd91E80cF2E04a2C30e95865E91aA5304C2D686e3"), # Legacy/Specific Markets
]

MAX_INT = 2**256 - 1

def approve_token(w3, account, token_contract, spender, is_erc1155=False, name="Token"):
    """
    Checks if approval exists. If not, sends the transaction.
    """
    spender = w3.to_checksum_address(spender)
    owner = account.address

    try:
        if is_erc1155:
            # Check CTF (Shares) Approval
            is_approved = token_contract.functions.isApprovedForAll(owner, spender).call()
            if not is_approved:
                logger.info(f"SETTING APPROVAL: {name} -> {spender}...")
                tx = token_contract.functions.setApprovalForAll(spender, True).build_transaction({
                    'from': owner,
                    'nonce': w3.eth.get_transaction_count(owner),
                    'gas': 100000,
                    'gasPrice': int(w3.eth.gas_price * 1.5)
                })
                return tx
            else:
                logger.info(f"✅ Already Approved: {name} -> {spender}")

        else:
            # Check USDC (Money) Allowance
            current_allowance = token_contract.functions.allowance(owner, spender).call()
            if current_allowance < (MAX_INT // 2):
                logger.info(f"SETTING APPROVAL: {name} -> {spender}...")
                tx = token_contract.functions.approve(spender, MAX_INT).build_transaction({
                    'from': owner,
                    'nonce': w3.eth.get_transaction_count(owner),
                    'gas': 100000,
                    'gasPrice': int(w3.eth.gas_price * 1.5)
                })
                return tx
            else:
                logger.info(f"✅ Already Approved: {name} -> {spender}")
                
    except Exception as e:
        logger.error(f"Error checking approval for {spender}: {e}")
    
    return None

def main():
    load_dotenv(".env")
    
    rpc_url = os.getenv("RPC_URL", "https://polygon-rpc.com")
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("METAMASK_PRIVATE_KEY")
    
    if not private_key:
        logger.error("No Private Key found in .env")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)
    logger.info(f"Bot Address: {account.address}")
    logger.info("--- STARTING APPROVAL SWEEP ---")
    
    # Contract Objects
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=[
        {"constant":True,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},
        {"constant":False,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}
    ])
    
    ctf = w3.eth.contract(address=CTF_ADDRESS, abi=[
        {"constant":True,"inputs":[{"name":"account","type":"address"},{"name":"operator","type":"address"}],"name":"isApprovedForAll","outputs":[{"name":"","type":"bool"}],"type":"function"},
        {"constant":False,"inputs":[{"name":"operator","type":"address"},{"name":"approved","type":"bool"}],"name":"setApprovalForAll","outputs":[],"type":"function"}
    ])

    # Loop through every spender and approve both USDC and CTF
    for name, address in SPENDERS:
        # 1. USDC Approval
        tx_usdc = approve_token(w3, account, usdc, address, is_erc1155=False, name="USDC")
        if tx_usdc:
            signed = w3.eth.account.sign_transaction(tx_usdc, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"Sent USDC Approve: {w3.to_hex(tx_hash)}")
            w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info("Confirmed.")

        # 2. CTF Approval
        tx_ctf = approve_token(w3, account, ctf, address, is_erc1155=True, name="CTF Shares")
        if tx_ctf:
            signed = w3.eth.account.sign_transaction(tx_ctf, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"Sent CTF Approve: {w3.to_hex(tx_hash)}")
            w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info("Confirmed.")
            
    logger.info("--- ALL APPROVALS COMPLETE ---")

if __name__ == "__main__":
    main()