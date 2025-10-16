# -*- coding: utf-8 -*-
"""
Custom Cryptocurrency Tracker Model
-----------------------------------
Manages user-defined custom cryptocurrencies with their balances and price fetching.
This allows tracking of any cryptocurrency beyond the built-in major ones.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from colorama import Fore, Style
from tabulate import tabulate

from config.constants import *
from utils.helpers import (
    print_error,
    print_warning,
    print_info,
    print_success,
    safe_float_convert,
    format_currency,
)


class CustomCoinTracker:
    """Manages custom cryptocurrency definitions and balances."""

    def __init__(self, storage_file: str = "data/custom_coins.json"):
        self.storage_file = storage_file
        self.custom_coins: Dict[str, Dict[str, Any]] = {}
        self._load_data()

    def _load_data(self):
        """Load custom coin data from storage file."""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)

        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    self.custom_coins = data.get("custom_coins", {})
            except json.JSONDecodeError:
                print_error(f"Error decoding {self.storage_file}. Initializing with empty data.")
                self.custom_coins = {}
            except Exception as e:
                print_error(f"Error loading custom coins from {self.storage_file}: {e}")
                self.custom_coins = {}
        else:
            print_info(f"Creating new custom coins storage at {self.storage_file}")
            self.custom_coins = {}
            self.save_data()

    def save_data(self):
        """Save custom coin data to storage file."""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)

        data = {"custom_coins": self.custom_coins, "last_updated": datetime.now().isoformat()}
        try:
            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print_error(f"Error saving custom coins to {self.storage_file}: {e}")
        except Exception as e:
            print_error(f"Unexpected error saving custom coins: {e}")

    def add_custom_coin(self, symbol: str) -> bool:
        """Adds a new custom coin for price tracking. Only symbol is mandatory.
        Name will initially default to the symbol and can be updated later by fetching.
        """
        symbol = symbol.upper()
        if not symbol:
            print_error("Symbol cannot be empty.")
            return False

        if symbol in self.custom_coins:
            print_warning(f"{symbol} is already in the custom coin list.")
            return False

        # Name defaults to symbol, can be updated by a separate call after fetching
        effective_name = symbol

        self.custom_coins[symbol] = {
            "symbol": symbol,
            "name": effective_name,
            "balance": 0.0,
            "price_only": True,
            "coingecko_id": None,
            "exchange_pairs": [],
            "last_price": None,
            "price_source": "auto-fetched",
        }
        self.save_data()
        return True

    def update_coin_name(self, symbol: str, new_name: str) -> bool:
        """Updates the name of an existing custom coin."""
        symbol = symbol.upper()
        if symbol not in self.custom_coins:
            # This case should ideally be handled by the caller or logged,
            # as the coin should exist if we're trying to update its name.
            print_warning(
                f"Attempted to update name for non-existent coin {symbol}. This might indicate an issue."
            )
            return False

        if not new_name or not new_name.strip():
            print_warning(f"New name for {symbol} cannot be empty. Name not updated.")
            return False

        self.custom_coins[symbol]["name"] = new_name.strip()
        self.custom_coins[symbol][
            "last_updated"
        ] = datetime.now().isoformat()  # Also update timestamp
        self.save_data()
        # Success message is handled by the calling menu function
        return True

    def update_balance(self, symbol: str, new_balance: float) -> bool:
        """Update the balance for a custom coin."""
        symbol = symbol.upper().strip()
        new_balance = safe_float_convert(new_balance)

        if symbol not in self.custom_coins:
            print_error(f"Custom coin {symbol} not found")
            return False

        if new_balance < 0:
            print_error("Balance cannot be negative")
            return False

        old_balance = self.custom_coins[symbol]["balance"]
        self.custom_coins[symbol]["balance"] = new_balance
        self.custom_coins[symbol]["last_updated"] = datetime.now().isoformat()
        self.save_data()

        print_success(f"Updated {symbol} balance: {old_balance} → {new_balance}")
        return True

    def remove_custom_coin(self, symbol: str) -> bool:
        """Remove a custom coin from tracking."""
        symbol = symbol.upper().strip()

        if symbol not in self.custom_coins:
            print_error(f"Custom coin {symbol} not found")
            return False

        coin_data = self.custom_coins[symbol]
        del self.custom_coins[symbol]
        self.save_data()

        print_success(f"Removed custom coin {symbol} (balance: {coin_data['balance']})")
        return True

    def list_custom_coins(self):
        """Lists all custom coins in a cleaner, modern format."""
        if not self.custom_coins:
            print_info("📭 No custom coins are currently being tracked.")
            print_info("💡 Use 'Add Custom Coin' to start tracking cryptocurrency prices.")
            return

        # Color scheme for modern display
        HEADER = Fore.CYAN + Style.BRIGHT
        COIN_NAME = Fore.WHITE + Style.BRIGHT
        SYMBOL = Fore.YELLOW + Style.BRIGHT
        COUNT = Fore.GREEN + Style.BRIGHT
        SUBTITLE = Style.DIM + Fore.WHITE
        RESET = Style.RESET_ALL

        # Header with count
        print(f"\n{HEADER}📊 CUSTOM COINS OVERVIEW{RESET}")
        print(f"{SUBTITLE}{'─' * 30}{RESET}")
        print(
            f"{COUNT}{len(self.custom_coins)}{RESET} {SUBTITLE}coins tracked for automatic price monitoring{RESET}"
        )

        # Sort coins alphabetically by name
        sorted_coins = sorted(
            self.custom_coins.values(), key=lambda x: x.get("name", x["symbol"]).lower()
        )

        print(f"\n{HEADER}🪙 TRACKED COINS{RESET}")
        print(f"{SUBTITLE}{'─' * 15}{RESET}")

        for i, coin_data in enumerate(sorted_coins, 1):
            symbol_upper = coin_data["symbol"].upper()
            name = coin_data.get("name", symbol_upper).strip()
            if not name:
                name = symbol_upper

            # Create display string with proper formatting
            if name.lower() != symbol_upper.lower():
                display_name = f"{COIN_NAME}{name}{RESET}"
                display_symbol = f"{SYMBOL}({symbol_upper}){RESET}"
                coin_display = f"{display_name} {display_symbol}"
            else:
                coin_display = f"{SYMBOL}{symbol_upper}{RESET}"

            # Add number and coin icon
            print(f"  {SUBTITLE}{i:2d}.{RESET} 🪙 {coin_display}")

        # Footer with helpful info
        print(f"\n{SUBTITLE}{'─' * 50}{RESET}")
        print(f"{SUBTITLE}💡 Prices are automatically fetched during portfolio analysis{RESET}")
        print(f"{SUBTITLE}🔄 Use 'Test All Custom Coin Prices' to verify price sources{RESET}")
        print(f"{SUBTITLE}➕ Use 'Add Custom Coin' to track more cryptocurrencies{RESET}")

    def get_all_symbols(self) -> List[str]:
        """Get list of all custom coin symbols."""
        return list(self.custom_coins.keys())

    def get_coin_data(self, symbol: str) -> Dict[str, Any]:
        """Get data for a specific coin."""
        return self.custom_coins.get(symbol, {})

    def get_custom_coins_summary(self) -> Dict[str, Any]:
        """Get a summary of all custom coins including total value."""
        total_value = 0.0
        total_coins = len(self.custom_coins)

        for symbol, coin_data in self.custom_coins.items():
            balance = coin_data.get("balance", 0)
            last_price = coin_data.get("last_price", 0)

            if balance and last_price:
                total_value += balance * last_price

        return {
            "custom_coins_count": total_coins,
            "custom_coins_total_value": total_value,
            "custom_coins_data": self.custom_coins.copy(),
        }

    def update_price(self, symbol: str, price: float):
        """Update the last fetched price for a custom coin."""
        symbol = symbol.upper()
        if symbol in self.custom_coins:
            self.custom_coins[symbol]["last_price"] = price
            self.custom_coins[symbol]["last_price_fetch"] = datetime.now().isoformat()

    def get_total_value(self) -> float:
        """Calculate total USD value of all custom coins (if prices available)."""
        total = 0.0
        for coin_data in self.custom_coins.values():
            balance = coin_data["balance"]
            last_price = coin_data.get("last_price")
            if last_price and last_price > 0:
                total += balance * last_price
        return total

    def export_to_dict(self) -> Dict[str, Any]:
        """Export custom coins data for inclusion in portfolio analysis."""
        return {
            "custom_coins_count": len(self.custom_coins),
            "custom_coins_data": self.custom_coins.copy(),
            "custom_coins_total_value": self.get_total_value(),
            "custom_coins_symbols": self.get_all_symbols(),
        }
