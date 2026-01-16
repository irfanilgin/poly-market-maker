from poly_market_maker.token import Token, Collateral
from poly_market_maker.order import Order, Side
from poly_market_maker.orderbook import OrderBook

from poly_market_maker.strategies.bands import Bands
from poly_market_maker.strategies.base_strategy import BaseStrategy


class BandsStrategy(BaseStrategy):
    def __init__(
        self,
        config: dict,
    ):
        assert isinstance(config, dict)

        super().__init__()
        self.bands = Bands(config.get("bands"))
        
        # Map String -> Enum (O(1) lookup)
        token_map = {"A": Token.A, "B": Token.B}

        active_tokens_config = config.get("active_tokens", ["A", "B"])

        # Create the list (List Comprehension is faster than for-loops)
        self.tradable_tokens = [
            token_map[t] for t in active_tokens_config 
            if t in token_map
        ]

        # Safety Check (Cost: Runs once, saves you from 0-order bugs)
        if not self.tradable_tokens:
            self.logger.warning("No valid tokens configured! Defaulting to Token A.")
            self.tradable_tokens = [Token.A]
            
        self.logger.info(f"Strategy active on: {self.tradable_tokens}")

        self.vanilla_mode = config.get("vanilla_mode", False)

    def get_orders(self, orderbook: OrderBook, target_prices):
        """
        Synchronize the orderbook by cancelling orders out of bands and placing new orders if necessary
        """
        orders_to_place = []
        orders_to_cancel = []

        for token in self.tradable_tokens:
            self.logger.info(f"{token.value} target price: {target_prices[token]}")
        #TODO: make this function more modular
        # cancel orders
        for token in self.tradable_tokens:
            
            if self.vanilla_mode:
                # VANILLA: Filter for orders of the CURRENT token (Buy A + Sell A)
                orders = [
                    o for o in orderbook.orders 
                    if o.token == token
                ]
            else:
                # ARBITRAGE: Use the original helper (Buy A + Sell B)
                orders = self._orders_by_corresponding_buy_token(orderbook.orders, token)
            
            orders_to_cancel += self.bands.cancellable_orders(
                orders, target_prices[token], vanilla_mode=self.vanilla_mode
            )

        # remaining open orders
        open_orders = list(set(orders) - set(orders_to_cancel))
        balance_locked_by_open_buys = sum(
            order.size * order.price for order in open_orders if order.side == Side.BUY
        )
        self.logger.info(f"Collateral locked by buys: {balance_locked_by_open_buys}")

        free_collateral_balance = (
            orderbook.balances[Collateral] - balance_locked_by_open_buys
        )
        self.logger.info(f"Free collateral balance: {free_collateral_balance}")

        # place orders
        for token in self.tradable_tokens:
            if self.vanilla_mode:
                orders = [
                    o for o in orderbook.orders 
                    if o.token == token
                ]
            else:
                # Arbitrage Mode (If you use this, verify this helper works)
                orders = self._orders_by_corresponding_buy_token(orderbook.orders, token)

            if self.vanilla_mode:
                # VANILLA: We look at the SAME token for selling
                token_to_sell = token 
            else:
                # ARBITRAGE: We look at the COMPLEMENT token for selling
                token_to_sell = token.complement()

            balance_locked_by_open_sells = sum(
                order.size for order in orders if order.side == Side.SELL
            )
            self.logger.info(
                f"{token.complement().value} locked by sells: {balance_locked_by_open_sells}"
            )

            free_token_balance = (
                orderbook.balances[token_to_sell] - balance_locked_by_open_sells
            )
            self.logger.info(
                f"Free {token.complement().value} balance: {free_token_balance}"
            )

            new_orders = self.bands.new_orders(
                orders,
                free_collateral_balance,
                free_token_balance,
                target_prices[token],
                token,
                vanilla_mode=self.vanilla_mode
            )
            
            valid_new_orders = new_orders

            free_collateral_balance -= sum(
                order.size * order.price
                for order in valid_new_orders
                if order.side == Side.BUY
            )
            orders_to_place += valid_new_orders
            

        return (orders_to_cancel, orders_to_place)

    def _orders_by_corresponding_buy_token(self, orders: list[Order], buy_token: Token):
        return list(
            filter(
                lambda order: self._filter_by_corresponding_buy_token(order, buy_token),
                orders,
            )
        )

    def _filter_by_corresponding_buy_token(self, order: Order, buy_token: Token):
        if self.vanilla_mode:
            # VANILLA: We manage Buy and Sell orders for the SAME token
            return order.token == buy_token
        
        # ARBITRAGE: Buy A, Sell B
        return (order.side == Side.BUY and order.token == buy_token) or (
            order.side == Side.SELL and order.token != buy_token
        )
