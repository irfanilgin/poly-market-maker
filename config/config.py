import json
import logging
import os
from dotenv import load_dotenv


class Config:
    def __init__(self, config_path="config/config.json", env_path="config.env"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_path = config_path
        self._config = self._load_config()
        
        # Load environment variables
        # Prioritize config.env if specified, otherwise rely on default dotenv behavior (searching .env)
        # If the file doesn't exist, load_dotenv is silent by default.
        if os.path.exists(env_path):
             self.logger.info(f"Loading environment variables from {env_path}")
             load_dotenv(dotenv_path=env_path)
        else:
             self.logger.info("Loading environment variables from .env")
             load_dotenv()

    def _load_config(self):
        try:
            if not os.path.exists(self.config_path):
                # Try relative to the package if not found in cwd
                # Assuming the script runs from root, config/config.json is correct.
                self.logger.warning(f"Config file not found at {self.config_path}")
                return {}
            
            with open(self.config_path, "r") as f:
                config_data = json.load(f)
                self.logger.info(f"Loaded config from {self.config_path}")
                return config_data
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {}

    def get_clob_credentials(self):
        return self._config.get("clob_client", {}).get("credentials", {})

    @property
    def api_key(self):
        # Priority 1: Environment Variable
        env_val = os.getenv("CLOB_API_KEY")
        if env_val:
            return env_val
        # Priority 2: JSON Config
        return self.get_clob_credentials().get("api_key")

    @property
    def api_secret(self):
        env_val = os.getenv("CLOB_API_SECRET")
        if env_val:
            return env_val
        return self.get_clob_credentials().get("api_secret")

    @property
    def api_passphrase(self):
        env_val = os.getenv("CLOB_API_PASSPHRASE")
        if env_val:
            return env_val
        return self.get_clob_credentials().get("api_passphrase")

    def __repr__(self):
        """Safe string representation masking sensitive fields."""
        return (
            f"Config(path={self.config_path}, "
            f"api_key={self.api_key}, "
            f"api_secret=***, "
            f"api_passphrase=***)"
        )

