# -*- coding: utf-8 -*-
"""
Menu and User Interface Module
------------------------------
Contains all menu and user interface functions for the portfolio tracker.
This module handles user interaction, navigation, and the main application flow.
"""

import asyncio
import sys
import traceback
import os
from pathlib import Path
from typing import Dict, Any, Optional
from colorama import Fore, Style

# Import configuration and utilities
from config.constants import *
from models.custom_coins import CustomCoinTracker
from utils.helpers import (
    print_header,
    print_subheader,
    print_error,
    print_warning,
    print_info,
    print_success,
    clear_screen,
    print_loading_animation,
    safe_float_convert,
    format_currency,
    get_menu_choice,
    get_yes_no,
    get_validated_number,
    get_validated_choice,
    get_validated_address,
    get_confirmed_input,
    print_loading_dots,
)
from utils.display_theme import theme
from ui.display_functions import (
    display_comprehensive_overview,
    display_wallet_balances,
    display_perp_dex_positions,
    display_cex_breakdown,
    display_asset_distribution,
)
from core.portfolio_analyzer import PortfolioAnalyzer

# Additional imports needed for view_past_analysis
import json
from datetime import datetime
from config.constants import ANALYSIS_FILE_PATTERN


class MenuSystem:
    """Handles all menu and user interface functionality."""

    def __init__(self, api_module, exchange_manager):
        """Initialize with required dependencies."""
        self.api_module = api_module
        self.exchange_manager = exchange_manager

    async def run_analysis_submenu(
        self,
        portfolio_metrics: Dict[str, Any],
        source_info: str,
        analysis_folder: Optional[str] = None,
    ):
        """
        Runs the sub-menu for exploring analysis results (live or saved) with professional styling.
        This function is now asynchronous to support refresh functionality.
        """
        # Professional color scheme
        PRIMARY = Fore.WHITE + Style.BRIGHT
        SUCCESS = Fore.GREEN + Style.BRIGHT
        WARNING = Fore.YELLOW
        ERROR = Fore.RED
        ACCENT = Fore.CYAN
        SUBTLE = Style.DIM
        RESET = Style.RESET_ALL

        while True:
            clear_screen()
            # Always display the main overview first
            display_comprehensive_overview(portfolio_metrics, source_info=source_info)

            print(f"\n{PRIMARY}ANALYSIS OPTIONS{RESET}")
            print(f"{SUBTLE}{'─' * 18}{RESET}")
            print(f"{ACCENT}1.{RESET} {PRIMARY}Wallet Balances{RESET}")
            print(f"{ACCENT}2.{RESET} {PRIMARY}Perp DEX Positions{RESET}")
            print(f"{ACCENT}3.{RESET} {PRIMARY}CEX Account Breakdown{RESET}")
            print(f"{ACCENT}4.{RESET} {PRIMARY}Asset Distribution Chart{RESET}")
            exposure_option = None
            if not portfolio_metrics.get("quick_mode", False):
                exposure_option = "5"
                print(
                    f"{ACCENT}5.{RESET} {PRIMARY}🎯 Exposure Analysis{RESET} "
                    f"{SUBTLE}• Risk & concentration tracking{RESET}"
                )
            back_option = "6" if exposure_option else "5"
            print(f"{ACCENT}{back_option}.{RESET} {SUBTLE}Back to Previous Menu{RESET}")
            print(f"{SUBTLE}{'─' * 40}{RESET}")
            print(
                f"{SUBTLE}💡 Type 'refresh' to recalculate exposure analysis & save portfolio summary stats{RESET}"
            )
            print(
                f"{SUBTLE}💡 Type 'combine' to generate combined portfolio analysis from all wallets{RESET}"
            )

            menu_prompt = "1-6" if exposure_option else "1-5"
            choice = input(
                f"{PRIMARY}Select option ({menu_prompt}, 'refresh', or 'combine'): {RESET}"
            )

            if choice.lower() == "refresh":
                # Refresh exposure analysis - recalculate from existing data only (debugging)
                print_info(
                    "🔄 Recalculating exposure analysis & generating portfolio summary stats..."
                )
                try:
                    # Add analysis folder context to portfolio metrics if available
                    if analysis_folder:
                        portfolio_metrics["_analysis_folder"] = analysis_folder

                    updated_metrics = await self._recalculate_exposure_analysis(portfolio_metrics)
                    if updated_metrics:
                        portfolio_metrics.update(updated_metrics)
                        print_success("✅ Exposure analysis & portfolio summary stats updated!")
                    else:
                        print_error("❌ Failed to recalculate exposure analysis")
                except Exception as e:
                    print_error(f"Error recalculating exposure: {e}")
                # Stay in overview menu, don't display exposure analysis
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
                continue
            elif choice.lower() == "combine":
                # Generate combined portfolio analysis
                print_info("🔄 Generating combined portfolio analysis from all wallets...")
                try:
                    from combined_wallet_integration import generate_combined_for_current_analysis

                    combined_file = generate_combined_for_current_analysis(portfolio_metrics)
                    if combined_file:
                        print_success("✅ Combined portfolio analysis generated!")
                        print_info(f"📁 Saved to: {combined_file}")
                    else:
                        print_error("❌ Failed to generate combined portfolio analysis")
                except Exception as e:
                    print_error(f"Error generating combined analysis: {e}")
                # Stay in overview menu
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
                continue
            elif choice == "1":
                # Pass complete portfolio metrics instead of just raw wallet data
                # This ensures enhanced wallet breakdown with submenu works in past analysis
                # Add analysis folder context to portfolio metrics if available
                if analysis_folder:
                    portfolio_metrics["_analysis_folder"] = analysis_folder
                display_wallet_balances(portfolio_metrics)
            elif choice == "2":
                display_perp_dex_positions(portfolio_metrics)
            elif choice == "3":
                display_cex_breakdown(portfolio_metrics)
            elif choice == "4":
                display_asset_distribution(portfolio_metrics)
            elif (
                choice == exposure_option
                and exposure_option is not None
                and not portfolio_metrics.get("quick_mode", False)
            ):
                # Import here to avoid circular imports
                from ui.display_functions import display_exposure_analysis

                # Add analysis folder context to portfolio metrics if available
                if analysis_folder:
                    portfolio_metrics["_analysis_folder"] = analysis_folder

                # Automatically refresh exposure analysis before displaying to ensure accurate data
                print_info("🔄 Refreshing exposure analysis for accurate data...")
                try:
                    updated_metrics = await self._recalculate_exposure_analysis(portfolio_metrics)
                    if updated_metrics:
                        portfolio_metrics.update(updated_metrics)
                        print_success("✅ Exposure analysis refreshed!")
                        print_info("⏳ Finalizing data processing...")
                        await asyncio.sleep(3)  # Wait 3 seconds for data to be fully processed
                    else:
                        print_warning("⚠️ Exposure refresh failed, showing cached data")
                except Exception as e:
                    print_error(f"⚠️ Error refreshing exposure: {e}")
                    print_info("Showing cached exposure data...")

                display_exposure_analysis(portfolio_metrics)
            elif choice == back_option:
                break  # Exit analysis sub-menu
            else:
                print(f"{ERROR}Invalid choice. Please try again.{RESET}")

            input(
                f"\n{SUBTLE}Press Enter to continue...{RESET}"
            )  # Pause after showing detail views

    async def _recalculate_exposure_analysis(
        self, portfolio_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recalculate exposure analysis from portfolio metrics data using existing saved data only."""
        try:
            from core.exposure_tracker import ExposureTracker, get_exposure_summary

            # Extract portfolio data for exposure analysis (similar to recalculate_exposure.py)
            portfolio_data_for_exposure = {
                "total_portfolio_value": portfolio_metrics.get("total_portfolio_value", 0),
                "wallet_platform_data_raw": portfolio_metrics.get("wallet_platform_data_raw", []),
                "detailed_breakdowns": portfolio_metrics.get("detailed_breakdowns", {}),
                "crypto_prices": portfolio_metrics.get("crypto_prices", {}),
                # Add individual balance mappings for fallback processing
                "binance_balance": portfolio_metrics.get("binance", 0) or 0,
                "okx_balance": portfolio_metrics.get("okx", 0) or 0,
                "bybit_balance": portfolio_metrics.get("bybit", 0) or 0,
                "backpack_balance": portfolio_metrics.get("backpack", 0) or 0,
                "bitcoin_balance": portfolio_metrics.get("bitcoin", 0) or 0,
                "solana_balance": portfolio_metrics.get("solana", 0) or 0,
                "hyperliquid_balance": portfolio_metrics.get("hyperliquid", 0) or 0,
                # Add analysis folder context for Portfolio Summary Statistics integration
                "_analysis_folder": portfolio_metrics.get("_analysis_folder"),
            }

            # Create exposure tracker and recalculate
            exposure_tracker = ExposureTracker()
            new_exposure_analysis = exposure_tracker.analyze_portfolio_exposure(
                portfolio_data_for_exposure
            )
            new_exposure_summary = get_exposure_summary(new_exposure_analysis)

            # Generate and save Portfolio Summary Statistics if analysis folder is available
            analysis_folder = portfolio_metrics.get("_analysis_folder")

            # If no analysis folder, try to find the most recent one or generate combined data
            if not analysis_folder:
                try:
                    from combined_wallet_integration import (
                        find_most_recent_analysis_folder,
                        generate_combined_for_current_analysis,
                    )

                    # Try to find most recent analysis folder
                    analysis_folder = find_most_recent_analysis_folder()

                    if not analysis_folder:
                        # No existing analysis folder found, try to generate combined data for current session
                        print_info(
                            "🔄 No existing analysis folder found, generating combined wallet data..."
                        )
                        combined_file = generate_combined_for_current_analysis(portfolio_metrics)
                        if combined_file:
                            # Extract analysis folder from combined file path
                            import os

                            analysis_folder = os.path.dirname(combined_file)
                            print_success(
                                "✅ Combined wallet data generated for Portfolio Summary Statistics"
                            )
                        else:
                            print_info("ℹ️ Could not generate combined wallet data")

                except Exception as e:
                    print_error(f"⚠️ Error finding or generating analysis data: {e}")

            if analysis_folder:
                try:
                    from combined_wallet_integration import get_combined_wallet_file_path
                    from utils.portfolio_summary_extractor import (
                        generate_and_save_portfolio_summary,
                    )

                    # Check if combined wallet data exists or can be generated
                    combined_file = get_combined_wallet_file_path(analysis_folder)

                    if combined_file:
                        print_info(
                            "🔄 Generating Portfolio Summary Statistics for exposure analysis integration..."
                        )
                        summary_stats_file = generate_and_save_portfolio_summary(
                            combined_file, analysis_folder
                        )

                        if summary_stats_file:
                            print_success(
                                "✅ Portfolio Summary Statistics updated for exposure analysis"
                            )
                        else:
                            print_error("⚠️ Portfolio Summary Statistics generation failed")
                    else:
                        print_info(
                            "ℹ️ No combined wallet data available - Portfolio Summary Statistics not generated"
                        )

                except Exception as e:
                    print_error(f"⚠️ Portfolio Summary Statistics generation failed: {e}")
            else:
                print_info(
                    "ℹ️ No analysis folder available - Portfolio Summary Statistics not generated"
                )

            # Handle ETH exposure data - use existing data only (no live fetching)
            existing_eth_data = portfolio_metrics.get("eth_exposure_data", {})

            if existing_eth_data:
                # Count existing data entries
                successful_count = sum(
                    1
                    for data in existing_eth_data.values()
                    if isinstance(data, dict) and "export_data" in data
                )
                total_count = len(
                    [addr for addr in existing_eth_data.keys() if addr != "enhancement_error"]
                )

                if successful_count > 0:
                    print_info(
                        f"🔄 Using existing ETH exposure data ({successful_count}/{total_count} addresses)"
                    )
                    print_success(f"✅ ETH exposure analysis refreshed using saved data")
                else:
                    print_info("ℹ️ ETH exposure data present but no valid export data found")
            else:
                print_info("ℹ️ No ETH exposure data available in this analysis")

            # Update portfolio_metrics with new exposure data
            portfolio_metrics["exposure_analysis"] = new_exposure_analysis
            portfolio_metrics["exposure_summary"] = new_exposure_summary

            # Preserve existing ETH exposure data (no changes to it)
            if existing_eth_data:
                portfolio_metrics["eth_exposure_data"] = existing_eth_data

            # Save the updated portfolio analysis back to file if we have analysis folder
            if analysis_folder:
                try:
                    import os
                    import json

                    # Find the portfolio analysis file in the analysis folder
                    portfolio_file = os.path.join(analysis_folder, "portfolio_analysis.json")

                    if os.path.exists(portfolio_file):
                        # Save the updated metrics back to the file
                        with open(portfolio_file, "w") as f:
                            json.dump(portfolio_metrics, f, indent=2, default=str)
                        print_success("💾 Updated exposure analysis saved to portfolio file")
                    else:
                        print_info(
                            "ℹ️ Portfolio analysis file not found - exposure updates are in-memory only"
                        )

                except Exception as e:
                    print_error(f"⚠️ Error saving updated exposure analysis: {e}")

            # Return updated metrics with existing ETH exposure data
            updated_metrics = {
                "exposure_analysis": new_exposure_analysis,
                "exposure_summary": new_exposure_summary,
            }

            # Preserve existing ETH exposure data (no changes to it)
            if existing_eth_data:
                updated_metrics["eth_exposure_data"] = existing_eth_data

            return updated_metrics

        except Exception as e:
            print_error(f"Failed to recalculate exposure: {e}")
            return {}

    def manage_wallets_menu(self, wallet_tracker):
        """Enhanced wallet management with improved validation and user experience."""
        while True:
            print_header("Wallet Management")
            wallet_tracker.list_wallets()  # Show current wallets first

            print(f"\n{theme.PRIMARY}🏦 WALLET OPTIONS{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 16}{theme.RESET}")
            print(f"{theme.ACCENT}1.{theme.RESET} {theme.SUCCESS}➕ Add Wallet{theme.RESET}")
            print(f"{theme.ACCENT}2.{theme.RESET} {theme.WARNING}➖ Remove Wallet{theme.RESET}")
            print(
                f"{theme.ACCENT}3.{theme.RESET} {theme.PRIMARY}⚡ Toggle Hyperliquid{theme.RESET} {theme.SUBTLE}(Ethereum only){theme.RESET}"
            )
            print(
                f"{theme.ACCENT}4.{theme.RESET} {theme.PRIMARY}🪙 Toggle Lighter{theme.RESET} {theme.SUBTLE}(Ethereum only){theme.RESET}"
            )
            print(f"{theme.ACCENT}5.{theme.RESET} {theme.SUBTLE}⬅️ Back to Main Menu{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 40}{theme.RESET}")

            # Simple clean input
            choice = input(f"{theme.PRIMARY}Choose an option (1-5): {theme.RESET}").strip()

            if choice not in ["1", "2", "3", "4", "5"]:
                clear_screen()
                print_header("Wallet Management")
                wallet_tracker.list_wallets()

                print(f"\n{theme.PRIMARY}🏦 WALLET OPTIONS{theme.RESET}")
                print(f"{theme.SUBTLE}{'─' * 16}{theme.RESET}")
                print(f"{theme.ACCENT}1.{theme.RESET} {theme.SUCCESS}➕ Add Wallet{theme.RESET}")
                print(f"{theme.ACCENT}2.{theme.RESET} {theme.WARNING}➖ Remove Wallet{theme.RESET}")
                print(
                    f"{theme.ACCENT}3.{theme.RESET} {theme.PRIMARY}⚡ Toggle Hyperliquid{theme.RESET} {theme.SUBTLE}(Ethereum only){theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}4.{theme.RESET} {theme.PRIMARY}🪙 Toggle Lighter{theme.RESET} {theme.SUBTLE}(Ethereum only){theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}5.{theme.RESET} {theme.SUBTLE}⬅️ Back to Main Menu{theme.RESET}"
                )
                print(f"{theme.SUBTLE}{'─' * 40}{theme.RESET}")

                print_error(f"❌ Invalid choice '{choice}'. Please select 1-5.")
                input("\nPress Enter to continue...")
                continue

            if choice == "1":
                # Enhanced add wallet with validation
                self._add_wallet_enhanced(wallet_tracker)
            elif choice == "2":
                # Enhanced remove wallet
                self._remove_wallet_enhanced(wallet_tracker)
            elif choice == "3":
                self._toggle_hyperliquid_enhanced(wallet_tracker)
            elif choice == "4":
                self._toggle_lighter_enhanced(wallet_tracker)
            elif choice == "5":
                break

            input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")

    def _add_wallet_enhanced(self, wallet_tracker):
        """Enhanced wallet addition with validation."""
        print_header("Add New Wallet")

        try:
            from utils.helpers import get_validated_address, get_yes_no

            # Chain selection with validation
            supported_chains = SUPPORTED_CHAINS
            print(f"{theme.INFO}💡 Supported blockchains:{theme.RESET}")
            for i, chain in enumerate(supported_chains, 1):
                print(f"  {theme.ACCENT}{i}.{theme.RESET} {chain.capitalize()}")

            raw_choice = input(f"Select blockchain (1-{len(supported_chains)} or name): ").strip()
            if raw_choice.isdigit():
                idx = int(raw_choice) - 1
                if idx < 0 or idx >= len(supported_chains):
                    raise ValueError("Invalid numeric selection")
                chain = supported_chains[idx]
            else:
                chain = raw_choice.lower()
                if chain not in supported_chains:
                    raise ValueError("Invalid chain name")

            # Address input with validation
            print(f"\n{theme.PRIMARY}📍 WALLET ADDRESS{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 16}{theme.RESET}")
            print(f"{theme.INFO} Enter your {chain.capitalize()} wallet address{theme.RESET}")

            address = get_validated_address(f"Enter {chain.capitalize()} wallet address", chain)

            # Add the wallet
            if address:
                wallet_tracker.add_wallet(address, chain)

                if chain.lower() == "ethereum":
                    from web3 import Web3

                    try:
                        address = Web3.to_checksum_address(address)
                    except ValueError:
                        pass

                    print(f"\n{theme.PRIMARY}⚡ HYPERLIQUID TRADING{theme.RESET}")
                    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
                    print(
                        f"{theme.INFO}💡 Enable Hyperliquid trading tracking for this wallet?{theme.RESET}"
                    )
                    if get_yes_no("Enable Hyperliquid tracking", default=True):
                        if address not in wallet_tracker.hyperliquid_enabled:
                            wallet_tracker.toggle_hyperliquid(address)
                        else:
                            print_info("Hyperliquid tracking already enabled for this address.")
                    else:
                        print_info("Hyperliquid tracking left disabled.")

                    print(f"\n{theme.PRIMARY}🪙 LIGHTER PERP DEX{theme.RESET}")
                    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
                    print(
                        f"{theme.INFO}💡 Enable Lighter perpetual trading tracking for this wallet?{theme.RESET}"
                    )
                    if get_yes_no("Enable Lighter tracking", default=False):
                        if address not in wallet_tracker.lighter_enabled:
                            wallet_tracker.toggle_lighter(address)
                            print_success("✅ Lighter tracking enabled!")
                        else:
                            print_info("Lighter tracking already enabled for this address.")

        except ValueError as exc:
            print_error(
                f"Invalid choice '{raw_choice}'. Valid options: {', '.join(supported_chains)}"
            )
            input(f"{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
            return
        except (ImportError, NameError):
            # Fallback to original method
            chain = input(f"Enter chain ({'/'.join(SUPPORTED_CHAINS)}): ").lower()
            if chain not in SUPPORTED_CHAINS:
                print_error("Invalid chain.")
                return

            address = input(f"Enter {chain.capitalize()} wallet address: ").strip()
            wallet_tracker.add_wallet(address, chain)

    def _remove_wallet_enhanced(self, wallet_tracker):
        """Enhanced wallet removal with better selection."""
        print_header("Remove Wallet")

        # Check if any wallets exist
        all_wallets = []
        for chain, addresses in wallet_tracker.wallets.items():
            for addr in addresses:
                all_wallets.append((chain, addr))

        if not all_wallets:
            print_info("No wallets are currently tracked.")
            return

        try:
            from utils.helpers import get_validated_choice, get_yes_no

            # Display all wallets with numbers
            print(f"{theme.PRIMARY}📋 TRACKED WALLETS{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 16}{theme.RESET}")

            for i, (chain, addr) in enumerate(all_wallets, 1):
                short_addr = addr[:8] + "..." + addr[-6:] if len(addr) > 20 else addr
                status_labels = []
                if chain == "ethereum" and addr in wallet_tracker.hyperliquid_enabled:
                    status_labels.append(f"{theme.WARNING}⚡ Hyperliquid{theme.RESET}")
                if chain == "ethereum" and addr in wallet_tracker.lighter_enabled:
                    status_labels.append(f"{theme.PRIMARY}🪙 Lighter{theme.RESET}")

                status_suffix = f" ({', '.join(status_labels)})" if status_labels else ""

                print(
                    f"  {theme.ACCENT}{i}.{theme.RESET} {theme.SUCCESS}{chain.capitalize()}{theme.RESET}: {short_addr}{status_suffix}"
                )

            print(
                f"  {theme.ACCENT}{len(all_wallets) + 1}.{theme.RESET} {theme.SUBTLE}Cancel{theme.RESET}"
            )

            choice = get_validated_choice(
                "Select wallet to remove", [str(i) for i in range(1, len(all_wallets) + 2)]
            )

            if choice == str(len(all_wallets) + 1):
                print_info("Operation cancelled.")
                return

            # Get selected wallet
            selected_idx = int(choice) - 1
            chain, address = all_wallets[selected_idx]

            # Confirm removal
            short_addr = address[:8] + "..." + address[-6:] if len(address) > 20 else address
            print(f"\n{theme.WARNING}⚠️ REMOVE CONFIRMATION{theme.RESET}")
            print(f"Chain:   {theme.ACCENT}{chain.capitalize()}{theme.RESET}")
            print(f"Address: {theme.ACCENT}{short_addr}{theme.RESET}")

            if get_yes_no("Are you sure you want to remove this wallet?", default=False):
                wallet_tracker.remove_wallet(address, chain)
                print_success("✅ Wallet removed successfully!")
            else:
                print_info("Removal cancelled.")

        except (ImportError, NameError):
            # Fallback to original method
            chain = input(
                f"Enter chain of wallet to remove ({'/'.join(SUPPORTED_CHAINS)}): "
            ).lower()
            if chain not in SUPPORTED_CHAINS:
                print_error("Invalid chain.")
                return
            elif not wallet_tracker.wallets.get(chain):
                print_info(f"No wallets tracked for {chain.capitalize()}.")
                return

            address = input(f"Enter {chain.capitalize()} wallet address to remove: ").strip()
            wallet_tracker.remove_wallet(address, chain)

    def _toggle_lighter_enhanced(self, wallet_tracker):
        """Enhanced Lighter toggle with better selection."""
        print_header("Toggle Lighter Tracking")

        eth_wallets = wallet_tracker.wallets.get("ethereum", [])
        if not eth_wallets:
            print_info("No Ethereum wallets tracked.")
            print(
                f"{theme.SUBTLE}💡 Add an Ethereum wallet first to enable Lighter tracking.{theme.RESET}"
            )
            return

        try:
            from utils.helpers import get_validated_choice, get_yes_no

            print(f"{theme.PRIMARY}🪙 ETHEREUM WALLETS{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 18}{theme.RESET}")

            for i, addr in enumerate(eth_wallets, 1):
                short_addr = addr[:8] + "..." + addr[-6:] if len(addr) > 20 else addr
                status = (
                    f"{theme.SUCCESS}✅ Enabled{theme.RESET}"
                    if addr in wallet_tracker.lighter_enabled
                    else f"{theme.ERROR}❌ Disabled{theme.RESET}"
                )
                print(f"  {theme.ACCENT}{i}.{theme.RESET} {short_addr} {status}")

            print(
                f"  {theme.ACCENT}{len(eth_wallets) + 1}.{theme.RESET} {theme.SUBTLE}Cancel{theme.RESET}"
            )

            choice = get_validated_choice(
                "Select wallet to toggle Lighter",
                [str(i) for i in range(1, len(eth_wallets) + 2)],
            )

            if choice == str(len(eth_wallets) + 1):
                print_info("Operation cancelled.")
                return

            selected_idx = int(choice) - 1
            selected_address = eth_wallets[selected_idx]

            current_status = (
                "enabled" if selected_address in wallet_tracker.lighter_enabled else "disabled"
            )
            new_status = "disabled" if current_status == "enabled" else "enabled"

            print(f"\n{theme.INFO}💡 Current status: {current_status.capitalize()}{theme.RESET}")

            if get_yes_no(f"Toggle Lighter tracking to {new_status}?", default=True):
                wallet_tracker.toggle_lighter(selected_address)
                print_success(f"✅ Lighter tracking {new_status}!")
            else:
                print_info("Toggle cancelled.")

        except (ImportError, NameError):
            print("\nSelect Ethereum wallet to toggle Lighter:")
            for i, addr in enumerate(eth_wallets, 1):
                status = (
                    Fore.GREEN + "(Enabled)" + Style.RESET_ALL
                    if addr in wallet_tracker.lighter_enabled
                    else Fore.RED + "(Disabled)" + Style.RESET_ALL
                )
                print(f"  {Fore.CYAN}{i}.{Style.RESET_ALL} {addr} {status}")

            try:
                select_idx = int(input("Enter number: ")) - 1
                if 0 <= select_idx < len(eth_wallets):
                    wallet_tracker.toggle_lighter(eth_wallets[select_idx])
                else:
                    print_error("Invalid selection.")
            except ValueError:
                print_error("Invalid input.")

    def _toggle_hyperliquid_enhanced(self, wallet_tracker):
        """Enhanced Hyperliquid toggle with better selection."""
        print_header("Toggle Hyperliquid Tracking")

        eth_wallets = wallet_tracker.wallets.get("ethereum", [])
        if not eth_wallets:
            print_info("No Ethereum wallets tracked.")
            print(
                f"{theme.SUBTLE}💡 Add an Ethereum wallet first to enable Hyperliquid tracking.{theme.RESET}"
            )
            return

        try:
            from utils.helpers import get_validated_choice, get_yes_no

            print(f"{theme.PRIMARY}⚡ ETHEREUM WALLETS{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 19}{theme.RESET}")

            for i, addr in enumerate(eth_wallets, 1):
                short_addr = addr[:8] + "..." + addr[-6:] if len(addr) > 20 else addr
                status = (
                    f"{theme.SUCCESS}✅ Enabled{theme.RESET}"
                    if addr in wallet_tracker.hyperliquid_enabled
                    else f"{theme.ERROR}❌ Disabled{theme.RESET}"
                )
                print(f"  {theme.ACCENT}{i}.{theme.RESET} {short_addr} {status}")

            print(
                f"  {theme.ACCENT}{len(eth_wallets) + 1}.{theme.RESET} {theme.SUBTLE}Cancel{theme.RESET}"
            )

            choice = get_validated_choice(
                "Select wallet to toggle Hyperliquid",
                [str(i) for i in range(1, len(eth_wallets) + 2)],
            )

            if choice == str(len(eth_wallets) + 1):
                print_info("Operation cancelled.")
                return

            selected_idx = int(choice) - 1
            selected_address = eth_wallets[selected_idx]

            current_status = (
                "enabled" if selected_address in wallet_tracker.hyperliquid_enabled else "disabled"
            )
            new_status = "disabled" if current_status == "enabled" else "enabled"

            print(f"\n{theme.INFO}💡 Current status: {current_status.capitalize()}{theme.RESET}")

            if get_yes_no(f"Toggle Hyperliquid tracking to {new_status}?", default=True):
                wallet_tracker.toggle_hyperliquid(selected_address)
                print_success(f"✅ Hyperliquid tracking {new_status}!")
            else:
                print_info("Toggle cancelled.")

        except (ImportError, NameError):
            print("\nSelect Ethereum wallet to toggle Hyperliquid:")
            for i, addr in enumerate(eth_wallets, 1):
                status = (
                    Fore.GREEN + "(Enabled)" + Style.RESET_ALL
                    if addr in wallet_tracker.hyperliquid_enabled
                    else Fore.RED + "(Disabled)" + Style.RESET_ALL
                )
                print(f"  {Fore.CYAN}{i}.{Style.RESET_ALL} {addr} {status}")

            try:
                select_idx = int(input("Enter number: ")) - 1
                if 0 <= select_idx < len(eth_wallets):
                    wallet_tracker.toggle_hyperliquid(eth_wallets[select_idx])
                else:
                    print_error("Invalid selection.")
            except ValueError:
                print_error("Invalid input.")

    async def main_menu(self, binance_exchange, wallet_tracker):
        """Enhanced main menu with improved input validation and user experience."""
        while True:
            print_header("Crypto Portfolio Tracker")

            # Enhanced main menu with theme
            print(f"\n{theme.PRIMARY}MAIN MENU{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 11}{theme.RESET}")

            # Menu options with better visual hierarchy and icons
            print(
                f"{theme.ACCENT}1.{theme.RESET} {theme.SUCCESS}🚀 Run FULL Portfolio Analysis{theme.RESET} {theme.SUBTLE}• Real-time with deep wallet data{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}2.{theme.RESET} {theme.PRIMARY}⚡ Run QUICK Portfolio Analysis{theme.RESET} {theme.SUBTLE}• Skip enhanced wallet scraping{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}3.{theme.RESET} {theme.PRIMARY}📊 View Past Analysis{theme.RESET} {theme.SUBTLE}• Historical data{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}4.{theme.RESET} {theme.PRIMARY}🏦 Manage Wallets{theme.RESET} {theme.SUBTLE}• Add/remove addresses{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}5.{theme.RESET} {theme.PRIMARY}🔑 Manage API Keys{theme.RESET} {theme.SUBTLE}• Exchange credentials{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}6.{theme.RESET} {theme.PRIMARY}🪙 Manage Custom Coins{theme.RESET} {theme.SUBTLE}• Track additional tokens{theme.RESET}"
            )
            print(
                f"{theme.ACCENT}7.{theme.RESET} {theme.WARNING}⚖️ Adjust Balance Offset{theme.RESET} {theme.SUBTLE}• Portfolio adjustments{theme.RESET}"
            )
            print(f"{theme.ACCENT}8.{theme.RESET} {theme.SUBTLE}👋 Exit{theme.RESET}")

            print(f"\n{theme.SUBTLE}{'═' * 70}{theme.RESET}")

            # Simple clean input without function dependency
            choice = input(f"{theme.PRIMARY}Choose an option (1-8): {theme.RESET}").strip()

            if choice not in ["1", "2", "3", "4", "5", "6", "7", "8"]:
                clear_screen()
                print_header("Crypto Portfolio Tracker")

                # Redisplay menu
                print(f"\n{theme.PRIMARY}MAIN MENU{theme.RESET}")
                print(f"{theme.SUBTLE}{'─' * 11}{theme.RESET}")
                print(
                    f"{theme.ACCENT}1.{theme.RESET} {theme.SUCCESS}🚀 Run FULL Portfolio Analysis{theme.RESET} {theme.SUBTLE}• Real-time with deep wallet data{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}2.{theme.RESET} {theme.PRIMARY}⚡ Run QUICK Portfolio Analysis{theme.RESET} {theme.SUBTLE}• Skip enhanced wallet scraping{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}3.{theme.RESET} {theme.PRIMARY}📊 View Past Analysis{theme.RESET} {theme.SUBTLE}• Historical data{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}4.{theme.RESET} {theme.PRIMARY}🏦 Manage Wallets{theme.RESET} {theme.SUBTLE}• Add/remove addresses{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}5.{theme.RESET} {theme.PRIMARY}🔑 Manage API Keys{theme.RESET} {theme.SUBTLE}• Exchange credentials{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}6.{theme.RESET} {theme.PRIMARY}🪙 Manage Custom Coins{theme.RESET} {theme.SUBTLE}• Track additional tokens{theme.RESET}"
                )
                print(
                    f"{theme.ACCENT}7.{theme.RESET} {theme.WARNING}⚖️ Adjust Balance Offset{theme.RESET} {theme.SUBTLE}• Portfolio adjustments{theme.RESET}"
                )
                print(f"{theme.ACCENT}8.{theme.RESET} {theme.SUBTLE}👋 Exit{theme.RESET}")
                print(f"\n{theme.SUBTLE}{'═' * 70}{theme.RESET}")

                print_error(f"❌ Invalid choice '{choice}'. Please select 1-8.")
                continue

            if choice == "1":
                # Full analysis (current behavior)
                from config.constants import DEBUG_MODE

                if DEBUG_MODE and binance_exchange is None:
                    print_warning("⚠️  Live portfolio analysis requires exchange connections")
                    print_info("🐛 Debug mode: No API keys configured - cannot fetch live data")
                    print_info("💡 To use this feature:")
                    print_info("   • Add API keys via menu option 5")
                    print_info("   • Or view past analysis via menu option 3")
                    input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                else:
                    print_loading_dots("Initializing full portfolio analysis", 2)
                    await self.run_live_portfolio_analysis(
                        binance_exchange, wallet_tracker, quick_mode=False
                    )
            elif choice == "2":
                # Quick analysis
                from config.constants import DEBUG_MODE

                if DEBUG_MODE and binance_exchange is None:
                    print_warning("⚠️  Live portfolio analysis requires exchange connections")
                    print_info("🐛 Debug mode: No API keys configured - cannot fetch live data")
                    input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                else:
                    print_loading_dots("Initializing quick portfolio analysis", 1)
                    await self.run_live_portfolio_analysis(
                        binance_exchange, wallet_tracker, quick_mode=True
                    )
            elif choice == "3":
                # View past analysis
                await self.view_past_analysis()
            elif choice == "4":
                # Manage wallets
                self.manage_wallets_menu(wallet_tracker)
            elif choice == "5":
                # Manage API keys
                self.manage_api_keys()
            elif choice == "6":
                # Manage custom coins
                await self.custom_coins_menu()
            elif choice == "7":
                # Enhanced balance offset adjustment
                self._enhanced_offset_adjustment(wallet_tracker)
            elif choice == "8":
                print_success("Thank you for using Portfolio Tracker. Goodbye!")
                break

    def _enhanced_offset_adjustment(self, wallet_tracker):
        """Enhanced balance offset adjustment with better validation."""
        print_header("Adjust Balance Offset")
        current_offset = wallet_tracker.balance_offset

        print(f"{theme.PRIMARY}💰 CURRENT OFFSET{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 17}{theme.RESET}")
        offset_display = (
            f"{theme.WARNING}{format_currency(current_offset)}{theme.RESET}"
            if current_offset > 0
            else f"{theme.SUBTLE}{format_currency(current_offset)}{theme.RESET}"
        )
        print(f"Current Offset: {offset_display}")
        print(
            f"{theme.SUBTLE}This amount is subtracted from the total portfolio value.{theme.RESET}"
        )
        print(f"{theme.INFO}💡 Use this to account for external holdings or debts.{theme.RESET}")

        try:
            # Ask if user wants to change the offset
            if not get_yes_no("Do you want to change the current offset?", default=False):
                print_info("Offset unchanged.")
                input(f"\n{theme.SUBTLE}Press Enter to return to main menu...{theme.RESET}")
                return

            # Get new offset with validation
            new_offset = get_validated_number(
                "Enter new offset value (in USD)", min_val=-999999999, allow_negative=True
            )

            # Confirm the change
            print(f"\n{theme.WARNING}⚠️ CONFIRMATION{theme.RESET}")
            print(f"Current Offset: {offset_display}")
            print(f"New Offset:     {theme.ACCENT}{format_currency(new_offset)}{theme.RESET}")

            if get_yes_no("Apply this change?", default=True):
                wallet_tracker.set_balance_offset(new_offset)
                print_success(f"✅ Offset updated to {format_currency(new_offset)}")
            else:
                print_info("Change cancelled.")

        except ImportError:
            # Fallback to original method
            try:
                new_offset_str = input(
                    f"\n{theme.PRIMARY}Enter new offset value (or press Enter to keep current): ${theme.RESET}"
                )
                if new_offset_str.strip():
                    new_offset = safe_float_convert(new_offset_str.replace(",", ""), -1.0)
                    wallet_tracker.set_balance_offset(new_offset)
                    print_success("Offset updated successfully")
            except Exception as e:
                print_error(f"Error setting offset: {e}")

        input(f"\n{theme.SUBTLE}Press Enter to return to main menu...{theme.RESET}")

    async def run_live_portfolio_analysis(
        self, binance_exchange, wallet_tracker, quick_mode: bool = False
    ):
        """Fetches live data, calculates, displays, saves, and runs the analysis sub-menu."""
        try:
            print_header("Running Live Portfolio Analysis")

            custom_coin_tracker = CustomCoinTracker()

            # Pass api_module and exchange_manager from MenuSystem instance (self)
            analyzer = PortfolioAnalyzer(
                api_module=self.api_module,
                exchange_manager=self.exchange_manager,
                custom_coin_tracker=custom_coin_tracker,
            )

            fetched_data = await analyzer.fetch_all_portfolio_data(
                binance_exchange, wallet_tracker, custom_coin_tracker, quick_mode=quick_mode
            )
            if not fetched_data:
                print_error("Failed to fetch necessary data for analysis.")
                input("Press Enter to return to main menu...")
                return

            print_info("Calculating portfolio metrics...")
            # Pass the wallet_tracker instance to calculate_portfolio_metrics
            portfolio_metrics = analyzer.calculate_portfolio_metrics(
                fetched_data, wallet_tracker.balance_offset, wallet_tracker
            )
            print_success("Portfolio analysis complete!")

            print_loading_animation("Preparing display", 1)
            analysis_folder = analyzer.save_portfolio_analysis(
                portfolio_metrics
            )  # Save results and get folder path

            # Enter the analysis sub-menu for exploring the live results with analysis folder context
            await self.run_analysis_submenu(
                portfolio_metrics, source_info="Live Data", analysis_folder=analysis_folder
            )

        except Exception as e:
            print_error(f"An error occurred during live portfolio analysis: {e}")
            traceback.print_exc()  # Print full traceback for debugging
            input("\nPress Enter to return to main menu...")

    async def view_past_analysis(self):
        """Handles the sub-menu for viewing past analysis files with delete functionality."""
        # No longer need to create an analyzer instance just to list files
        # analyzer = PortfolioAnalyzer(self.api_module, self.exchange_manager)

        while True:
            print_header("View Past Portfolio Analysis")
            saved_files = PortfolioAnalyzer.list_analysis_files()

            if not saved_files:
                print_info("No saved analysis files found matching pattern:")
                print_info(f"  {ANALYSIS_FILE_PATTERN}")
                input("\nPress Enter to return to main menu...")
                return

            print_info("Available analysis files (newest first):")
            for i, filename in enumerate(saved_files):
                try:
                    # NEW: Handle unified structure vs legacy files
                    if "exported_data/analysis_" in filename:
                        # New unified structure: extract timestamp from folder name
                        # Path format: exported_data/analysis_20250608_161724/portfolio_analysis.json
                        folder_name = os.path.dirname(filename).split("/")[
                            -1
                        ]  # Get "analysis_20250608_161724"
                        ts_part = folder_name.replace("analysis_", "")  # Get "20250608_161724"
                        dt_obj = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                        display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        # Legacy structure: extract timestamp from filename
                        basename = os.path.basename(filename)
                        ts_part = basename.replace("portfolio_analysis_", "").replace(".json", "")
                        dt_obj = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                        display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")

                    # Get file size for display
                    file_size = os.path.getsize(filename) / 1024  # KB
                    # Determine if analysis was run in quick mode
                    quick_flag = False
                    try:
                        with open(filename, "r") as _f:
                            meta_sample = json.load(_f)
                            quick_flag = bool(meta_sample.get("quick_mode", False))
                    except Exception:
                        quick_flag = False

                    mode_label = "[Quick]" if quick_flag else "[Full ]"
                    basename = os.path.basename(filename)
                    print(
                        f"  {Fore.CYAN}{i + 1:2d}.{Style.RESET_ALL} {basename} {mode_label} ({Style.DIM}{display_ts}{Style.RESET_ALL}) {Style.DIM}[{file_size:.1f} KB]{Style.RESET_ALL}"
                    )
                except ValueError:
                    basename = os.path.basename(filename)
                    file_size = os.path.getsize(filename) / 1024  # KB
                    print(
                        f"  {Fore.CYAN}{i + 1:2d}.{Style.RESET_ALL} {basename} ({Style.DIM}Unknown time{Style.RESET_ALL}) {Style.DIM}[{file_size:.1f} KB]{Style.RESET_ALL}"
                    )
                except OSError:
                    basename = os.path.basename(filename)
                    print(
                        f"  {Fore.CYAN}{i + 1:2d}.{Style.RESET_ALL} {basename} ({Style.DIM}File error{Style.RESET_ALL})"
                    )

            print(f"\n{Fore.YELLOW}OPTIONS:{Style.RESET_ALL}")
            print(f"  {Fore.GREEN}[number]{Style.RESET_ALL} - View analysis")
            print(
                f"  {Fore.RED}d[number]{Style.RESET_ALL} - Delete analysis (e.g., 'd1' to delete #1)"
            )
            print(f"  {Fore.YELLOW}cleanup{Style.RESET_ALL} - Delete old files (keeps newest 10)")
            print(f"  {Fore.CYAN}b{Style.RESET_ALL} - Back to main menu")
            print()

            choice = input("Choice: ").lower().strip()

            if choice == "b":
                break
            elif choice == "cleanup":
                self._cleanup_old_analysis_files(saved_files)
                continue
            elif choice.startswith("d") and len(choice) > 1:
                # Delete specific file
                try:
                    delete_index = int(choice[1:]) - 1
                    if 0 <= delete_index < len(saved_files):
                        self._delete_analysis_file(saved_files[delete_index])
                    else:
                        print_error("Invalid file number for deletion.")
                        input("Press Enter to continue...")
                except ValueError:
                    print_error("Invalid delete command. Use format 'd1', 'd2', etc.")
                    input("Press Enter to continue...")
            else:
                # View file
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(saved_files):
                        selected_file = saved_files[index]
                        try:
                            with open(selected_file, "r") as f:
                                past_data = json.load(f)
                            print_success(f"Loaded data from {os.path.basename(selected_file)}")

                            # Extract timestamp for display and analysis folder context
                            analysis_folder = None
                            try:
                                if "exported_data/analysis_" in selected_file:
                                    # New unified structure: extract timestamp from folder name
                                    analysis_folder = os.path.dirname(selected_file)
                                    folder_name = analysis_folder.split("/")[
                                        -1
                                    ]  # Get "analysis_20250608_161724"
                                    ts_part = folder_name.replace(
                                        "analysis_", ""
                                    )  # Get "20250608_161724"
                                    dt_obj = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                                    display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                                else:
                                    # Legacy structure: extract timestamp from filename
                                    basename = os.path.basename(selected_file)
                                    ts_part = basename.replace("portfolio_analysis_", "").replace(
                                        ".json", ""
                                    )
                                    dt_obj = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                                    display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                display_ts = os.path.basename(selected_file)  # Fallback

                            # Run the analysis display sub-menu with the loaded data and analysis folder context
                            await self.run_analysis_submenu(
                                past_data,
                                source_info=f"Saved {display_ts}",
                                analysis_folder=analysis_folder,
                            )
                            # After returning from submenu, loop back to file selection
                        except json.JSONDecodeError:
                            print_error(
                                f"Could not decode JSON from {os.path.basename(selected_file)}."
                            )
                            input("Press Enter to continue...")
                        except FileNotFoundError:
                            print_error(f"File {os.path.basename(selected_file)} not found.")
                            input("Press Enter to continue...")
                        except Exception as e:
                            print_error(
                                f"Error loading or displaying {os.path.basename(selected_file)}: {e}"
                            )
                            input("Press Enter to continue...")
                    else:
                        print_error("Invalid number selected.")
                        input("Press Enter to continue...")
                except ValueError:
                    print_error("Invalid input. Enter a number, 'd[number]', 'cleanup', or 'b'.")
                    input("Press Enter to continue...")

    def _delete_analysis_file(self, filepath: str) -> None:
        """Delete a specific analysis file with confirmation."""
        basename = os.path.basename(filepath)

        print(f"\n{Fore.RED}DELETE CONFIRMATION{Style.RESET_ALL}")
        print(f"File: {Fore.YELLOW}{basename}{Style.RESET_ALL}")

        # Show file details
        try:
            file_size = os.path.getsize(filepath) / 1024
            modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            print(f"Size: {file_size:.1f} KB")
            print(f"Modified: {modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except OSError:
            print("Could not read file details")

        confirm = input(f"\n{Fore.RED}Type 'DELETE' to confirm removal: {Style.RESET_ALL}")

        if confirm == "DELETE":
            try:
                os.remove(filepath)
                print_success(f"Successfully deleted {basename}")
            except OSError as e:
                print_error(f"Failed to delete {basename}: {e}")
        else:
            print_info("Deletion cancelled.")

        input("Press Enter to continue...")

    def _cleanup_old_analysis_files(self, saved_files: list) -> None:
        """Clean up old analysis files, keeping only the newest 10."""
        if len(saved_files) <= 10:
            print_info("10 or fewer files found. Nothing to clean up.")
            input("Press Enter to continue...")
            return

        files_to_delete = saved_files[10:]  # Keep first 10 (newest)

        print(f"\n{Fore.YELLOW}CLEANUP CONFIRMATION{Style.RESET_ALL}")
        print(f"This will delete {len(files_to_delete)} old analysis files, keeping the newest 10.")
        print(f"Files to be deleted:")

        for i, filepath in enumerate(files_to_delete[:5]):  # Show first 5
            basename = os.path.basename(filepath)
            try:
                file_size = os.path.getsize(filepath) / 1024
                print(f"  • {basename} ({file_size:.1f} KB)")
            except OSError:
                print(f"  • {basename}")

        if len(files_to_delete) > 5:
            print(f"  ... and {len(files_to_delete) - 5} more files")

        confirm = input(f"\n{Fore.YELLOW}Type 'CLEANUP' to confirm: {Style.RESET_ALL}")

        if confirm == "CLEANUP":
            deleted_count = 0
            failed_count = 0

            for filepath in files_to_delete:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except OSError:
                    failed_count += 1

            if deleted_count > 0:
                print_success(f"Successfully deleted {deleted_count} files")
            if failed_count > 0:
                print_warning(f"Failed to delete {failed_count} files")
        else:
            print_info("Cleanup cancelled.")

        input("Press Enter to continue...")

    def manage_api_keys(self):
        """Handles the API key management sub-menu."""
        from api_clients.api_manager import api_key_manager, APICredentials
        import getpass
        from datetime import datetime

        # Professional color scheme
        PRIMARY = Fore.WHITE + Style.BRIGHT
        SUCCESS = Fore.GREEN + Style.BRIGHT
        WARNING = Fore.YELLOW
        ERROR = Fore.RED
        ACCENT = Fore.CYAN
        SUBTLE = Style.DIM
        RESET = Style.RESET_ALL

        # Authenticate first
        if not api_key_manager.authenticate():
            print_error("Authentication failed. Cannot access API key management.")
            input(f"{SUBTLE}Press Enter to return to main menu...{RESET}")
            return

        while True:
            print_header("API Key Management")

            print(f"\n{PRIMARY}API KEY OPTIONS{RESET}")
            print(f"{SUBTLE}{'─' * 17}{RESET}")
            print(f"{ACCENT}1.{RESET} {SUCCESS}Add API Key{RESET}")
            print(f"{ACCENT}2.{RESET} {PRIMARY}View Stored Keys{RESET}")
            print(f"{ACCENT}3.{RESET} {WARNING}Remove API Key{RESET}")
            print(f"{ACCENT}4.{RESET} {SUBTLE}Back to Main Menu{RESET}")
            print(f"{SUBTLE}{'═' * 40}{RESET}")

            choice = input(f"{PRIMARY}Select option (1-4): {RESET}")

            if choice == "1":
                # Add API Key
                self._add_api_key(
                    api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
                )
            elif choice == "2":
                # View stored keys
                self._view_stored_keys(
                    api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
                )
            elif choice == "3":
                # Remove API key
                self._remove_api_key(
                    api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
                )
            elif choice == "4":
                # Back to main menu
                break
            else:
                print(f"{ERROR}✘ Invalid choice. Please try again.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")

    def _add_api_key(
        self, api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
    ):
        """Add a new API key."""
        from api_clients.api_manager import APICredentials
        import getpass
        from datetime import datetime

        print_header("Add API Key")

        print(f"{PRIMARY}SUPPORTED EXCHANGES{RESET}")
        print(f"{SUBTLE}{'─' * 20}{RESET}")
        exchanges = list(api_key_manager.supported_exchanges.items())
        for i, (key, name) in enumerate(exchanges, 1):
            print(f"{ACCENT}{i}.{RESET} {name} ({key})")

        print(f"{ACCENT}{len(exchanges) + 1}.{RESET} {SUBTLE}Cancel{RESET}")

        try:
            choice = int(input(f"\n{PRIMARY}Select exchange (1-{len(exchanges) + 1}): {RESET}"))
            if choice == len(exchanges) + 1:
                return
            if 1 <= choice <= len(exchanges):
                exchange_key = exchanges[choice - 1][0]
                exchange_name = exchanges[choice - 1][1]
            else:
                print(f"{ERROR}✘ Invalid choice.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")
                return
        except ValueError:
            print(f"{ERROR}✘ Invalid input.{RESET}")
            input(f"{SUBTLE}Press Enter to continue...{RESET}")
            return

        # Check if credentials already exist
        existing = api_key_manager.list_stored_credentials()
        if exchange_key in existing:
            confirm = input(
                f"{WARNING}⚠ Credentials for {exchange_name} already exist. Overwrite? (y/N): {RESET}"
            ).lower()
            if confirm != "y":
                print(f"{SUBTLE}Operation cancelled.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")
                return

        print(f"\n{PRIMARY}ENTER CREDENTIALS FOR {exchange_name.upper()}{RESET}")
        print(f"{SUBTLE}{'─' * (25 + len(exchange_name))}{RESET}")

        # Get API key
        api_key = input(f"{ACCENT}API Key: {RESET}").strip()
        if not api_key:
            print(f"{ERROR}✘ API Key is required.{RESET}")
            input(f"{SUBTLE}Press Enter to continue...{RESET}")
            return

        # Get API secret
        api_secret = getpass.getpass(f"{ACCENT}API Secret: {RESET}").strip()
        if not api_secret:
            print(f"{ERROR}✘ API Secret is required.{RESET}")
            input(f"{SUBTLE}Press Enter to continue...{RESET}")
            return

        # Get passphrase (required for OKX, optional for others)
        passphrase = None
        if exchange_key == "okx":
            passphrase = getpass.getpass(f"{ACCENT}Passphrase (required for OKX): {RESET}").strip()
            if not passphrase:
                print(f"{ERROR}✘ Passphrase is required for OKX.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")
                return
        else:
            passphrase_input = getpass.getpass(
                f"{ACCENT}Passphrase (optional, press Enter to skip): {RESET}"
            ).strip()
            if passphrase_input:
                passphrase = passphrase_input
        testnet = False

        # Get optional note
        note = input(f"{ACCENT}Note (optional): {RESET}").strip()
        if not note:
            note = None

        # Create credentials
        credentials = APICredentials(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=testnet,
            note=note,
            created_at=datetime.now().isoformat(),
        )

        try:
            api_key_manager.store_credentials(exchange_key, credentials)
            print(f"{SUCCESS}✅ API credentials successfully stored for {exchange_name}!{RESET}")
        except Exception as e:
            print(f"{ERROR}✘ Failed to store credentials: {e}{RESET}")

        input(f"{SUBTLE}Press Enter to continue...{RESET}")

    def _view_stored_keys(
        self, api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
    ):
        """View stored API keys."""
        print_header("Stored API Keys")

        try:
            stored_creds = api_key_manager.list_stored_credentials()

            if not stored_creds:
                print(f"{SUBTLE}No API credentials stored yet.{RESET}")
                print(f"{SUBTLE}Use 'Add API Key' to store your first credentials.{RESET}")
            else:
                print(f"{PRIMARY}STORED CREDENTIALS{RESET}")
                print(f"{SUBTLE}{'─' * 19}{RESET}")

                for exchange, info in stored_creds.items():
                    exchange_name = info["exchange_name"]
                    api_key_preview = info["api_key_preview"]
                    has_passphrase = info["has_passphrase"]
                    testnet = info.get("testnet", False)
                    note = info["note"]
                    created_at = info["created_at"]

                    print(f"\n{ACCENT}🔶 {exchange_name}{RESET}")
                    print(f"   API Key:     {SUCCESS}{api_key_preview}{RESET}")
                    print(f"   Passphrase:  {'✅ Yes' if has_passphrase else '❌ No'}")
                    print(f"   Environment: {'🧪 Testnet' if testnet else '🌐 Mainnet'}")
                    if note:
                        print(f"   Note:        {SUBTLE}{note}{RESET}")
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at)
                            date_str = dt.strftime("%Y-%m-%d %H:%M")
                            print(f"   Created:     {SUBTLE}{date_str}{RESET}")
                        except ValueError:
                            print(f"   Created:     {SUBTLE}{created_at}{RESET}")

                print(
                    f"\n{SUBTLE}For security, API secrets are encrypted and not displayed.{RESET}"
                )

        except Exception as e:
            print(f"{ERROR}✘ Failed to retrieve stored credentials: {e}{RESET}")

        input(f"{SUBTLE}Press Enter to continue...{RESET}")

    def _remove_api_key(
        self, api_key_manager, PRIMARY, SUCCESS, WARNING, ERROR, ACCENT, SUBTLE, RESET
    ):
        """Remove an API key."""
        print_header("Remove API Key")

        try:
            stored_creds = api_key_manager.list_stored_credentials()

            if not stored_creds:
                print(f"{SUBTLE}No API credentials stored to remove.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")
                return

            print(f"{PRIMARY}STORED CREDENTIALS{RESET}")
            print(f"{SUBTLE}{'─' * 19}{RESET}")

            exchanges = list(stored_creds.items())
            for i, (exchange_key, info) in enumerate(exchanges, 1):
                exchange_name = info["exchange_name"]
                api_key_preview = info["api_key_preview"]
                print(f"{ACCENT}{i}.{RESET} {exchange_name} ({api_key_preview})")

            print(f"{ACCENT}{len(exchanges) + 1}.{RESET} {SUBTLE}Cancel{RESET}")

            try:
                choice = int(
                    input(
                        f"\n{PRIMARY}Select credentials to remove (1-{len(exchanges) + 1}): {RESET}"
                    )
                )
                if choice == len(exchanges) + 1:
                    return
                if 1 <= choice <= len(exchanges):
                    exchange_key = exchanges[choice - 1][0]
                    exchange_name = exchanges[choice - 1][1]["exchange_name"]
                else:
                    print(f"{ERROR}✘ Invalid choice.{RESET}")
                    input(f"{SUBTLE}Press Enter to continue...{RESET}")
                    return
            except ValueError:
                print(f"{ERROR}✘ Invalid input.{RESET}")
                input(f"{SUBTLE}Press Enter to continue...{RESET}")
                return

            # Confirm deletion
            print(
                f"{WARNING}⚠ WARNING: This will permanently delete API credentials for {exchange_name}.{RESET}"
            )
            confirm = input(f"{WARNING}Type 'DELETE' to confirm: {RESET}")

            if confirm == "DELETE":
                if api_key_manager.remove_credentials(exchange_key):
                    print(
                        f"{SUCCESS}✅ API credentials for {exchange_name} successfully removed!{RESET}"
                    )
                else:
                    print(f"{ERROR}✘ Failed to remove credentials for {exchange_name}.{RESET}")
            else:
                print(f"{SUBTLE}Deletion cancelled.{RESET}")

        except Exception as e:
            print(f"{ERROR}✘ Failed to remove credentials: {e}{RESET}")

        input(f"{SUBTLE}Press Enter to continue...{RESET}")

    async def custom_coins_menu(self):
        """Handles the custom coins management sub-menu (Asynchronous)."""
        # Ensure a single CustomCoinTracker instance is used throughout this menu's lifecycle.
        if not hasattr(self, "custom_coin_tracker") or self.custom_coin_tracker is None:
            print_warning(
                "custom_coins_menu: Creating a new CustomCoinTracker instance. For shared state, inject it into MenuSystem."
            )
            self.custom_coin_tracker = CustomCoinTracker()
        custom_coin_tracker = self.custom_coin_tracker

        # Ensure PortfolioAnalyzer uses the same custom_coin_tracker instance and other necessary dependencies.
        if (
            not hasattr(self, "portfolio_analyzer")
            or self.portfolio_analyzer is None
            or self.portfolio_analyzer.custom_coin_tracker is not custom_coin_tracker
            or self.portfolio_analyzer.api_module is not self.api_module
            or self.portfolio_analyzer.exchange_manager is not self.exchange_manager
        ):
            if not hasattr(self, "portfolio_analyzer") or self.portfolio_analyzer is None:
                print_warning(
                    "custom_coins_menu: Creating new PortfolioAnalyzer. For shared state, inject it."
                )
            else:
                print_warning(
                    "custom_coins_menu: Re-creating PortfolioAnalyzer due to dependency mismatch."
                )
            self.portfolio_analyzer = PortfolioAnalyzer(
                api_module=self.api_module,
                exchange_manager=self.exchange_manager,
                custom_coin_tracker=custom_coin_tracker,
            )
        portfolio_analyzer = self.portfolio_analyzer

        PRIMARY = Fore.WHITE + Style.BRIGHT
        SUCCESS = Fore.GREEN + Style.BRIGHT
        WARNING = Fore.YELLOW
        ERROR = Fore.RED
        ACCENT = Fore.CYAN
        SUBTLE = Style.DIM
        RESET = Style.RESET_ALL

        while True:
            clear_screen()  # Added screen clear here
            print_header("Custom Coins Menu")
            print(f"{ACCENT}1.{RESET} {PRIMARY}Add Custom Coin{RESET}")
            print(f"{ACCENT}2.{RESET} {PRIMARY}View All Coins{RESET}")
            print(f"{ACCENT}3.{RESET} {PRIMARY}Remove Coin{RESET}")
            print(f"{ACCENT}4.{RESET} {PRIMARY}Test All Custom Coin Prices{RESET}")
            print(f"{ACCENT}5.{RESET} {SUBTLE}Back to Main Menu{RESET}")
            print(f"{SUBTLE}{'-' * 40}{RESET}")
            choice = input(f"{PRIMARY}Select option (1-5): {RESET}")

            if choice == "1":
                clear_screen()
                print_header("Add Custom Coin")
                print_info("Enter the coin symbol (e.g., PEPE, SHIB).")
                symbol = input("Enter coin symbol: ").strip().upper()
                if symbol:
                    if symbol in custom_coin_tracker.custom_coins:
                        print_warning(f"{symbol} is already tracked.")
                    else:
                        custom_coin_tracker.add_custom_coin(symbol=symbol)
                        print_success(f"{symbol} added. Attempting to fetch full name...!")

                        try:
                            price_service_instance = portfolio_analyzer.price_service
                            if price_service_instance:
                                print_info(f"Fetching name for {symbol}...")
                                full_name = await price_service_instance.get_coin_full_name(symbol)
                                if full_name and full_name.lower() != symbol.lower():
                                    custom_coin_tracker.update_coin_name(symbol, full_name)
                                    print_success(f"Full name for {symbol} updated to: {full_name}")
                                elif full_name:
                                    print_info(
                                        f"Full name for {symbol} is the same as symbol: {full_name}"
                                    )
                                else:
                                    print_warning(
                                        f"Could not automatically fetch full name for {symbol}. It remains '{symbol}'."
                                    )
                            else:
                                print_warning("Price service not available to fetch full name.")
                        except Exception as e:
                            print_error(f"Error fetching full name for {symbol}: {e}")
                        print_info("The system will automatically fetch prices from exchanges.")
                else:
                    print_error("Symbol cannot be empty.")
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
            elif choice == "2":
                clear_screen()
                print_header("View All Coins")
                custom_coin_tracker.list_custom_coins()
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
            elif choice == "3":
                clear_screen()
                print_header("Remove Custom Coin")
                symbol_to_remove = input("Enter symbol of coin to remove: ").strip().upper()
                if symbol_to_remove in custom_coin_tracker.custom_coins:
                    custom_coin_tracker.remove_custom_coin(symbol_to_remove)
                else:
                    print_warning(f"{symbol_to_remove} is not a tracked custom coin.")
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
            elif choice == "4":
                clear_screen()
                print_header("Test All Custom Coin Prices")
                await self._test_all_custom_coin_prices(custom_coin_tracker, portfolio_analyzer)
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")
            elif choice == "5":
                clear_screen()  # Clear before going back to main menu
                break
            else:
                print_error("Invalid choice.")
                input(f"\n{SUBTLE}Press Enter to continue...{RESET}")

    async def _test_all_custom_coin_prices(self, custom_coin_tracker, portfolio_analyzer):
        """Test price fetching for all custom coins with improved display."""
        PRIMARY = Fore.WHITE + Style.BRIGHT
        SUCCESS = Fore.GREEN + Style.BRIGHT
        WARNING = Fore.YELLOW
        ERROR = Fore.RED
        ACCENT = Fore.CYAN
        SUBTLE = Style.DIM
        RESET = Style.RESET_ALL

        print(f"\n{ACCENT}🧪 TESTING CUSTOM COIN PRICES{RESET}")
        print(f"{SUBTLE}{'═' * 35}{RESET}")

        all_custom_symbols = custom_coin_tracker.get_all_symbols()
        if not all_custom_symbols:
            print(f"{WARNING}📭 No custom coins added to test.{RESET}")
            print(f"{SUBTLE}💡 Use 'Add Custom Coin' to start tracking prices.{RESET}")
            return

        print(f"{PRIMARY}📊 Testing {len(all_custom_symbols)} custom coins...{RESET}")
        print(f"{SUBTLE}🔍 Fetching: {', '.join(all_custom_symbols)}{RESET}")
        print(f"{SUBTLE}{'─' * 50}{RESET}")

        try:
            import time

            start_time = time.time()

            # Use the portfolio_analyzer's method which uses the standard price_service
            fetched_prices = await portfolio_analyzer.get_custom_coin_prices(all_custom_symbols)

            elapsed_time = time.time() - start_time

            if not fetched_prices:
                print(f"{WARNING}⚠️  No prices returned from any service.{RESET}")
                print(f"{SUBTLE}💡 Check your internet connection and try again.{RESET}")
                return

            # Results summary
            successful_count = sum(1 for price in fetched_prices.values() if price and price > 0)
            failed_count = len(all_custom_symbols) - successful_count

            print(f"\n{PRIMARY}📈 PRICE TEST RESULTS{RESET}")
            print(f"{SUBTLE}{'─' * 22}{RESET}")
            print(f"{SUCCESS}✅ Successful: {successful_count}{RESET}")
            print(f"{ERROR}❌ Failed: {failed_count}{RESET}")
            print(f"{ACCENT}⏱️  Time taken: {elapsed_time:.1f}s{RESET}")
            print(f"{SUBTLE}{'─' * 50}{RESET}")

            # Individual results
            for symbol in all_custom_symbols:
                price = fetched_prices.get(symbol)
                coin_data = custom_coin_tracker.get_coin_data(symbol)
                name = coin_data.get("name", symbol)

                # Format display name
                if name.lower() != symbol.lower():
                    display_name = f"{name} ({symbol.upper()})"
                else:
                    display_name = symbol.upper()

                # Truncate long names
                if len(display_name) > 25:
                    display_name = display_name[:22] + "..."

                if price and price > 0:
                    # Format price based on value
                    if price >= 1:
                        price_str = f"${price:,.4f}"
                    elif price >= 0.01:
                        price_str = f"${price:.6f}"
                    else:
                        price_str = f"${price:.8f}"

                    print(f"  {SUCCESS}✅{RESET} {display_name:<25} {PRIMARY}{price_str}{RESET}")
                else:
                    print(f"  {ERROR}❌{RESET} {display_name:<25} {ERROR}Price not found{RESET}")

            print(f"{SUBTLE}{'─' * 50}{RESET}")

            # Performance feedback (only warn when noticeably slow)
            if elapsed_time >= 10:
                print(f"{WARNING}⏳ Price fetching took longer than expected{RESET}")
                print(f"{SUBTLE}💡 This may be due to API rate limits or network delays{RESET}")

        except Exception as e:
            print(f"{ERROR}❌ Error during price testing: {e}{RESET}")
            print(f"{SUBTLE}💡 Please check your internet connection and API availability{RESET}")

    async def main(self):
        """Main asynchronous entry point of the application."""
        print_info("Initializing Portfolio Tracker...")
        binance_exchange = None

        # Initialize Wallet Tracker (loads saved wallets)
        from models.wallet_tracker import MultiChainWalletTracker
        from port2 import initialize_binance, get_exchange_manager

        wallet_tracker_instance = MultiChainWalletTracker()

        # Initialize Binance Exchange (synchronous part, run in executor)
        # Needed for price fetching even if not tracking Binance balance directly
        print_loading_animation("Validating credentials & initializing services...", 1)
        try:
            loop = asyncio.get_running_loop()
            binance_exchange = await loop.run_in_executor(None, initialize_binance)
            if not binance_exchange:
                from config.constants import DEBUG_MODE

                if DEBUG_MODE:
                    print_warning("⚠️  No exchanges initialized (debug mode - this is expected)")
                    print_info("🐛 Debug mode: Continuing without exchange connections")
                    print_info(
                        "💡 You can still use wallet management, view analysis, and other features"
                    )
                else:
                    print_warning(
                        "⚠️  Binance exchange not initialized. Add API keys via 'Manage API Keys' to enable live pricing."
                    )
                binance_exchange = None
            else:
                # Success is silent here, or a very generic "Services ready."
                # The main_menu will handle displaying authenticated services.
                pass

                # Update our exchange_manager reference after initialization
                from port2 import get_exchange_manager

                self.exchange_manager = get_exchange_manager()

        except Exception as e:
            # Check if we're in debug mode - if so, allow continuing without exchanges
            from config.constants import DEBUG_MODE

            if DEBUG_MODE:
                print_warning(f"⚠️  Exchange initialization error in debug mode: {e}")
                print_info("🐛 Debug mode: Continuing without exchange connections")
                binance_exchange = None
            else:
                print_warning(f"⚠️  Exchange initialization error: {e}")
                binance_exchange = None

        # Ensure we have an exchange manager reference even if initialization failed
        if self.exchange_manager is None:
            from port2 import get_exchange_manager

            self.exchange_manager = get_exchange_manager()

        # Start the main menu loop (now async), passing the initialized tracker instance
        if wallet_tracker_instance:  # Ensure instance was created
            await self.main_menu(binance_exchange, wallet_tracker_instance)
        else:
            print_error("Failed to initialize Wallet Tracker. Exiting.")
            return
