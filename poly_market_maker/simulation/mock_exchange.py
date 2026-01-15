import logging
import requests
import time
from typing import Optional

from poly_market_maker.order import Order, Side
from poly_market_maker.token import Token, Collateral
from poly_market_maker.simulation.shadow_book import ShadowBook


class MockExchange:
    """
    A mock implementation of the ClobApi that interacts with a ShadowBook for simulation.
    It provides the same interface as ClobApi but operates entirely in-memory.
    """

    def __init__(self, shadow_book: ShadowBook, host: str=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.shadow_book = shadow_book
        self._mock_address = "0x" + "2"*40
        self._mock_collateral_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        self._mock_conditional_address = "0x" + "4"*40
        self._mock_exchange_address = "0x" + "5"*40
        self.host = host
        self.collateral_balance = 10000.0
        self.token_A_balance = 100.0
        self.token_B_balance = 100.0

    def set_token_ids(self, token_a_id, token_b_id):
        # In mock mode, we might just store them or ignore if we depend on ShadowBook token_id
        pass


    def get_address(self) -> str:
        return self._mock_address

    def get_collateral_address(self) -> str:
        return self._mock_collateral_address

    def get_conditional_address(self) -> str:
        return self._mock_conditional_address

    def get_exchange(self, neg_risk: bool = False) -> str:
        return self._mock_exchange_address

    def get_price(self, token_id: int) -> float:
        """
        Returns the current mid-price from the shadow book\"s market state.
        """
        best_bid = self.shadow_book.get_best_bid()
        best_ask = self.shadow_book.get_best_ask()
        if best_bid == 0.0 or best_ask == float("inf"):
            return 0.5 # Default price if no market data yet
        return (best_bid + best_ask) / 2.0

    def get_orders(self, condition_id: str) -> list[dict]:
        """
        Returns open virtual orders from the shadow book, formatted like ClobApi response.
        """
        # condition_id is not directly used by shadow_book as it\"s initialized with a specific token_id
        # but we keep the signature for compatibility.
        orders = self.shadow_book.get_open_orders()
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                "size": order.size,
                "price": order.price,
                "side": order.side.value,
                "token_id": self.shadow_book.token_id, # Assuming single token_id for now
                "id": order.id,
                "original_size": order.size, # For compatibility with ClobApi structure
                "size_matched": 0.0 # For compatibility
            })
        return formatted_orders

    def place_order(self, price: float, size: float, side: str, token_id: int) -> Optional[str]:
        """
        Places a virtual order in the shadow book.
        """
        time.sleep(0.2)
        # Ensure token_id matches the shadow book\"s token_id, or handle multiple markets if needed
        if token_id != self.shadow_book.token_id:
            self.logger.error(f"Attempted to place order for token_id {token_id} on shadow book for {self.shadow_book.token_id}")
            return None

        # In simulation, directly use Token.A as a placeholder for the token, since shadow_book.token_id is a generic integer.
        order = Order(size=size, price=price, side=Side(side), token=Token.A)
        order.token_id = token_id # Store the original token_id as an attribute on the order for reference
        order_id = self.shadow_book.add_virtual_order(order)
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancels a virtual order in the shadow book.
        """
        time.sleep(0.2)
        return self.shadow_book.cancel_virtual_order(order_id)

    def cancel_all_orders(self) -> bool:
        """
        Cancels all virtual orders in the shadow book.
        """
        open_orders = self.shadow_book.get_open_orders()
        for order in open_orders:
            self.shadow_book.cancel_virtual_order(order.id)
        return True
    
    def get_balances(self) -> dict:
        """
        Returns the current virtual balances from the shadow book.
        """
        return {Collateral: self.collateral_balance,
                Token.A: self.token_A_balance,
                Token.B: self.token_B_balance,}

    def get_market(self, condition_id: str) -> Optional[dict]:
        """
        Mocks fetching market details for a given condition_id.
        Returns a dictionary similar to what the real CLOB API\"s get_market would return,
        containing outcomes with assetIds.
        """
        if self.shadow_book and str(self.shadow_book.token_id) == str(condition_id): # Simple condition_id check for mock
            yes_asset_id = self.shadow_book.token_id
            return {
                "id": condition_id, # Or market ID, but condition_id is passed
                "question": f"Mock Market for {condition_id}",
                "slug": f"mock-market-{condition_id}",
                "outcomes": [
                    {"assetId": str(self.shadow_book.token_id)}, # Token.A (YES)
                    {"assetId": str(self.get_token_ids(condition_id)["no"])} # Token.B (NO) - using CTHelpers for mock consistency
                ]
            }
        return None # Return None if market not found in mock
    

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
                if outcome == 'yes':
                    token_ids['yes'] = t.get('token_id')
                elif outcome == 'no':
                    token_ids['no'] = t.get('token_id')
                        
        except Exception as e:
            self.logger.error(f"Error fetching token_ids from CLOB API for condition {condition_id}: {e}")
        
        if len(token_ids) != 2:
            self.logger.error(f"Failed to get both Token.A and Token.B IDs for condition {condition_id}. Only got: {token_ids}. This might lead to errors.")

        return token_ids


