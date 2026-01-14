import logging

from poly_market_maker.ct_helpers import CTHelpers
from poly_market_maker.token import Token


class Market:
    def __init__(self, condition_id: str, token_ids: dict, collateral_address: str):
        self.logger = logging.getLogger(self.__class__.__name__)

        assert isinstance(condition_id, str)
        assert isinstance(token_ids, dict)
        assert isinstance(collateral_address, str)

        self.condition_id = condition_id
        self.token_ids = {Token.A: token_ids['yes'], Token.B: token_ids['no']}
        self.logger.info(f"Initialized Market: {self}")

    def __repr__(self):
        return f"Market[condition_id={self.condition_id}, token_id_a={self.token_ids[Token.A]}, token_id_b={self.token_ids[Token.B]}]"

    def token_id(self, token: Token) -> int:
        return self.token_ids[token]

    def token(self, token_id: int) -> Token:
        #TODO: should we make these str()?
        for token in Token:
            if token_id == self.token_ids[token]:
                return token
        raise ValueError("Unrecognized token ID")
