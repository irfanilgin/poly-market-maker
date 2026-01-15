import os
import sys
import logging
import json
from dotenv import load_dotenv

# Add project root to path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from poly_market_maker.clob_api import ClobApi
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Hardcode the Condition ID from your logs
# (You could also load this from arguments or config)
CONDITION_ID = "0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422"

def main():
    logger.info("🔍 Initializing Inventory Status Check...")

    # 1. Load Config
    load_dotenv("config.env")
    pk = os.getenv("PRIVATE_KEY") or os.getenv("METAMASK_PRIVATE_KEY")
    host = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
    chain_id = int(os.getenv("CHAIN_ID", 137))

    if not pk:
        logger.error("❌ No Private Key found in config.env!")
        return

    # 2. Connect
    try:
        api = ClobApi(host=host, chain_id=chain_id, private_key=pk)
    except Exception as e:
        logger.error(f"❌ Connection failed: {e}")
        return

    # 3. Get Token IDs (to identify YES vs NO)
    logger.info(f"🔍 Fetching Token IDs for Condition {CONDITION_ID}...")
    token_ids = api.get_token_ids(CONDITION_ID)
    yes_id = token_ids.get('yes')
    no_id = token_ids.get('no')
    
    if not yes_id:
        logger.error("❌ Could not find YES token ID!")
        return
    
    logger.info(f"   YES ID: {yes_id}")
    logger.info(f"   NO  ID: {no_id}")

    # 4. Check Conditional Token Balance (YES)
    logger.info("\n💰 Checking Shares Balance (YES Token)...")
    try:
        # Note: We access the underlying client directly because clob_api.get_balances() 
        # ignores share balances.
        yes_balance_resp = api.client.get_balance_allowance(
            params=BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL, 
                token_id=yes_id
            )
        )
        yes_balance = float(yes_balance_resp.get('balance', 0))
        logger.info(f"   ✅ YES Shares Owned: {yes_balance}")
        
    except Exception as e:
        logger.error(f"❌ Failed to check YES balance: {e}")


    # 5. Check Collateral (USDC)
    logger.info("\n💰 Checking Collateral (USDC)...")
    try:
        usdc_resp = api.client.get_balance_allowance(
            params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        usdc_balance = float(usdc_resp.get('balance', 0))
        logger.info(f"   ✅ USDC Available: {usdc_balance}")
    except Exception as e:
        logger.error(f"❌ Failed to check USDC balance: {e}")


    # 6. Check Open Orders
    logger.info("\n📋 Checking Open Orders (Locked Funds/Shares)...")
    orders = api.get_orders(CONDITION_ID)
    
    if not orders:
        logger.info("   ✅ No open orders found.")
    else:
        logger.info(f"   ⚠️ Found {len(orders)} OPEN orders!")
        for o in orders:
            side = o.get('side')
            price = o.get('price')
            size = o.get('size')
            asset_id = str(o.get('token_id'))
            
            token_name = "YES" if asset_id == str(yes_id) else "NO"
            logger.info(f"      - {side} {size} {token_name} @ {price}")

    logger.info("\n🏁 Done.")

if __name__ == "__main__":
    main()