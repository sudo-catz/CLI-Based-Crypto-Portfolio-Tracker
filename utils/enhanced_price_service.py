# -*- coding: utf-8 -*-
"""
Enhanced Price Service with Custom Cryptocurrency Support
---------------------------------------------------------
Extended price service that supports fetching prices for custom cryptocurrencies
using multiple sources: CoinGecko API, Exchange APIs, and fallback methods.
"""

import asyncio
import time
import requests
import ccxt
from typing import Dict, List, Optional, Union
from threading import Lock

from utils.helpers import print_info, print_warning, print_error
from utils.rate_limiter import binance_retry, okx_retry, bybit_retry
from utils.price_service import ExchangePriceService


class EnhancedPriceService(ExchangePriceService):
    """Enhanced price service with custom cryptocurrency support."""

    def __init__(self):
        super().__init__()

        # CoinGecko API configuration
        self._coingecko_base_url = "https://api.coingecko.com/api/v3"
        self._coingecko_rate_limit = 50  # requests per minute for free tier
        self._last_coingecko_request = 0
        # Reduced from 60/50=1.2s to 60/60=1.0s for faster testing while staying within limits
        self._coingecko_min_interval = 1.0

        # Extended CoinGecko ID mappings for popular altcoins
        self._coingecko_mappings = {
            # Major coins (already in base service)
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "APT": "aptos",
            "NEAR": "near",
            "BNB": "binancecoin",
            # Popular altcoins
            "PEPE": "pepe",
            "SHIB": "shiba-inu",
            "DOGE": "dogecoin",
            "FLOKI": "floki",
            "BONK": "bonk",
            "WIF": "dogwifcoin",
            "POPCAT": "popcat",
            "MEW": "cat-in-a-dogs-world",
            "BRETT": "brett",
            "TURBO": "turbo",
            "MYRO": "myro",
            "JTO": "jito-governance-token",
            "PYTH": "pyth-network",
            "JUP": "jupiter-exchange-solana",
            "RNDR": "render-token",
            "FET": "fetch-ai",
            "AGIX": "singularitynet",
            "OCEAN": "ocean-protocol",
            "TAO": "bittensor",
            "INJ": "injective-protocol",
            "SEI": "sei-network",
            "TIA": "celestia",
            "STRK": "starknet",
            "OP": "optimism",
            "ARB": "arbitrum",
            "MATIC": "matic-network",
            "AVAX": "avalanche-2",
            "DOT": "polkadot",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "AAVE": "aave",
            "MKR": "maker",
            "CRV": "curve-dao-token",
            "LDO": "lido-dao",
            "COMP": "compound-governance-token",
            "SUSHI": "sushi",
            "GRT": "the-graph",
            "SNX": "havven",
            "ENS": "ethereum-name-service",
            "MANA": "decentraland",
            "SAND": "the-sandbox",
            "AXS": "axie-infinity",
            "GALA": "gala",
            "CHZ": "chiliz",
            "FLOW": "flow",
            "ICP": "internet-computer",
            "FTM": "fantom",
            "LUNA": "terra-luna-2",
            "ADA": "cardano",
            "XRP": "ripple",
            "LTC": "litecoin",
            "BCH": "bitcoin-cash",
            "ETC": "ethereum-classic",
            "XLM": "stellar",
            "VET": "vechain",
            "TRX": "tron",
            "FIL": "filecoin",
            "EOS": "eos",
            "XTZ": "tezos",
            "ALGO": "algorand",
            "THETA": "theta-token",
            "XMR": "monero",
            "DASH": "dash",
            "ZEC": "zcash",
            "ATOM": "cosmos",
        }

    def _respect_coingecko_rate_limit(self):
        """Ensure we respect CoinGecko's rate limits."""
        current_time = time.time()
        time_since_last = current_time - self._last_coingecko_request

        if time_since_last < self._coingecko_min_interval:
            sleep_time = self._coingecko_min_interval - time_since_last
            time.sleep(sleep_time)

        self._last_coingecko_request = time.time()

    def get_coingecko_price(
        self, symbol: str, coingecko_id: Optional[str] = None
    ) -> Optional[float]:
        """
        Fetch price from CoinGecko API.

        Args:
            symbol: Cryptocurrency symbol (e.g., 'PEPE')
            coingecko_id: Optional specific CoinGecko ID, otherwise uses mapping

        Returns:
            Price in USD or None if failed
        """
        try:
            # Determine CoinGecko ID
            if coingecko_id:
                gecko_id = coingecko_id
            else:
                gecko_id = self._coingecko_mappings.get(symbol.upper())

            if not gecko_id:
                print_warning(f"⚠️ No CoinGecko mapping for {symbol}")
                return None

            # Respect rate limits
            self._respect_coingecko_rate_limit()

            # Make API request
            url = f"{self._coingecko_base_url}/simple/price"
            params = {"ids": gecko_id, "vs_currencies": "usd", "include_24hr_change": "false"}

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if gecko_id in data and "usd" in data[gecko_id]:
                price = float(data[gecko_id]["usd"])
                print_info(f"💰 CoinGecko {symbol}: ${price:.6f}")
                return price
            else:
                print_warning(f"⚠️ No price data for {symbol} from CoinGecko")
                return None

        except requests.exceptions.RequestException as e:
            print_warning(f"⚠️ CoinGecko API error for {symbol}: {e}")
            return None
        except (KeyError, ValueError) as e:
            print_warning(f"⚠️ CoinGecko data parsing error for {symbol}: {e}")
            return None
        except Exception as e:
            print_error(f"❌ Unexpected CoinGecko error for {symbol}: {e}")
            return None

    def get_exchange_price_for_custom_pair(
        self, symbol: str, trading_pairs: List[str]
    ) -> Optional[float]:
        """
        Try to fetch price from exchanges using specific trading pairs.

        Args:
            symbol: Cryptocurrency symbol
            trading_pairs: List of trading pairs to try (e.g., ['PEPE/USDT', 'PEPE/USDC'])

        Returns:
            Price in USD or None if failed
        """
        # Ensure exchanges are initialized
        self._init_exchanges()

        # Try each exchange with the provided pairs
        exchanges = [
            ("Binance", self._binance_exchange, self._fetch_binance_custom_price),
            ("OKX", self._okx_exchange, self._fetch_okx_custom_price),
            ("Bybit", self._bybit_exchange, self._fetch_bybit_custom_price),
        ]

        for exchange_name, exchange_instance, fetch_func in exchanges:
            if exchange_instance:
                for pair in trading_pairs:
                    try:
                        price = fetch_func(pair)
                        if price and price > 0:
                            print_info(f"💰 {exchange_name} {symbol}: ${price:.6f} (via {pair})")
                            return price
                    except Exception as e:
                        print_warning(f"⚠️ {exchange_name} {pair} failed: {e}")
                        continue

        return None

    @binance_retry
    def _fetch_binance_custom_price(self, pair: str) -> Optional[float]:
        """Fetch custom pair price from Binance."""
        try:
            if not self._binance_exchange:
                return None
            ticker = self._binance_exchange.fetch_ticker(pair)
            if ticker and ticker.get("last") is not None:
                last_price = ticker["last"]
                if isinstance(last_price, (int, float)) and last_price > 0:
                    return float(last_price)
        except Exception:
            pass
        return None

    @okx_retry
    def _fetch_okx_custom_price(self, pair: str) -> Optional[float]:
        """Fetch custom pair price from OKX."""
        try:
            if not self._okx_exchange:
                return None
            ticker = self._okx_exchange.fetch_ticker(pair)
            if ticker and ticker.get("last") is not None:
                last_price = ticker["last"]
                if isinstance(last_price, (int, float)) and last_price > 0:
                    return float(last_price)
        except Exception:
            pass
        return None

    @bybit_retry
    def _fetch_bybit_custom_price(self, pair: str) -> Optional[float]:
        """Fetch custom pair price from Bybit."""
        try:
            if not self._bybit_exchange:
                return None
            ticker = self._bybit_exchange.fetch_ticker(pair)
            if ticker and ticker.get("last") is not None:
                last_price = ticker["last"]
                if isinstance(last_price, (int, float)) and last_price > 0:
                    return float(last_price)
        except Exception:
            pass
        return None

    def get_custom_coin_price(
        self,
        symbol: str,
        coingecko_id: Optional[str] = None,
        exchange_pairs: Optional[List[str]] = None,
    ) -> Optional[float]:
        """
        Get price for a custom cryptocurrency using multiple fallback methods.

        Args:
            symbol: Cryptocurrency symbol
            coingecko_id: Optional CoinGecko ID for direct lookup
            exchange_pairs: Optional trading pairs for exchange lookup

        Returns:
            Price in USD or None if all methods fail
        """
        # Handle stablecoins
        if symbol.upper() in ["USDT", "USDC", "DAI", "BUSD", "FDUSD", "TUSD"]:
            return 1.0

        # Method 1: Try existing exchange method first (for major coins)
        if symbol.upper() in self._supported_pairs:
            price = self.get_price(symbol)
            if price and price > 0:
                return price

        # Method 2: Try CoinGecko API
        price = self.get_coingecko_price(symbol, coingecko_id)
        if price and price > 0:
            return price

        # Method 3: Try exchange pairs if provided
        if exchange_pairs:
            price = self.get_exchange_price_for_custom_pair(symbol, exchange_pairs)
            if price and price > 0:
                return price

        # Method 4: Try auto-generated common pairs
        auto_pairs = [f"{symbol.upper()}/USDT", f"{symbol.upper()}/USDC", f"{symbol.upper()}/USD"]
        price = self.get_exchange_price_for_custom_pair(symbol, auto_pairs)
        if price and price > 0:
            return price

        print_warning(f"⚠️ Could not fetch price for {symbol} from any source")
        return None

    def get_multiple_custom_prices(
        self, custom_coins_data: Dict[str, Dict]
    ) -> Dict[str, Optional[float]]:
        """
        Fetch prices for multiple custom coins efficiently.

        Args:
            custom_coins_data: Dictionary of custom coin data from CustomCoinTracker

        Returns:
            Dictionary mapping symbol to price (or None if failed)
        """
        prices = {}

        for symbol, coin_data in custom_coins_data.items():
            coingecko_id = coin_data.get("coingecko_id")
            exchange_pairs = coin_data.get("exchange_pairs", [])

            price = self.get_custom_coin_price(symbol, coingecko_id, exchange_pairs)
            prices[symbol] = price

            # Reduced delay between requests for faster testing while still being respectful
            time.sleep(0.05)

        return prices

    async def get_multiple_custom_prices_async(
        self, custom_coins_data: Dict[str, Dict]
    ) -> Dict[str, Optional[float]]:
        """Async version of get_multiple_custom_prices."""
        # For now, wrap the synchronous version
        # TODO: Implement truly async version with aiohttp
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_multiple_custom_prices, custom_coins_data)


# Global enhanced price service instance
enhanced_price_service = EnhancedPriceService()


# Convenience functions for easy import
def get_custom_crypto_price(
    symbol: str, coingecko_id: Optional[str] = None, exchange_pairs: Optional[List[str]] = None
) -> Optional[float]:
    """Get price for a custom cryptocurrency."""
    return enhanced_price_service.get_custom_coin_price(symbol, coingecko_id, exchange_pairs)


def get_multiple_custom_crypto_prices(
    custom_coins_data: Dict[str, Dict],
) -> Dict[str, Optional[float]]:
    """Get prices for multiple custom cryptocurrencies."""
    return enhanced_price_service.get_multiple_custom_prices(custom_coins_data)


async def get_multiple_custom_crypto_prices_async(
    custom_coins_data: Dict[str, Dict],
) -> Dict[str, Optional[float]]:
    """Get prices for multiple custom cryptocurrencies asynchronously."""
    return await enhanced_price_service.get_multiple_custom_prices_async(custom_coins_data)
