# -*- coding: utf-8 -*-
"""
Exchange Manager for Multi-Chain Portfolio Tracker
Handles initialization and management of various exchange connections
"""
import ccxt
import base64
import time
import json
import requests
from typing import Optional, Dict, Any, Union
from datetime import datetime

# Import constants and utilities
from config.constants import BACKPACK_API_URL, BACKPACK_WINDOW
from utils.helpers import (
    print_error,
    print_info,
    print_success,
    print_warning,
    safe_float_convert,
    format_currency,
)
from api_clients.okx_client import OkxClient
from api_clients.api_manager import api_key_manager  # Import our new API key manager
from utils.rate_limiter import bybit_retry, backpack_retry

# Try to import PyNaCl for Backpack support
try:
    from nacl.signing import SigningKey
except ImportError:
    SigningKey = None


# Define a type alias for the different client types the manager can hold
ExchangeClientType = Union[ccxt.Exchange, OkxClient, "BackpackClient", None]


class ExchangeManager:
    """Manages connections to various cryptocurrency exchanges"""

    _auth_notice_shown = False

    def __init__(self, api_module, encryption_manager):
        self.api = api_module
        self.encryption_manager = encryption_manager
        self._exchanges: Dict[str, ExchangeClientType] = {}

        # Try to authenticate with API key manager
        self._api_keys_authenticated = False
        try:
            auth_result = api_key_manager.authenticate()
            if auth_result:
                self._api_keys_authenticated = True
                if not ExchangeManager._auth_notice_shown:
                    print_success("✅ API key manager ready")
                    ExchangeManager._auth_notice_shown = True
            else:
                print_warning(
                    "⚠️  API key manager authentication failed - will use fallback methods"
                )
        except Exception as e:
            print_warning(f"⚠️  API key manager not available: {e}")

    def initialize_binance(self) -> Optional[ccxt.Exchange]:
        """Initializes and returns a ccxt Binance exchange instance."""
        try:
            # First try to get API keys from the new API key manager
            if self._api_keys_authenticated:
                credentials = api_key_manager.get_credentials("binance")
                if credentials:
                    api_key = credentials.api_key
                    api_secret = credentials.api_secret
                else:
                    print_warning("No Binance API keys found in secure storage, trying fallback...")
                    fallback_result = self._initialize_binance_fallback()
                    if not fallback_result:
                        print_info(
                            "ℹ To add Binance API keys, use menu option 4: 'Manage API Keys'"
                        )
                    return fallback_result

            # Initialize Binance with the retrieved credentials
            exchange = ccxt.binance(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                }
            )
            exchange.load_markets()
            self._exchanges["binance"] = exchange
            # print_success("✅ Binance connected using stored API keys") # Suppressed for initial validation phase
            return exchange

        except ccxt.AuthenticationError:
            print_error("❌ Binance authentication failed. Check your stored API keys.")
        except ccxt.NetworkError as e:
            print_error(f"❌ Binance network error: {e}")
        except Exception as e:
            print_error(f"❌ Failed to connect to Binance: {e}")
        return None

    def _initialize_binance_fallback(self) -> Optional[ccxt.Exchange]:
        """Fallback method using old encrypted keys from api.py"""
        try:
            if not self.encryption_manager or not hasattr(self.encryption_manager, "decrypt_key"):
                print_warning(
                    "Legacy Binance fallback unavailable: encryption manager not configured"
                )
                return None
            # Ensure encrypted keys are present
            if not hasattr(self.api, "encrypted_sub_api_key") or not hasattr(
                self.api, "encrypted_sub_api_secret"
            ):
                print_warning(
                    "No legacy encrypted Binance keys found in api.py (this is normal when using the new API key manager)"
                )
                return None

            # Try to decrypt keys - this will fail if wrong password is entered
            try:
                decrypted_api_key = self.encryption_manager.decrypt_key(
                    self.api.encrypted_sub_api_key
                )
                decrypted_api_secret = self.encryption_manager.decrypt_key(
                    self.api.encrypted_sub_api_secret
                )
                print_info("Using fallback Binance API keys from api.py")
            except Exception as decrypt_error:
                # This typically indicates wrong encryption password
                if (
                    "InvalidToken" in str(type(decrypt_error))
                    or "decrypt" in str(decrypt_error).lower()
                ):
                    print_error("Failed to decrypt API keys. This usually indicates:")
                    print_error("  • Wrong encryption password entered")
                    print_error("  • Corrupted encrypted keys in api.py")
                else:
                    print_error(f"Error decrypting Binance API keys: {decrypt_error}")
                return None

            exchange = ccxt.binance(
                {
                    "apiKey": decrypted_api_key,
                    "secret": decrypted_api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                }
            )
            exchange.load_markets()
            self._exchanges["binance"] = exchange
            print_success("✅ Binance connected using fallback method")
            return exchange
        except ccxt.AuthenticationError:
            print_error("Binance authentication failed (Sub-account). Check API key/secret.")
        except ccxt.NetworkError as e:
            print_error(f"Binance network error: {e}")
        except Exception as e:
            print_error(f"Failed to connect to Binance (Sub-account): {e}")
        return None

    @bybit_retry
    def initialize_bybit(self) -> Optional[ccxt.Exchange]:
        """Initializes and returns a ccxt Bybit exchange instance."""
        try:
            # First try to get API keys from the new API key manager
            if self._api_keys_authenticated:
                credentials = api_key_manager.get_credentials("bybit")
                if credentials:
                    api_key = credentials.api_key
                    api_secret = credentials.api_secret
                    # Use testnet flag if specified
                    sandbox = credentials.testnet if hasattr(credentials, "testnet") else False
                else:
                    print_warning("No Bybit API keys found in secure storage, trying fallback...")
                    return self._initialize_bybit_fallback()
            else:
                print_warning("API key manager not authenticated, using fallback method...")
                return self._initialize_bybit_fallback()

            # Initialize Bybit with the retrieved credentials
            exchange = ccxt.bybit(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "sandbox": sandbox,
                    "options": {"defaultType": "unified"},
                }
            )
            exchange.load_markets()
            self._exchanges["bybit"] = exchange

            env_info = " (testnet)" if sandbox else " (mainnet)"
            return exchange

        except ccxt.AuthenticationError:
            print_error("❌ Bybit authentication failed. Check your stored API keys.")
        except ccxt.NetworkError as e:
            print_error(f"❌ Bybit network error: {e}")
            raise  # Let the retry decorator handle network errors
        except Exception as e:
            print_error(f"❌ Failed to connect to Bybit: {e}")
            raise  # Let the retry decorator handle other exceptions
        return None

    @bybit_retry
    def _initialize_bybit_fallback(self) -> Optional[ccxt.Exchange]:
        """Fallback method using old keys from api.py"""
        try:
            # Ensure API keys are present in api module
            if not hasattr(self.api, "bybit_api_key") or not hasattr(self.api, "bybit_api_secret"):
                print_error("Bybit API key or secret not found in api.py.")
                return None

            decrypted_api_key = self.api.bybit_api_key  # Assuming plain text in api.py for Bybit
            decrypted_api_secret = self.api.bybit_api_secret
            print_info("Using fallback Bybit API keys from api.py")

            exchange = ccxt.bybit(
                {
                    "apiKey": decrypted_api_key,
                    "secret": decrypted_api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "unified"},
                }
            )
            exchange.load_markets()
            self._exchanges["bybit"] = exchange
            print_success("✅ Bybit connected using fallback method")
            return exchange
        except ccxt.AuthenticationError:
            print_error("Bybit authentication failed. Please check your API key and secret.")
        except ccxt.NetworkError as e:
            print_error(f"Bybit network error: {e}")
            raise  # Let the retry decorator handle network errors
        except Exception as e:
            print_error(f"Failed to connect to Bybit: {e}")
            raise  # Let the retry decorator handle other exceptions
        return None

    def initialize_okx(self) -> Optional[OkxClient]:
        """Initializes and returns an OKX client instance."""
        try:
            # First try to get API keys from the new API key manager
            if self._api_keys_authenticated:
                credentials = api_key_manager.get_credentials("okx")
                if credentials:
                    if not credentials.passphrase:
                        print_error(
                            "❌ OKX requires a passphrase. Please add your OKX credentials with a passphrase."
                        )
                        return None

                    api_key = credentials.api_key
                    api_secret = credentials.api_secret
                    passphrase = credentials.passphrase
                    sandbox_bool = credentials.testnet if hasattr(credentials, "testnet") else False
                    okx_flag = "1" if sandbox_bool else "0"
                else:
                    print_warning("No OKX API keys found in secure storage")
                    return None
            else:
                print_warning("API key manager not authenticated, cannot initialize OKX")
                return None

            # Initialize OKX with the retrieved credentials
            client = OkxClient(api_key, api_secret, passphrase, okx_flag)
            self._exchanges["okx"] = client

            env_info = " (testnet)" if sandbox_bool else " (mainnet)"
            print_success(f"✅ OKX connected using stored API keys{env_info}")
            return client

        except Exception as e:
            print_error(f"❌ Failed to connect to OKX: {e}")
        return None

    def initialize_backpack(self) -> Optional["BackpackClient"]:
        """Initializes and returns a Backpack client instance."""
        try:
            if self._api_keys_authenticated:
                credentials = api_key_manager.get_credentials("backpack")
                if credentials:
                    api_key = credentials.api_key
                    api_secret = credentials.api_secret
                else:
                    print_warning("No Backpack API keys found in secure storage")
                    return None
            else:
                print_warning("API key manager not authenticated, cannot initialize Backpack")
                return None

            # Create a simple module-like object for BackpackClient if needed by its constructor
            class BackpackAPIModule:
                def __init__(self, api_key, api_secret):
                    self.backpack_api_key = api_key
                    self.backpack_api_secret = api_secret

            backpack_api_module = BackpackAPIModule(api_key, api_secret)
            client = BackpackClient(backpack_api_module)
            self._exchanges["backpack"] = client
            print_success("✅ Backpack connected using stored API keys")
            return client
        except Exception as e:
            print_error(f"❌ Failed to initialize Backpack: {e}")
            return None

    def get_exchange(self, name: str) -> ExchangeClientType:
        """Get a cached exchange instance or initialize if not exists."""
        exchange = self._exchanges.get(name.lower())
        if exchange is None:
            # Attempt to initialize on-demand if not already done
            # This can be useful if an exchange wasn't pre-initialized
            print_info(f"Exchange '{name}' not pre-initialized, attempting on-demand setup...")
            if name.lower() == "binance":
                self.initialize_binance()
            elif name.lower() == "bybit":
                self.initialize_bybit()
            elif name.lower() == "okx":
                self.initialize_okx()
            elif name.lower() == "backpack":
                self.initialize_backpack()
            else:
                print_warning(f"Exchange '{name}' is not supported for on-demand initialization.")

            exchange = self._exchanges.get(name.lower())  # Try getting again

        if exchange is None:
            print_warning(f"⚠️ Exchange '{name}' is not available or failed to initialize.")

        return exchange

    def list_available_exchanges(self) -> Dict[str, str]:
        """List all exchanges that can be initialized based on stored API keys."""
        available = {}

        if self._api_keys_authenticated:
            stored_creds = api_key_manager.list_stored_credentials()
            for exchange, info in stored_creds.items():
                available[exchange] = f"{info['exchange_name']} (API keys stored)"

        # Add fallback options
        if hasattr(self.api, "encrypted_sub_api_key"):
            available["binance_fallback"] = "Binance (fallback from api.py)"
        if hasattr(self.api, "bybit_api_key"):
            available["bybit_fallback"] = "Bybit (fallback from api.py)"

        return available

    @bybit_retry
    def get_backpack_balance(self) -> Optional[float]:
        """Get total balance from Backpack exchange."""
        try:
            # Make API call to Backpack to get balance
            url = "https://api.backpack.exchange/api/v1/balance"
            # ... rest of the method remains unchanged ...

        except Exception as e:
            print_error(f"Error fetching Backpack balance: {e}")
            raise  # Let the retry decorator handle exceptions
            return None


class BackpackClient:
    """Client for interacting with Backpack exchange"""

    def __init__(self, api_module):
        self.api = api_module

    def _sign_request(self, api_secret: str, timestamp: int, window: int) -> str:
        """Signs a Backpack API request using ED25519 signing."""
        if SigningKey is None:
            raise ImportError("PyNaCl library is required for Backpack integration")

        priv = base64.b64decode(api_secret)
        sk = SigningKey(priv)
        msg = f"instruction=collateralQuery&timestamp={timestamp}&window={window}".encode()
        sig = sk.sign(msg).signature
        return base64.b64encode(sig).decode()

    def _sign_request_custom(self, api_secret: str, message: str) -> str:
        """Signs a Backpack API request using ED25519 signing with custom message."""
        if SigningKey is None:
            raise ImportError("PyNaCl library is required for Backpack integration")

        priv = base64.b64decode(api_secret)
        sk = SigningKey(priv)
        sig = sk.sign(message.encode()).signature
        return base64.b64encode(sig).decode()

    def get_balance(self) -> Optional[float]:
        """Fetches the total balance from Backpack (Synchronous). Returns None on failure."""
        if SigningKey is None:
            print_error("Backpack support not available: PyNaCl library not installed.")
            return None

        try:
            # Ensure API keys are present in api module
            if not hasattr(self.api, "backpack_api_key") or not hasattr(
                self.api, "backpack_api_secret"
            ):
                print_error("Backpack API key or secret not found in api.py.")
                return None

            ts = int(time.time() * 1000)
            sig = self._sign_request(self.api.backpack_api_secret, ts, BACKPACK_WINDOW)

            headers = {
                "X-API-Key": self.api.backpack_api_key,
                "X-Signature": sig,
                "X-Timestamp": str(ts),
                "X-Window": str(BACKPACK_WINDOW),
                "Content-Type": "application/json",
            }

            response = requests.get(BACKPACK_API_URL, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()

            # Extract balance value (prioritize assetsValue, fallback to netEquity)
            assets_value = data.get("assetsValue", 0.0)
            net_equity = data.get("netEquity", 0.0)
            net_equity_available = data.get("netEquityAvailable", 0.0)

            balance = (
                safe_float_convert(assets_value) if assets_value else safe_float_convert(net_equity)
            )
            if balance is None:
                balance = safe_float_convert(net_equity_available, 0.0)

            print_success(
                f"Backpack balance fetching completed. Balance: {format_currency(balance)}"
            )
            return balance

        except requests.exceptions.HTTPError as e:
            print_error(
                f"HTTP Error fetching Backpack balance: {e.response.status_code} - {e.response.text}"
            )
        except requests.exceptions.RequestException as e:
            is_network = isinstance(
                e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
            )
            print_error(
                f"Network Error fetching Backpack balance: {e}", is_network_issue=is_network
            )
            if is_network:
                raise
        except json.JSONDecodeError as e:
            print_error(f"JSON decode error fetching Backpack balance: {e}")
        except Exception as e:
            print_error(f"Unexpected error fetching Backpack balance: {e}")

        print_warning("Backpack balance fetching failed.")
        return None

    def get_detailed_balance(self) -> Optional[Dict[str, Any]]:
        """Get detailed Backpack balance breakdown by asset using collateral endpoint."""
        try:
            if SigningKey is None:
                print_warning("Backpack support not available: PyNaCl library not installed.")
                return None

            api_key = self.api.backpack_api_key
            api_secret = self.api.backpack_api_secret

            ts = int(time.time() * 1000)

            # Use collateral endpoint (the balances endpoint doesn't exist)
            collateral_msg = f"instruction=collateralQuery&timestamp={ts}&window={BACKPACK_WINDOW}"
            collateral_sig = self._sign_request_custom(api_secret, collateral_msg)

            headers = {
                "X-API-Key": api_key,
                "X-Signature": collateral_sig,
                "X-Timestamp": str(ts),
                "X-Window": str(BACKPACK_WINDOW),
                "Content-Type": "application/json",
            }

            print_info("Fetching Backpack asset breakdown via collateral endpoint...")

            # Use the collateral endpoint which provides individual asset breakdown
            resp = requests.get(BACKPACK_API_URL, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                print_warning("Backpack collateral endpoint returned empty data")
                return None

            # Extract individual asset breakdowns from collateral data
            asset_breakdown = []
            total_equity = safe_float_convert(data.get("assetsValue", 0))

            # Get individual asset breakdowns from collateral array
            collateral_assets = data.get("collateral", [])
            for asset in collateral_assets:
                symbol = asset.get("symbol", "")
                total_quantity = safe_float_convert(asset.get("totalQuantity", 0))
                available_quantity = safe_float_convert(asset.get("availableQuantity", 0))
                lend_quantity = safe_float_convert(asset.get("lendQuantity", 0))
                balance_notional = safe_float_convert(asset.get("balanceNotional", 0))  # USD value

                if total_quantity > 0.000001:  # Only show assets with meaningful value
                    asset_breakdown.append(
                        {
                            "coin": symbol,
                            "total": total_quantity,
                            "available": available_quantity,
                            "locked": lend_quantity,  # lendQuantity represents locked/staked amount
                            "usd_value": balance_notional,
                        }
                    )

            print_success(
                f"Backpack detailed balance: Found {len(asset_breakdown)} assets, total: ${total_equity:.2f}"
            )

            return {
                "total_equity": total_equity,
                "assets": sorted(asset_breakdown, key=lambda x: x["usd_value"], reverse=True),
            }

        except requests.exceptions.HTTPError as e:
            print_error(
                f"HTTP Error fetching Backpack collateral data: {e.response.status_code} - {e.response.text}"
            )
            return None
        except Exception as e:
            print_error(f"Error fetching Backpack detailed balance: {e}")
            return None


# Global functions for backward compatibility
def sign_backpack_request(api_secret: str, timestamp: int, window: int) -> str:
    """Signs a Backpack API request using ED25519 signing."""
    if SigningKey is None:
        raise ImportError("PyNaCl library is required for Backpack integration")

    priv = base64.b64decode(api_secret)
    sk = SigningKey(priv)
    msg = f"instruction=collateralQuery&timestamp={timestamp}&window={window}".encode()
    sig = sk.sign(msg).signature
    return base64.b64encode(sig).decode()


def sign_backpack_request_custom(api_secret: str, message: str) -> str:
    """Signs a Backpack API request using ED25519 signing with custom message."""
    if SigningKey is None:
        raise ImportError("PyNaCl library is required for Backpack integration")

    priv = base64.b64decode(api_secret)
    sk = SigningKey(priv)
    sig = sk.sign(message.encode()).signature
    return base64.b64encode(sig).decode()


@backpack_retry
def get_backpack_balance() -> Optional[float]:
    """Global function for backward compatibility."""
    # Get Backpack credentials from API key manager
    if not api_key_manager.authenticate():
        print_warning("API key manager authentication failed")
        return None

    credentials = api_key_manager.get_credentials("backpack")
    if not credentials:
        print_warning("Backpack API credentials not found")
        return None

    # Create a temporary API module-like object for BackpackClient
    class BackpackAPIModule:
        def __init__(self, api_key, api_secret):
            self.backpack_api_key = api_key
            self.backpack_api_secret = api_secret

    temp_api = BackpackAPIModule(credentials.api_key, credentials.api_secret)
    client = BackpackClient(temp_api)
    return client.get_balance()


@backpack_retry
def get_backpack_detailed_balance() -> Optional[Dict[str, Any]]:
    """Global function for backward compatibility."""
    # Get Backpack credentials from API key manager
    if not api_key_manager.authenticate():
        print_warning("API key manager authentication failed")
        return None

    credentials = api_key_manager.get_credentials("backpack")
    if not credentials:
        print_warning("Backpack API credentials not found")
        return None

    # Create a temporary API module-like object for BackpackClient
    class BackpackAPIModule:
        def __init__(self, api_key, api_secret):
            self.backpack_api_key = api_key
            self.backpack_api_secret = api_secret

    temp_api = BackpackAPIModule(credentials.api_key, credentials.api_secret)
    client = BackpackClient(temp_api)
    return client.get_detailed_balance()
