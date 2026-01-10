import logging
from prometheus_client import start_http_server
import time

from poly_market_maker.args import get_args
from poly_market_maker.price_feed import PriceFeedClob
from poly_market_maker.gas import GasStation, GasStrategy
from poly_market_maker.utils import setup_logging, setup_web3
from poly_market_maker.order import Order, Side
from poly_market_maker.market import Market
from poly_market_maker.token import Token, Collateral
from poly_market_maker.clob_api import ClobApi
from poly_market_maker.lifecycle import Lifecycle
from poly_market_maker.orderbook import OrderBookManager
from poly_market_maker.contracts import Contracts
from poly_market_maker.metrics import keeper_balance_amount
from poly_market_maker.strategy import StrategyManager
from poly_market_maker.price_listener import PriceListener
from poly_market_maker.simulation.shadow_book import ShadowBook
from poly_market_maker.simulation.mock_exchange import MockExchange


class App:
    """Market maker keeper on Polymarket CLOB"""

    def __init__(self, args: list):
        setup_logging()
        self.logger = logging.getLogger(__name__)

        args = get_args(args)

        # server to expose the metrics.
        self.metrics_server_port = args.metrics_server_port
        start_http_server(self.metrics_server_port)

        self.web3 = setup_web3(args.rpc_url, args.private_key)
        self.address = self.web3.eth.account.from_key(args.private_key).address

        self.shadow_book = None
        if args.simulate:
            # Initialize MockExchange first to get collateral address
            # ShadowBook needs a token_id which is derived from Market, which needs collateral address
            mock_exchange_instance = MockExchange(shadow_book=None, host=args.clob_api_url) # Pass None initially for shadow_book
            token_ids = mock_exchange_instance.get_token_ids(args.condition_id)
            self.market = Market(
                args.condition_id,
                token_ids,
                mock_exchange_instance.get_collateral_address(),
            )
            # Derive token_id for YES outcome (Token.A) using the real collateral address
            # This will ensure the ShadowBook tracks the correct real-world token.
            real_token_id = self.market.token_id(Token.A)
            self.logger.info(f"Derived real token_id for Token.A (YES outcome): {real_token_id}")

            self.shadow_book = ShadowBook(token_id=real_token_id)
            # Now re-initialize MockExchange with the actual shadow_book
            self.clob_api = MockExchange(shadow_book=self.shadow_book)
            self.logger.info("Initialized MockExchange for simulation mode with real token_id.")
        else:
            self.clob_api = ClobApi(
                host=args.clob_api_url,
                chain_id=self.web3.eth.chain_id,
                private_key=args.private_key,
            )
            token_ids = self.clob_api.get_token_ids(args.condition_id)
            self.market = Market(
                args.condition_id,
                self.clob_api.get_collateral_address(),
            )
            
            self.market.token_ids = {token_ids[Token.A], token_ids[Token.B]}
            self.shadow_book = ShadowBook(token_id=self.market.token_id(Token.A)) # Initialize in live mode

        self.last_strategy_run = 0
        self.strategy_interval = args.refresh_frequency

        self.gas_station = GasStation(
            strat=GasStrategy(args.gas_strategy),
            w3=self.web3,
            url=args.gas_station_url,
            fixed=args.fixed_gas_price,
        )
        self.contracts = Contracts(self.web3, self.gas_station)

        self.price_feed = PriceFeedClob(self.market, self.clob_api)

        self.order_book_manager = OrderBookManager(
            args.refresh_frequency, max_workers=1
        )
        self.order_book_manager.get_orders_with(self.get_orders)
        self.order_book_manager.get_balances_with(self.get_balances)
        self.order_book_manager.cancel_orders_with(
            lambda order: self.clob_api.cancel_order(order.id)
        )
        self.order_book_manager.place_orders_with(self.place_order)
        self.order_book_manager.cancel_all_orders_with(
            lambda _: self.clob_api.cancel_all_orders()
        )
        self.order_book_manager.start()

        self.strategy_manager = StrategyManager(
            args.strategy,
            args.strategy_config,
            self.price_feed,
            self.order_book_manager,
        )

        self.price_listener = PriceListener(
            ws_url=args.clob_ws_url,
            condition_id=args.condition_id,
            callback=self.synchronize,
            debounce_ms=args.websocket_debounce_ms,
            shadow_book=self.shadow_book,
            asset_id=real_token_id if args.simulate else self.market.token_id(Token.A) # Pass the derived real_token_id for subscription
        )
        self.price_listener.start()

    """
    main
    """

    def main(self):
        with Lifecycle() as lifecycle:
            lifecycle.on_startup(self.startup)
            lifecycle.on_shutdown(self.shutdown)

    """
    lifecycle
    """

    def startup(self):
        self.logger.info("Running startup callback...")
        # Only approve real contracts if not in simulation mode
        if not self.shadow_book:
            self.approve()
        time.sleep(5)  # 5 second initial delay so that bg threads fetch the orderbook
        self.logger.info("Startup complete!")

    def synchronize(self):
        """
        Synchronize the orderbook by cancelling orders out of bands and placing new orders if necessary
        """
        self.logger.debug("Synchronizing orderbook...")
        self.strategy_manager.synchronize()
        self.logger.debug("Synchronized orderbook!")

    def shutdown(self):
        """
        Shut down the keeper
        """
        self.logger.info("Keeper shutting down...")
        self.order_book_manager.cancel_all_orders()
        self.logger.info("Keeper is shut down!")

    """
    handlers
    """

    def get_balances(self) -> dict:
        """
        Fetch the balances of collateral and conditional tokens for the keeper.
        In simulation mode, fetches from MockExchange. Otherwise, from on-chain contracts.
        """
        if self.shadow_book:
            # In simulation mode, get balances directly from the mock exchange (ShadowBook)
            return self.clob_api.get_balances()
        else:
            # Original on-chain balance fetching logic
            self.logger.debug(f"Getting balances for address: {self.address}")

            collateral_balance = self.contracts.token_balance_of(
                self.clob_api.get_collateral_address(), self.address
            )
            token_A_balance = self.contracts.token_balance_of(
                self.clob_api.get_conditional_address(),
                self.address,
                self.market.token_id(Token.A),
            )
            token_B_balance = self.contracts.token_balance_of(
                self.clob_api.get_conditional_address(),
                self.address,
                self.market.token_id(Token.B),
            )
            gas_balance = self.contracts.gas_balance(self.address)

            keeper_balance_amount.labels(
                accountaddress=self.address,
                assetaddress=self.clob_api.get_collateral_address(),
                tokenid="-1",
            ).set(collateral_balance)
            keeper_balance_amount.labels(
                accountaddress=self.address,
                assetaddress=self.clob_api.get_conditional_address(),
                tokenid=self.market.token_id(Token.A),
            ).set(token_A_balance)
            keeper_balance_amount.labels(
                accountaddress=self.address,
                assetaddress=self.clob_api.get_conditional_address(),
                tokenid=self.market.token_id(Token.B),
            ).set(token_B_balance)
            keeper_balance_amount.labels(
                accountaddress=self.address,
                assetaddress="0x0",
                tokenid="-1",
            ).set(gas_balance)

            return {
                Collateral: collateral_balance,
                Token.A: token_A_balance,
                Token.B: token_B_balance,
            }

    def get_orders(self) -> list[Order]:
        orders = self.clob_api.get_orders(self.market.condition_id)
        return [
            Order(
                size=order_dict["size"],
                price=order_dict["price"],
                side=Side(order_dict["side"]),
                token=self.market.token(order_dict["token_id"]),
                id=order_dict["id"],
            )
            for order_dict in orders
        ]

    def place_order(self, new_order: Order) -> Order:
        order_id = self.clob_api.place_order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side.value,
            token_id=self.market.token_id(new_order.token),
        )
        return Order(
            price=new_order.price,
            size=new_order.size,
            side=new_order.side,
            id=order_id,
            token=new_order.token,
        )

    def approve(self):
        """
        Approve the keeper on the collateral and conditional tokens
        """
        collateral = self.clob_api.get_collateral_address()
        conditional = self.clob_api.get_conditional_address()
        exchange = self.clob_api.get_exchange()

        self.contracts.max_approve_erc20(collateral, self.address, exchange)
        self.contracts.max_approve_erc1155(conditional, self.address, exchange)
