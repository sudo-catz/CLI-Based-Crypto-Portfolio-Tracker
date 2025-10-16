# -*- coding: utf-8 -*-
"""
Exposure Tracking Module
------------------------
Tracks portfolio exposure across different dimensions including:
1. Non-stable asset percentage of total portfolio
2. Consolidated asset breakdown (sum same assets across platforms)
3. Composition within non-stable assets

This module integrates with the existing portfolio analysis system
and saves exposure data alongside portfolio metrics.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import json
import re

# Import utilities for consistent formatting
from utils.helpers import safe_float_convert, format_currency


@dataclass
class AssetExposure:
    """Represents exposure data for a single asset."""

    symbol: str
    total_quantity: float
    total_value_usd: float
    percentage_of_portfolio: float
    percentage_of_non_stable: float
    platforms: Dict[str, float]  # platform -> value mapping
    is_stable: Optional[bool]  # None for neutral assets
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExposureTracker:
    """Tracks and analyzes portfolio exposure across multiple dimensions."""

    def __init__(self):
        # Define what we consider stable assets
        self.stable_assets = {
            "USDT",
            "USDC",
            "DAI",
            "BUSD",
            "TUSD",
            "USDP",
            "FRAX",
            "FDUSD",
            "USDD",
            "LUSD",
            "SUSD",
            "sUSD",
            "MIM",
            "HUSD",
            "USDE",
            "USDAI",
            "USDT0",
            "USDR",
            "USDL",
            "USDX",
            "USDM",
            "EUSD",
            "PYUSD",
            "GUSD",
            "CRVUSD",
            "CUSDC",
            # Mixed stablecoins from EVM wallet breakdown
            "STABLECOINS_EVM",
        }

        # CEX Mixed assets - these should be neutral (neither stable nor non-stable)
        # since we don't know their composition. Use uppercase to match normalization.
        self.neutral_assets = {
            "CEX_MIXED_BINANCE",
            "CEX_MIXED_OKX",
            "CEX_MIXED_BYBIT",
            "CEX_MIXED_BACKPACK",
        }

        # Common asset mappings for consolidation
        self.asset_aliases = {
            "WETH": "ETH",
            "WBTC": "BTC",
            "WSOL": "SOL",
            "stETH": "ETH",  # Treat as ETH exposure
            "cbETH": "ETH",
            "rETH": "ETH",
        }

        # Precompute normalized lookup tables for stability and neutrality checks
        self._stable_lookup = {symbol.replace(" ", "").upper() for symbol in self.stable_assets}
        self._neutral_lookup = {symbol.replace(" ", "").upper() for symbol in self.neutral_assets}

    def _normalize_symbol(self, symbol: Optional[str]) -> str:
        """Normalize asset symbols for consistent comparisons."""
        if not symbol:
            return ""
        cleaned = symbol.strip()
        if "(" in cleaned:
            cleaned = cleaned.split("(", 1)[0]
        if "." in cleaned:
            cleaned = cleaned.split(".", 1)[0]
        cleaned = cleaned.replace(" ", "").replace(")", "")
        return cleaned.upper()

    def _format_margin_symbol(self, platform_name: str, reserve: bool = False) -> str:
        """Generate consistent margin identifiers for exposure tracking."""
        platform_key = (platform_name or "").strip().lower()
        custom_map = {
            "binance usdm futures": "BINANCE_USDM",
            "binance coinm futures": "BINANCE_COINM",
            "hyperliquid": "HYPERLIQUID",
            "lighter": "LIGHTER",
        }
        base = custom_map.get(platform_key)
        if not base:
            base = re.sub(r"[^a-zA-Z0-9]+", "_", platform_name or "").strip("_").upper()
            if not base:
                base = "MARGIN"
        prefix = "MARGIN_RESERVE_" if reserve else "MARGIN_"
        return prefix + base

    def _is_stable_symbol(self, symbol: str) -> Optional[bool]:
        """
        Determine if a symbol should be treated as stable, non-stable, or neutral.
        Returns:
            True  -> Stable asset
            False -> Non-stable asset
            None  -> Neutral / unknown composition
        """
        clean = self._normalize_symbol(symbol)
        if not clean:
            return False

        if clean in self._neutral_lookup:
            return None
        if clean in self._stable_lookup:
            return True

        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            if parts and all(self._is_stable_symbol(part) is True for part in parts):
                return True

        if clean.startswith("STABLE_") or clean.endswith("_STABLE"):
            return True

        return False

    def analyze_portfolio_exposure(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for exposure analysis.
        Returns comprehensive exposure data for the 3 requested metrics.
        """
        # Extract crypto prices for quantity calculations
        crypto_prices = portfolio_data.get("crypto_prices", {})

        # Check if we have analysis folder context and preserve it
        analysis_folder = portfolio_data.get("_analysis_folder")

        # Extract all assets from portfolio data
        consolidated_assets = self._consolidate_assets(portfolio_data, crypto_prices)

        # Calculate total portfolio value - use the raw total without offset adjustments
        total_portfolio_value = portfolio_data.get(
            "total_portfolio_value", 0
        ) or portfolio_data.get("total_value", 0)

        if total_portfolio_value <= 0:
            return {
                "error": "No positive portfolio value found",
                "total_portfolio_value": 0,
                "stable_value": 0,
                "non_stable_value": 0,
                "consolidated_assets": {},
                "non_stable_assets": {},
                "stable_assets": {},
                "asset_count": 0,
                "stable_asset_count": 0,
                "non_stable_asset_count": 0,
                "neutral_asset_count": 0,
                "crypto_prices_snapshot": crypto_prices,
            }

        # Separate stable vs non-stable assets
        stable_assets, non_stable_assets, neutral_assets = self._categorize_assets(
            consolidated_assets, total_portfolio_value
        )

        # Calculate metrics
        total_stable_value = sum(asset.total_value_usd for asset in stable_assets.values())
        total_non_stable_value = sum(asset.total_value_usd for asset in non_stable_assets.values())
        # Ensure percentages add up to 100% (account for rounding errors)
        total_accounted_value = total_stable_value + total_non_stable_value
        if total_accounted_value > 0:
            stable_percentage = (total_stable_value / total_accounted_value) * 100
            non_stable_percentage = (total_non_stable_value / total_accounted_value) * 100
        else:
            stable_percentage = 0
            non_stable_percentage = 0

        # Metric 2 & 3: Asset breakdown and composition
        asset_breakdown = self._create_asset_breakdown(
            consolidated_assets, total_portfolio_value, crypto_prices
        )

        return {
            "total_portfolio_value": total_portfolio_value,
            "consolidated_assets": {
                **asset_breakdown["stable_assets"],
                **asset_breakdown["non_stable_assets"],
            },
            "stable_assets": asset_breakdown["stable_assets"],
            "non_stable_assets": asset_breakdown["non_stable_assets"],
            "stable_value": asset_breakdown["total_stable_value"],
            "non_stable_value": asset_breakdown["total_non_stable_value"],
            "total_stable_value": asset_breakdown["total_stable_value"],
            "total_non_stable_value": asset_breakdown["total_non_stable_value"],
            "stable_percentage": (
                (asset_breakdown["total_stable_value"] / total_portfolio_value * 100)
                if total_portfolio_value > 0
                else 0
            ),
            "non_stable_percentage": asset_breakdown["non_stable_percentage"],
            "crypto_prices_snapshot": crypto_prices,
            "asset_count": len(consolidated_assets),
            "stable_asset_count": len(stable_assets),
            "non_stable_asset_count": len(non_stable_assets),
            "neutral_asset_count": len(neutral_assets),
            "debug_info": {
                "total_consolidated_value": sum(
                    asset.total_value_usd for asset in consolidated_assets.values()
                ),
                "scaling_factor_applied": None,
                "assets_processed": len(consolidated_assets),
            },
        }

    def _consolidate_assets(
        self, portfolio_data: Dict[str, Any], crypto_prices: Dict[str, float]
    ) -> Dict[str, AssetExposure]:
        """
        Consolidate same assets across all platforms and wallets.
        This handles the core logic for summing SOL from wallet + exchanges, etc.
        """
        consolidated = {}

        # Process CEX balances
        self._process_cex_balances(consolidated, portfolio_data, crypto_prices)

        # Process wallet balances
        self._process_wallet_balances(consolidated, portfolio_data, crypto_prices)

        # Process DeFi positions (like Hyperliquid)
        self._process_defi_positions(consolidated, portfolio_data, crypto_prices)

        return consolidated

    def _process_cex_balances(
        self,
        consolidated: Dict[str, AssetExposure],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ):
        """Process balances from centralized exchanges."""
        # First try to use detailed exchange data for accurate asset categorization
        detailed_data = portfolio_data.get("detailed_breakdowns", {})
        exchanges_with_detailed_data = set()

        # Process detailed exchange data if available
        exchange_details = {
            "binance_details": ("CEX_Binance", "binance_balance"),
            "okx_details": ("CEX_OKX", "okx_balance"),
            "bybit_details": ("CEX_Bybit", "bybit_balance"),
            "backpack_details": ("CEX_Backpack", "backpack_balance"),
        }

        for detail_key, (platform, balance_key) in exchange_details.items():
            exchange_data = detailed_data.get(detail_key, {})
            if isinstance(exchange_data, dict) and "assets" in exchange_data:
                assets = exchange_data.get("assets", [])
                any_assets_processed = False

                for asset in assets:
                    if isinstance(asset, dict):
                        asset_symbol = asset.get("coin", "").upper()
                        # Use different value keys depending on exchange format
                        value = (
                            asset.get("usd_value") or asset.get("equity") or asset.get("total", 0)
                        )
                        value = safe_float_convert(value)

                        # Extract quantity from exchange data if available
                        quantity = safe_float_convert(asset.get("total", 0))

                        if asset_symbol and value > 0.01:  # Filter dust
                            self._add_to_consolidated(
                                consolidated, asset_symbol, quantity, value, platform, crypto_prices
                            )
                            any_assets_processed = True

                # Track that this exchange was processed in detail
                if any_assets_processed:
                    exchanges_with_detailed_data.add(balance_key)

            if detail_key == "binance_details":
                self._process_binance_futures_positions(
                    consolidated,
                    detailed_data,
                    portfolio_data,
                    crypto_prices,
                )
            elif detail_key == "okx_details":
                self._process_okx_futures_positions(
                    consolidated,
                    detailed_data,
                    portfolio_data,
                    crypto_prices,
                )
            elif detail_key == "bybit_details":
                self._process_bybit_futures_positions(
                    consolidated,
                    detailed_data,
                    portfolio_data,
                    crypto_prices,
                )

        # Process simple balances only for exchanges WITHOUT detailed data
        exchange_balance_mappings = {
            "binance_balance": "CEX_Mixed_Binance",
            "okx_balance": "CEX_Mixed_OKX",
            "bybit_balance": "CEX_Mixed_Bybit",
            "backpack_balance": "CEX_Mixed_Backpack",
        }

        for balance_key, asset_symbol in exchange_balance_mappings.items():
            # Only process if this exchange wasn't handled via detailed data
            if balance_key not in exchanges_with_detailed_data:
                value = safe_float_convert(portfolio_data.get(balance_key, 0))
                if value > 0.01:
                    platform = f"CEX_{asset_symbol.split('_')[-1]}"
                    self._add_to_consolidated(
                        consolidated, asset_symbol, 0, value, platform, crypto_prices
                    )

        # Always process non-CEX simple balances (wallets, etc.)
        self._process_non_cex_simple_balances(consolidated, portfolio_data, crypto_prices)

    def _process_binance_futures_positions(
        self,
        consolidated: Dict[str, AssetExposure],
        detailed_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ) -> None:
        """Map Binance futures balances into margin exposures."""
        account_types_data = detailed_data.get("binance_account_types") or {}
        if isinstance(account_types_data, dict):
            account_type_map = account_types_data.get("account_types") or {}
        else:
            account_type_map = {}

        futures_positions_data = detailed_data.get("binance_futures_positions") or {}
        if not isinstance(futures_positions_data, dict):
            futures_positions_data = {}

        usd_m_positions = futures_positions_data.get("usd_m") or []
        coin_m_positions = futures_positions_data.get("coin_m") or []

        # Convert to list of dicts if not already
        if not isinstance(usd_m_positions, list):
            usd_m_positions = []
        if not isinstance(coin_m_positions, list):
            coin_m_positions = []

        usd_m_account_value = safe_float_convert(account_type_map.get("USD-M Futures", 0))
        coin_m_account_value = safe_float_convert(account_type_map.get("Coin-M Futures", 0))

        # Fallback to legacy totals if account types weren't available
        if usd_m_account_value <= 0 and coin_m_account_value <= 0:
            account_totals_raw = portfolio_data.get("binance_account_totals_raw")
            if isinstance(account_totals_raw, (list, tuple)) and account_totals_raw:
                # account_totals_raw structure: [total_all_accounts, spot_balance, futures_balance?]
                total_all_accounts = safe_float_convert(
                    account_totals_raw[0] if len(account_totals_raw) > 0 else 0
                )
                spot_balance = safe_float_convert(
                    account_totals_raw[1] if len(account_totals_raw) > 1 else 0
                )
                explicit_futures = safe_float_convert(
                    account_totals_raw[2] if len(account_totals_raw) > 2 else 0
                )

                if explicit_futures > 0:
                    usd_m_account_value = explicit_futures
                elif total_all_accounts > 0:
                    derived_futures = max(total_all_accounts - spot_balance, 0.0)
                    if derived_futures > 0:
                        usd_m_account_value = derived_futures

        has_usd_positions = any(isinstance(pos, dict) for pos in usd_m_positions)
        has_coin_positions = any(isinstance(pos, dict) for pos in coin_m_positions)

        if usd_m_account_value > 0.01 or has_usd_positions:
            self._process_margin_positions(
                consolidated,
                usd_m_account_value,
                usd_m_positions,
                crypto_prices,
                platform_name="Binance USDM Futures",
                symbol_key="symbol",
                value_key="position_value",
            )

        if coin_m_account_value > 0.01 or has_coin_positions:
            self._process_margin_positions(
                consolidated,
                coin_m_account_value,
                coin_m_positions,
                crypto_prices,
                platform_name="Binance CoinM Futures",
                symbol_key="symbol",
                value_key="position_value",
            )

    def _process_okx_futures_positions(
        self,
        consolidated: Dict[str, AssetExposure],
        detailed_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ) -> None:
        """Map OKX futures balances into margin exposures."""
        positions_data = detailed_data.get("okx_futures_positions") or {}
        if isinstance(positions_data, dict):
            positions = positions_data.get("positions") or []
        elif isinstance(positions_data, list):
            positions = positions_data
        else:
            positions = []

        valid_positions = [pos for pos in positions if isinstance(pos, dict)]
        if not valid_positions:
            return

        account_value = 0.0
        okx_details = detailed_data.get("okx_details") or {}
        assets = okx_details.get("assets") or []
        if isinstance(assets, list):
            for asset in assets:
                if isinstance(asset, dict):
                    account_value += max(safe_float_convert(asset.get("frozen", 0.0)), 0.0)

        if account_value <= 0.0:
            account_value = sum(
                max(safe_float_convert(pos.get("margin")), 0.0)
                for pos in valid_positions
                if pos.get("margin") is not None
            )

        if account_value <= 0.0:
            account_value = sum(
                max(safe_float_convert(pos.get("initial_margin")), 0.0)
                for pos in valid_positions
                if pos.get("initial_margin") is not None
            )

        if account_value <= 0.0:
            for pos in valid_positions:
                notional = safe_float_convert(pos.get("position_value"), 0.0)
                leverage = safe_float_convert(pos.get("leverage"), 0.0)
                if notional <= 0:
                    continue
                if leverage > 0:
                    account_value += notional / leverage
                else:
                    account_value += notional

        self._process_margin_positions(
            consolidated,
            account_value,
            valid_positions,
            crypto_prices,
            platform_name="OKX Futures",
            symbol_key="symbol",
            value_key="position_value",
        )

    def _process_bybit_futures_positions(
        self,
        consolidated: Dict[str, AssetExposure],
        detailed_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ) -> None:
        """Map Bybit futures balances into margin exposures."""
        positions_data = detailed_data.get("bybit_futures_positions") or {}
        if isinstance(positions_data, dict):
            positions = positions_data.get("positions") or []
        elif isinstance(positions_data, list):
            positions = positions_data
        else:
            positions = []

        valid_positions = [pos for pos in positions if isinstance(pos, dict)]
        if not valid_positions:
            return

        account_value = sum(
            max(safe_float_convert(pos.get("margin")), 0.0)
            for pos in valid_positions
            if pos.get("margin") is not None
        )

        if account_value <= 0.0:
            account_value = sum(
                max(safe_float_convert(pos.get("initial_margin")), 0.0)
                for pos in valid_positions
                if pos.get("initial_margin") is not None
            )

        if account_value <= 0.0:
            for pos in valid_positions:
                notional = safe_float_convert(pos.get("position_value"), 0.0)
                leverage = safe_float_convert(pos.get("leverage"), 0.0)
                if notional <= 0:
                    continue
                if leverage > 0:
                    account_value += notional / leverage
                else:
                    account_value += notional

        self._process_margin_positions(
            consolidated,
            account_value,
            valid_positions,
            crypto_prices,
            platform_name="Bybit Futures",
            symbol_key="symbol",
            value_key="position_value",
        )

    def _process_non_cex_simple_balances(
        self,
        consolidated: Dict[str, AssetExposure],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ):
        """Process simple balance totals for non-CEX sources only."""
        # Check which chains have detailed wallet data to avoid double-counting
        wallet_data = portfolio_data.get("wallet_platform_data_raw", [])
        chains_with_detailed_data = set()

        # Check if Portfolio Summary Statistics are available and will be used for EVM
        portfolio_summary_stats = self._load_portfolio_summary_stats(portfolio_data)
        will_use_portfolio_summary_stats = False

        if portfolio_summary_stats:
            # Check if there are ethereum wallets that would trigger Portfolio Summary Statistics usage
            for wallet_info in wallet_data:
                if (
                    isinstance(wallet_info, dict)
                    and wallet_info.get("chain", "").lower() == "ethereum"
                ):
                    total_balance = (
                        wallet_info.get("total_balance", 0)
                        or wallet_info.get("total_balance_usd", 0)
                        or 0
                    )
                    if total_balance > 0:
                        will_use_portfolio_summary_stats = True
                        break

        for wallet_info in wallet_data:
            if isinstance(wallet_info, dict):
                chain = wallet_info.get("chain", "").lower()
                # Check for balance using the appropriate field for each chain
                if chain == "solana":
                    total_balance = wallet_info.get("total_balance_usd", 0)
                else:
                    total_balance = wallet_info.get("total_balance", 0)

                # Consider a chain as having detailed data if it has wallet entries with meaningful balances
                if total_balance > 0.01:
                    chains_with_detailed_data.add(chain)

        # Map non-CEX balance keys only, with chain mapping for double-counting prevention
        balance_mappings = {
            "bitcoin_balance": ("BTC", "bitcoin"),
            "solana_balance": ("SOL", "solana"),
            "hyperliquid_balance": ("USDC", None),  # Hyperliquid fallback if no detailed data
        }

        for balance_key, (asset_symbol, chain) in balance_mappings.items():
            # Skip if we have detailed wallet data for this chain
            if chain and chain in chains_with_detailed_data:
                continue

            value = safe_float_convert(portfolio_data.get(balance_key, 0))
            if value > 0.01:
                if balance_key == "hyperliquid_balance":
                    # Skip if detailed platform data exists, otherwise treat as margin reserve
                    has_detailed_hyperliquid = any(
                        isinstance(info, dict)
                        and (info.get("platform") or "").lower() == "hyperliquid"
                        for info in wallet_data
                    )
                    if has_detailed_hyperliquid:
                        continue

                    platform = "Hyperliquid"
                    margin_symbol = self._format_margin_symbol(platform, reserve=True)
                    self._add_to_consolidated(
                        consolidated,
                        margin_symbol,
                        0,
                        value,
                        platform,
                        crypto_prices,
                        metadata={
                            "is_margin_reserve": True,
                            "source_platform": platform,
                            "force_is_stable": True,
                        },
                    )
                else:
                    platform = "Wallet"
                    self._add_to_consolidated(
                        consolidated, asset_symbol, 0, value, platform, crypto_prices
                    )

    def _process_wallet_balances(
        self,
        consolidated: Dict[str, AssetExposure],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ):
        """Process individual wallet balances."""
        wallet_data = portfolio_data.get("wallet_platform_data_raw", [])

        # Try to load Portfolio Summary Statistics for enhanced EVM wallet processing
        portfolio_summary_stats = self._load_portfolio_summary_stats(portfolio_data)
        evm_processed = False

        if portfolio_summary_stats:
            try:
                from utils.helpers import print_info

                print_info(
                    "🔄 Using Portfolio Summary Statistics for enhanced EVM wallet breakdown"
                )
            except ImportError:
                pass  # Silently fail if import not available

        for wallet_info in wallet_data:
            if not isinstance(wallet_info, dict):
                continue

            chain = wallet_info.get("chain", "").lower()
            total_balance = (
                wallet_info.get("total_balance", 0) or wallet_info.get("total_balance_usd", 0) or 0
            )

            if total_balance <= 0:
                continue

            # Handle different chain types
            if chain == "ethereum":
                # Try to use Portfolio Summary Statistics for proper asset breakdown
                if portfolio_summary_stats and not evm_processed:
                    success = self._process_evm_with_summary_stats(
                        consolidated, portfolio_summary_stats, crypto_prices
                    )
                    if success:
                        evm_processed = True
                        continue  # Skip the fallback ETH processing

                # If Portfolio Summary Statistics were already processed successfully, skip all subsequent ethereum wallets
                if evm_processed:
                    continue  # Portfolio Summary Statistics already contain all EVM wallet data

                # IMPORTANT: Skip ethereum wallet processing if Portfolio Summary Statistics are not available
                # This prevents treating the entire combined EVM balance as pure ETH (800% inflation issue)
                # The refresh function will handle proper asset breakdown when Portfolio Summary Statistics are generated
                if not portfolio_summary_stats:
                    continue  # Skip - let refresh handle detailed breakdown

                # This fallback should now rarely be reached, but kept for edge cases
                self._add_to_consolidated(
                    consolidated, "ETH", 0, total_balance, "Wallet_ethereum", crypto_prices
                )

            elif chain == "bitcoin":
                btc_balance = wallet_info.get("balance_btc", 0)
                self._add_to_consolidated(
                    consolidated, "BTC", btc_balance, total_balance, "Wallet_bitcoin", crypto_prices
                )
            elif chain == "solana":
                # Only count actual SOL balance, not SOL equivalent (which includes other tokens)
                sol_balance = wallet_info.get("balance_sol", 0)
                sol_price = crypto_prices.get("SOL", 0)
                sol_value_usd = sol_balance * sol_price if sol_price > 0 else 0

                # Only add SOL if we have actual SOL balance
                if sol_balance > 0:
                    self._add_to_consolidated(
                        consolidated,
                        "SOL",
                        sol_balance,
                        sol_value_usd,
                        "Wallet_solana",
                        crypto_prices,
                    )

                # Handle token balances separately (USDC, USDT, etc.)
                token_balances = wallet_info.get("token_balances", {})
                for token_symbol, token_amount in token_balances.items():
                    if token_amount > 0 and token_symbol.upper() in ["USDC", "USDT"]:
                        # Assume stablecoins are worth $1 each (for wallet tokens)
                        self._add_to_consolidated(
                            consolidated,
                            token_symbol.upper(),
                            token_amount,
                            token_amount,
                            "Wallet_solana",
                            crypto_prices,
                        )

    def _process_defi_positions(
        self,
        consolidated: Dict[str, AssetExposure],
        portfolio_data: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ):
        """Process DeFi positions like Hyperliquid."""
        # Process Hyperliquid positions
        wallet_data = portfolio_data.get("wallet_platform_data_raw", [])

        for wallet_info in wallet_data:
            if not isinstance(wallet_info, dict):
                continue

            # Check if this wallet entry is actually a platform/protocol entry
            platform = wallet_info.get("platform")
            if platform == "hyperliquid":
                # Hyperliquid platform data
                account_value = safe_float_convert(wallet_info.get("total_balance", 0))
                positions = (
                    wallet_info.get("positions", wallet_info.get("open_positions", [])) or []
                )
                self._process_margin_positions(
                    consolidated,
                    account_value,
                    positions,
                    crypto_prices,
                    platform_name="Hyperliquid",
                )

            elif platform == "lighter":
                account_value = safe_float_convert(wallet_info.get("total_balance", 0))
                positions = wallet_info.get("positions", []) or []
                self._process_margin_positions(
                    consolidated,
                    account_value,
                    positions,
                    crypto_prices,
                    platform_name="Lighter",
                    symbol_key="symbol",
                    value_key="position_value",
                )
            else:
                # Check for hyperliquid data nested within wallet info
                hyperliquid_data = wallet_info.get("hyperliquid", {})
                if isinstance(hyperliquid_data, dict):
                    # Account value
                    account_value = safe_float_convert(hyperliquid_data.get("account_value", 0))
                    positions = hyperliquid_data.get("positions", [])
                    self._process_margin_positions(
                        consolidated,
                        account_value,
                        positions,
                        crypto_prices,
                        platform_name="Hyperliquid",
                    )

    def _process_margin_positions(
        self,
        consolidated: Dict[str, AssetExposure],
        account_value_raw: Any,
        positions: List[Any],
        crypto_prices: Dict[str, float],
        platform_name: str,
        symbol_key: str = "asset",
        value_key: str = "position_value",
    ) -> None:
        """Allocate derivative exposure using margin instead of notional."""
        account_value = safe_float_convert(account_value_raw, 0.0)
        valid_positions: List[Dict[str, Any]] = [pos for pos in positions if isinstance(pos, dict)]

        if not valid_positions:
            if account_value > 0.01:
                self._add_to_consolidated(
                    consolidated,
                    self._format_margin_symbol(platform_name, reserve=True),
                    0,
                    account_value,
                    platform_name,
                    crypto_prices,
                    metadata={
                        "is_margin_reserve": True,
                        "source_platform": platform_name,
                        "force_is_stable": True,
                    },
                )
            return

        margin_positions: List[Dict[str, Any]] = []
        total_notional = 0.0
        explicit_margin_total = 0.0

        for position in valid_positions:
            raw_symbol = (
                position.get(symbol_key) if symbol_key in position else position.get("asset")
            )
            symbol = (raw_symbol or "").upper()
            if not symbol:
                continue

            raw_size = safe_float_convert(position.get("size", position.get("position", 0)), 0.0)
            size = abs(raw_size)
            notional = 0.0

            if value_key and position.get(value_key) is not None:
                notional = abs(safe_float_convert(position.get(value_key, 0), 0.0))

            if notional <= 0 and size > 0:
                entry_price = safe_float_convert(
                    position.get("entry_price")
                    or position.get("avg_entry_price")
                    or position.get("entryPrice")
                    or 0,
                    0.0,
                )
                if entry_price > 0:
                    notional = size * entry_price
                else:
                    market_price = safe_float_convert(
                        position.get("mark_price")
                        or position.get("market_price")
                        or position.get("markPrice")
                        or crypto_prices.get(symbol, 0),
                        0.0,
                    )
                    if market_price > 0:
                        notional = size * market_price

            if notional <= 0:
                continue

            explicit_margin = safe_float_convert(
                position.get("margin")
                or position.get("position_margin")
                or position.get("initial_margin"),
                0.0,
            )

            entry_price = safe_float_convert(
                position.get("entry_price")
                or position.get("avg_entry_price")
                or position.get("entryPrice")
                or 0,
                0.0,
            )
            mark_price = safe_float_convert(
                position.get("mark_price")
                or position.get("market_price")
                or position.get("markPrice")
                or 0,
                0.0,
            )
            if mark_price <= 0:
                mark_price = safe_float_convert(crypto_prices.get(symbol, 0), 0.0)
            liquidation_price = safe_float_convert(
                position.get("liquidation_price") or position.get("liquidationPx") or 0, 0.0
            )
            leverage = safe_float_convert(position.get("leverage"), 0.0)
            if isinstance(position.get("leverage"), dict):
                leverage = (
                    safe_float_convert(position.get("leverage", {}).get("value", 0), 0.0) / 1e4
                )

            margin_positions.append(
                {
                    "symbol": symbol,
                    "notional": max(notional, 0.0),
                    "explicit_margin": max(explicit_margin, 0.0),
                    "raw_size": raw_size,
                    "abs_size": size,
                    "entry_price": entry_price if entry_price > 0 else None,
                    "mark_price": mark_price if mark_price > 0 else None,
                    "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                    "leverage": leverage if leverage > 0 else None,
                    "margin_mode": position.get("margin_mode"),
                    "unrealized_pnl": safe_float_convert(
                        position.get("unrealized_pnl") or position.get("unrealizedPnl") or 0, 0.0
                    ),
                }
            )
            total_notional += max(notional, 0.0)
            explicit_margin_total += max(explicit_margin, 0.0)

        if not margin_positions:
            if account_value > 0.01:
                self._add_to_consolidated(
                    consolidated,
                    self._format_margin_symbol(platform_name, reserve=True),
                    0,
                    account_value,
                    platform_name,
                    crypto_prices,
                    metadata={
                        "is_margin_reserve": True,
                        "source_platform": platform_name,
                        "force_is_stable": True,
                        "delta_neutral": True,
                    },
                )
            return

        # Determine whether the margin portfolio is effectively delta-neutral
        symbol_abs_notional: Dict[str, float] = {}
        symbol_net_notional: Dict[str, float] = {}
        for position_meta in margin_positions:
            symbol = position_meta["symbol"]
            abs_notional = position_meta["notional"]
            direction_sign = 1 if (position_meta.get("raw_size", 0) or 0) >= 0 else -1
            position_meta["direction_sign"] = direction_sign

            symbol_abs_notional[symbol] = symbol_abs_notional.get(symbol, 0.0) + abs_notional
            symbol_net_notional[symbol] = (
                symbol_net_notional.get(symbol, 0.0) + direction_sign * abs_notional
            )

        total_abs_notional = sum(symbol_abs_notional.values())
        max_symbol_net_ratio = 0.0
        if total_abs_notional > 0:
            for symbol, abs_total in symbol_abs_notional.items():
                if abs_total <= 0:
                    continue
                net_exposure = abs(symbol_net_notional.get(symbol, 0.0))
                ratio = net_exposure / abs_total if abs_total > 0 else 0.0
                if ratio > max_symbol_net_ratio:
                    max_symbol_net_ratio = ratio

        delta_neutral = (
            max_symbol_net_ratio <= 0.10
        )  # Treat as stable if each asset nets out within 10%

        allocation_base = account_value if account_value > 0 else explicit_margin_total
        margin_total = 0.0

        margin_symbol = self._format_margin_symbol(platform_name, reserve=False)
        for position_meta in margin_positions:
            symbol = position_meta["symbol"]
            notional = position_meta["notional"]
            explicit_margin = position_meta["explicit_margin"]
            if explicit_margin > 0:
                margin_value = explicit_margin
            elif allocation_base > 0 and total_notional > 0:
                margin_value = allocation_base * (notional / total_notional)
            else:
                margin_value = 0.0

            margin_value = max(margin_value, 0.0)
            if margin_value <= 0.01:
                continue

            margin_underlying_entry = {
                "symbol": symbol,
                "direction": "Long" if (position_meta.get("raw_size", 0) or 0) >= 0 else "Short",
                "abs_size": position_meta.get("abs_size"),
                "size": position_meta.get("raw_size"),
                "direction_sign": position_meta.get("direction_sign"),
                "entry_price": position_meta.get("entry_price"),
                "mark_price": position_meta.get("mark_price"),
                "liquidation_price": position_meta.get("liquidation_price"),
                "notional_value": notional,
                "margin_value": margin_value,
                "margin_mode": position_meta.get("margin_mode"),
                "unrealized_pnl": position_meta.get("unrealized_pnl"),
                "platform": platform_name,
            }
            leverage = position_meta.get("leverage")
            if not leverage and margin_value > 0:
                leverage = notional / margin_value if margin_value > 0 else None
            if leverage:
                margin_underlying_entry["leverage"] = leverage

            margin_total += margin_value
            position_pnl = safe_float_convert(position_meta.get("unrealized_pnl", 0))
            self._add_to_consolidated(
                consolidated,
                margin_symbol,
                0,
                margin_value,
                platform_name,
                crypto_prices,
                metadata={
                    "is_margin_position": True,
                    "source_platform": platform_name,
                    "margin_underlyings": {symbol: margin_value},
                    "margin_underlying_details": [margin_underlying_entry],
                    "force_is_stable": delta_neutral,
                    "delta_neutral": delta_neutral,
                    "net_exposure_ratio": max_symbol_net_ratio,
                    "total_unrealized_pnl": position_pnl,
                },
                unrealized_pnl_delta=position_pnl,
            )

        if account_value > 0:
            residual_collateral = max(account_value - margin_total, 0.0)
            if residual_collateral > 0.01:
                reserve_symbol = self._format_margin_symbol(platform_name, reserve=True)
                self._add_to_consolidated(
                    consolidated,
                    reserve_symbol,
                    0,
                    residual_collateral,
                    platform_name,
                    crypto_prices,
                    metadata={
                        "is_margin_reserve": True,
                        "source_platform": platform_name,
                        "force_is_stable": True,
                        "delta_neutral": True,
                    },
                )

    def _add_to_consolidated(
        self,
        consolidated: Dict[str, AssetExposure],
        asset_symbol: str,
        quantity: float,
        value: float,
        platform: str,
        crypto_prices: Dict[str, float],
        metadata: Optional[Dict[str, Any]] = None,
        unrealized_pnl_delta: float = 0.0,
    ):
        """Helper to add asset data to consolidated tracking."""
        # Normalize asset symbol
        base_symbol = self.asset_aliases.get(asset_symbol, asset_symbol)
        normalized_symbol = self._normalize_symbol(base_symbol)

        if not normalized_symbol:
            return

        lookup_candidates = [
            normalized_symbol,
            self._normalize_symbol(asset_symbol),
            base_symbol.upper() if isinstance(base_symbol, str) else "",
            asset_symbol.upper() if isinstance(asset_symbol, str) else "",
        ]

        price = 0.0
        for key in lookup_candidates:
            if not key:
                continue
            candidate_price = safe_float_convert(crypto_prices.get(key, 0))
            if candidate_price > 0:
                price = candidate_price
                break

        # Calculate quantity if not provided and we have price data
        if quantity == 0 and value > 0:
            if price > 0:
                quantity = value / price
            elif self._is_stable_symbol(normalized_symbol) is True:
                # For major stablecoins, assume $1.00 if no market price available
                quantity = value / 1.0

        if metadata:
            metadata = metadata.copy()
        else:
            metadata = {}

        if normalized_symbol not in consolidated:
            # Determine if asset is stable or neutral
            is_stable = self._is_stable_symbol(normalized_symbol)
            if normalized_symbol == "OTHER_TOKENS":
                is_stable = False  # Explicitly treat OTHER_TOKENS as non-stable
            force_is_stable = metadata.get("force_is_stable") if metadata else None
            if force_is_stable is not None:
                is_stable = force_is_stable

            consolidated[normalized_symbol] = AssetExposure(
                symbol=normalized_symbol,
                total_quantity=0,
                total_value_usd=0,
                percentage_of_portfolio=0,  # Will calculate later
                percentage_of_non_stable=0,  # Will calculate later
                platforms={},
                is_stable=is_stable,
                metadata={},
            )
        else:
            force_is_stable = metadata.get("force_is_stable") if metadata else None
            if force_is_stable is not None:
                consolidated[normalized_symbol].is_stable = force_is_stable

        asset_exposure = consolidated[normalized_symbol]

        self._merge_metadata(asset_exposure.metadata, metadata)
        force_is_stable = metadata.get("force_is_stable")
        if force_is_stable is not None:
            asset_exposure.is_stable = force_is_stable
        # For margin positions, use aggregated delta neutrality to drive stability
        margin_flag = (
            metadata.get("is_margin_position")
            or metadata.get("is_margin_reserve")
            or asset_exposure.metadata.get("is_margin_position")
            or asset_exposure.metadata.get("is_margin_reserve")
        )
        if margin_flag:
            delta_flag = asset_exposure.metadata.get("delta_neutral")
            if delta_flag is True:
                asset_exposure.is_stable = True
            elif delta_flag is False:
                asset_exposure.is_stable = False

        asset_exposure.total_quantity += quantity
        asset_exposure.total_value_usd += value

        if platform in asset_exposure.platforms:
            asset_exposure.platforms[platform] += value
        else:
            asset_exposure.platforms[platform] = value

        if unrealized_pnl_delta:
            current_pnl = safe_float_convert(asset_exposure.metadata.get("total_unrealized_pnl", 0))
            new_total_pnl = current_pnl + unrealized_pnl_delta
            asset_exposure.metadata["total_unrealized_pnl"] = new_total_pnl
            platform_pnl = asset_exposure.metadata.setdefault("platform_unrealized_pnl", {})
            platform_pnl[platform] = platform_pnl.get(platform, 0.0) + unrealized_pnl_delta

    def _categorize_assets(
        self, consolidated_assets: Dict[str, AssetExposure], total_portfolio_value: float
    ) -> tuple:
        """Separate assets into stable and non-stable categories."""
        stable_assets = {}
        non_stable_assets = {}
        neutral_assets = {}  # CEX mixed assets that we can't categorize

        for symbol, asset in consolidated_assets.items():
            # Update percentage calculations
            asset.percentage_of_portfolio = (asset.total_value_usd / total_portfolio_value) * 100

            if asset.is_stable is True:
                stable_assets[symbol] = asset
            elif asset.is_stable is False:
                non_stable_assets[symbol] = asset
            else:  # is_stable is None (neutral)
                neutral_assets[symbol] = asset

        # Calculate percentage within non-stable assets
        total_non_stable_value = sum(asset.total_value_usd for asset in non_stable_assets.values())
        if total_non_stable_value > 0:
            for asset in non_stable_assets.values():
                asset.percentage_of_non_stable = (
                    asset.total_value_usd / total_non_stable_value
                ) * 100

        return stable_assets, non_stable_assets, neutral_assets

    def _merge_metadata(self, target: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """Merge metadata dictionaries with special handling for nested structures."""
        if not updates:
            return

        for key, value in updates.items():
            if key == "force_is_stable":
                continue
            if key == "margin_underlyings" and isinstance(value, dict):
                existing = target.setdefault("margin_underlyings", {})
                for sym, amt in value.items():
                    try:
                        amt_val = float(amt)
                    except (TypeError, ValueError):
                        amt_val = 0.0
                    existing[sym] = existing.get(sym, 0.0) + amt_val
            elif key == "margin_underlying_details" and isinstance(value, list):
                existing_details = target.setdefault("margin_underlying_details", [])
                existing_details.extend(value)
            elif key == "delta_neutral":
                if "delta_neutral" in target:
                    target["delta_neutral"] = bool(target["delta_neutral"]) and bool(value)
                else:
                    target["delta_neutral"] = bool(value)
            elif key == "platform_unrealized_pnl" and isinstance(value, dict):
                platform_map = target.setdefault("platform_unrealized_pnl", {})
                for plat, pnl in value.items():
                    try:
                        pnl_val = float(pnl)
                    except (TypeError, ValueError):
                        pnl_val = 0.0
                    platform_map[plat] = platform_map.get(plat, 0.0) + pnl_val
            elif key == "total_unrealized_pnl":
                try:
                    pnl_val = float(value)
                except (TypeError, ValueError):
                    pnl_val = 0.0
                existing_total = safe_float_convert(target.get(key, 0))
                target[key] = existing_total + pnl_val
            else:
                target[key] = value

    def _create_asset_breakdown(
        self,
        consolidated_assets: Dict[str, AssetExposure],
        total_portfolio_value: float,
        crypto_prices: Dict[str, float],
    ) -> Dict[str, Any]:
        """Create the final breakdown with categories, metrics, and enhanced data."""
        stable_assets = {}
        non_stable_assets = {}

        for symbol, asset_data in consolidated_assets.items():
            total_quantity = asset_data.total_quantity
            total_value = asset_data.total_value_usd

            # Get market price from crypto_prices, or calculate implied price
            market_price = crypto_prices.get(symbol)
            implied_price = None

            # Calculate implied price if we have quantity and value but no market price
            if market_price is None and total_quantity > 0 and total_value > 0:
                implied_price = total_value / total_quantity
                # Use implied price as the current price for display
                current_price = implied_price
            elif market_price is None and symbol in [
                "USDT",
                "USDC",
                "DAI",
                "BUSD",
                "TUSD",
                "USDP",
                "FRAX",
                "FDUSD",
                "USDD",
                "LUSD",
            ]:
                # For major stablecoins without market price, assume $1.00
                current_price = 1.0
            else:
                current_price = market_price

            metadata_copy = asset_data.metadata.copy() if asset_data.metadata else {}
            asset_info = {
                "symbol": symbol,
                "total_quantity": total_quantity,
                "current_price": current_price,
                "market_price": market_price,  # Keep track of actual market price vs implied
                "implied_price": implied_price,  # Store calculated price for reference
                "total_value_usd": total_value,
                "percentage_of_portfolio": (
                    (total_value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
                ),
                "platforms": asset_data.platforms,
                "is_stable": asset_data.is_stable,
                "platform_count": len(asset_data.platforms),
                "metadata": metadata_copy,
            }
            total_unrealized_pnl = safe_float_convert(metadata_copy.get("total_unrealized_pnl", 0))
            if total_unrealized_pnl != 0:
                asset_info["total_unrealized_pnl"] = total_unrealized_pnl
            platform_pnl_map = metadata_copy.get("platform_unrealized_pnl")
            if isinstance(platform_pnl_map, dict):
                asset_info["platform_unrealized_pnl"] = {
                    k: safe_float_convert(v) for k, v in platform_pnl_map.items()
                }
            if metadata_copy.get("margin_underlying_details"):
                asset_info["margin_underlying_details"] = metadata_copy.get(
                    "margin_underlying_details"
                )

            if asset_data.is_stable:
                stable_assets[symbol] = asset_info
            else:
                non_stable_assets[symbol] = asset_info

        # Calculate non-stable percentages
        total_non_stable_value = sum(
            asset["total_value_usd"] for asset in non_stable_assets.values()
        )
        for asset_info in non_stable_assets.values():
            asset_info["percentage_of_non_stable"] = (
                (asset_info["total_value_usd"] / total_non_stable_value * 100)
                if total_non_stable_value > 0
                else 0
            )

        return {
            "stable_assets": stable_assets,
            "non_stable_assets": non_stable_assets,
            "total_non_stable_value": total_non_stable_value,
            "total_stable_value": sum(asset["total_value_usd"] for asset in stable_assets.values()),
            "non_stable_percentage": (
                (total_non_stable_value / total_portfolio_value * 100)
                if total_portfolio_value > 0
                else 0
            ),
        }

    def _get_native_asset_symbol(self, chain: str) -> str:
        """Map chain names to their native asset symbols."""
        chain_mappings = {
            "ethereum": "ETH",
            "bitcoin": "BTC",
            "solana": "SOL",
        }
        return chain_mappings.get(chain.lower(), chain.upper())

    def _empty_exposure_result(self) -> Dict[str, Any]:
        """Return empty result structure when no data available."""
        return {
            "total_portfolio_value": 0,
            "stable_value": 0,
            "non_stable_value": 0,
            "non_stable_percentage": 0,
            "stable_percentage": 0,
            "consolidated_assets": {},
            "stable_assets": {},
            "non_stable_assets": {},
            "neutral_assets": {},
            "analysis_timestamp": datetime.now().isoformat(),
            "asset_count": 0,
            "stable_asset_count": 0,
            "non_stable_asset_count": 0,
            "neutral_asset_count": 0,
        }

    def _load_portfolio_summary_stats(
        self, portfolio_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Load Portfolio Summary Statistics if available.
        This provides the correct asset breakdown for EVM wallets.
        """
        try:
            # Try to get analysis folder from portfolio data context
            analysis_folder = None

            # Check if we have analysis folder context (from refresh operations)
            if hasattr(portfolio_data, "get") and "_analysis_folder" in portfolio_data:
                analysis_folder = portfolio_data["_analysis_folder"]

            # If no analysis folder, try to find the most recent one
            if not analysis_folder:
                try:
                    from combined_wallet_integration import find_most_recent_analysis_folder

                    analysis_folder = find_most_recent_analysis_folder()
                except ImportError:
                    pass

            if not analysis_folder:
                return None

            # Try to load Portfolio Summary Statistics
            from utils.portfolio_summary_extractor import load_portfolio_summary_stats

            summary_stats = load_portfolio_summary_stats(analysis_folder)

            if summary_stats:
                return summary_stats

        except Exception as e:
            # Silently fail - this is an enhancement, not a requirement
            pass

        return None

    def _process_evm_with_summary_stats(
        self,
        consolidated: Dict[str, AssetExposure],
        portfolio_summary_stats: Dict[str, Any],
        crypto_prices: Dict[str, float],
    ) -> bool:
        """
        Process EVM wallet balances using Portfolio Summary Statistics.
        This provides the correct asset breakdown instead of treating everything as ETH.
        """
        try:
            # Process major non-stable positions (direct format from Portfolio Summary Statistics)
            major_positions = portfolio_summary_stats.get("major_non_stable_positions", {})
            positions_processed = 0

            for symbol, position_data in major_positions.items():
                if isinstance(position_data, dict):
                    symbol = symbol.upper()
                    quantity = position_data.get("amount", 0)
                    value_usd = position_data.get("usd_value", 0)

                    if symbol and value_usd > 0:
                        # Add to consolidated tracking with EVM wallet platform
                        self._add_to_consolidated(
                            consolidated,
                            symbol,
                            quantity,
                            value_usd,
                            "Wallet_ethereum",
                            crypto_prices,
                        )
                        positions_processed += 1

            # Process stablecoins from the stable_total
            stable_total = portfolio_summary_stats.get("stable_total", 0)
            if stable_total > 0:
                # Add as mixed stablecoins from EVM wallets rather than assuming all USDC
                # This provides accurate representation that it's a mix of stablecoins
                self._add_to_consolidated(
                    consolidated,
                    "STABLECOINS_EVM",
                    stable_total,
                    stable_total,
                    "Wallet_ethereum",
                    crypto_prices,
                )
                positions_processed += 1

            # Process other positions (smaller amounts, but still significant)
            other_positions = portfolio_summary_stats.get("other_positions", {})
            if isinstance(other_positions, dict):
                other_value = other_positions.get("total_value", 0)

                # Add other positions as a mixed category if the value is meaningful (>$1)
                # Since we don't know the specific composition, treat as mixed non-stable assets
                if other_value > 1.0:
                    # Add as "Other Tokens" to indicate mixed composition
                    self._add_to_consolidated(
                        consolidated,
                        "OTHER_TOKENS",
                        0,
                        other_value,
                        "Wallet_ethereum",
                        crypto_prices,
                    )
                    positions_processed += 1

            # Success if we processed any data
            return positions_processed > 0

        except Exception as e:
            # If anything goes wrong, fall back to the original method
            return False


def get_exposure_summary(exposure_data: Dict[str, Any]) -> str:
    """Generate a quick text summary of exposure analysis."""
    if not exposure_data or exposure_data.get("total_portfolio_value", 0) <= 0:
        return "No exposure data available"

    non_stable_pct = safe_float_convert(exposure_data.get("non_stable_percentage", 0))
    asset_count_raw = exposure_data.get("non_stable_asset_count", 0)
    try:
        asset_count = int(asset_count_raw) if asset_count_raw is not None else 0
    except (ValueError, TypeError):
        asset_count = int(safe_float_convert(asset_count_raw, 0))

    risk_level = "Low" if non_stable_pct < 30 else "Medium" if non_stable_pct < 70 else "High"

    return (
        f"Portfolio Risk Exposure: {non_stable_pct:.1f}% in {asset_count} "
        f"non-stable assets ({risk_level} risk profile)"
    )
