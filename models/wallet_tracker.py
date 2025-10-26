# -*- coding: utf-8 -*-
"""
Wallet Tracker Model
--------------------
Contains the MultiChainWalletTracker class for managing wallet addresses
and associated data across multiple blockchain networks.
"""

import json
import os
import re
from typing import Dict, List, Any, Optional
from colorama import Fore, Style

# Import configuration and utilities
from config.constants import SUPPORTED_CHAINS, WALLET_STORAGE_FILE
from web3 import Web3
from utils.helpers import (
    print_error,
    print_warning,
    print_info,
    print_success,
    safe_float_convert,
    format_currency,
)
from wallets.fetchers import WalletPlatformFetcher


class MultiChainWalletTracker:
    """Manages wallet addresses and associated data."""

    def __init__(self, storage_file: str = WALLET_STORAGE_FILE):
        self.storage_file = storage_file
        self.wallets: Dict[str, List[str]] = {}
        self.hyperliquid_enabled: List[str] = []
        self.lighter_enabled: List[str] = []
        self.polymarket_enabled: List[str] = []
        self.polymarket_proxies: Dict[str, str] = {}
        self.balance_offset: float = 0.0
        self._load_data()  # Load data on initialization
        self._sync_hyperliquid_tracking()
        self._sync_polymarket_tracking()

    def _load_data(self):
        """Loads wallet data, hyperliquid status, and offset from the storage file."""
        default_wallets = {chain: [] for chain in SUPPORTED_CHAINS}
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    loaded_wallets = data.get("wallets", {})
                    # Ensure all supported chains are present, even if empty
                    self.wallets = {
                        chain: loaded_wallets.get(chain, []) for chain in SUPPORTED_CHAINS
                    }
                    self.hyperliquid_enabled = data.get("hyperliquid_enabled", [])
                    self.lighter_enabled = data.get("lighter_enabled", [])
                    self.polymarket_enabled = data.get("polymarket_enabled", [])
                    raw_proxy_map = data.get("polymarket_proxies", {})
                    self.polymarket_proxies = (
                        raw_proxy_map if isinstance(raw_proxy_map, dict) else {}
                    )
                    self.balance_offset = safe_float_convert(data.get("balance_offset", 0.0))
            except json.JSONDecodeError:
                print_error(f"Error decoding {self.storage_file}. Initializing with empty data.")
                self.wallets = default_wallets
                self.hyperliquid_enabled = []
                self.lighter_enabled = []
                self.polymarket_enabled = []
                self.polymarket_proxies = {}
                self.balance_offset = 0.0
            except Exception as e:
                print_error(
                    f"Error loading data from {self.storage_file}: {e}. Initializing with empty data."
                )
                self.wallets = default_wallets
                self.hyperliquid_enabled = []
                self.lighter_enabled = []
                self.polymarket_enabled = []
                self.polymarket_proxies = {}
                self.balance_offset = 0.0
        else:
            print_warning(f"{self.storage_file} not found. Initializing with empty data.")
            self.wallets = default_wallets
            self.hyperliquid_enabled = []
            self.lighter_enabled = []
            self.polymarket_enabled = []
            self.polymarket_proxies = {}
            self.balance_offset = 0.0
        # Ensure all supported chains exist as keys after loading
        for chain in SUPPORTED_CHAINS:
            if chain not in self.wallets:
                self.wallets[chain] = []

        # Normalize Ethereum addresses and ensure tracking lists stay in sync
        if self.wallets.get("ethereum"):
            normalized_eth = []
            for addr in self.wallets["ethereum"]:
                try:
                    checksum = Web3.to_checksum_address(addr)
                except ValueError:
                    checksum = addr
                if checksum not in normalized_eth:
                    normalized_eth.append(checksum)
            self.wallets["ethereum"] = normalized_eth

            normalized_hl = []
            for addr in self.hyperliquid_enabled:
                try:
                    checksum = Web3.to_checksum_address(addr)
                except ValueError:
                    checksum = addr
                if checksum in normalized_eth and checksum not in normalized_hl:
                    normalized_hl.append(checksum)
            self.hyperliquid_enabled = normalized_hl

            normalized_lighter = []
            for addr in self.lighter_enabled:
                try:
                    checksum = Web3.to_checksum_address(addr)
                except ValueError:
                    checksum = addr
                if checksum in normalized_eth and checksum not in normalized_lighter:
                    normalized_lighter.append(checksum)
            self.lighter_enabled = normalized_lighter

            normalized_polymarket = []
            for addr in self.polymarket_enabled:
                try:
                    checksum = Web3.to_checksum_address(addr)
                except ValueError:
                    checksum = addr
                if checksum in normalized_eth and checksum not in normalized_polymarket:
                    normalized_polymarket.append(checksum)
            self.polymarket_enabled = normalized_polymarket

            normalized_proxy_map: Dict[str, str] = {}
            for owner, proxy in self.polymarket_proxies.items():
                try:
                    owner_checksum = Web3.to_checksum_address(owner)
                    proxy_checksum = Web3.to_checksum_address(proxy)
                except ValueError:
                    continue
                if owner_checksum in normalized_eth:
                    normalized_proxy_map[owner_checksum] = proxy_checksum
            self.polymarket_proxies = normalized_proxy_map

        self._sync_hyperliquid_tracking()
        self._sync_polymarket_tracking()

    def _sync_hyperliquid_tracking(self) -> None:
        """Keep Hyperliquid tracking list in sync with existing Ethereum wallets (no auto-enable)."""
        eth_wallets = set(self.wallets.get("ethereum", []))
        synced: List[str] = []
        seen = set()
        for addr in self.hyperliquid_enabled:
            if addr in eth_wallets and addr not in seen:
                synced.append(addr)
                seen.add(addr)
        self.hyperliquid_enabled = synced

    def _sync_polymarket_tracking(self) -> None:
        """Keep Polymarket tracking data in sync with tracked Ethereum wallets."""
        eth_wallets = set(self.wallets.get("ethereum", []))
        synced: List[str] = []
        seen = set()
        for addr in self.polymarket_enabled:
            if addr in eth_wallets and addr not in seen:
                synced.append(addr)
                seen.add(addr)
        self.polymarket_enabled = synced

        # Drop proxy mappings for wallets no longer tracked
        self.polymarket_proxies = {
            owner: proxy for owner, proxy in self.polymarket_proxies.items() if owner in eth_wallets
        }

    def save_data(self):
        """Saves the current wallet data, hyperliquid status, and offset to the storage file."""
        self._sync_hyperliquid_tracking()
        self._sync_polymarket_tracking()
        data = {
            "wallets": self.wallets,
            "hyperliquid_enabled": self.hyperliquid_enabled,
            "lighter_enabled": self.lighter_enabled,
            "polymarket_enabled": self.polymarket_enabled,
            "polymarket_proxies": self.polymarket_proxies,
            "balance_offset": self.balance_offset,
        }
        try:
            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print_error(f"Error saving data to {self.storage_file}: {e}")
        except Exception as e:
            print_error(f"Unexpected error saving data: {e}")

    def set_balance_offset(self, offset: float):
        """Sets the balance offset and saves the data."""
        self.balance_offset = offset
        self.save_data()
        print_success(f"Balance offset updated to {format_currency(self.balance_offset)}")

    def add_wallet(self, address: str, chain: str):
        """Adds a wallet address for a specific chain."""
        chain = chain.lower()
        if chain not in SUPPORTED_CHAINS:
            print_error(
                f"Unsupported chain: {chain}. Supported chains are: {', '.join(SUPPORTED_CHAINS)}"
            )
            return
        if not address or not isinstance(address, str):
            print_error(f"Invalid address provided for {chain}.")
            return
        # Basic address validation (example, can be improved)
        if chain == "ethereum" and not re.match(r"^0x[a-fA-F0-9]{40}$", address):
            print_error(f"Invalid Ethereum address format: {address}")
            return
        if chain == "ethereum":
            try:
                address = Web3.to_checksum_address(address)
            except ValueError:
                print_error(f"Invalid Ethereum address checksum: {address}")
                return
        if chain == "bitcoin" and not (
            address.startswith("1") or address.startswith("3") or address.startswith("bc1")
        ):
            print_warning(f"Unusual Bitcoin address format: {address}")  # Warning, not error
        # Add more specific checks for NEAR, Aptos, Solana if needed

        if chain not in self.wallets:
            self.wallets[chain] = []  # Should not happen due to _load_data logic, but safe check
        if address not in self.wallets[chain]:
            self.wallets[chain].append(address)
            self.save_data()
            print_success(f"{chain.capitalize()} wallet added: {address}")
        else:
            print_warning(f"{chain.capitalize()} wallet {address} already exists.")

    def remove_wallet(self, address: str, chain: str):
        """Removes a wallet address for a specific chain."""
        chain = chain.lower()
        if chain in self.wallets and address in self.wallets[chain]:
            self.wallets[chain].remove(address)
            # Remove optional platform tracking if it's an Ethereum wallet being removed
            if chain == "ethereum":
                if address in self.lighter_enabled:
                    self.lighter_enabled.remove(address)
                if address in self.hyperliquid_enabled:
                    self.hyperliquid_enabled.remove(address)
                if address in self.polymarket_enabled:
                    self.polymarket_enabled.remove(address)
                if address in self.polymarket_proxies:
                    self.polymarket_proxies.pop(address, None)
            self.save_data()
            print_success(f"{chain.capitalize()} wallet removed: {address}")
        else:
            print_error(f"{chain.capitalize()} wallet {address} not found.")

    def toggle_lighter(self, address: str):
        """Enables or disables Lighter perp tracking for a specific Ethereum wallet."""
        try:
            address = Web3.to_checksum_address(address)
        except ValueError:
            pass
        if "ethereum" in self.wallets and address in self.wallets["ethereum"]:
            if address in self.lighter_enabled:
                self.lighter_enabled.remove(address)
                print_success(f"Lighter tracking disabled for {address}")
            else:
                self.lighter_enabled.append(address)
                print_success(f"Lighter tracking enabled for {address}")
            self.save_data()
        else:
            print_error(f"Address {address} is not in the list of tracked Ethereum wallets.")

    def toggle_hyperliquid(self, address: str):
        """Enables or disables Hyperliquid tracking for a specific Ethereum wallet."""
        try:
            address = Web3.to_checksum_address(address)
        except ValueError:
            pass
        if "ethereum" in self.wallets and address in self.wallets["ethereum"]:
            if address in self.hyperliquid_enabled:
                self.hyperliquid_enabled.remove(address)
                print_success(f"Hyperliquid tracking disabled for {address}")
            else:
                self.hyperliquid_enabled.append(address)
                print_success(f"Hyperliquid tracking enabled for {address}")
            self.save_data()
        else:
            print_error(f"Address {address} is not in the list of tracked Ethereum wallets.")

    def toggle_polymarket(self, address: str):
        """Enables or disables Polymarket tracking for a specific Ethereum wallet."""
        try:
            address = Web3.to_checksum_address(address)
        except ValueError:
            pass
        if "ethereum" in self.wallets and address in self.wallets["ethereum"]:
            if address in self.polymarket_enabled:
                self.polymarket_enabled.remove(address)
                print_success(f"Polymarket tracking disabled for {address}")
            else:
                self.polymarket_enabled.append(address)
                print_success(f"Polymarket tracking enabled for {address}")
            self.save_data()
        else:
            print_error(f"Address {address} is not in the list of tracked Ethereum wallets.")

    def set_polymarket_proxy(self, owner: str, proxy: str) -> None:
        """Associates a Polymarket proxy wallet with the specified owner address."""
        try:
            owner_checksum = Web3.to_checksum_address(owner)
        except ValueError:
            print_error(f"Invalid owner address for Polymarket proxy: {owner}")
            return

        try:
            proxy_checksum = Web3.to_checksum_address(proxy)
        except ValueError:
            print_error(f"Invalid proxy address for Polymarket tracking: {proxy}")
            return

        if owner_checksum not in self.wallets.get("ethereum", []):
            print_error(f"Owner address {owner_checksum} is not a tracked Ethereum wallet.")
            return

        self.polymarket_proxies[owner_checksum] = proxy_checksum
        print_success(f"Polymarket proxy set: {owner_checksum} → {proxy_checksum}")
        self.save_data()

    def clear_polymarket_proxy(self, owner: str) -> None:
        """Removes the Polymarket proxy mapping for the given owner address."""
        try:
            owner_checksum = Web3.to_checksum_address(owner)
        except ValueError:
            print_error(f"Invalid owner address for Polymarket proxy removal: {owner}")
            return

        if owner_checksum in self.polymarket_proxies:
            self.polymarket_proxies.pop(owner_checksum, None)
            print_success(f"Polymarket proxy cleared for {owner_checksum}")
            self.save_data()
        else:
            print_warning(f"No Polymarket proxy configured for {owner_checksum}")

    def get_polymarket_proxy(self, owner: str) -> Optional[str]:
        """Returns the configured Polymarket proxy for the supplied owner address."""
        try:
            owner_checksum = Web3.to_checksum_address(owner)
        except ValueError:
            owner_checksum = owner
        return self.polymarket_proxies.get(owner_checksum)

    def list_wallets(self):
        """Prints a list of all tracked wallets."""
        if not any(self.wallets.values()):
            print_info("No wallets added yet.")
            return
        # Header printed by manage_wallets_menu
        for chain in SUPPORTED_CHAINS:
            addresses = self.wallets.get(chain, [])
            if addresses:
                print(
                    f"\n{Fore.MAGENTA + Style.BRIGHT}{chain.capitalize()} Wallets:{Style.RESET_ALL}"
                )  # Changed color
                for i, address in enumerate(addresses, 1):
                    status_labels = []
                    if chain == "ethereum" and address in self.hyperliquid_enabled:
                        status_labels.append(Fore.GREEN + "Hyperliquid" + Style.RESET_ALL)
                    if chain == "ethereum" and address in self.lighter_enabled:
                        status_labels.append(Fore.CYAN + "Lighter" + Style.RESET_ALL)
                    if chain == "ethereum" and address in self.polymarket_enabled:
                        proxy = self.polymarket_proxies.get(address)
                        if proxy:
                            status_labels.append(Fore.MAGENTA + "Polymarket" + Style.RESET_ALL)
                        else:
                            status_labels.append(Fore.YELLOW + "Polymarket⚠" + Style.RESET_ALL)
                    status_str = " (" + ", ".join(status_labels) + ")" if status_labels else ""
                    print(f"  {i}. {address}{status_str}")

    # --- Wallet/Platform Info Fetching Methods (Async Wrappers where needed) ---

    async def get_all_wallets_and_platforms_info(self) -> List[Dict[str, Any]]:
        """Fetches info for all tracked wallets and enabled platforms using WalletPlatformFetcher."""
        fetcher = WalletPlatformFetcher(
            self.wallets,
            hyperliquid_enabled=self.hyperliquid_enabled,
            lighter_enabled=self.lighter_enabled,
            polymarket_enabled=self.polymarket_enabled,
            polymarket_proxies=self.polymarket_proxies,
        )
        return await fetcher.get_all_wallets_and_platforms_info()
