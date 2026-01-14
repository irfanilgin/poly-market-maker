import os
from dotenv import load_dotenv
from web3 import Web3

# --- CONFIGURATION ---
RPC_URL = "https://polygon-rpc.com"
# Polymarket uses THIS one (Bridged USDC)
BRIDGED_USDC_ADDR = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
# Coinbase sends THIS one (Native USDC)
NATIVE_USDC_ADDR  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

ABI = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]

def main():
    load_dotenv("config.env")
    private_key = os.getenv("METAMASK_PRIVATE_KEY")
    if not private_key:
        print("❌ Error: PRIVATE_KEY not found in config.env")
        return

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ Failed to connect to RPC")
        return

    account = w3.eth.account.from_key(private_key)
    my_address = account.address
    print(f"🆔 Checking Wallet: {my_address}")
    
    # Check MATIC
    matic_bal = w3.eth.get_balance(my_address) / 10**18
    print(f"⛽ MATIC Balance: {matic_bal:.4f}")

    # Check Bridged USDC (USDC.e)
    bridged_contract = w3.eth.contract(address=BRIDGED_USDC_ADDR, abi=ABI)
    bridged_bal = bridged_contract.functions.balanceOf(my_address).call() / 1_000_000
    print(f"📉 Bridged USDC (Polymarket uses this): ${bridged_bal}")

    # Check Native USDC
    native_contract = w3.eth.contract(address=NATIVE_USDC_ADDR, abi=ABI)
    native_bal = native_contract.functions.balanceOf(my_address).call() / 1_000_000
    print(f"🆕 Native USDC (Coinbase uses this):   ${native_bal}")

    if native_bal > 0 and bridged_bal == 0:
        print("\n🚨 DIAGNOSIS FOUND: You have the WRONG USDC!")
        print("You have Native USDC. Polymarket only accepts Bridged USDC (USDC.e).")
        print("You need to SWAP 'Native USDC' -> 'USDC.e' on Uniswap or MetaMask.")

if __name__ == "__main__":
    main()