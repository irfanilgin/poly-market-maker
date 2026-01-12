import logging
import os
import yaml
from logging import config
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware, SignAndSendRawMiddlewareBuilder
from web3.gas_strategies.time_based import fast_gas_price_strategy


def setup_logging(
    log_path="logging.yaml",
    log_level=logging.INFO,
    env_key="LOGGING_CONFIG_FILE",
):
    """
    :param default_path:
    :param default_level:
    :param env_key:
    :return:
    """
    log_value = os.getenv(env_key, None)
    if log_value:
        log_path = log_value
    if os.path.exists(log_path):
        with open(log_path) as fh:
            config.dictConfig(yaml.safe_load(fh.read()))
        logging.getLogger(__name__).info("Logging configured with config file!")
    else:
        logging.basicConfig(
            format="%(asctime)-15s %(levelname)-4s %(threadName)s %(message)s",
            level=log_level,
        )
        logging.getLogger(__name__).info("Logging configured with default attributes!")
    # Suppress requests and web3 verbose logs
    logging.getLogger("requests").setLevel(logging.INFO)
    logging.getLogger("web3").setLevel(logging.INFO)


def setup_web3(rpc_url, private_key):
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    # 1. POA Middleware (Updated for v7)
    # Replaces: w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # 2. Signing Middleware (Updated to Builder Pattern)
    # Replaces: w3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))
    w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(private_key))
    
    # Set default account (Unchanged)
    w3.eth.default_account = w3.eth.account.from_key(private_key).address

    # 3. Gas Middleware (Unchanged, but ensure import is correct)
    w3.eth.set_gas_price_strategy(fast_gas_price_strategy)

    # 4. Caching Middleware
    # NOTE: These were removed in v6/v7. 
    # Do not include: time_based_cache_middleware, simple_cache_middleware, etc.
    # If you need caching, you must implement it at the application level 
    # (e.g. using functools.lru_cache on specific functions).

    return w3
