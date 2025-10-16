# -*- coding: utf-8 -*-
"""
CEX Balance Fetching Module
---------------------------
Contains functions for fetching balances and market data from centralized exchanges.
These functions handle comprehensive balance retrieval and price data fetching.
"""

import ccxt
from typing import List, Dict, Any, Optional, Tuple
from colorama import Fore, Style

# Import configuration and utilities
from config.constants import *
from utils.helpers import (
    print_error,
    print_warning,
    print_info,
    print_success,
    safe_float_convert,
    format_currency,
    format_btc,
)
from api_clients.exchange_balances import (
    fetch_binance_single_account_balance,
    get_binance_account_types_breakdown,
)
from utils.rate_limiter import binance_retry


@binance_retry
def get_binance_overall_balance(
    exchange: Optional[ccxt.Exchange], api_module=None
) -> Tuple[
    Optional[float], List[List[Any]], Tuple[Optional[float], Optional[float], Optional[float]]
]:
    """
    Fetches total Binance balance across all account types using the new API key manager.
    Returns: (total_balance_usd | None, detailed_balances_table_data, account_totals_tuple | None)
    Returns None for balances if fetching fails critically (e.g., price lookup).
    """
    from api_clients.api_manager import api_key_manager
    from urllib.parse import urlencode
    import hmac
    import hashlib
    import time
    import requests

    try:
        # Use the account types breakdown function to get total across all accounts
        account_types_data = get_binance_account_types_breakdown()

        if not account_types_data:
            print_warning("Could not fetch Binance account types breakdown")
            return None, [], (None, None, None)

        # Get the total across all account types
        total_balance_usdt = account_types_data.get("total_all_accounts", 0.0)
        account_types = account_types_data.get("account_types", {})

        # Create display data for the main balance
        detailed_balances_data = []
        main_account_total = total_balance_usdt

        # Add a summary entry for the main display
        if total_balance_usdt > 0:
            detailed_balances_data.append(
                [
                    "Main Account",
                    f"Multiple Types",
                    format_currency(total_balance_usdt),
                    "Yes",
                    total_balance_usdt,
                ]
            )

        # Store account totals (using the breakdown data)
        account_totals = {"main": total_balance_usdt, "sub2": None, "master": None}

        print_success(
            f"Binance total balance: {format_currency(total_balance_usdt)} across {len([k for k,v in account_types.items() if v is not None and v > 0])} account types"
        )

        return (
            total_balance_usdt,
            detailed_balances_data,
            (account_totals["main"], None, None),
        )

    except Exception as e:
        print_error(f"Error fetching Binance overall balance: {e}")
        return None, [], (None, None, None)


def get_crypto_prices(exchange: Optional[ccxt.Exchange]) -> Dict[str, Optional[float]]:
    """Fetches current prices (USD). Returns None for price if fetch fails."""
    prices: Dict[str, Optional[float]] = {
        "BTC": None,
        "ETH": None,
        "SOL": None,
        "NEAR": None,
        "APT": None,
    }  # Added NEAR, APT
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "NEAR/USDT", "APT/USDT"]  # Added NEAR, APT
    success_count = 0
    if not exchange:
        print_error("Cannot fetch crypto prices: Exchange object is invalid.")
        return prices  # Return dict with None values
    try:
        print_info("  Fetching market prices from Binance...")
        tickers = exchange.fetch_tickers(symbols)
        for symbol in symbols:
            asset = symbol.split("/")[0]
            try:
                # Check ticker structure carefully
                if (
                    symbol in tickers
                    and tickers[symbol]
                    and "last" in tickers[symbol]
                    and tickers[symbol]["last"] is not None
                ):
                    price = safe_float_convert(tickers[symbol]["last"], 0.0)
                    if price <= 0:  # Treat 0 or negative price as invalid
                        print_warning(f"  Invalid price (<=0) received for {symbol}.")
                        prices[asset] = None
                    else:
                        prices[asset] = price
                        print(
                            f"    {Fore.WHITE}{asset}: {format_currency(price, color=Fore.WHITE)}{Style.RESET_ALL}"
                        )  # Print successful price fetch
                        success_count += 1
                else:
                    print_warning(f"  Could not fetch valid price data for {symbol}")
                    prices[asset] = None  # Explicitly set to None if missing
            except (KeyError, TypeError) as e:
                print_warning(f"  Error processing ticker data for {symbol}: {e}")
                prices[asset] = None
    except (ccxt.NetworkError, ccxt.ExchangeError, AttributeError) as e:
        is_network = isinstance(e, ccxt.NetworkError)
        print_error(
            f"Fetching crypto prices from {getattr(exchange, 'id', 'exchange')}: {e}",
            is_network_issue=is_network,
        )
        # Keep existing prices as None
    except Exception as e:
        print_error(f"Unexpected error fetching crypto prices: {e}")
        # Keep existing prices as None

    # Report overall success/failure
    if success_count == len(symbols):
        print_success("Crypto price fetching completed.")
    elif success_count > 0:
        print_warning(
            f"Crypto price fetching completed with {len(symbols) - success_count} errors."
        )
    else:
        print_warning("Crypto price fetching failed.")

    return prices
