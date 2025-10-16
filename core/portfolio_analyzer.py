# -*- coding: utf-8 -*-
"""
Portfolio Analysis and Calculation Module
-----------------------------------------
Contains core business logic for portfolio analysis, metrics calculation,
and data persistence. This module handles the orchestration of data fetching
and the computation of portfolio metrics.
"""

import asyncio
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from colorama import Fore, Style

# Import configuration and utilities
from config.constants import *
from utils.helpers import print_error, print_warning, print_info, print_success, safe_float_convert
from api_clients.cex_balances import get_binance_overall_balance
from api_clients.exchange_balances import (
    get_okx_detailed_balance,
    get_bybit_detailed_balance,
    get_backpack_detailed_balance,
    get_okx_total_balance_async,
    get_bybit_total_balance,
    get_binance_detailed_balance,
    get_binance_account_types_breakdown,
    get_okx_account_types_breakdown,
    get_bybit_account_types_breakdown,
    get_binance_futures_positions,
    get_okx_futures_positions,
    get_bybit_futures_positions,
)
from api_clients.exchange_manager import get_backpack_balance

# from utils.price_service import price_service # Commented out

# Import performance optimization
from utils.performance_optimizer import (
    performance_optimizer,
    enable_performance_mode,
    disable_performance_mode,
)

# Import the enhanced price service and custom coin tracker
from utils.enhanced_price_service import (
    enhanced_price_service,
    get_multiple_custom_crypto_prices_async,
)
from models.custom_coins import CustomCoinTracker

# Import exposure tracking
from core.exposure_tracker import ExposureTracker, get_exposure_summary

# Try to import ETH exposure enhancement
ETH_EXPOSURE_AVAILABLE = False
ETH_EXPOSURE_SOURCE: Optional[str] = None

for candidate in (
    "eth_exposure_enhancement",
    os.path.join("reference", "eth_exposure_enhancement"),
):
    candidate_path = Path(candidate)
    if not candidate_path.exists():
        continue

    candidate_str = str(candidate_path.resolve())
    if candidate_str not in sys.path:
        sys.path.append(candidate_str)

    try:
        from data_fetcher import ETHExposureDataFetcher  # type: ignore

        ETH_EXPOSURE_AVAILABLE = True
        ETH_EXPOSURE_SOURCE = candidate_str
        break
    except ImportError:
        continue


class PortfolioAnalyzer:
    """Handles portfolio analysis, metrics calculation, and data persistence."""

    def __init__(
        self, api_module: Any, exchange_manager: Any, custom_coin_tracker: CustomCoinTracker
    ):
        self.api_module = api_module
        self.exchange_manager = exchange_manager
        self.price_service = enhanced_price_service
        self.enhanced_price_service = enhanced_price_service
        self.custom_coin_tracker = custom_coin_tracker
        # ... (rest of __init__) ...

    def save_portfolio_analysis(self, analysis_data: Dict[str, Any]):
        """Saves the portfolio analysis results to a timestamped JSON file in organized folder structure."""

        # First, check if we have ETH exposure data with an existing analysis folder
        eth_exposure_data = analysis_data.get("eth_exposure_data", {})
        existing_analysis_folder = None

        # Look for existing analysis folder from ETH exposure data
        for addr_data in eth_exposure_data.values():
            if isinstance(addr_data, dict) and "analysis_folder" in addr_data:
                existing_analysis_folder = addr_data["analysis_folder"]
                break

        if existing_analysis_folder:
            # Reuse existing folder from ETH exposure enhancement
            organized_folder = existing_analysis_folder
            print_info(f"📁 Reusing analysis folder: {organized_folder}")
        else:
            # Generate new folder (fallback behavior)
            timestamp_str = analysis_data.get("timestamp", datetime.now().isoformat())
            try:
                # Attempt to parse timestamp for filename, fallback if needed
                dt_object = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                # Convert to local timezone for filename
                local_dt = dt_object.astimezone()
                filename_ts = local_dt.strftime("%Y%m%d_%H%M%S")
            except ValueError:
                # Fallback to local time
                filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            organized_folder = f"exported_data/analysis_{filename_ts}"
            print_info(f"📁 Creating new analysis folder: {organized_folder}")

        # Ensure folder exists
        os.makedirs(organized_folder, exist_ok=True)

        # Simple filename in organized folder
        filename = f"{organized_folder}/portfolio_analysis.json"

        try:
            with open(filename, "w") as f:
                json.dump(
                    analysis_data, f, indent=2, default=str
                )  # Use default=str for non-serializable types
            print_success(f"Portfolio analysis saved to {filename}")

            # Generate combined wallet JSON if wallet breakdown files exist
            try:
                from combined_wallet_integration import generate_combined_wallet_json

                # Check if there are wallet breakdown files in this analysis folder
                wallet_files = []
                for file in os.listdir(organized_folder):
                    if file.startswith("wallet_breakdown_") and file.endswith(".json"):
                        wallet_files.append(file)

                if wallet_files:
                    print_info(
                        f"🔄 Generating combined wallet analysis from {len(wallet_files)} wallet files..."
                    )
                    combined_file = generate_combined_wallet_json(organized_folder)
                    if combined_file:
                        print_success("✅ Combined wallet analysis generated!")
                    else:
                        print_warning("⚠️ Combined wallet analysis generation failed")
                else:
                    print_info(
                        "ℹ️ No wallet breakdown files found - combined analysis not generated"
                    )

            except Exception as e:
                print_warning(f"⚠️ Combined wallet generation failed: {e}")

            # Return the analysis folder path for use in live analysis
            return organized_folder
        except IOError as e:
            print_error(f"Saving analysis to {filename}: {e}")
            return None
        except Exception as e:
            print_error(f"Unexpected error saving analysis: {e}")
            return None

    @staticmethod
    def list_analysis_files() -> List[str]:
        """Returns a sorted list of saved analysis JSON files from organized folder structure."""

        # Look for organized analysis folders
        organized_folders = glob.glob("exported_data/analysis_*/")
        files = []

        for folder in organized_folders:
            # Look for portfolio_analysis.json in each folder
            analysis_file = os.path.join(folder, "portfolio_analysis.json")
            if os.path.exists(analysis_file):
                files.append(analysis_file)

        # Also check legacy location for backward compatibility
        legacy_files = glob.glob("data/analysis/portfolio_analysis_*.json")
        files.extend(legacy_files)

        files.sort(reverse=True)  # Sort newest first
        return files

    async def fetch_all_portfolio_data(
        self,
        binance_exchange,
        wallet_tracker,
        custom_coin_tracker=None,
        quick_mode: bool = False,
    ) -> Dict[str, Any]:
        """Fetches data from all sources asynchronously with enhanced progress tracking and performance optimization."""
        # Enable performance optimization
        enable_performance_mode()

        print_info("🚀 Starting Live Portfolio Analysis")
        print_info("=" * 50)

        # Create a single analysis timestamp for the entire session to ensure consistency
        analysis_start_time = datetime.now(timezone.utc)
        analysis_timestamp_iso = analysis_start_time.isoformat()
        analysis_timestamp_folder = analysis_start_time.astimezone().strftime("%Y%m%d_%H%M%S")

        try:
            # Step 1: CEX Balances with optimized concurrent processing
            print_info("📊 Step 1/4: Fetching CEX Balances...")

            start_time = time.time()

            # Create optimized tasks for concurrent CEX balance fetching
            exchange_tasks = []
            exchange_names = []
            failed_exchanges = set()

            exchange_tasks.append(
                lambda: get_binance_overall_balance(binance_exchange, self.api_module)
            )
            exchange_names.append("Binance")

            async def okx_wrapper():
                return await get_okx_total_balance_async()

            exchange_tasks.append(okx_wrapper)
            exchange_names.append("OKX")

            exchange_tasks.append(lambda: get_bybit_total_balance(self.exchange_manager))
            exchange_names.append("Bybit")

            exchange_tasks.append(get_backpack_balance)
            exchange_names.append("Backpack")

            # Wait for all CEX balance tasks with optimized gathering
            cex_results = await performance_optimizer.optimized_gather(
                exchange_tasks, max_concurrent=4
            )

            # Process results safely with detailed status
            success_count = 0
            processed_results = {}

            for i, (name, result) in enumerate(zip(exchange_names, cex_results)):
                if isinstance(result, Exception):
                    print_error(f"   ❌ {name}: {str(result)}")
                    # Original rate limit check
                    if "429" in str(result) or "Too Many Requests" in str(result):
                        print_warning(f"      Rate limited - will retry with backoff")
                    processed_results[name] = None
                    failed_exchanges.add(name)
                elif result is not None:
                    print_success(f"   ✅ {name}: Connected successfully")
                    success_count += 1
                    processed_results[name] = result
                else:
                    print_warning(f"   ⚠️  {name}: No data returned")
                    processed_results[name] = None

            cex_time = time.time() - start_time
            print_info(
                f"   📈 CEX Progress: {success_count}/4 exchanges connected ({cex_time:.1f}s)"
            )

            # Extract results
            binance_result = processed_results.get("Binance", (None, [], (None, None, None)))
            if binance_result and not isinstance(binance_result, Exception):
                binance_total, binance_details, binance_acc_totals = binance_result
            else:
                binance_total, binance_details, binance_acc_totals = (None, [], (None, None, None))

            okx_total = processed_results.get("OKX")
            bybit_total = processed_results.get("Bybit")
            backpack_total = processed_results.get("Backpack")

            # Step 1.5: Detailed breakdowns with optimized processing
            print_info("📋 Step 1.5/4: Fetching exchange breakdowns...")
            detailed_data = {}
            breakdown_start = time.time()

            # Create tasks for detailed breakdowns
            breakdown_tasks = []
            breakdown_task_names = []

            if binance_total is not None:
                breakdown_tasks.append(get_binance_detailed_balance)
                breakdown_task_names.append("binance_details")
                breakdown_tasks.append(get_binance_account_types_breakdown)
                breakdown_task_names.append("binance_account_types")
                breakdown_tasks.append(get_binance_futures_positions)
                breakdown_task_names.append("binance_futures_positions")

            if okx_total is not None:

                async def okx_details_wrapper():
                    return await get_okx_detailed_balance()

                breakdown_tasks.append(okx_details_wrapper)
                breakdown_task_names.append("okx_details")

                async def okx_account_types_wrapper():
                    return await get_okx_account_types_breakdown()

                breakdown_tasks.append(okx_account_types_wrapper)
                breakdown_task_names.append("okx_account_types")

                async def okx_positions_wrapper():
                    return await get_okx_futures_positions()

                breakdown_tasks.append(okx_positions_wrapper)
                breakdown_task_names.append("okx_futures_positions")

            if bybit_total is not None:
                breakdown_tasks.append(lambda: get_bybit_detailed_balance(self.exchange_manager))
                breakdown_task_names.append("bybit_details")
                breakdown_tasks.append(
                    lambda: get_bybit_account_types_breakdown(self.exchange_manager)
                )
                breakdown_task_names.append("bybit_account_types")
                breakdown_tasks.append(lambda: get_bybit_futures_positions(self.exchange_manager))
                breakdown_task_names.append("bybit_futures_positions")

            if backpack_total is not None:
                breakdown_tasks.append(get_backpack_detailed_balance)
                breakdown_task_names.append("backpack_details")

            # Execute breakdown tasks with optimization
            if breakdown_tasks:
                breakdown_results = await performance_optimizer.optimized_gather(
                    breakdown_tasks, max_concurrent=6
                )

                # Process breakdown results
                for i, (task_name, result) in enumerate(
                    zip(breakdown_task_names, breakdown_results)
                ):
                    if result and not isinstance(result, Exception):
                        detailed_data[task_name] = result
                    elif isinstance(result, Exception):
                        print_error(f"   ❌ {task_name}: {str(result)}")

            breakdown_time = time.time() - breakdown_start
            print_info(
                f"   📋 Detailed Exchange Balances: {len(detailed_data)} sources processed ({breakdown_time:.1f}s)"
            )

            # Step 2: Wallet and platform balances with optimized processing
            print_info("🔗 Step 2/4: Scanning wallets and platforms...")
            wallet_count = sum(len(addresses) for addresses in wallet_tracker.wallets.values())

            # Import and create wallet fetcher
            from wallets.fetchers import WalletPlatformFetcher

            skip_basic_ethereum = (not quick_mode) and ETH_EXPOSURE_AVAILABLE
            fetcher = WalletPlatformFetcher(
                wallet_tracker.wallets,
                wallet_tracker.hyperliquid_enabled,
                getattr(wallet_tracker, "lighter_enabled", []),
                skip_basic_ethereum=skip_basic_ethereum,
            )

            wallet_start = time.time()
            wallet_data = await fetcher.get_all_wallets_and_platforms_info()
            wallet_time = time.time() - wallet_start

            # Avoid double-counting Hyperliquid data when both DeBank and direct API are used
            hyper_platform_addresses = {
                entry.get("address")
                for entry in wallet_data
                if entry.get("platform") == "hyperliquid" and entry.get("address")
            }
            if hyper_platform_addresses:
                for entry in wallet_data:
                    if entry.get("chain") == "ethereum" and isinstance(
                        entry.get("hyperliquid"), dict
                    ):
                        entry.pop("hyperliquid", None)

            # Subtract Hyperliquid balances that DeBank already includes in wallet totals
            hyperliquid_totals = {}
            for entry in wallet_data:
                if entry.get("platform") == "hyperliquid":
                    address = entry.get("address")
                    if address:
                        hyperliquid_totals[address] = hyperliquid_totals.get(
                            address, 0.0
                        ) + safe_float_convert(entry.get("total_balance", 0.0))

            if hyperliquid_totals:
                for entry in wallet_data:
                    if entry.get("chain") != "ethereum":
                        continue
                    address = entry.get("address")
                    if not address:
                        continue
                    deduction = hyperliquid_totals.get(address)
                    if not deduction:
                        continue

                    current_total = safe_float_convert(
                        entry.get("total_balance", entry.get("total_balance_usd", 0.0))
                    )
                    if current_total <= 0:
                        continue

                    removed_value = min(current_total, deduction)
                    new_total = max(current_total - removed_value, 0.0)

                    if "total_balance" in entry:
                        entry["total_balance"] = new_total
                    elif "total_balance_usd" in entry:
                        entry["total_balance_usd"] = new_total

                    entry.setdefault("adjustments", {})["hyperliquid_deduction"] = removed_value
                    hyperliquid_totals[address] -= removed_value

            # Step 2.5: ETH Exposure Enhancement (NEW)
            eth_exposure_data = {}

            # Skip the enhanced ETH exposure step when running in quick mode
            if quick_mode:
                print_info("⚡ Quick mode enabled – skipping enhanced ETH exposure data (Step 2.5)")
            elif ETH_EXPOSURE_AVAILABLE and wallet_tracker.wallets.get("ethereum"):
                print_info("🔍 Step 2.5/5: Fetching enhanced ETH exposure data...")
                if ETH_EXPOSURE_SOURCE:
                    print_info(f"   ℹ️ Using ETH exposure module from {ETH_EXPOSURE_SOURCE}")

                eth_addresses = wallet_tracker.wallets.get("ethereum", [])
                if eth_addresses:
                    print_info(f"   📊 Analyzing {len(eth_addresses)} Ethereum addresses...")

                    try:
                        # Use the consistent analysis timestamp for folder creation
                        organized_output_dir = f"exported_data/analysis_{analysis_timestamp_folder}"

                        eth_fetcher = ETHExposureDataFetcher(output_dir=organized_output_dir)
                        eth_start = time.time()

                        print_info(f"   📁 Organizing exports in: {organized_output_dir}")

                        for address in eth_addresses:
                            try:
                                print_info(f"   🔍 Fetching enhanced data for {address[:8]}...")

                                # Create export name for live analysis (shorter since we have organized folders)
                                export_name = f"wallet_breakdown_{address[:8]}.json"

                                export_data, filepath = await eth_fetcher.fetch_and_export_address(
                                    address, export_name=export_name
                                )

                                if export_data:
                                    eth_exposure_data[address] = {
                                        "export_data": export_data,
                                        "filepath": str(filepath),
                                        "timestamp": analysis_timestamp_iso,  # Use consistent timestamp
                                        "analysis_folder": organized_output_dir,
                                    }
                                    print_success(f"   ✅ Enhanced data captured for {address[:8]}")
                                else:
                                    print_warning(f"   ⚠️ No enhanced data for {address[:8]}")
                                    eth_exposure_data[address] = {
                                        "error": "No data returned",
                                        "timestamp": analysis_timestamp_iso,  # Use consistent timestamp
                                        "analysis_folder": organized_output_dir,
                                    }

                            except Exception as e:
                                print_error(
                                    f"   ❌ Error fetching enhanced data for {address[:8]}: {e}"
                                )
                                eth_exposure_data[address] = {
                                    "error": str(e),
                                    "timestamp": analysis_timestamp_iso,  # Use consistent timestamp
                                    "analysis_folder": organized_output_dir,
                                }

                        eth_time = time.time() - eth_start
                        successful_eth = len(
                            [data for data in eth_exposure_data.values() if "export_data" in data]
                        )
                        print_info(
                            f"   🔍 ETH Enhancement: {successful_eth}/{len(eth_addresses)} addresses processed ({eth_time:.1f}s)"
                        )
                        print_success(
                            f"   📁 ETH exposure data organized in: {organized_output_dir}"
                        )

                    except Exception as e:
                        print_error(f"   ❌ ETH exposure enhancement failed: {e}")
                        eth_exposure_data["enhancement_error"] = str(e)
                else:
                    print_info("   ℹ️ No Ethereum addresses to analyze")
            else:
                if not ETH_EXPOSURE_AVAILABLE:
                    print_info("   ℹ️ ETH exposure enhancement not available")
                else:
                    print_info("   ℹ️ No Ethereum addresses configured")

            print_info(
                f"   💼 Scanned: {len(wallet_data)}/{wallet_count} sources ({wallet_time:.1f}s)"
            )
            # If we skipped the basic DeBank scrape, replace Ethereum wallet entries with enhanced results
            if not quick_mode and skip_basic_ethereum and wallet_tracker.wallets.get("ethereum"):
                enhanced_entries: List[Dict[str, Any]] = []
                missing_addresses: List[str] = []
                for address in wallet_tracker.wallets.get("ethereum", []):
                    data = eth_exposure_data.get(address, {})
                    export_data = data.get("export_data") if isinstance(data, dict) else None
                    if export_data:
                        total_value = safe_float_convert(export_data.get("total_usd_value", 0.0))
                        token_count = len(export_data.get("tokens") or [])
                        protocol_count = len(export_data.get("protocols") or [])
                        enhanced_entries.append(
                            {
                                "address": address,
                                "chain": "ethereum",
                                "total_balance": total_value,
                                "token_count": token_count,
                                "protocol_count": protocol_count,
                                "source": "DeBank (Enhanced)",
                                "analysis_timestamp": export_data.get("timestamp"),
                            }
                        )
                    else:
                        missing_addresses.append(address)

                if enhanced_entries:
                    wallet_data = [
                        entry
                        for entry in wallet_data
                        if not (
                            entry.get("chain") == "ethereum"
                            and entry.get("address") in wallet_tracker.wallets.get("ethereum", [])
                        )
                    ]
                    wallet_data.extend(enhanced_entries)
                    print_success(
                        f"   ✅ Enhanced wallet entries generated for {len(enhanced_entries)} Ethereum address(es)"
                    )
                    if hyperliquid_totals:
                        for entry in wallet_data:
                            if entry.get("chain") != "ethereum":
                                continue
                            address = entry.get("address")
                            if not address:
                                continue
                            deduction = hyperliquid_totals.get(address)
                            if not deduction:
                                continue

                            current_total = safe_float_convert(
                                entry.get("total_balance", entry.get("total_balance_usd", 0.0))
                            )
                            if current_total <= 0:
                                continue

                            removed_value = min(current_total, deduction)
                            new_total = max(current_total - removed_value, 0.0)

                            if "total_balance" in entry:
                                entry["total_balance"] = new_total
                            elif "total_balance_usd" in entry:
                                entry["total_balance_usd"] = new_total

                            entry.setdefault("adjustments", {})[
                                "hyperliquid_deduction"
                            ] = removed_value
                            hyperliquid_totals[address] -= removed_value
                if missing_addresses:
                    print_warning(
                        f"   ⚠️ Enhanced Ethereum data unavailable for: {', '.join(addr[:8] for addr in missing_addresses)}"
                    )

            # Step 3: Crypto prices with caching
            print_info("💰 Step 3/5: Fetching crypto prices...")

            price_start = time.time()
            # Use self.price_service (which points to enhanced_price_service)
            prices = self.price_service.get_prices(["BTC", "ETH", "SOL", "NEAR", "APT"])

            # Fetch custom coin prices if custom coin tracker is provided
            custom_coin_prices = {}
            custom_coin_data = {}
            if custom_coin_tracker and custom_coin_tracker.custom_coins:
                custom_start = time.time()
                print_info(
                    f"   🎯 Fetching {len(custom_coin_tracker.custom_coins)} custom coin prices..."
                )

                # Get custom coin symbols
                custom_symbols = list(custom_coin_tracker.custom_coins.keys())

                # Use standard price service for consistency with major cryptos
                custom_coin_prices = await self.get_custom_coin_prices(custom_symbols)

                # Get export data for analysis
                custom_coin_data = custom_coin_tracker.export_to_dict()

                custom_time = time.time() - custom_start
                successful_custom_prices = len(custom_coin_prices)
                print_info(
                    f"   🎯 Custom coins: {successful_custom_prices}/{len(custom_coin_tracker.custom_coins)} prices fetched ({custom_time:.1f}s)"
                )

            price_time = time.time() - price_start

            if prices:
                print_success("✅ Price data fetched successfully")
                # Display fetched prices compactly
                price_summary = ", ".join(
                    [f"{symbol}: ${price:,.0f}" for symbol, price in prices.items()]
                )
                print_info(f"   {price_summary}")

                # Display custom coin prices if any
                if custom_coin_prices:
                    custom_price_summary = ", ".join(
                        [
                            f"{symbol}: ${price:.6f}"
                            for symbol, price in custom_coin_prices.items()
                            if price is not None
                        ]
                    )
                    if custom_price_summary:
                        print_info(f"   Custom: {custom_price_summary}")
            else:
                print_error("Failed to fetch crypto prices")

            total_price_count = len(prices) if prices else 0
            total_price_count += len(custom_coin_prices)
            expected_price_count = 5 + len(
                custom_coin_tracker.custom_coins if custom_coin_tracker else {}
            )
            print_info(
                f"   💱 Prices: {total_price_count}/{expected_price_count} fetched ({price_time:.1f}s)"
            )

            # Step 4: Consolidation
            print_info("📊 Step 4/5: Consolidating data...")

            # Prepare consolidated data structure with consistent timestamp
            fetched_data = {
                "failed_exchanges": failed_exchanges,
                "binance_total": binance_total,
                "binance_details": binance_details,
                "binance_account_totals": binance_acc_totals,
                "okx_total": okx_total,
                "bybit_total": bybit_total,
                "backpack_total": backpack_total,
                "wallet_data": wallet_data,
                "prices": prices,
                "custom_coin_prices": custom_coin_prices,
                "custom_coin_data": custom_coin_data,
                "detailed_data": detailed_data,
                "eth_exposure_data": eth_exposure_data,
                "timestamp": analysis_timestamp_iso,  # Add the consistent timestamp to fetched data
                "quick_mode": quick_mode,
            }

            print_success("🎉 Portfolio data collection complete!")

            # Calculate total time and performance summary
            total_time = time.time() - start_time
            print_info("=" * 50)
            print_info(f"⏱️  Total Time: {total_time:.1f}s")
            print_info(
                f"📊 CEX: {success_count}/4 • 💼 Wallets: {len(wallet_data)} • 💰 Prices: {total_price_count}/{expected_price_count}"
            )

            # Performance recommendations
            if total_time > 45:
                print_warning(
                    "⚠️  Analysis took longer than expected - this may indicate API rate limits"
                )

            return fetched_data

        except Exception as e:
            print_error(f"Critical error during portfolio data fetching: {e}")
            raise
        finally:
            # Cleanup performance optimization
            disable_performance_mode()

    def calculate_portfolio_metrics(
        self, fetched_data: Dict[str, Any], balance_offset: float, wallet_tracker
    ) -> Dict[str, Any]:
        """
        Calculates portfolio metrics from fetched data.
        Handles None values for CEX balances gracefully.
        Updated for performance-optimized data structure.
        Now includes exposure tracking analysis.
        """
        # Use new wallet_data key instead of wallet_platform_data
        wallet_data = fetched_data.get("wallet_data", [])

        # Use .get() with default 0.0 for wallet/platform data (assuming fetch success means 0 balance if not found)
        # Note: Solana data uses 'total_balance_usd', others use 'total_balance'
        balances = {
            "ethereum": sum(
                info.get("total_balance", 0.0)
                for info in wallet_data
                if info.get("chain") == "ethereum"
            ),
            "bitcoin": sum(
                info.get("total_balance", 0.0)
                for info in wallet_data
                if info.get("chain") == "bitcoin"
            ),
            "solana": sum(
                info.get("total_balance_usd", 0.0)
                for info in wallet_data
                if info.get("chain") == "solana"
            ),
            "hyperliquid": sum(
                info.get("total_balance", 0.0)
                for info in wallet_data
                if info.get("platform") == "hyperliquid"
            ),
            "lighter": sum(
                info.get("total_balance", 0.0)
                for info in wallet_data
                if info.get("platform") == "lighter"
            ),
            # Use None for CEX if fetch failed
            "binance": fetched_data.get("binance_total"),  # Can be None
            "okx": fetched_data.get("okx_total"),  # Can be None
            "bybit": fetched_data.get("bybit_total"),  # Can be None
            "backpack": fetched_data.get("backpack_total"),  # Can be None
        }

        # Calculate totals, treating None as 0 for summation but preserving None in individual entries
        total_cex = sum(
            bal
            for bal in [
                balances["binance"],
                balances["okx"],
                balances["bybit"],
                balances["backpack"],
            ]
            if bal is not None
        )
        total_defi_platforms = sum(
            bal
            for bal in [
                balances.get("hyperliquid", 0.0),
                balances.get("lighter", 0.0),
            ]
            if bal is not None
        )
        total_wallets = sum(
            bal
            for bal in [
                balances["ethereum"],
                balances["bitcoin"],
                balances["solana"],
            ]
            if bal is not None
        )

        # Calculate custom coins total value
        custom_coin_data = fetched_data.get("custom_coin_data", {})
        total_custom_coins = custom_coin_data.get("custom_coins_total_value", 0.0)

        # Grand total (unadjusted) - sum only non-None values + custom coins
        valid_balances = [b for b in balances.values() if b is not None]
        total_portfolio_value = sum(valid_balances) + total_custom_coins

        # Unrealized PnL contribution from margin exposures (if available)
        exposure_analysis = fetched_data.get("exposure_analysis") or {}
        consolidated_assets = exposure_analysis.get("consolidated_assets") or {}
        total_unrealized_pnl = 0.0
        included_platform_tokens = ("binance", "bybit")
        try:
            for asset_data in consolidated_assets.values():
                if not isinstance(asset_data, dict):
                    continue

                metadata_raw = asset_data.get("metadata")
                metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
                platform_pnl_map = metadata.get("platform_unrealized_pnl")
                if not isinstance(platform_pnl_map, dict):
                    platform_pnl_map = asset_data.get("platform_unrealized_pnl")

                pnl_contribution = 0.0
                used_platform_map = False
                if isinstance(platform_pnl_map, dict):
                    for platform_name, value in platform_pnl_map.items():
                        platform_label = str(platform_name).lower()
                        if not any(token in platform_label for token in included_platform_tokens):
                            continue
                        pnl_contribution += safe_float_convert(value, 0.0)
                    used_platform_map = True

                if not used_platform_map:
                    source_platform = (
                        str(metadata.get("source_platform", ""))
                        or str(asset_data.get("source_platform", ""))
                    ).lower()
                    if not any(token in source_platform for token in included_platform_tokens):
                        continue
                    pnl_value = metadata.get("total_unrealized_pnl")
                    if pnl_value is None:
                        pnl_value = asset_data.get("total_unrealized_pnl")
                    pnl_contribution = safe_float_convert(pnl_value, 0.0)

                total_unrealized_pnl += pnl_contribution
        except Exception:
            total_unrealized_pnl = safe_float_convert(total_unrealized_pnl, 0.0)

        total_portfolio_value_with_pnl = total_portfolio_value + total_unrealized_pnl

        # Adjusted totals
        adjusted_portfolio_value = max(total_portfolio_value - balance_offset, 0)
        adjusted_portfolio_value_with_pnl = max(total_portfolio_value_with_pnl - balance_offset, 0)

        # Identify failed sources
        failed_sources = []
        failed_exchanges = fetched_data.get("failed_exchanges", set())

        # Check CEX failures
        # A source failed if its key exists in fetched_data but the value is None
        if "Binance" in failed_exchanges:
            failed_sources.append("Binance")
        if "OKX" in failed_exchanges:
            failed_sources.append("OKX")
        if "Bybit" in failed_exchanges:
            failed_sources.append("Bybit")
        if "Backpack" in failed_exchanges:
            failed_sources.append("Backpack")

        # Check wallet/platform failures
        # Use the passed wallet_tracker instance here
        tracked_chains = [chain for chain, wallets in wallet_tracker.wallets.items() if wallets]

        for chain in tracked_chains:
            # Check if *any* wallet for this tracked chain was successfully fetched
            if not any(d.get("chain") == chain for d in wallet_data):
                failed_sources.append(chain.capitalize())

        # Check Hyperliquid specifically for tracked Ethereum wallets
        if wallet_tracker.wallets.get("ethereum"):
            # Check if *any* hyperliquid data was fetched
            if not any(d.get("platform") == "hyperliquid" for d in wallet_data):
                failed_sources.append("Hyperliquid")

        if any(
            addr in getattr(wallet_tracker, "lighter_enabled", [])
            for addr in wallet_tracker.wallets.get("ethereum", [])
        ):
            if not any(d.get("platform") == "lighter" for d in wallet_data):
                failed_sources.append("Lighter")

        metrics = {
            "timestamp": fetched_data.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            ),  # Use timestamp from fetched_data
            "adjusted_portfolio_value": adjusted_portfolio_value,
            "adjusted_portfolio_value_with_pnl": adjusted_portfolio_value_with_pnl,
            "total_portfolio_value_with_pnl": total_portfolio_value_with_pnl,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_portfolio_value": total_portfolio_value,  # Sum of successfully fetched balances
            "balance_offset": balance_offset,
            **balances,  # Includes individual balances (can be None)
            "total_cex_balance": total_cex,
            "total_defi_balance": total_wallets + total_defi_platforms,
            "total_wallet_balance": total_wallets,
            "total_custom_coins_balance": total_custom_coins,
            "crypto_prices": fetched_data.get("prices", {}),  # Updated key name
            "custom_coin_prices": fetched_data.get("custom_coin_prices", {}),
            "custom_coin_data": custom_coin_data,
            "binance_details_raw": fetched_data.get("binance_details", []),
            "binance_account_totals_raw": fetched_data.get(
                "binance_account_totals", (None, None, None)
            ),  # Elements can be None
            "wallet_platform_data_raw": wallet_data,  # Updated to use new key
            "detailed_breakdowns": fetched_data.get("detailed_data", {}),  # Updated key name
            "failed_sources": list(set(failed_sources)),  # Store unique list of failed source names
            "eth_exposure_data": fetched_data.get("eth_exposure_data", {}),  # Add ETH exposure data
            "quick_mode": fetched_data.get("quick_mode", False),
        }

        # Add exposure tracking analysis
        try:
            print_info("🎯 Analyzing portfolio exposure...")
            exposure_tracker = ExposureTracker()

            # Create portfolio data structure for exposure analysis
            portfolio_data_for_exposure = {
                "total_portfolio_value": total_portfolio_value,  # Use the correct key name
                "wallet_platform_data_raw": wallet_data,
                "detailed_breakdowns": fetched_data.get(
                    "detailed_data", {}
                ),  # Use correct key name
                "crypto_prices": fetched_data.get("prices", {}),  # Add crypto prices
                # Add individual balance mappings for fallback processing
                "binance_balance": balances.get("binance", 0) or 0,
                "okx_balance": balances.get("okx", 0) or 0,
                "bybit_balance": balances.get("bybit", 0) or 0,
                "backpack_balance": balances.get("backpack", 0) or 0,
                "bitcoin_balance": balances.get("bitcoin", 0),
                "solana_balance": balances.get("solana", 0),
                "hyperliquid_balance": balances.get("hyperliquid", 0),
                "lighter_balance": balances.get("lighter", 0),
            }

            exposure_analysis = exposure_tracker.analyze_portfolio_exposure(
                portfolio_data_for_exposure
            )

            # Add exposure data to metrics
            metrics["exposure_analysis"] = exposure_analysis

            # Add quick exposure summary for display
            exposure_summary = get_exposure_summary(exposure_analysis)
            metrics["exposure_summary"] = exposure_summary

            print_success(f"✅ Exposure analysis complete: {exposure_summary}")

            # Recalculate unrealized PnL-aware totals now that exposure data is available
            consolidated_assets = exposure_analysis.get("consolidated_assets") or {}
            total_unrealized_pnl = 0.0
            included_platform_tokens = ("binance", "bybit")
            try:
                for asset_data in consolidated_assets.values():
                    if not isinstance(asset_data, dict):
                        continue

                    metadata_raw = asset_data.get("metadata")
                    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
                    platform_pnl_map = metadata.get("platform_unrealized_pnl")
                    if not isinstance(platform_pnl_map, dict):
                        platform_pnl_map = asset_data.get("platform_unrealized_pnl")

                    pnl_contribution = 0.0
                    used_platform_map = False
                    if isinstance(platform_pnl_map, dict):
                        for platform_name, value in platform_pnl_map.items():
                            platform_label = str(platform_name).lower()
                            if not any(
                                token in platform_label for token in included_platform_tokens
                            ):
                                continue
                            pnl_contribution += safe_float_convert(value, 0.0)
                        used_platform_map = True

                    if not used_platform_map:
                        source_platform = (
                            str(metadata.get("source_platform", ""))
                            or str(asset_data.get("source_platform", ""))
                        ).lower()
                        if not any(token in source_platform for token in included_platform_tokens):
                            continue
                        pnl_value = metadata.get("total_unrealized_pnl")
                        if pnl_value is None:
                            pnl_value = asset_data.get("total_unrealized_pnl")
                        pnl_contribution = safe_float_convert(pnl_value, 0.0)

                    total_unrealized_pnl += pnl_contribution
            except Exception:
                total_unrealized_pnl = safe_float_convert(total_unrealized_pnl, 0.0)

            metrics["total_unrealized_pnl"] = total_unrealized_pnl
            total_with_pnl = metrics.get("total_portfolio_value", 0.0) + total_unrealized_pnl
            metrics["total_portfolio_value_with_pnl"] = total_with_pnl
            metrics["adjusted_portfolio_value_with_pnl"] = max(total_with_pnl - balance_offset, 0)

        except Exception as e:
            print_warning(f"⚠️  Exposure analysis failed: {e}")
            # Add empty exposure data so the structure is consistent
            metrics["exposure_analysis"] = {}
            metrics["exposure_summary"] = "Exposure analysis unavailable"

        # Pass through quick_mode flag so UI can disable detailed views
        metrics["quick_mode"] = fetched_data.get("quick_mode", False)

        return metrics

    async def get_custom_coin_prices(self, custom_symbols: List[str]) -> Dict[str, float]:
        """
        Fetch prices for custom coins using the standard price service.
        """
        if not custom_symbols:
            return {}

        try:
            # Use self.price_service (which points to enhanced_price_service)
            prices = await self.price_service.get_prices_async(custom_symbols)

            # Update custom coin storage with fetched prices
            # Consider passing custom_coin_tracker instance if this method needs to update it directly
            # For now, assuming CustomCoinTracker might be updated elsewhere or this is just for fetching.
            # Re-instantiating CustomCoinTracker() here seems incorrect if it's meant to be a shared state.
            # This part needs review based on how CustomCoinTracker state is managed.
            # If this method is part of PortfolioAnalyzer, it should use self.custom_coin_tracker
            # custom_coin_tracker_instance = CustomCoinTracker() # This line is problematic if tracker is stateful
            if self.custom_coin_tracker:  # Use the instance member
                for symbol, price in prices.items():
                    if price is not None:
                        self.custom_coin_tracker.update_price(symbol, price)

            return {k: v for k, v in prices.items() if v is not None}

        except Exception as e:
            print_error(f"Error fetching custom coin prices: {e}")
            return {}
