# -*- coding: utf-8 -*-
"""
Multi-Chain Portfolio Tracker Script (v9 - Modern API Key Management)
---------------------------------------------------------------------
This script tracks cryptocurrency portfolio balances across multiple CEXs (Binance, OKX, Bybit, Backpack)
and blockchain wallets (Ethereum, Bitcoin, NEAR, Aptos, Solana), including DeFi platforms
like Hyperliquid. It uses ccxt, Playwright (for DeBank scraping), requests, and custom API
clients to fetch data.

Key Features:
- Fetches balances from Binance, OKX, Bybit, and Backpack exchanges.
- Fetches balances for Ethereum, Bitcoin, NEAR, Aptos, Solana wallets.
- Scrapes Ethereum wallet data from DeBank (Note: Scraping can be unreliable).
- Fetches Hyperliquid account data.
- Calculates total portfolio value and breakdown by platform/chain.
- Allows managing tracked wallets (add/remove/toggle Hyperliquid).
- Provides detailed views for wallets, CEX accounts, and Hyperliquid positions.
- Includes an adjustable balance offset feature.
- Saves analysis results to a JSON file.
- Allows viewing previously saved analysis results.
- Secure API key management with master password encryption.
- Professional UI with color-coded displays and tabular formatting.
- Enhanced UX with clearer fetching feedback and error handling.
- **NEW (v8):** Code quality improvements: type hints, organized directory structure, linting setup.
- **NEW (v9):** Modern API key management system - no hardcoded credentials required.

Requirements:
- Python 3.8+
- See requirements.txt for specific libraries.
- PyNaCl for Backpack exchange support (pip install pynacl)

Setup:
1. Install required libraries: pip install -r requirements.txt
2. Install Playwright browsers: playwright install
3. Install PyNaCl for Backpack support: pip install pynacl
4. Run the application - no additional setup required!
   API keys are managed securely through the application menu.

First-Time Setup:
1. Run: python port2.py
2. Go to menu option 4: "Manage API Keys"
3. Set a master password (one-time setup)
4. Add API keys for your exchanges
5. Start using live portfolio analysis

Security Features:
- Master password protection for all stored API keys
- Encrypted storage with PBKDF2-HMAC key derivation
- No hardcoded credentials in source files
- Easy-to-use menu interface for key management

Usage:
    python port2.py           # Normal mode with password prompts
    python port2.py --debug   # Debug mode - skip password prompts
"""

import asyncio
import ccxt
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import List, Dict, Any, Optional, Tuple
import json
import base64
import os
import sys
import hashlib
import re
import time
import hmac
from urllib.parse import urlencode
import requests
import getpass
from colorama import init, Fore, Style
from tabulate import tabulate
import httpx
from datetime import datetime, timezone
import traceback  # Added for detailed error printing
import glob  # For finding analysis files
import argparse  # Added for argument parsing

# Import our modularized components
from config.constants import *
from utils.helpers import *
from api_clients.okx_client import OkxClient
from api_clients.blockchain_clients import (
    make_solana_json_rpc_request,
    get_solana_token_accounts,
    get_solana_token_exchange_rate,
)
from api_clients.exchange_manager import (
    ExchangeManager,
    BackpackClient,
    sign_backpack_request,
    sign_backpack_request_custom,
    get_backpack_balance,
)
from api_clients.exchange_balances import (
    get_okx_detailed_balance,
    get_bybit_detailed_balance,
    get_backpack_detailed_balance,
    fetch_binance_single_account_balance,
    get_okx_total_balance_async,
    get_bybit_total_balance,
)
from ui.display_functions import (
    display_exchange_detailed_breakdown,
    display_comprehensive_overview,
    display_asset_distribution,
    display_wallet_balances,
    display_hyperliquid_positions,
    display_cex_breakdown,
)
from wallets.fetchers import WalletPlatformFetcher
from api_clients.cex_balances import get_binance_overall_balance, get_crypto_prices
from core.portfolio_analyzer import PortfolioAnalyzer

# Import the MultiChainWalletTracker class from models/wallet_tracker.py
from models.wallet_tracker import MultiChainWalletTracker

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Import PyNaCl for Backpack ED25519 signing (optional)
try:
    from nacl.signing import SigningKey
except ImportError:
    print(
        f"{Fore.YELLOW}Warning: PyNaCl not found. Backpack exchange will not be available.{Style.RESET_ALL}"
    )
    print("Install with: pip install pynacl")
    SigningKey = None

# Global exchange manager instance
exchange_manager: Optional[ExchangeManager] = None


class MockAPIModule:
    """Backward-compatible API shim for exchange manager."""


def get_exchange_manager() -> ExchangeManager:
    """Return a singleton ExchangeManager instance."""
    global exchange_manager
    if exchange_manager is None:
        exchange_manager = ExchangeManager(MockAPIModule(), None)
    return exchange_manager


def initialize_binance() -> Optional["ccxt.Exchange"]:
    """Initialize Binance exchange using stored API credentials."""
    return get_exchange_manager().initialize_binance()


def initialize_bybit() -> Optional["ccxt.Exchange"]:
    """Initialize Bybit exchange using stored API credentials."""
    return get_exchange_manager().initialize_bybit()


# --- Application Components ---
# Main functionality has been modularized into specialized components:
# - ui/menus.py: User interface and menu system
# - api_clients/: Exchange and API management
# - core/: Portfolio analysis logic
# - models/: Data models and wallet tracking

# Global variable to hold WalletTracker instance
wallet_tracker_instance: Optional[MultiChainWalletTracker] = None


async def main() -> None:
    """Main asynchronous entry point of the application."""
    global wallet_tracker_instance  # Allow modification of global instance

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Multi-Chain Portfolio Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python port2.py          # Normal mode with password prompts
  python port2.py --debug  # Debug mode - skip password prompts
        """,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (skip password prompts, use default credentials)",
    )

    args = parser.parse_args()

    # Set debug mode in constants
    if args.debug:
        import config.constants as constants

        constants.DEBUG_MODE = True
        print(f"{Fore.CYAN}🐛 Debug mode enabled{Style.RESET_ALL}")

    # Import the MenuSystem class
    from ui.menus import MenuSystem

    # Create a mock API module for backward compatibility
    # Create MenuSystem instance with required dependencies
    menu_system = MenuSystem(
        api_module=MockAPIModule(),
        exchange_manager=get_exchange_manager(),
    )

    # Run the main application
    await menu_system.main()


if __name__ == "__main__":
    # Setup exception handler for uncaught asyncio exceptions (optional but good practice)
    # def handle_exception(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
    #     msg = context.get("exception", context["message"])
    #     print(f"{Fore.RED}{Style.BRIGHT}Caught unexpected asyncio error: {msg}{Style.RESET_ALL}")
    #     # Optionally log traceback context.get('exception')
    # loop = asyncio.get_event_loop()
    # loop.set_exception_handler(handle_exception)

    try:
        # Ensure platform compatibility for asyncio policies if needed (e.g., Windows)
        # if sys.platform == "win32":
        #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.")
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            print_error("Detected a potential issue with nested asyncio loops.")
        else:
            print(
                f"\n{Fore.RED}{Style.BRIGHT}An unexpected runtime error occurred: {e}{Style.RESET_ALL}"
            )
            traceback.print_exc()
    except Exception as e:
        print(
            f"\n{Fore.RED}{Style.BRIGHT}An unexpected critical error occurred: {e}{Style.RESET_ALL}"
        )
        traceback.print_exc()
    finally:
        print_info("Program finished.")
