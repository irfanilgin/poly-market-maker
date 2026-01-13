import asyncio
import os
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

async def derive_api_credentials(private_key: str):
    """
    Connects to Polymarket and derives API credentials (Key, Secret, Passphrase)
    using the provided wallet private key.
    
    Args:
        private_key (str): The Ethereum wallet private key (starts with "0x").
        
    Returns:
        dict: A dictionary containing 'api_key', 'api_secret', and 'api_passphrase',
              or None if an error occurs.
    """
    if not private_key or private_key == "0x...":
        raise ValueError("Invalid private key provided.")

    # Initialize the client with L1 (Wallet) Auth
    client = ClobClient(
        host="https://clob.polymarket.com", 
        key=private_key, 
        chain_id=POLYGON
    )

    try:
        # Request new (or existing) keys from the server
        # This signs a message with your wallet to prove identity
        creds = client.create_or_derive_api_creds()
        
        return {
            "api_key": creds.api_key,
            "api_secret": creds.api_secret,
            "api_passphrase": creds.api_passphrase
        }
        
    except Exception as e:
        # Re-raise the exception to let the caller handle logging/error reporting
        raise e
