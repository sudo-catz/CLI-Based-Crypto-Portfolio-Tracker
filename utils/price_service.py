"""
Exchange-Based Price Service (Real-Time, No Cache)
------------------------------------------------
Centralized price fetching service that uses exchange APIs directly
for real-time cryptocurrency prices with maximum accuracy.

Primary sources (in order of priority):
1. Binance API via ccxt (highest liquidity, most reliable)
2. OKX API via ccxt (secondary source)
3. Bybit API via ccxt (tertiary source)

Features:
- Direct exchange API integration for maximum reliability
- Smart fallback between multiple exchanges
- Always fresh, real-time price data from actual trading venues
- No caching - guaranteed accurate prices for every request
- Better rate limits compared to aggregator APIs
"""

import asyncio
import time
import ccxt
from typing import Dict, List, Optional, Any, Tuple, Callable
from threading import Lock
from functools import lru_cache, partial
from collections import defaultdict
from inspect import signature
from cachetools import TTLCache
import aiohttp  # For CoinGecko API calls

# import async_timeout # Can be commented out if ClientTimeout is used exclusively

# Import CoinMarketCap library
try:
    from coinmarketcapapi import CoinMarketCapAPI, CoinMarketCapAPIError
except ImportError:
    CoinMarketCapAPI = None  # Allow graceful failure if not installed
    CoinMarketCapAPIError = None
    print(
        "WARNING: CoinMarketCap library not found. Please install with 'pip install python-coinmarketcap'"
    )

from config.constants import (
    SUPPORTED_EXCHANGES_FOR_PRICES,
    COINGECKO_COIN_LIST_URL,
    COINMARKETCAP_API_KEY,  # Added for CMC
)
from utils.helpers import print_info, print_warning, print_error
from utils.rate_limiter import binance_retry, okx_retry, bybit_retry


class ExchangePriceService:
    """Exchange-based price service with multi-exchange fallback - always fresh data."""

    def __init__(self):
        # Exchange initialization flags
        self._binance_exchange = None
        self._okx_exchange = None
        self._bybit_exchange = None
        self._exchanges_initialized = False

        # Supported cryptocurrencies with their trading pairs
        self._supported_pairs = {
            "BTC": ["BTC/USDT", "BTC/USDC"],
            "ETH": ["ETH/USDT", "ETH/USDC"],
            "SOL": ["SOL/USDT", "SOL/USDC"],
            "APT": ["APT/USDT", "APT/USDC"],
            "NEAR": ["NEAR/USDT", "NEAR/USDC"],
            "USDC": ["USDC/USDT"],  # For cross-reference
            "USDT": [],  # Stablecoin (always $1.00)
        }

        # Stablecoin definitions
        self._stablecoins = {"USDT": 1.0, "USDC": 1.0, "DAI": 1.0, "BUSD": 1.0}

        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.cache = TTLCache(maxsize=100, ttl=300)  # General cache for things like names

        # CoinGecko specific cache
        self._coingecko_coin_list_cache = TTLCache(maxsize=1, ttl=24 * 60 * 60)
        self._coingecko_coin_list_lock = asyncio.Lock()

        # CoinMarketCap specific cache & client
        self._cmc_client = None
        self._exchange_known_pairs = defaultdict(set)
        self._exchange_supports_partial_markets: Dict[str, bool] = {}
        if (
            CoinMarketCapAPI
            and COINMARKETCAP_API_KEY
            and COINMARKETCAP_API_KEY != "YOUR_API_KEY_HERE"
        ):
            try:
                self._cmc_client = CoinMarketCapAPI(COINMARKETCAP_API_KEY)
            except Exception as e:
                print_error(f"Failed to initialize CoinMarketCapAPI client: {e}")
                self._cmc_client = None
        elif not CoinMarketCapAPI:
            print(
                "WARNING: CoinMarketCap library not installed. Name fetching from CMC will be skipped."
            )
        elif not COINMARKETCAP_API_KEY or COINMARKETCAP_API_KEY == "YOUR_API_KEY_HERE":
            print(
                "WARNING: CoinMarketCap API key not configured. Name fetching from CMC will be skipped."
            )

        self._cmc_metadata_cache = TTLCache(maxsize=50, ttl=24 * 60 * 60)  # Cache CMC names for 24h
        self._cmc_metadata_lock = asyncio.Lock()

        self._init_exchanges()

    def _init_exchanges(self):
        """Initialize exchange connections with proper error handling."""
        if self._exchanges_initialized:
            return

        try:
            # Initialize Binance
            try:
                self._binance_exchange = ccxt.binance(
                    {
                        "sandbox": False,
                        "rateLimit": 1200,
                        "enableRateLimit": True,
                        "timeout": 5000,
                    }
                )
            except Exception as e:
                print_warning(f"⚠️ Binance initialization failed: {e}")

            # Initialize OKX
            try:
                self._okx_exchange = ccxt.okx(
                    {
                        "sandbox": False,
                        "rateLimit": 2000,
                        "enableRateLimit": True,
                        "timeout": 5000,
                    }
                )
            except Exception as e:
                print_warning(f"⚠️ OKX initialization failed: {e}")

            # Initialize Bybit
            try:
                self._bybit_exchange = ccxt.bybit(
                    {
                        "sandbox": False,
                        "rateLimit": 1000,
                        "enableRateLimit": True,
                        "timeout": 5000,
                    }
                )
            except Exception as e:
                print_warning(f"⚠️ Bybit initialization failed: {e}")

            self._exchanges_initialized = True
            print_info("🔄 Exchange connections initialized for real-time pricing")

        except Exception as e:
            print_error(f"❌ Critical error initializing exchanges: {e}")

    @binance_retry
    def _fetch_binance_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from Binance exchange."""
        try:
            if not self._binance_exchange:
                return None

            # Get predefined pairs or generate common trading pairs for custom coins
            pairs = self._supported_pairs.get(symbol.upper(), [])
            if not pairs:
                # Auto-generate common trading pairs for custom coins
                pairs = [
                    f"{symbol.upper()}/USDT",
                    f"{symbol.upper()}/USDC",
                    f"{symbol.upper()}/BTC",
                ]

            for pair in pairs:
                try:
                    ticker = self._binance_exchange.fetch_ticker(pair)
                    if ticker and ticker.get("last") and ticker["last"] > 0:
                        price = float(ticker["last"])
                        print_info(f"💰 Binance {symbol}: ${price:.4f} (real-time)")
                        return price
                except Exception as e:
                    # Silent fail for auto-generated pairs, but log predefined ones
                    if symbol.upper() in self._supported_pairs:
                        print_warning(f"⚠️ Binance {pair} failed: {e}")
                    continue

            return None

        except Exception as e:
            print_warning(f"⚠️ Binance connection error for {symbol}: {e}")
            return None

    @okx_retry
    def _fetch_okx_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from OKX exchange."""
        try:
            if not self._okx_exchange:
                return None

            # Get predefined pairs or generate common trading pairs for custom coins
            pairs = self._supported_pairs.get(symbol.upper(), [])
            if not pairs:
                # Auto-generate common trading pairs for custom coins
                pairs = [
                    f"{symbol.upper()}/USDT",
                    f"{symbol.upper()}/USDC",
                    f"{symbol.upper()}/BTC",
                ]

            for pair in pairs:
                try:
                    ticker = self._okx_exchange.fetch_ticker(pair)
                    if ticker and ticker.get("last") and ticker["last"] > 0:
                        price = float(ticker["last"])
                        print_info(f"💰 OKX {symbol}: ${price:.4f} (real-time)")
                        return price
                except Exception as e:
                    # Silent fail for auto-generated pairs, but log predefined ones
                    if symbol.upper() in self._supported_pairs:
                        print_warning(f"⚠️ OKX {pair} failed: {e}")
                    continue

            return None
        except Exception as e:
            print_warning(f"⚠️ OKX connection error for {symbol}: {e}")
            return None

    @bybit_retry
    def _fetch_bybit_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time price from Bybit exchange."""
        try:
            if not self._bybit_exchange:
                return None

            # Get predefined pairs or generate common trading pairs for custom coins
            pairs = self._supported_pairs.get(symbol.upper(), [])
            if not pairs:
                # Auto-generate common trading pairs for custom coins
                pairs = [
                    f"{symbol.upper()}/USDT",
                    f"{symbol.upper()}/USDC",
                    f"{symbol.upper()}/BTC",
                ]

            for pair in pairs:
                try:
                    ticker = self._bybit_exchange.fetch_ticker(pair)
                    if ticker and ticker.get("last") and ticker["last"] > 0:
                        price = float(ticker["last"])
                        print_info(f"💰 Bybit {symbol}: ${price:.4f} (real-time)")
                        return price
                except Exception as e:
                    # Silent fail for auto-generated pairs, but log predefined ones
                    if symbol.upper() in self._supported_pairs:
                        print_warning(f"⚠️ Bybit {pair} failed: {e}")
                    continue

            return None

        except Exception as e:
            print_warning(f"⚠️ Bybit connection error for {symbol}: {e}")
            return None

    # Synchronous helper for the synchronous get_price method
    def _get_sync_price_from_exchange(
        self, symbol: str, exchange_name: str, exchange_instance
    ) -> Optional[float]:
        if not exchange_instance:
            return None

        exchange_key = exchange_name.lower()
        pairs = self._supported_pairs.get(symbol.upper(), [])
        if not pairs:
            pairs = [f"{symbol.upper()}/USDT", f"{symbol.upper()}/USDC", f"{symbol.upper()}/BTC"]

        # Load only the trading pairs we care about to avoid pulling full market catalogs.
        known_pairs = self._exchange_known_pairs[exchange_key]
        markets = getattr(exchange_instance, "markets", {}) or {}
        missing_pairs = [
            pair
            for pair in pairs
            if pair not in known_pairs and pair not in markets
        ]

        if missing_pairs:
            supports_partial = self._exchange_supports_partial_markets.get(exchange_key)
            if supports_partial is None:
                try:
                    sig = signature(exchange_instance.load_markets)
                    supports_partial = "symbols" in sig.parameters
                except (TypeError, ValueError):
                    supports_partial = False
                self._exchange_supports_partial_markets[exchange_key] = bool(supports_partial)

            if supports_partial:
                try:
                    exchange_instance.load_markets(symbols=missing_pairs, reload=False)
                    known_pairs.update(missing_pairs)
                    print_info(
                        f"⚡ Quick warm-up for {exchange_name}: {', '.join(missing_pairs)}"
                    )
                except ccxt.NotSupported:
                    # Some exchanges ignore partial market loading; fall back to lazy loading.
                    known_pairs.update(missing_pairs)
                    self._exchange_supports_partial_markets[exchange_key] = False
                except TypeError:
                    # Signalled at runtime that partial symbols are unsupported.
                    self._exchange_supports_partial_markets[exchange_key] = False
                    known_pairs.update(missing_pairs)
                except Exception as e:
                    print_warning(
                        f"⚠️ {exchange_name} quick warm-up for {', '.join(missing_pairs)} failed: {e}"
                    )
            else:
                # No partial support; rely on lazy loading via fetch_ticker to avoid heavy init.
                known_pairs.update(missing_pairs)

        for pair in pairs:
            try:
                # This is a synchronous call
                ticker = exchange_instance.fetch_ticker(pair)
                if ticker and ticker.get("last") is not None:
                    price = float(ticker["last"])
                    if price > 0:
                        # print_info(f"💰 {exchange_name} {symbol}: ${price:.4f} (real-time via sync helper)")
                        return price
            except Exception:
                # Silent fail for auto-generated pairs
                continue  # Try next pair
        return None

    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for a cryptocurrency symbol from exchanges (always fresh)."""
        if symbol.upper() in self._stablecoins:
            return 1.0
        self._init_exchanges()

        # Order of preference for synchronous fetching
        exchanges_to_try = [
            ("Binance", self._binance_exchange),
            ("OKX", self._okx_exchange),
            ("Bybit", self._bybit_exchange),
        ]

        for name, instance in exchanges_to_try:
            if instance:  # Ensure instance is initialized
                price = self._get_sync_price_from_exchange(
                    symbol, name, instance
                )  # Call the synchronous helper
                if price is not None:
                    return price

        # print_warning(f"❌ Failed to fetch {symbol} price from all exchanges (sync path)")
        return 0.0  # Consistent with existing logic for failed fetches

    def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get real-time prices for multiple cryptocurrencies using exchange APIs.
        Returns a dictionary with symbol -> price mapping.
        Failed fetches return 0.0 to prevent format string errors.
        """
        prices = {}
        for symbol in symbols:
            price = self.get_price(symbol)
            prices[symbol] = price if price is not None else 0.0  # Ensure no None values
        return prices

    async def get_price_async(self, symbol: str) -> Optional[float]:
        """Async version of get_price - always real-time."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_price, symbol)

    async def get_prices_async(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        prices: Dict[str, Optional[float]] = {}
        tasks = []

        # Inner async function to fetch price for a single symbol to be used with asyncio.gather
        async def fetch_single_symbol_price_task(
            symbol_to_fetch: str,
        ) -> Tuple[str, Optional[float]]:
            if symbol_to_fetch.upper() in self._stablecoins:
                return symbol_to_fetch, 1.0

            # Determine trading pairs
            current_symbol_pairs = self._supported_pairs.get(symbol_to_fetch.upper(), [])
            if not current_symbol_pairs:
                current_symbol_pairs = [
                    f"{symbol_to_fetch.upper()}/USDT",
                    f"{symbol_to_fetch.upper()}/USDC",
                    f"{symbol_to_fetch.upper()}/BTC",
                ]

            # Try fetching from exchanges in order
            for exchange_id_to_try in SUPPORTED_EXCHANGES_FOR_PRICES:
                price = await self._get_price_from_exchange(
                    exchange_id_to_try, symbol_to_fetch, current_symbol_pairs
                )
                if price is not None:
                    return symbol_to_fetch, price
            return (
                symbol_to_fetch,
                0.0,
            )  # Return 0.0 for failed fetches, consistent with sync version

        for s_global in symbols:
            tasks.append(fetch_single_symbol_price_task(s_global))

        results = await asyncio.gather(*tasks)
        for symbol_result, price_result in results:
            prices[symbol_result] = price_result
        return prices

    def get_service_stats(self) -> Dict[str, Any]:
        """Return basic stats about the service and initialized exchanges."""
        return {
            "exchanges_initialized": self._exchanges_initialized,
            "binance_initialized": self._binance_exchange is not None,
            "okx_initialized": self._okx_exchange is not None,
            "bybit_initialized": self._bybit_exchange is not None,
            "supported_symbols_count": len(self._supported_pairs),
        }

    def close_exchanges(self):
        """
        Clean up exchange connections if necessary.
        For standard synchronous ccxt exchanges, explicit close is usually not required.
        This method is retained for compatibility or future ccxt.pro usage.
        """
        # Standard ccxt synchronous instances do not have a .close() method that
        # needs to be called for HTTP connection pooling. It's managed internally or by underlying libs.
        # print_info("Attempting to close exchange connections if applicable...")
        # try:
        #     if self._binance_exchange and hasattr(self._binance_exchange, 'close'):
        #         # await self._binance_exchange.close() # If it were async
        #         self._binance_exchange.close()
        #     if self._okx_exchange and hasattr(self._okx_exchange, 'close'):
        #         # await self._okx_exchange.close()
        #         self._okx_exchange.close()
        #     if self._bybit_exchange and hasattr(self._bybit_exchange, 'close'):
        #         # await self._bybit_exchange.close()
        #         self._bybit_exchange.close()
        #     print_info("Exchange connections closed/checked.")
        # except Exception as e:
        #     print_warning(f"⚠ Error closing exchanges: {e}")
        print_info(
            "Exchange cleanup check: Standard ccxt instances manage connections automatically."
        )

    def _get_exchange_instance(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        """Helper to get an initialized exchange instance by id."""
        # This method needs to be implemented based on how exchanges are stored.
        # Assuming they are stored in self.exchanges as added by the previous diff for get_coin_full_name
        # or from the direct attributes like self._binance_exchange if that's the pattern.
        # For consistency with get_coin_full_name, let's assume self.exchanges is populated by _init_exchanges
        if exchange_id.lower() == "binance":
            return self._binance_exchange
        elif exchange_id.lower() == "okx":
            return self._okx_exchange
        elif exchange_id.lower() == "bybit":
            return self._bybit_exchange
        # Add other exchanges if self.exchanges dict is not the primary way.
        return self.exchanges.get(exchange_id.lower())

    async def _fetch_coingecko_coin_list(self) -> List[Dict[str, str]]:
        """Fetches the full list of coins from CoinGecko and caches it."""
        cached_list = self._coingecko_coin_list_cache.get("coin_list")
        if cached_list is not None:
            return cached_list

        async with self._coingecko_coin_list_lock:
            cached_list = self._coingecko_coin_list_cache.get("coin_list")  # Re-check after lock
            if cached_list is not None:
                return cached_list

            print_info("Fetching full coin list from CoinGecko...")
            coin_list_data = []
            try:
                # Using aiohttp.ClientTimeout for request timeout
                timeout_settings = aiohttp.ClientTimeout(
                    total=10
                )  # 10 seconds total timeout for the request
                async with aiohttp.ClientSession(timeout=timeout_settings) as session:
                    async with session.get(COINGECKO_COIN_LIST_URL) as response:
                        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
                        data = await response.json()
                        if isinstance(data, list):
                            coin_list_data = data
                        else:
                            print_warning("CoinGecko coin list response was not a list.")

                if coin_list_data:
                    self._coingecko_coin_list_cache["coin_list"] = coin_list_data
                    print_info(
                        f"Successfully fetched and cached {len(coin_list_data)} coins from CoinGecko."
                    )
                    return coin_list_data
                else:
                    return []  # Return empty list if no data or bad data, error already printed

            except asyncio.TimeoutError:  # This can be raised by aiohttp.ClientTimeout
                print_warning("Timeout fetching CoinGecko coin list.")
                return []
            except aiohttp.ClientResponseError as e:  # More specific exception for HTTP errors
                print_warning(
                    f"aiohttp HTTP error fetching CoinGecko coin list: {e.status} {e.message}"
                )
                return []
            except aiohttp.ClientError as e:  # General aiohttp client error
                print_warning(f"aiohttp client error fetching CoinGecko coin list: {e}")
                return []
            except Exception as e:
                print_error(f"Unexpected error fetching CoinGecko coin list: {e}")
                return []
        # Fallback, should ideally not be reached due to lock logic
        return []

    async def _fetch_name_from_coinmarketcap(self, symbol: str) -> Optional[str]:
        """Fetches the full name of a coin from CoinMarketCap using its symbol."""
        if not self._cmc_client:
            return None  # Client not initialized or library not found

        target_symbol_upper = symbol.upper()
        cached_name = self._cmc_metadata_cache.get(target_symbol_upper)
        if cached_name is not None:
            return cached_name if cached_name else None  # Return None if failure was cached

        async with self._cmc_metadata_lock:
            # Re-check cache after acquiring lock
            cached_name = self._cmc_metadata_cache.get(target_symbol_upper)
            if cached_name is not None:
                return cached_name if cached_name else None

            print_info(f"Fetching metadata for {target_symbol_upper} from CoinMarketCap...")
            loop = asyncio.get_event_loop()
            try:
                # Use functools.partial to pass keyword arguments to the function in executor
                cmc_info_func = partial(
                    self._cmc_client.cryptocurrency_info, symbol=target_symbol_upper
                )
                response = await loop.run_in_executor(None, cmc_info_func)

                if response and response.data and target_symbol_upper in response.data:
                    coin_data = response.data[target_symbol_upper]
                    if isinstance(coin_data, list):
                        if not coin_data:
                            print_warning(
                                f"CoinMarketCap returned empty list for {target_symbol_upper} in data object."
                            )
                            self._cmc_metadata_cache[target_symbol_upper] = None
                            return None
                        coin_data = coin_data[0]

                    name = coin_data.get("name")
                    if name:
                        print_info(f"Name for {target_symbol_upper} from CoinMarketCap: {name}")
                        self._cmc_metadata_cache[target_symbol_upper] = name
                        return name
                    else:
                        print_warning(
                            f"Symbol {target_symbol_upper} found in CoinMarketCap but 'name' attribute missing. Data: {coin_data}"
                        )
                        self._cmc_metadata_cache[target_symbol_upper] = None
                        return None
                else:
                    # Safely access status and error_message
                    status_msg = "Unknown error or no data."
                    if response and response.status:
                        status_msg = (
                            response.status.error_message
                            if response.status.error_message
                            else f"Error code: {response.status.error_code}"
                        )
                    elif response is None:
                        status_msg = "Response object was None (possibly executor failure)."

                    print_warning(
                        f"Symbol {target_symbol_upper} not found in CoinMarketCap response or empty data. Message: {status_msg}"
                    )
                    self._cmc_metadata_cache[target_symbol_upper] = None
                    return None
            except CoinMarketCapAPIError as e:
                print_error(f"CoinMarketCap API error for {target_symbol_upper}: {e}")
                self._cmc_metadata_cache[target_symbol_upper] = None
                return None
            except Exception as e:
                print_error(
                    f"Unexpected error fetching name for {target_symbol_upper} from CoinMarketCap: {e}"
                )
                self._cmc_metadata_cache[target_symbol_upper] = None
                return None
        return None  # Should be covered by lock re-check or try/except

    async def get_coin_full_name(self, symbol: str) -> Optional[str]:
        target_symbol_upper = symbol.upper()
        # Use the general self.cache for the final chosen name
        cache_key = f"name_{target_symbol_upper}"

        cached_name_val = self.cache.get(cache_key)
        if cached_name_val is not None:
            return cached_name_val

        # Attempt 1: Fetch from CoinMarketCap
        if self._cmc_client:
            name_from_cmc = await self._fetch_name_from_coinmarketcap(target_symbol_upper)
            if name_from_cmc:
                self.cache[cache_key] = name_from_cmc
                return name_from_cmc
            # If CMC fails (returns None), we'll fall through to CoinGecko.
            # A warning/error would have been printed by _fetch_name_from_coinmarketcap

        print_info(
            f"Name for {target_symbol_upper} not found on CoinMarketCap or CMC unavailable, trying CoinGecko..."
        )

        # Attempt 2: Fetch from CoinGecko (existing logic)
        coin_list = await self._fetch_coingecko_coin_list()
        if not coin_list:
            print_warning(
                f"CoinGecko coin list is empty. Cannot fetch name for {target_symbol_upper}."
            )
            self.cache[cache_key] = None
            return None

        target_symbol_lower = symbol.lower()
        symbol_matches = [
            ci for ci in coin_list if ci.get("symbol", "").lower() == target_symbol_lower
        ]

        if not symbol_matches:
            print_warning(f"No symbol match for {target_symbol_upper} in CoinGecko list.")
            self.cache[cache_key] = None
            return None

        chosen_name_cg: Optional[str] = None

        # Priority 1 (CoinGecko): Exact ID match
        for coin_info in symbol_matches:
            cg_id_lower = coin_info.get("id", "").lower()
            if cg_id_lower == target_symbol_lower:
                name_candidate = coin_info.get("name")
                if name_candidate:
                    chosen_name_cg = name_candidate
                    print_info(
                        f"Name for {target_symbol_upper} (from CoinGecko ID match {cg_id_lower}): {chosen_name_cg}"
                    )
                    break

        if chosen_name_cg:
            self.cache[cache_key] = chosen_name_cg
            return chosen_name_cg

        # Priority 2 (CoinGecko): Clean Name with preferred ID structure
        clean_named_matches = []
        for coin_info in symbol_matches:
            name = coin_info.get("name")
            if name and not any(
                indicator.lower() in name.lower()
                for indicator in [
                    "-Peg",
                    "Pegged",
                    "Wrapped",
                    "Bridged",
                    "(Wormhole)",
                    " on ",
                    " Token",
                    " Finance",
                ]
            ):
                cg_id_lower = coin_info.get("id", "").lower()
                if (
                    cg_id_lower == target_symbol_lower
                    or f"{target_symbol_lower}-inu" == cg_id_lower
                    or f"{target_symbol_lower}coin" == cg_id_lower
                    or target_symbol_lower in cg_id_lower.split("-")
                ):
                    clean_named_matches.insert(0, name)
                else:
                    clean_named_matches.append(name)

        if clean_named_matches:
            chosen_name_cg = clean_named_matches[0]
        elif symbol_matches:
            first_match_name = symbol_matches[0].get("name")
            if first_match_name:
                chosen_name_cg = first_match_name
            else:
                for sm in symbol_matches:
                    if sm.get("name"):
                        chosen_name_cg = sm.get("name")
                        break

        if chosen_name_cg:
            print_info(
                f"Name for {target_symbol_upper} (from CoinGecko heuristic, {len(symbol_matches)} matches): {chosen_name_cg}"
            )
            self.cache[cache_key] = chosen_name_cg
            return chosen_name_cg
        else:
            print_warning(
                f"Could not determine a suitable name for {target_symbol_upper} from CoinGecko."
            )
            self.cache[cache_key] = None
            return None

    async def _fetch_price_from_single_exchange(
        self, exchange_id: str, symbol_pair: str
    ) -> Optional[float]:
        exchange = self._get_exchange_instance(exchange_id)
        if not exchange:
            return None
        loop = asyncio.get_event_loop()
        try:
            # Important: exchange.fetch_ticker is a synchronous (blocking) call
            ticker = await loop.run_in_executor(None, exchange.fetch_ticker, symbol_pair)
            if ticker and isinstance(ticker.get("last"), (int, float)):
                price = float(ticker["last"])
                if price > 0:
                    return price
        except Exception as e:
            # print_warning(f"Error fetching {symbol_pair} from {exchange_id}: {e}")
            pass
        return None

    async def _get_price_from_exchange(
        self, exchange_id: str, symbol: str, trading_pairs: List[str]
    ) -> Optional[float]:
        # This is the ASYNC helper called by get_prices_async
        for pair in trading_pairs:
            price = await self._fetch_price_from_single_exchange(exchange_id, pair)
            if price is not None:
                return price
        return None


# Global instance - always real-time, no cache
# price_service = ExchangePriceService() # Commented out to prevent double initialization


# Convenience functions for backward compatibility
def get_crypto_price(symbol: str) -> Optional[float]:
    """Get real-time crypto price (convenience function)"""
    # This would need to be re-evaluated if price_service is removed.
    # For now, assuming it might be used by other modules directly,
    # but it will raise NameError if price_service is not defined.
    # A better approach would be to have a single global service from enhanced_price_service
    # or a getter function.
    # For now, to fix the double init, we comment the instance,
    # usages like this might break if not updated to use enhanced_price_service
    global price_service  # Declare intent to use the (now potentially undefined) global
    if "price_service" not in globals():
        # Fallback or error if the main app hasn't replaced this usage
        # This is a temporary guard. Ideally, direct usage of this old instance should be refactored.
        print_error(
            "Fallback get_crypto_price: price_service global not found, re-instantiating ExchangePriceService. Refactor needed."
        )
        price_service = ExchangePriceService()  # Temporary self-correction, still prints init msg.
    return price_service.get_price(symbol)


async def get_crypto_price_async(symbol: str) -> Optional[float]:
    """Get real-time crypto price async (convenience function)"""
    global price_service
    if "price_service" not in globals():
        print_error(
            "Fallback get_crypto_price_async: price_service global not found, re-instantiating ExchangePriceService. Refactor needed."
        )
        price_service = ExchangePriceService()
    return await price_service.get_price_async(symbol)


def get_multiple_crypto_prices(symbols: List[str]) -> Dict[str, float]:
    """Wrapper to get multiple crypto prices using the global service instance."""
    global price_service
    if "price_service" not in globals():
        print_error(
            "Fallback get_multiple_crypto_prices: price_service global not found, re-instantiating ExchangePriceService. Refactor needed."
        )
        price_service = ExchangePriceService()
    return price_service.get_prices(
        symbols
    )  # Assumes get_prices returns Dict[str, float] with 0.0 for errors


async def get_multiple_crypto_prices_async(
    symbols: List[str],
) -> Dict[str, Optional[float]]:  # Corrected return type
    """Async wrapper to get multiple crypto prices using the global service instance."""
    global price_service
    if "price_service" not in globals():
        print_error(
            "Fallback get_multiple_crypto_prices_async: price_service global not found, re-instantiating ExchangePriceService. Refactor needed."
        )
        price_service = ExchangePriceService()
    return await price_service.get_prices_async(symbols)


# price_service = ExchangePriceService() # Original instantiation commented out

# Ensure it's instantiated once. If it's already at the end after the functions, that's fine.
