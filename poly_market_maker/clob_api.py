import logging
import sys
import time
import requests
from py_clob_client.client import ClobClient, ApiCreds, OrderArgs
from py_clob_client.clob_types import OpenOrderParams, AssetType, BalanceAllowanceParams
from py_clob_client.exceptions import PolyApiException

from poly_market_maker.utils import randomize_default_price
from poly_market_maker.constants import OK
from poly_market_maker.metrics import clob_requests_latency
from poly_market_maker.token import Token, Collateral

DEFAULT_PRICE = 0.5


class ClobApi:
    def __init__(self, host, chain_id, private_key, is_mock: bool = False):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = None
        self.host = host

        if not is_mock:
            self.client = self._init_client_L1(
                host=host,
                chain_id=chain_id,
                private_key=private_key,
            )

            try:
                api_creds = self.client.derive_api_key()
                self.logger.debug(f"Api key found: {api_creds.api_key}")
            except PolyApiException:
                self.logger.debug("Api key not found. Creating a new one...")
                api_creds = self.client.create_api_key()
                self.logger.debug(f"Api key created: {api_creds.api_key}.")

            self.client = self._init_client_L2(
                host=host,
                chain_id=chain_id,
                private_key=private_key,
                creds=api_creds,
            )
        else:
            self.logger.info("ClobApi initialized in mock mode.")
        
        self.token_a_id = None
        self.token_b_id = None

    def set_token_ids(self, token_a_id, token_b_id):
        self.token_a_id = token_a_id
        self.token_b_id = token_b_id

    def get_address(self):
        return self.client.get_address()

    def get_collateral_address(self):
        return self.client.get_collateral_address()

    def get_conditional_address(self):
        return self.client.get_conditional_address()

    def get_exchange(self, neg_risk = False):
        return self.client.get_exchange_address(neg_risk)

    def get_price(self, token_id: int) -> float:
        """
        Get the current price on the orderbook.
        Returns None if the API call fails.
        """
        self.logger.debug("Fetching midpoint price from the API...")
        start_time = time.time()
        try:
            resp = self.client.get_midpoint(token_id)
            
            # Log success metric
            clob_requests_latency.labels(method="get_midpoint", status="ok").observe(
                (time.time() - start_time)
            )
            
            if resp.get("mid") is not None:
                return float(resp.get("mid"))
                
        except Exception as e:
            self.logger.error(f"Error fetching current price from the CLOB API: {e}")
            # Log error metric
            clob_requests_latency.labels(method="get_midpoint", status="error").observe(
                (time.time() - start_time)
            )
        
        # CRITICAL CHANGE: Return None (or raise Error) instead of guessing
        self.logger.warning(f"Could not fetch price for {token_id}. Returning None.")
        return None

    def _rand_price(self) -> float:
        price = randomize_default_price(DEFAULT_PRICE)
        self.logger.info(
            f"Could not fetch price from CLOB API, returning random price: {price}"
        )
        return price

    def get_orders(self, condition_id: str):
        """
        Get open keeper orders on the orderbook.
        Fetches ALL orders and filters client-side to avoid API parameter issues.
        """
        self.logger.debug("Fetching open keeper orders from the API...")
        start_time = time.time()
        try:

            #TODO: test OpenOrderParams for client call
            resp = self.client.get_orders()

            clob_requests_latency.labels(method="get_orders", status="ok").observe(
                (time.time() - start_time)
            )

            #TODO: Do we need this filter
            valid_token_ids = [str(self.token_a_id), str(self.token_b_id)]
            
            filtered_resp = []
            for order in resp:
                if str(order.get("asset_id")) in valid_token_ids:
                    filtered_resp.append(order)
            
            self.logger.debug(f"Fetched {len(resp)} orders, {len(filtered_resp)} match our tokens.")

            return [self._get_order(order) for order in filtered_resp]

        except Exception as e:
            self.logger.error(
                f"Error fetching keeper open orders from the CLOB API: {e}"
            )
            clob_requests_latency.labels(method="get_orders", status="error").observe(
                (time.time() - start_time)
            )
        return []

    def place_order(self, price: float, size: float, side: str, token_id: int) -> str:
        """
        Places a new order
        """
        self.logger.info(
            f"Placing a new order: Order[price={price},size={size},side={side},token_id={token_id}]"
        )
        start_time = time.time()
        try:
            resp = self.client.create_and_post_order(
                OrderArgs(price=price, size=size, side=side, token_id=token_id)
            )
            clob_requests_latency.labels(
                method="create_and_post_order", status="ok"
            ).observe((time.time() - start_time))
            order_id = None
            if resp and resp.get("success") and resp.get("orderID"):
                order_id = resp.get("orderID")
                self.logger.info(
                    f"Succesfully placed new order: Order[id={order_id},price={price},size={size},side={side},tokenID={token_id}]!"
                )
                return order_id

            err_msg = resp.get("errorMsg")
            self.logger.error(
                f"Could not place new order! CLOB returned error: {err_msg}"
            )
        except Exception as e:
            self.logger.error(f"Request exception: failed placing new order: {e}")
            clob_requests_latency.labels(
                method="create_and_post_order", status="error"
            ).observe((time.time() - start_time))
        return None

    def cancel_order(self, order_id) -> bool:
        self.logger.info(f"Cancelling order {order_id}...")
        if order_id is None:
            self.logger.debug("Invalid order_id")
            return True

        start_time = time.time()
        try:
            resp = self.client.cancel(order_id)
            clob_requests_latency.labels(method="cancel", status="ok").observe(
                (time.time() - start_time)
            )
            # Fix: Check for list, dict with 'canceled' items, or success=True
            if isinstance(resp, list) or (isinstance(resp, dict) and (resp.get("success", False) or len(resp.get("canceled", [])) > 0)):
                return True
            return resp == OK # Fallback for mock/legacy behavior
        except Exception as e:
            self.logger.error(f"Error cancelling order: {order_id}: {e}")
            clob_requests_latency.labels(method="cancel", status="error").observe(
                (time.time() - start_time)
            )
        return False

    def cancel_all_orders(self) -> bool:
        self.logger.info("Cancelling all open keeper orders..")
        start_time = time.time()
        try:
            resp = self.client.cancel_all()
            clob_requests_latency.labels(method="cancel_all", status="ok").observe(
                (time.time() - start_time)
            )
            # Fix: Check for list, dict with 'canceled' items, or success=True
            if isinstance(resp, list) or (isinstance(resp, dict) and (resp.get("success", False) or len(resp.get("canceled", [])) > 0)):
                return True
            return resp == OK # Fallback for mock/legacy behavior
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            clob_requests_latency.labels(method="cancel_all", status="error").observe(
                (time.time() - start_time)
            )
        return False

    def _init_client_L1(
        self,
        host,
        chain_id,
        private_key,
    ) -> ClobClient:
        clob_client = ClobClient(host, chain_id, private_key)
        try:
            if clob_client.get_ok() == OK:
                self.logger.info("Connected to CLOB API!")
                self.logger.info(
                    "CLOB Keeper address: {}".format(clob_client.get_address())
                )
                return clob_client
        except: # Catch all exceptions here for robustness
            self.logger.error("Unable to connect to CLOB API, shutting down!")
            sys.exit(1)

    def _init_client_L2(
        self, host, chain_id, private_key, creds: ApiCreds
    ) -> ClobClient:
        clob_client = ClobClient(host, chain_id, private_key, creds)
        try:
            if clob_client.get_ok() == OK:
                self.logger.info("Connected to CLOB API!")
                self.logger.info(
                    "CLOB Keeper address: {}".format(clob_client.get_address())
                )
                return clob_client
        except: # Catch all exceptions here for robustness
            self.logger.error("Unable to connect to CLOB API, shutting down!")
            sys.exit(1)


    def get_balances(self):
        """
        Fetches the user's collateral (USDC) and Conditional Token balances.
        """
        self.logger.debug("Fetching user balances...")
        balances = {Collateral: 0.0, Token.A: 0.0, Token.B: 0.0}
        
        # Polymarket uses 6 decimals for USDC and Conditional Tokens
        DECIMALS = 10**6

        try:
            # 1. Collateral
            try:
                resp = self.client.get_balance_allowance(
                    params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
                )
                balance = float(resp.get('balance', 0)) / DECIMALS
                balances[Collateral] = balance
                
                # Add by address as well (legacy support)
                collateral_address = self.client.get_collateral_address()
                balances[collateral_address] = balance
                balances[collateral_address.lower()] = balance
            except Exception as e:
                 self.logger.error(f"Error fetching Collateral balance: {e}")

            # 2. Token A
            if self.token_a_id:
                try:
                    resp = self.client.get_balance_allowance(
                        params=BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=self.token_a_id)
                    )
                    balances[Token.A] = float(resp.get('balance', 0)) / DECIMALS
                except Exception as e:
                    self.logger.error(f"Error fetching Token A balance: {e}")

            # 3. Token B
            if self.token_b_id:
                try:
                    resp = self.client.get_balance_allowance(
                        params=BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=self.token_b_id)
                    )
                    balances[Token.B] = float(resp.get('balance', 0)) / DECIMALS
                except Exception as e:
                    self.logger.error(f"Error fetching Token B balance: {e}")

            self.logger.info(f"💰 Balances: USDC={balances.get(Collateral)}, A={balances.get(Token.A)}, B={balances.get(Token.B)}")
            return balances

        except Exception as e:
            self.logger.error(f"Error fetching balances: {e}")
            return balances
    
    def _get_order(self, order_dict: dict) -> dict:
        size = float(order_dict.get("original_size")) - float(order_dict.get("size_matched"))
        price = float(order_dict.get("price"))
        side = order_dict.get("side")
        order_id = order_dict.get("id")
        token_id = int(order_dict.get("asset_id"))

        return {
            "size": size,
            "price": price,
            "side": side,
            "token_id": token_id,
            "id": order_id,
        }

    def get_token_ids(self, condition_id: str) -> dict:
        """
        Fetches token IDs (asset IDs) from the CLOB API for a given condition_id.
        Returns a dictionary with Token.A and Token.B mapped to their respective IDs.
        """
        token_ids = {}
        url = self.host + f"/markets/{condition_id}"
        try:
            response = requests.get(url)
            if response.status_code != 200:
                self.logger.warning(f"Market details or outcomes not found for condition {condition_id} from CLOB API.")
            data = response.json()
            tokens = data.get('tokens', [])
        
            for t in tokens:
                outcome = t.get('outcome', '').lower()
                t_id = t.get('token_id')
                self.logger.info(f"DEBUG: Found token: Outcome='{outcome}', ID='{t_id}'")
                if outcome == 'yes':
                    token_ids['yes'] = t_id
                elif outcome == 'no':
                    token_ids['no'] = t_id
                        
        except PolyApiException as e:
            self.logger.error(f"PolyApiException fetching token_ids for condition {condition_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error fetching token_ids from CLOB API for condition {condition_id}: {e}")
        
        if len(token_ids) != 2:
            self.logger.error(f"Failed to get both Token.A and Token.B IDs for condition {condition_id}. Only got: {token_ids}. This might lead to errors.")

        return token_ids
