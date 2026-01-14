import os
import sys
import time
import logging
from dotenv import load_dotenv
from poly_market_maker.app import App
from poly_market_maker.args import get_args

# --- CONFIGURATION ---
# The specific market Condition ID you want to trade
CONDITION_ID = "0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422"
# ---------------------

# 1. Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(threadName)s %(message)s'
)
logger = logging.getLogger(__name__)

def run():
    # 2. Load Environment Variables
    load_dotenv("config.env")

    # 3. Validation
    if not CONDITION_ID or CONDITION_ID.startswith("0x...") or len(CONDITION_ID) < 10:
        logger.error("Error: You must provide a valid CONDITION_ID in run_live.py")
        sys.exit(1)

    # Check for Private Key (Support both naming conventions just in case)
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("METAMASK_PRIVATE_KEY")
    if not private_key:
        logger.error("Error: PRIVATE_KEY not found in config.env")
        sys.exit(1)

    # 4. Construct Arguments List

    live_args_list = [
        "--private-key", private_key,
        "--rpc-url", os.getenv("RPC_URL", "https://polygon-rpc.com"),
        "--clob-api-url", os.getenv("CLOB_API_URL", "https://clob.polymarket.com/"),
        "--clob-ws-url", os.getenv("CLOB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market"),
        
        "--condition-id", CONDITION_ID,
        "--strategy", "bands",
        "--strategy-config", "config/bands.json",
        
        "--refresh-frequency", "5",
        "--min-size", "15",
        "--min-tick", "0.01",
        
        "--simulate", ""
    ]


    sys.argv = ["poly-market-maker"] + live_args_list

    try:
        logger.info("STEP 2: Initializing App Class...")
        bot_app = App(live_args_list)
        
        logger.info("STEP 3: Calling bot_app.main()...")
        
        # App.main() handles the lifecycle and blocks until shutdown
        bot_app.main()
        
        logger.info("App finished execution gracefully.")

    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        logger.info("\n User requested shutdown (Ctrl+C).")
        logger.info("Force killing process immediately...")
        # os._exit(0) kills the process INSTANTLY without waiting for cleanup.
        # It is the only way to stop a multi-threaded bot cleanly from the terminal.
        os._exit(0)
    except Exception as e:
        logger.exception(f"CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run()