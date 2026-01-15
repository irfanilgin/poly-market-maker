import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from logger import logger
import numpy as np


class PolymarketData:
    def __init__(self):
        self.clob_url = "https://clob.polymarket.com"
        self.gamma_url = "https://gamma-api.polymarket.com/markets"

    def get_market_info(self, condition_id):
        """
        Resolves a Condition ID to its YES Token ID and its Question Title.
        Returns: (token_id, question)
        """
        url = f"{self.clob_url}/markets/{condition_id}"
        try:
            response = requests.get(url)
            if response.status_code != 200:
                logger.error(f"API Error {response.status_code} for ID {condition_id}")
                return None, None

            data = response.json()
            question = data.get('question', 'Unknown Market')
            tokens = data.get('tokens', [])

            # Find the YES outcome token
            yes_token_id = None
            for t in tokens:
                if t.get('outcome') == 'Yes':
                    yes_token_id = t.get('token_id')
                    break

            # Fallback
            if not yes_token_id and tokens:
                yes_token_id = tokens[0].get('token_id')

            return yes_token_id, question

        except Exception as e:
            logger.error(f"Failed to resolve ID: {str(e)}")
            return None, None

    import requests

    def get_daily_volume(self, token_id: str) -> float:
        """
        Retrieves the 24-hour trading volume (in USDC) for the market
        associated with the given clobTokenId.

        Args:
            token_id (str): The CLOB Token ID (e.g. "2174...").

        Returns:
            float: The 24-hour volume in USDC. Returns 0.0 if not found.
        """
        try:
            # The Gamma API allows filtering markets by specific token IDs
            params = {
                "clob_token_ids": token_id
            }

            response = requests.get(self.gamma_url, params=params)
            response.raise_for_status()
            data = response.json()

            # The API returns a list of markets (usually just one for a unique token ID)
            if data and isinstance(data, list):
                market_data = data[0]
                # 'volume24hr' is the standard field for trailing 24h volume
                return float(market_data.get("volume24hr", 0.0))

            return 0.0

        except Exception as e:
            print(f"Error fetching volume for token {token_id}: {e}")
            return 0.0

    def fetch_history_by_dates(self, token_id, start_ts, end_ts, fidelity=60):
        """
        Fetches history using absolute start/end timestamps.
        """
        url = f"{self.clob_url}/prices-history"
        params = {
            "market": token_id,
            "startTs": int(start_ts),
            "endTs": int(end_ts),
            "fidelity": fidelity
        }
        try:
            response = requests.get(url, params=params)
            return response.json().get("history", []) if response.status_code == 200 else []
        except Exception as e:
            logger.error(f"History fetch failed: {str(e)}")
            return []


    def fetch_history_by_interval(self, token_id, interval="1w", fidelity=60):
        """
        Fetches raw history from the CLOB pricing endpoint.
        """
        url = f"{self.clob_url}/prices-history"
        params = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity
        }

        try:
            logger.info(f"Requesting history for token {token_id} with interval {interval}")
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Price history API error {response.status_code}")
                return []

            history = response.json().get("history", [])
            logger.info(f"Retrieved {len(history)} data points")
            return history
        except Exception as e:
            logger.error(f"History fetch failed: {str(e)}")
            return []

    def process_to_series(self, history_data, timeframe='1h', use_logs=True, clip=True, lower=0.01, upper=0.99):
        """
        Processes raw data into a series.
        clip: Boolean to enable/disable clipping.
        lower/upper: Bounds for clipping (default 0.01 and 0.99).
        """
        if not history_data:
            return pd.Series(dtype=float)

        df = pd.DataFrame(history_data)
        df['t'] = pd.to_datetime(df['t'], unit='s')
        df.set_index('t', inplace=True)
        df['p'] = df['p'].astype(float)

        series = df['p'].resample(timeframe).last().ffill()

        # Optional Clipping
        if clip:
            series = series.clip(lower=lower, upper=upper)
            logger.info(f"Series clipped to [{lower}, {upper}]")

        # Optional Log Transformation
        if use_logs:
            series = np.log(series)
            logger.info("Applied log transformation to series")

        return series

    def sync_series(self, series_a, series_b):
        """
        Aligns two series to the exact same timestamps using an inner join.
        THROWS A WARNING if the input series are not already perfectly aligned.
        """
        # 1. Pre-Check for Alignment
        if not series_a.index.equals(series_b.index):
            logger.warning("⚠️ Mismatch detected between Series A and Series B timestamps!")
            logger.warning(f"   Series A count: {len(series_a)}")
            logger.warning(f"   Series B count: {len(series_b)}")

            # Calculate how many points don't match
            # "Symmetric Difference" = points in A not in B + points in B not in A
            diff_count = len(series_a.index.symmetric_difference(series_b.index))
            logger.warning(f"   ⚠️ {diff_count} data points will be dropped during synchronization.")

        # 2. Perform the Sync (Inner Join)
        combined = pd.concat([series_a, series_b], axis=1, join='inner')
        combined.columns = ['a', 'b']

        # 3. Final Verification
        if len(combined) == 0:
            logger.error("❌ Critical Error: Synchronization resulted in 0 overlapping points!")
        else:
            logger.info(f"✅ Synchronized series: {len(combined)} overlapping points ready for analysis.")

        return combined['a'], combined['b']



if __name__ == "__main__":
    # Test Condition ID
    CID = "0x7ad403c3508f8e3912940fd1a913f227591145ca0614074208e0b962d5fcc422"
    REAL_CONDITION_ID = "0x258c7094054a85420362f6460980c54c3405d4b553e4b774640d04694902d338"
    # Initialize class
    pm = PolymarketData()

    # Run pipeline
    token, question = pm.get_market_info(CID)
    print(question)
    if token:
        raw = pm.fetch_history_by_interval(token, interval="1d", fidelity=5)
        clean_series = pm.process_to_series(raw, timeframe='5min')

        # Log basic summary instead of printing raw data
        logger.info(f"Series processed with {len(clean_series)} points")
        logger.info(f"Mean price: {clean_series.mean()}")

        volume = pm.get_daily_volume(token)
        print(f"24-Hour Volume: ${volume:,.2f}")
