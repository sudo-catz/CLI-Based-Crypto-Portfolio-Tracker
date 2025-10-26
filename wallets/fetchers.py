# -*- coding: utf-8 -*-
"""
Wallet and Platform Fetchers Module
-----------------------------------
Contains all wallet and platform data fetching functions for the portfolio tracker.
These functions handle fetching balance and position data from various blockchain networks
and DeFi platforms.
"""

import asyncio
import json
import re
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import traceback
import os
import time
from web3 import Web3

# Import configuration and utilities
from config.constants import *
from utils.helpers import (
    print_error,
    print_warning,
    print_info,
    print_success,
    safe_float_convert,
    format_currency,
)
from api_clients.blockchain_clients import (
    make_solana_json_rpc_request,
    get_solana_token_accounts,
    get_solana_token_exchange_rate,
)
from utils.enhanced_price_service import enhanced_price_service
from utils.network_utils import smart_request_with_fallback

# Import performance optimization decorators
from utils.performance_optimizer import cached_wallet_data, cached_api_call, cached_price_data

# Optimized cache TTLs for different blockchain types
CACHE_TTL_FAST = 60  # Fast-changing data (trading platforms)
CACHE_TTL_MEDIUM = 120  # Medium-changing data (wallet balances)
CACHE_TTL_SLOW = 300  # Slow-changing data (Bitcoin addresses)


class WalletPlatformFetcher:
    """Handles fetching data from various blockchain wallets and DeFi platforms."""

    def __init__(
        self,
        wallets: Dict[str, List[str]],
        hyperliquid_enabled: List[str],
        lighter_enabled: List[str],
        polymarket_enabled: Optional[List[str]] = None,
        polymarket_proxies: Optional[Dict[str, str]] = None,
        skip_basic_ethereum: bool = False,
    ):
        """Initialize with wallet data from MultiChainWalletTracker."""
        self.wallets = wallets
        ethereum_wallets = wallets.get("ethereum", []) if wallets else []
        self.hyperliquid_enabled = (
            list(hyperliquid_enabled) if hyperliquid_enabled else list(ethereum_wallets)
        )
        # Ensure deterministic ordering and no duplicates
        if self.hyperliquid_enabled:
            self.hyperliquid_enabled = list(dict.fromkeys(self.hyperliquid_enabled))
        self.lighter_enabled = list(lighter_enabled) if lighter_enabled else []
        if self.lighter_enabled:
            self.lighter_enabled = list(dict.fromkeys(self.lighter_enabled))
        self.polymarket_enabled = (
            list(polymarket_enabled) if polymarket_enabled else []
        )
        if self.polymarket_enabled:
            self.polymarket_enabled = list(dict.fromkeys(self.polymarket_enabled))
        raw_proxy_map = dict(polymarket_proxies) if polymarket_proxies else {}
        normalized_proxy_map: Dict[str, str] = {}
        for owner, proxy in raw_proxy_map.items():
            try:
                owner_checksum = Web3.to_checksum_address(owner)
                proxy_checksum = Web3.to_checksum_address(proxy)
            except ValueError:
                continue
            normalized_proxy_map[owner_checksum] = proxy_checksum
        self.polymarket_proxies = normalized_proxy_map
        self.skip_basic_ethereum = skip_basic_ethereum

    async def _run_sync_in_thread(self, func, *args):
        """Runs a synchronous function in a thread pool."""
        try:
            # asyncio.to_thread is available in Python 3.9+
            if hasattr(asyncio, "to_thread"):
                return await asyncio.to_thread(func, *args)
            else:
                # Fallback for Python 3.8
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, func, *args)
        except Exception as e:
            print_error(f"Error running sync function {func.__name__} in thread: {e}")
            return None

    # Wallet fetching methods will be added here

    @cached_wallet_data(ttl=CACHE_TTL_SLOW)  # Cache for 5 minutes
    async def get_bitcoin_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetches Bitcoin wallet info using blockchain.info API (via thread)."""

        def fetch_btc_sync(addr):
            try:
                response = requests.get(f"https://blockchain.info/rawaddr/{addr}", timeout=15)
                response.raise_for_status()
                data = response.json()
                balance_btc = data["final_balance"] / SATOSHIS_PER_BTC

                # Use smart price service for BTC price
                btc_price = enhanced_price_service.get_price("BTC")
                if btc_price is None:
                    print_warning("Could not fetch BTC price, using balance in BTC only")
                    balance_usd = 0.0
                else:
                    balance_usd = balance_btc * btc_price

                return {
                    "address": addr,
                    "chain": "bitcoin",
                    "total_balance": balance_usd,
                    "balance_btc": balance_btc,
                    "transaction_count": data["n_tx"],
                    "source": "Blockchain.info",
                }
            except requests.exceptions.RequestException as e:
                is_network = isinstance(
                    e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                )
                print_error(
                    f"Fetching Bitcoin wallet info for {addr[:6]}...: {e}",
                    is_network_issue=is_network,
                )
                # Note: This won't retry the current fetch, but may help the next run.
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                print_error(f"Processing Bitcoin wallet data for {addr[:6]}...: {e}")
            except Exception as e:
                print_error(f"Unexpected error fetching Bitcoin info for {addr[:6]}...: {e}")
            return None

        return await self._run_sync_in_thread(fetch_btc_sync, address)

    async def get_near_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Legacy stub retained for backward compatibility after NEAR removal."""
        print_warning("NEAR wallet integration has been removed.")
        return None

    async def get_aptos_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Legacy stub retained for backward compatibility after Aptos removal."""
        print_warning("Aptos wallet integration has been removed.")
        return None

    @cached_wallet_data(
        ttl=CACHE_TTL_FAST
    )  # Cache for 3.3 minutes - Solana data changes frequently
    async def get_solana_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetches Solana wallet info using Solana RPC and Jupiter (via thread)."""

        def fetch_sol_sync(addr):
            try:
                token_balances = {token: 0.0 for token in SOLANA_TOKENS.keys()}
                token_exchange_rates = {}  # Rate vs SOL

                sol_balance_response = make_solana_json_rpc_request("getBalance", [addr])
                if (
                    not sol_balance_response
                    or "result" not in sol_balance_response
                    or "value" not in sol_balance_response["result"]
                ):
                    # Error already printed by make_solana_json_rpc_request if it failed
                    if sol_balance_response:  # Check if response exists but is invalid
                        print_error(
                            f"Could not fetch native SOL balance for {addr[:6]}...: Invalid response format {sol_balance_response.get('error')}"
                        )
                    return None
                lamports_balance = sol_balance_response["result"]["value"]
                sol_balance = lamports_balance / LAMPOSTS_PER_SOL

                token_accounts = get_solana_token_accounts(addr)
                for account in token_accounts:
                    try:
                        info = (
                            account.get("account", {})
                            .get("data", {})
                            .get("parsed", {})
                            .get("info", {})
                        )
                        mint = info.get("mint")
                        ui_amount_str = info.get("tokenAmount", {}).get("uiAmountString")
                        if mint and ui_amount_str:
                            amount = safe_float_convert(ui_amount_str)
                            for token_name, token_address in SOLANA_TOKENS.items():
                                if mint == token_address:
                                    token_balances[token_name] = amount
                                    break
                    except Exception as e:
                        print_warning(f"Error processing a token account for {addr[:6]}...: {e}")

                # Use smart price service for SOL price
                sol_price_usd = enhanced_price_service.get_price("SOL")
                if sol_price_usd is None:
                    print_warning("Could not fetch SOL/USD price.")
                    sol_price_usd = 0.0

                total_sol_equivalent = sol_balance
                for token_name, token_address in SOLANA_TOKENS.items():
                    balance = token_balances.get(token_name, 0.0)
                    if balance > 0:
                        if token_name in ["USDC", "USDT"]:
                            # Assume 1 USD, convert to SOL equivalent using SOL price
                            rate = (1.0 / sol_price_usd) if sol_price_usd > 0 else 0
                            token_exchange_rates[token_name] = rate
                            total_sol_equivalent += balance * rate
                        else:
                            # Fetch rate vs SOL from Jupiter
                            rate = get_solana_token_exchange_rate(token_address)
                            token_exchange_rates[token_name] = rate
                            total_sol_equivalent += balance * rate

                total_balance_usd = total_sol_equivalent * sol_price_usd

                return {
                    "address": addr,
                    "chain": "solana",
                    "total_balance_usd": total_balance_usd,
                    "total_sol_equivalent": total_sol_equivalent,
                    "balance_sol": sol_balance,
                    "token_balances": token_balances,
                    "token_exchange_rates_sol": token_exchange_rates,
                    "sol_price_usd": sol_price_usd,
                    "source": "Solana RPC / Jupiter / CoinGecko",
                }
            except requests.exceptions.RequestException as e:
                is_network = isinstance(
                    e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                )
                print_error(
                    f"Network error fetching Solana wallet info for {addr[:6]}...: {e}",
                    is_network_issue=is_network,
                )
            except (KeyError, ValueError, json.JSONDecodeError, IndexError) as e:
                print_error(f"Processing Solana wallet data for {addr[:6]}...: {e}")
            except Exception as e:
                print_error(f"Unexpected error fetching Solana info for {addr[:6]}...: {e}")
            return None

        return await self._run_sync_in_thread(fetch_sol_sync, address)

    @cached_wallet_data(
        ttl=CACHE_TTL_FAST
    )  # Cache for 2 minutes - Trading positions change frequently
    async def get_hyperliquid_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetches account info from Hyperliquid API (via thread)."""

        def fetch_hl_sync(addr):
            try:
                payload = {"type": "clearinghouseState", "user": addr}
                response = requests.post(HYPERLIQUID_API_URL, json=payload, timeout=20)
                response.raise_for_status()
                data = response.json()

                if not isinstance(data, dict):
                    print_error(
                        f"Unexpected response type from Hyperliquid for {addr[:6]}...: {type(data)}"
                    )
                    return None

                margin_summary = data.get("marginSummary")
                asset_positions = data.get("assetPositions")

                if margin_summary is None or asset_positions is None:
                    # Check if it's an empty account response
                    if isinstance(data.get("meta"), list) and not data["meta"]:
                        # Account exists but has no state (0 balance, no positions)
                        return {
                            "address": addr,
                            "platform": "hyperliquid",
                            "total_balance": 0.0,
                            "open_positions": [],
                            "source": "Hyperliquid API",
                        }
                    else:
                        print_error(
                            f"Missing 'marginSummary' or 'assetPositions' in Hyperliquid response for {addr[:6]}..."
                        )
                        return None

                balance_usd = safe_float_convert(margin_summary.get("accountValue", 0))
                position_info = []
                if isinstance(asset_positions, list):
                    for position in asset_positions:
                        try:
                            if not isinstance(position, dict):
                                continue
                            pos_data = position.get("position")
                            if not isinstance(pos_data, dict):
                                continue
                            size_str = pos_data.get("szi")
                            if size_str is None:
                                continue
                            size_float = safe_float_convert(size_str)
                            # Filter out dust positions
                            if abs(size_float) < 1e-9:
                                continue

                            asset_symbol = pos_data.get("coin") or position.get("asset")
                            if asset_symbol:
                                asset_symbol = str(asset_symbol).upper()
                            else:
                                asset_symbol = "UNKNOWN"

                            position_info.append(
                                {
                                    "asset": asset_symbol,
                                    "size": size_float,
                                    "entry_price": safe_float_convert(pos_data.get("entryPx", 0)),
                                    "unrealized_pnl": safe_float_convert(
                                        pos_data.get("unrealizedPnl", 0)
                                    ),
                                    # Leverage is scaled by 1e4 in the API response
                                    "leverage": safe_float_convert(
                                        pos_data.get("leverage", {}).get("value", 0)
                                    )
                                    / 1e4,
                                    "liquidation_price": safe_float_convert(
                                        pos_data.get("liquidationPx", 0)
                                    ),
                                }
                            )
                        except Exception as e:
                            print_warning(
                                f"Processing a Hyperliquid position for {addr[:6]}...: {e}"
                            )

                return {
                    "address": addr,
                    "platform": "hyperliquid",
                    "total_balance": balance_usd,
                    "open_positions": position_info,
                    "source": "Hyperliquid API",
                }
            except requests.exceptions.RequestException as e:
                is_network = isinstance(
                    e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                )
                print_error(
                    f"HTTP Error fetching Hyperliquid info for {addr[:6]}...: {e}",
                    is_network_issue=is_network,
                )
            except json.JSONDecodeError as e:
                print_error(
                    f"JSON Decode Error fetching Hyperliquid info for {addr[:6]}...: {e} - Response: {response.text if 'response' in locals() else 'N/A'}"
                )
            except Exception as e:
                print_error(f"Unexpected error fetching Hyperliquid info for {addr[:6]}...: {e}")
            return None

        return await self._run_sync_in_thread(fetch_hl_sync, address)

    @cached_wallet_data(ttl=CACHE_TTL_FAST)
    async def get_lighter_account_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetch account info from Lighter perp DEX."""

        def fetch_lighter_sync(addr: str) -> Optional[Dict[str, Any]]:
            try:
                try:
                    addr = Web3.to_checksum_address(addr)
                except ValueError:
                    addr = addr.strip()
                response = requests.get(
                    LIGHTER_ACCOUNT_ENDPOINT,
                    params={"by": "l1_address", "value": addr},
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()

                if payload.get("code") != 200:
                    print_warning(
                        f"Lighter returned code {payload.get('code')} for {addr[:6]}...: {payload.get('message')}"
                    )
                    return None

                accounts = payload.get("accounts") or []
                if not accounts:
                    print_info(f"Lighter account response empty for {addr[:6]}...")
                    return None

                account_data = accounts[0]
                total_asset_value = safe_float_convert(account_data.get("total_asset_value", 0))
                available_balance = safe_float_convert(account_data.get("available_balance", 0))
                collateral = safe_float_convert(account_data.get("collateral", 0))

                positions_raw = account_data.get("positions", []) or []
                positions = []
                for pos in positions_raw:
                    try:
                        position_size = safe_float_convert(pos.get("position", 0))
                        position_value = safe_float_convert(pos.get("position_value", 0))
                        # Determine directional sign if provided by API
                        sign_field = pos.get("sign")
                        if sign_field is not None:
                            try:
                                sign_value = float(sign_field)
                                if sign_value < 0:
                                    position_size = -abs(position_size)
                                    position_value = -abs(position_value)
                                elif sign_value > 0:
                                    position_size = abs(position_size)
                                    position_value = abs(position_value)
                            except (ValueError, TypeError):
                                pass
                        if abs(position_size) < 1e-9 and abs(position_value) < 1e-6:
                            continue
                        positions.append(
                            {
                                "symbol": pos.get("symbol"),
                                "position": position_size,
                                "position_value": position_value,
                                "avg_entry_price": safe_float_convert(
                                    pos.get("avg_entry_price", 0)
                                ),
                                "unrealized_pnl": safe_float_convert(pos.get("unrealized_pnl", 0)),
                                "realized_pnl": safe_float_convert(pos.get("realized_pnl", 0)),
                                "liquidation_price": safe_float_convert(
                                    pos.get("liquidation_price", 0)
                                ),
                                "margin_mode": pos.get("margin_mode"),
                            }
                        )
                    except Exception as exc:
                        print_warning(f"Error processing Lighter position for {addr[:6]}...: {exc}")

                return {
                    "address": addr,
                    "platform": "lighter",
                    "total_balance": total_asset_value,
                    "available_balance": available_balance,
                    "collateral": collateral,
                    "positions": positions,
                    "source": "Lighter API",
                }
            except requests.exceptions.RequestException as e:
                print_error(
                    f"HTTP error fetching Lighter info for {addr[:6]}...: {e}",
                    is_network_issue=isinstance(
                        e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
                    ),
                )
            except json.JSONDecodeError as e:
                print_error(
                    f"JSON decode error fetching Lighter info for {addr[:6]}...: {e}",
                )
            except Exception as e:
                print_error(f"Unexpected error fetching Lighter info for {addr[:6]}...: {e}")
            return None

        return await self._run_sync_in_thread(fetch_lighter_sync, address)

    def _fetch_polygon_token_balance(self, account: str, token_address: str, decimals: int) -> float:
        """Fetch ERC-20 token balance on Polygon using a lightweight eth_call."""
        try:
            account_checksum = Web3.to_checksum_address(account)
            token_checksum = Web3.to_checksum_address(token_address)
        except ValueError:
            return 0.0

        data_field = "0x70a08231" + account_checksum[2:].rjust(64, "0")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": token_checksum, "data": data_field}, "latest"],
        }
        try:
            response = requests.post(POLYGON_RPC_URL, json=payload, timeout=20)
            response.raise_for_status()
            result = response.json().get("result")
            if not result:
                return 0.0
            raw_value = int(result, 16)
            divisor = 10 ** decimals
            return raw_value / divisor if divisor else float(raw_value)
        except requests.exceptions.RequestException as exc:
            print_error(f"Error fetching Polygon token balance: {exc}")
        except (ValueError, TypeError):
            print_warning(
                "Unexpected response while parsing Polygon token balance for Polymarket."
            )
        return 0.0

    @cached_wallet_data(ttl=CACHE_TTL_MEDIUM)
    async def get_polymarket_account_info(self, owner_address: str) -> Optional[Dict[str, Any]]:
        """Fetch Polymarket positions and USDC balances for a tracked owner wallet."""

        def fetch_polymarket_sync(owner: str) -> Optional[Dict[str, Any]]:
            try:
                owner_checksum = Web3.to_checksum_address(owner)
            except ValueError:
                owner_checksum = owner

            proxy_address = (
                self.polymarket_proxies.get(owner_checksum)
                or self.polymarket_proxies.get(owner_checksum.lower())
            )
            if not proxy_address:
                print_warning(
                    f"Polymarket proxy not configured for owner {owner_checksum[:8]}.... Skipping."
                )
                return {
                    "platform": "polymarket",
                    "address": owner_checksum,
                    "proxy": None,
                    "total_balance": 0.0,
                    "usdc_balance": 0.0,
                    "positions_value": 0.0,
                    "positions": [],
                    "error": "proxy_not_configured",
                    "source": "Polymarket Data API",
                }

            try:
                proxy_checksum = Web3.to_checksum_address(proxy_address)
            except ValueError:
                print_error(
                    f"Invalid proxy address configured for Polymarket owner {owner_checksum}"
                )
                return {
                    "platform": "polymarket",
                    "address": owner_checksum,
                    "proxy": proxy_address,
                    "total_balance": 0.0,
                    "usdc_balance": 0.0,
                    "positions_value": 0.0,
                    "positions": [],
                    "error": "invalid_proxy",
                    "source": "Polymarket Data API",
                }

            try:
                response = requests.get(
                    POLYMARKET_POSITIONS_ENDPOINT,
                    params={"user": proxy_checksum},
                    timeout=20,
                )
                response.raise_for_status()
                positions_data = response.json()
                if not isinstance(positions_data, list):
                    raise ValueError("Unexpected Polymarket response structure")
            except requests.exceptions.RequestException as exc:
                print_error(
                    f"HTTP error fetching Polymarket positions for {proxy_checksum[:8]}...: {exc}"
                )
                return None
            except ValueError as exc:
                print_error(f"Error parsing Polymarket response: {exc}")
                return None

            normalized_positions: List[Dict[str, Any]] = []
            total_current_value = 0.0
            total_initial_value = 0.0
            total_cash_pnl = 0.0

            for position in positions_data:
                if not isinstance(position, dict):
                    continue
                current_val = safe_float_convert(position.get("currentValue", 0.0))
                initial_val = safe_float_convert(position.get("initialValue", 0.0))
                cash_pnl = safe_float_convert(position.get("cashPnl", 0.0))
                redeemable_flag = bool(position.get("redeemable"))
                # Filter out settled/redeemable positions with no remaining value
                if redeemable_flag and current_val <= 0.01:
                    continue

                normalized_positions.append(
                    {
                        "title": position.get("title"),
                        "slug": position.get("slug"),
                        "outcome": position.get("outcome"),
                        "size": safe_float_convert(position.get("size", 0.0)),
                        "avg_price": safe_float_convert(position.get("avgPrice", 0.0)),
                        "current_price": safe_float_convert(position.get("curPrice", 0.0)),
                        "current_value": current_val,
                        "initial_value": initial_val,
                        "cash_pnl": cash_pnl,
                        "percent_pnl": safe_float_convert(position.get("percentPnl", 0.0)),
                        "redeemable": redeemable_flag,
                        "mergeable": bool(position.get("mergeable")),
                        "end_date": position.get("endDate"),
                        "condition_id": position.get("conditionId"),
                        "asset": position.get("asset"),
                    }
                )
                total_current_value += current_val
                total_initial_value += initial_val
                total_cash_pnl += cash_pnl

            usdc_balance = self._fetch_polygon_token_balance(
                proxy_checksum, POLYMARKET_USDC_CONTRACT, 6
            )
            total_balance = total_current_value + usdc_balance
            unrealized_pnl = total_current_value - total_initial_value

            return {
                "platform": "polymarket",
                "address": owner_checksum,
                "proxy": proxy_checksum,
                "total_balance": total_balance,
                "positions_value": total_current_value,
                "usdc_balance": usdc_balance,
                "positions": normalized_positions,
                "metadata": {
                    "initial_value": total_initial_value,
                    "cash_pnl": total_cash_pnl,
                    "unrealized_pnl": unrealized_pnl,
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "Polymarket Data API",
            }

        return await self._run_sync_in_thread(fetch_polymarket_sync, owner_address)

    async def get_ethereum_wallet_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Fetches Ethereum wallet info by scraping DeBank using Playwright.
        Robust implementation with proper page load waiting, retry mechanisms, and content validation.
        """
        # Removed excessive warning message: print_warning(f"Fetching Ethereum data for {address[:6]}... via DeBank scraping (robust implementation)...")

        # Multiple selectors for better reliability
        balance_selectors = [
            ".HeaderInfo_totalAssetInner__HyrdC",
            '[data-testid="total-asset"]',
            ".total-asset",
            ".HeaderInfo_totalAsset__",
            ".total-balance",
            '[class*="totalAsset"]',
            '[class*="TotalAsset"]',
            '[class*="headerInfo"]',
            ".asset-value",
            ".portfolio-value",
            ".HeaderInfo_totalAsset__WcFLB",
            ".HeaderInfo_totalAssetInner__4Gdgw",
        ]

        # User agents for rotation
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        max_retries = 3

        for attempt in range(max_retries):
            if attempt > 0:
                print_info(f"Retry attempt {attempt + 1}/{max_retries} for {address[:6]}...")
                await asyncio.sleep(5)  # Wait between retries

            async with async_playwright() as p:
                browser = None
                page = None
                context = None

                # Ensure the data/screenshots directory exists
                os.makedirs("data/screenshots", exist_ok=True)

                # Save screenshot to data/screenshots directory
                screenshot_path = f"data/screenshots/debank_error_{address}_{datetime.now().strftime('%Y%m%d%H%M%S')}_attempt{attempt+1}.png"

                try:
                    import random

                    user_agent = random.choice(user_agents)

                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-web-security",
                            "--disable-features=VizDisplayCompositor",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                        ],
                    )

                    context = await browser.new_context(
                        user_agent=user_agent,
                        viewport={"width": 1920, "height": 1080},
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            "Accept-Encoding": "gzip, deflate, br",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                            "Connection": "keep-alive",
                            "Upgrade-Insecure-Requests": "1",
                            "Cache-Control": "no-cache",
                            "Pragma": "no-cache",
                        },
                    )

                    page = await context.new_page()
                    url = DEBANK_URL_TEMPLATE.format(address)
                    if attempt == 0:  # Only log on first attempt
                        print_info(f"Fetching DeBank data for {address[:6]}...")

                    # Navigate with longer timeout and better wait strategy
                    await page.goto(url, wait_until="domcontentloaded", timeout=120000)

                    # Check if redirected to login page immediately
                    current_url = page.url
                    if "login" in current_url or "auth" in current_url:
                        print_warning(
                            f"Redirected to login page for {address[:6]}.... DeBank might be blocking automated access."
                        )
                        if DEBANK_SCREENSHOT_ON_ERROR:
                            await page.screenshot(path=screenshot_path)
                        continue  # Try next attempt

                    # Wait for basic page structure
                    await page.wait_for_selector("body", timeout=60000)

                    # Progressive waiting strategy - wait for multiple indicators
                    content_loaded = False

                    # Strategy 1: Wait for specific balance container elements
                    for selector in balance_selectors[:5]:  # Try first 5 selectors
                        try:
                            await page.wait_for_selector(selector, timeout=15000)
                            content_loaded = True
                            break
                        except:
                            continue

                    # Strategy 2: Wait for any dollar amount to appear in the page
                    if not content_loaded:
                        try:
                            await page.wait_for_function(
                                """() => {
                                    const text = document.body.innerText;
                                    return text.includes('$') && /\\$[\\d,]+/.test(text);
                                }""",
                                timeout=20000,
                            )
                            content_loaded = True
                        except:
                            pass

                    # Strategy 3: Wait for network idle (additional loading)
                    if not content_loaded:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=15000)
                            content_loaded = True
                        except:
                            pass

                    # Final wait to ensure all dynamic content is loaded
                    await asyncio.sleep(8)  # Reduced but still allowing for final loading

                    # Additional check: wait for any meaningful balance text to appear
                    try:
                        await page.wait_for_function(
                            """() => {
                                const elements = document.querySelectorAll('*');
                                for (let el of elements) {
                                    const text = el.textContent || '';
                                    if (text.match(/\\$[\\d,]+\\.?[\\d]*/) && parseFloat(text.replace(/[^\\d.]/g, '')) > 0) {
                                        return true;
                                    }
                                }
                                return false;
                            }""",
                            timeout=10000,
                        )
                    except Exception:
                        pass

                    # Try multiple selectors to find the total balance element
                    total_balance_element = None
                    used_selector = None

                    for selector in balance_selectors:
                        try:
                            elements = await page.query_selector_all(selector)
                            for element in elements:
                                if element:
                                    text = await element.inner_text()
                                    # Check if this element contains a dollar amount
                                    if re.search(r"\$[\d,]+", text):
                                        total_balance_element = element
                                        used_selector = selector
                                        break
                            if total_balance_element:
                                break
                        except Exception as e:
                            continue

                    # Fallback approach - look for any element containing dollar signs and numbers
                    if not total_balance_element:
                        print_warning(
                            f"Standard selectors failed, trying comprehensive fallback approach for {address[:6]}..."
                        )

                        # More comprehensive fallback search
                        try:
                            all_elements = await page.query_selector_all("*")
                            for element in all_elements:
                                try:
                                    text = await element.inner_text()
                                    # Look for dollar amounts that could be balances
                                    dollar_match = re.search(r"\$[\d,]+\.?\d*", text)
                                    if dollar_match:
                                        # Extract the number and check if it's reasonable
                                        amount_str = (
                                            dollar_match.group().replace("$", "").replace(",", "")
                                        )
                                        amount = safe_float_convert(amount_str, 0.0)
                                        if amount > 0:  # Found a positive dollar amount
                                            total_balance_element = element
                                            used_selector = "comprehensive_fallback_search"
                                            print_info(
                                                f"Found balance using comprehensive fallback: {text}"
                                            )
                                            break
                                except:
                                    continue
                        except Exception as e:
                            print_warning(f"Comprehensive fallback failed: {e}")

                    if not total_balance_element:
                        print_error(
                            f"Could not find total balance element for {address[:6]}... with any method"
                        )
                        if DEBANK_SCREENSHOT_ON_ERROR:
                            await page.screenshot(path=screenshot_path)
                        continue  # Try next attempt

                    # Get the balance text
                    total_balance_text = await total_balance_element.inner_text()
                    print_info(f"Raw balance text for {address[:6]}...: {total_balance_text}")

                    # Enhanced balance parsing with multiple regex patterns
                    balance_patterns = [
                        r"\$?([\d,]+\.?\d*)\s*([-+]?\d+\.?\d*%)?",  # Standard pattern
                        r"Total\s*:?\s*\$?([\d,]+\.?\d*)",  # "Total: $123.45"
                        r"Portfolio\s*:?\s*\$?([\d,]+\.?\d*)",  # "Portfolio: $123.45"
                        r"Assets?\s*:?\s*\$?([\d,]+\.?\d*)",  # "Assets: $123.45"
                        r"Net\s*Worth\s*:?\s*\$?([\d,]+\.?\d*)",  # "Net Worth: $123.45"
                        r"Balance\s*:?\s*\$?([\d,]+\.?\d*)",  # "Balance: $123.45"
                        r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",  # Just numbers with commas
                    ]

                    numerical_balance = None
                    percentage_change = "N/A"

                    for pattern in balance_patterns:
                        balance_match = re.search(pattern, total_balance_text, re.IGNORECASE)
                        if balance_match:
                            try:
                                numerical_balance = safe_float_convert(
                                    balance_match.group(1).replace(",", ""), 0.0
                                )
                                if len(balance_match.groups()) > 1 and balance_match.group(2):
                                    percentage_change = balance_match.group(2)
                                print_info(
                                    f"Successfully parsed balance using pattern: {pattern} -> ${numerical_balance}"
                                )
                                break
                            except (ValueError, IndexError):
                                continue

                    # Validate the balance - if it's 0 and we expect non-zero, this might be a loading issue
                    if numerical_balance is None or numerical_balance == 0:
                        print_warning(
                            f"Got zero or invalid balance for {address[:6]}... - text: '{total_balance_text}'"
                        )
                        if attempt < max_retries - 1:
                            print_info("This might indicate incomplete page loading, will retry...")
                            if DEBANK_SCREENSHOT_ON_ERROR:
                                await page.screenshot(path=screenshot_path)
                            continue  # Try next attempt
                        else:
                            print_error(
                                f"Final attempt failed to get valid balance for {address[:6]}..."
                            )
                            return None

                    # Try to get additional metadata with improved selectors
                    token_count = "N/A"
                    protocol_count = "N/A"

                    try:
                        # Multiple approaches to get token count
                        token_selectors = [
                            '.HeaderInfo_metaItem__KGTCP >> text="Tokens" >> xpath=./following-sibling::div',
                            '[data-testid="token-count"]',
                            "text=/Tokens?\\s*:?\\s*(\\d+)/",
                            ".token-count",
                            ".tokens-number",
                            ".TokenList_tokenCount__",
                            '.meta-item:has-text("Tokens")',
                        ]

                        for selector in token_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    text = await element.inner_text()
                                    # Extract number from text
                                    number_match = re.search(r"\d+", text)
                                    if number_match:
                                        token_count = number_match.group()
                                        break
                            except:
                                continue

                        # Multiple approaches to get protocol count
                        protocol_selectors = [
                            '.HeaderInfo_metaItem__KGTCP >> text="Protocols" >> xpath=./following-sibling::div',
                            '[data-testid="protocol-count"]',
                            "text=/Protocols?\\s*:?\\s*(\\d+)/",
                            ".protocol-count",
                            ".protocols-number",
                            ".ProtocolList_protocolCount__",
                            '.meta-item:has-text("Protocols")',
                        ]

                        for selector in protocol_selectors:
                            try:
                                element = await page.query_selector(selector)
                                if element:
                                    text = await element.inner_text()
                                    # Extract number from text
                                    number_match = re.search(r"\d+", text)
                                    if number_match:
                                        protocol_count = number_match.group()
                                        break
                            except:
                                continue

                    except Exception as e:
                        print_warning(f"Could not fetch metadata for {address[:6]}...: {e}")

                    print_success(
                        f"Successfully extracted data for {address[:6]}... from DeBank (attempt {attempt + 1}, selector: {used_selector})"
                    )
                    return {
                        "address": address,
                        "chain": "ethereum",
                        "total_balance": numerical_balance,
                        "percentage_change": percentage_change,
                        "token_count": token_count,
                        "protocol_count": protocol_count,
                        "source": "DeBank (Scraped)",
                        "selector_used": used_selector,
                        "attempts_made": attempt + 1,
                    }

                except PlaywrightTimeoutError as e:  # Renamed variable to e for consistency
                    print_error(
                        f"Timeout error while waiting for elements on DeBank page for {address[:6]}.... (attempt {attempt + 1})",
                        is_network_issue=True,
                    )
                    if DEBANK_SCREENSHOT_ON_ERROR and page:
                        await page.screenshot(path=screenshot_path)
                except Exception as e:
                    print_error(
                        f"Error fetching Ethereum wallet info for {address[:6]}... from DeBank (attempt {attempt + 1}): {e}"
                    )
                    if DEBANK_SCREENSHOT_ON_ERROR and page:
                        await page.screenshot(path=screenshot_path)
                finally:
                    try:
                        if page:
                            await page.close()
                        if context:
                            await context.close()
                        if browser:
                            await browser.close()
                    except:
                        pass  # Ignore cleanup errors

        # If all attempts failed, return None
        print_warning(
            f"DeBank scraping failed for {address[:6]}... after {max_retries} attempts. Ethereum data will be missing."
        )
        if DEBANK_SCREENSHOT_ON_ERROR:
            print_info(f"Screenshots saved for debugging if errors occurred.")
        return None

    async def get_all_wallets_and_platforms_info(self) -> List[Dict[str, Any]]:
        """Fetches info for all tracked wallets and enabled platforms concurrently."""
        tasks = []
        any_tasks = False

        # Count wallets by chain for summary
        chain_counts = {}
        for chain, addresses in self.wallets.items():
            if addresses:
                chain_counts[chain] = len(addresses)
                for address in addresses:
                    fetch_func = getattr(self, f"get_{chain}_wallet_info", None)
                    if fetch_func:
                        if chain == "ethereum" and self.skip_basic_ethereum:
                            pass
                        else:
                            tasks.append(fetch_func(address))
                            any_tasks = True
                    else:
                        print_warning(f"No fetch function found for chain: {chain}")

                    # Add Hyperliquid/Lighter tasks specifically for Ethereum addresses if enabled
                    if chain == "ethereum" and address in self.hyperliquid_enabled:
                        tasks.append(self.get_hyperliquid_info(address))
                        any_tasks = True
                    if chain == "ethereum" and address in self.lighter_enabled:
                        tasks.append(self.get_lighter_account_info(address))
                        any_tasks = True
                    if chain == "ethereum" and address in self.polymarket_enabled:
                        tasks.append(self.get_polymarket_account_info(address))
                        any_tasks = True

        if not any_tasks:
            print_info("No wallets or platforms configured for fetching.")
            return []

        # Show concise summary instead of listing each task
        chain_summary = ", ".join([f"{chain}: {count}" for chain, count in chain_counts.items()])
        print_info(f"Scanning wallets: {chain_summary}")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, filtering out None and logging errors
        final_results = []
        successful_fetches = 0
        failed_fetches = 0
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                print_error(f"Task {i} failed with an unexpected exception: {res}")
                traceback.print_exception(type(res), res, res.__traceback__)
                failed_fetches += 1
            elif res is not None:
                final_results.append(res)
                successful_fetches += 1
            else:
                failed_fetches += 1

        if failed_fetches > 0:
            print_warning(f"Wallet scan: {successful_fetches} succeeded, {failed_fetches} failed")
        else:
            print_success(f"✅ All {successful_fetches} wallet sources scanned successfully")

        return final_results


# --- CEX Balance Fetching Functions (Sync - consider async alternatives) ---
