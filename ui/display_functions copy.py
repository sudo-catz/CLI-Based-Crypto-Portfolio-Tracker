# -*- coding: utf-8 -*-
"""
Display Functions Module
------------------------
Contains all display/UI functions for the portfolio tracker.
"""

from typing import Dict, Any, List, Optional
from colorama import Fore, Style
from tabulate import tabulate
from utils.helpers import format_currency, print_header, print_error, get_menu_choice
from utils.display_theme import theme
from utils.enhanced_price_service import enhanced_price_service
from models.custom_coins import CustomCoinTracker
from datetime import datetime
from config.constants import SUPPORTED_CHAINS, SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY
import os
from pathlib import Path
import json


def display_exchange_detailed_breakdown(
    exchange_name: str, detailed_data: Optional[Dict[str, Any]], failed_sources: List[str]
):
    """Clean exchange breakdown with improved formatting."""

    if exchange_name in failed_sources:
        print(f"\n{theme.PRIMARY}{exchange_name} Status{theme.RESET}")
        print("Failed to fetch data")
        return

    if detailed_data is None:
        print(f"\n{theme.PRIMARY}{exchange_name} Status{theme.RESET}")
        print("Detailed breakdown not available")
        return

    # Safe handling of total equity
    total_equity = detailed_data.get("total_equity", 0) or 0

    if exchange_name.lower() == "binance":
        print(f"\n{theme.PRIMARY}Binance Spot Account{theme.RESET}")
        print(f"Spot Equity: {format_currency(total_equity)}")
        print("See account types above for complete balance")
    else:
        print(f"\n{theme.PRIMARY}{exchange_name} Detail{theme.RESET}")
        print(f"Total Equity: {format_currency(total_equity)}")

    assets = detailed_data.get("assets", [])[:10]  # Show top 10 assets

    if assets:
        print("\nTop Holdings")
        print("─" * 20)

        def format_balance(value, decimals=6):
            """Smart balance formatting"""
            if value >= 1:
                return f"{value:,.4f}"
            elif value >= 0.01:
                return f"{value:.6f}"
            else:
                return f"{value:.8f}"

        # Prepare table data based on exchange type
        table_data = []
        headers = ["Asset", "Balance", "USD Value"]

        if exchange_name.lower() == "okx":
            headers.append("Available")
            for asset in assets:
                coin = asset.get("coin", "N/A")
                equity = asset.get("equity", 0) or 0
                available = asset.get("available", 0) or 0
                clean_equity = f"${equity:,.0f}" if equity >= 1 else f"${equity:.3f}"

                table_data.append(
                    [coin, format_balance(equity), clean_equity, format_balance(available)]
                )

        elif exchange_name.lower() == "binance":
            headers.extend(["Available", "Locked"])
            for asset in assets:
                coin = asset.get("coin", "N/A")
                total_val = asset.get("total", 0) or 0
                available = asset.get("free", 0) or 0
                locked = asset.get("locked", 0) or 0
                usd_value = asset.get("usd_value", 0) or 0
                clean_usd = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append(
                    [
                        coin,
                        format_balance(total_val),
                        clean_usd,
                        format_balance(available),
                        format_balance(locked),
                    ]
                )

        elif exchange_name.lower() == "bybit":
            headers.append("Available")
            for asset in assets:
                coin = asset.get("coin", "N/A")
                total_val = asset.get("total", asset.get("equity", 0)) or 0
                usd_value = asset.get("usd_value", asset.get("equity", 0)) or 0
                available = asset.get("free", asset.get("available", 0)) or 0
                clean_usd = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append(
                    [coin, format_balance(total_val), clean_usd, format_balance(available)]
                )

        elif exchange_name.lower() == "backpack":
            headers.extend(["Available", "Locked"])
            for asset in assets:
                coin = asset.get("coin", "N/A")
                total_val = asset.get("total", 0) or 0
                available = asset.get("available", 0) or 0
                locked = asset.get("locked", 0) or 0
                usd_value = asset.get("usd_value", 0) or 0
                clean_usd = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append(
                    [
                        coin,
                        format_balance(total_val),
                        clean_usd,
                        format_balance(available),
                        format_balance(locked),
                    ]
                )

        if table_data:
            print(
                f"\n{tabulate(table_data, headers=headers, tablefmt='simple', numalign='right', stralign='left')}"
            )

        total_assets = len(detailed_data.get("assets", []))
        if total_assets > 10 and exchange_name.lower() != "backpack":
            print(f"\n... and {total_assets - 10} more assets")
    else:
        print("\nNo assets to display")

    print()


def display_comprehensive_overview(metrics: Dict[str, Any], source_info: str = "Live Data"):
    """Enhanced portfolio overview with improved visual design."""
    print_header(f"Portfolio Overview • {source_info}")

    total_value = metrics.get("total_portfolio_value", 0.0)
    adjusted_value = metrics.get("adjusted_portfolio_value", 0.0)
    offset = metrics.get("balance_offset", 0.0)
    crypto_prices = metrics.get("crypto_prices", {})
    timestamp_str = metrics.get("timestamp", "N/A")
    failed_sources = metrics.get("failed_sources", [])

    try:
        dt_obj = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        display_ts = timestamp_str

    # Enhanced timestamp display
    print(f"\n{theme.ACCENT}⏰ Analysis Timestamp: {display_ts}{theme.RESET}")

    if crypto_prices:
        print(f"{theme.SUBTLE}📊 Market data captured at time of analysis{theme.RESET}")

    print(f"{theme.SUBTLE}{'─' * 60}{theme.RESET}")

    # Failure Summary with better visibility
    if failed_sources:
        print(
            f"\n{theme.WARNING}⚠  Data Issues: {', '.join(failed_sources)} (totals may be incomplete){theme.RESET}"
        )
        print(f"{theme.SUBTLE}{'─' * 60}{theme.RESET}")

    # Enhanced Portfolio Values Section
    print(f"\n{theme.PRIMARY}💰 PORTFOLIO VALUE{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")

    print(f"Total Value:      {theme.ACCENT}{format_currency(total_value)}{theme.RESET}")

    if offset > 0:
        print(f"Applied Offset:   {theme.WARNING}-{format_currency(offset)}{theme.RESET}")
        print(f"Net Portfolio:    {theme.SUCCESS}{format_currency(adjusted_value)}{theme.RESET}")
    else:
        print(f"Applied Offset:   {theme.SUBTLE}{format_currency(offset)}{theme.RESET}")
        print(f"Net Portfolio:    {theme.SUCCESS}{format_currency(adjusted_value)}{theme.RESET}")

    # --- Distribution Summary ---
    total_cex = metrics.get("total_cex_balance", 0.0)
    total_defi = metrics.get("total_defi_balance", 0.0)

    print(f"\n{theme.PRIMARY}ALLOCATION{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 12}{theme.RESET}")

    if total_value > 0:
        cex_pct = (total_cex / total_value) * 100
        defi_pct = (total_defi / total_value) * 100
        print(
            f"Centralized:      {theme.ACCENT}{format_currency(total_cex)} ({cex_pct:.1f}%){theme.RESET}"
        )
        print(
            f"DeFi/Wallets:     {theme.ACCENT}{format_currency(total_defi)} ({defi_pct:.1f}%){theme.RESET}"
        )
    else:
        print(f"Centralized:      {theme.ACCENT}{format_currency(total_cex)}{theme.RESET}")
        print(f"DeFi/Wallets:     {theme.ACCENT}{format_currency(total_defi)}{theme.RESET}")

    # --- Platform Breakdown (Clean Table) ---
    print(f"\n{theme.PRIMARY}PLATFORM BREAKDOWN{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")

    headers = [
        f"{theme.PRIMARY}Platform{theme.RESET}",
        f"{theme.PRIMARY}Balance{theme.RESET}",
        f"{theme.PRIMARY}Share{theme.RESET}",
    ]
    data = []
    sources = [
        "Binance",
        "OKX",
        "Bybit",
        "Backpack",
        "Ethereum",
        "Bitcoin",
        "NEAR",
        "Aptos",
        "Solana",
        "Hyperliquid",
    ]
    grand_total_for_perc = total_value if total_value > 0 else 1

    for source in sources:
        key = source.lower()
        balance = metrics.get(key)

        if balance is not None and balance > 1e-3:
            percentage = (balance / grand_total_for_perc) * 100

            # Color coding by platform type
            if source in ["Binance", "OKX", "Bybit", "Backpack"]:
                platform_color = theme.ACCENT
            elif source in ["Ethereum", "Bitcoin", "NEAR", "Aptos", "Solana"]:
                platform_color = theme.SUCCESS
            else:  # Hyperliquid
                platform_color = theme.WARNING

            data.append(
                [
                    f"{platform_color}{source}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(balance)}{theme.RESET}",
                    f"{theme.SUBTLE}{percentage:.1f}%{theme.RESET}",
                    balance,  # For sorting
                ]
            )
        elif source in failed_sources:
            data.append(
                [
                    f"{theme.ERROR}{source} (Error){theme.RESET}",
                    f"{theme.ERROR}N/A{theme.RESET}",
                    f"{theme.ERROR}N/A{theme.RESET}",
                    -1,
                ]
            )

    if data:
        # Sort by balance descending
        data.sort(key=lambda row: row[3], reverse=True)
        # Remove raw balance before displaying
        display_data = [row[:-1] for row in data]
        print(
            tabulate(
                display_data, headers=headers, tablefmt="simple", numalign="right", stralign="left"
            )
        )
    else:
        print(f"{theme.SUBTLE}No platform data available{theme.RESET}")

    # --- Market Prices ---
    btc_price = crypto_prices.get("BTC")
    eth_price = crypto_prices.get("ETH")
    sol_price = crypto_prices.get("SOL")
    near_price = crypto_prices.get("NEAR")
    apt_price = crypto_prices.get("APT")

    # Get custom coin data for integration
    custom_coin_data_from_metrics = metrics.get("custom_coin_data", {})  # Renamed to avoid conflict
    custom_coin_prices = metrics.get("custom_coin_prices", {})

    # Ensure custom_coins_data is a dictionary
    custom_coins_list = custom_coin_data_from_metrics.get("custom_coins_data", {})
    if not isinstance(custom_coins_list, dict):
        custom_coins_list = {}

    # Display market prices with more prominence and all supported currencies
    price_available = any(
        [
            btc_price and btc_price > 0,
            eth_price and eth_price > 0,
            sol_price and sol_price > 0,
            near_price and near_price > 0,
            apt_price and apt_price > 0,
        ]
    )

    # Check if we have custom coin prices to add
    custom_prices_available = any(
        custom_coin_prices.get(symbol) and custom_coin_prices.get(symbol) > 0
        for symbol in custom_coins_list.keys()
    )

    if price_available or custom_prices_available:
        print(f"\n{theme.PRIMARY}📈 MARKET SNAPSHOT{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")

        price_data_table = []  # Renamed to avoid conflict with user's example

        # Add major cryptocurrencies first
        if btc_price and btc_price > 0:
            price_data_table.append(
                [
                    f"{theme.ACCENT}Bitcoin (BTC){theme.RESET}",
                    f"{theme.SUCCESS}{format_currency(btc_price)}{theme.RESET}",
                ]
            )
        if eth_price and eth_price > 0:
            price_data_table.append(
                [
                    f"{theme.ACCENT}Ethereum (ETH){theme.RESET}",
                    f"{theme.SUCCESS}{format_currency(eth_price)}{theme.RESET}",
                ]
            )
        if sol_price and sol_price > 0:
            price_data_table.append(
                [
                    f"{theme.ACCENT}Solana (SOL){theme.RESET}",
                    f"{theme.SUCCESS}{format_currency(sol_price)}{theme.RESET}",
                ]
            )
        if near_price and near_price > 0:
            price_data_table.append(
                [
                    f"{theme.ACCENT}NEAR Protocol (NEAR){theme.RESET}",
                    f"{theme.SUCCESS}{format_currency(near_price)}{theme.RESET}",
                ]
            )
        if apt_price and apt_price > 0:
            price_data_table.append(
                [
                    f"{theme.ACCENT}Aptos (APT){theme.RESET}",
                    f"{theme.SUCCESS}{format_currency(apt_price)}{theme.RESET}",
                ]
            )

        # Add custom cryptocurrencies with prices
        for symbol, coin_info in custom_coins_list.items():
            # Ensure coin_info is a dictionary
            if not isinstance(coin_info, dict):
                continue

            last_price = custom_coin_prices.get(symbol)
            name = coin_info.get("name", symbol)

            if last_price and last_price > 0:
                # Format: "Name (SYMBOL)" or just "SYMBOL" if no name or name is same as symbol
                display_name_str = symbol  # Default to symbol
                if name and name.lower() != symbol.lower():
                    display_name_str = f"{name.capitalize()} ({symbol.upper()})"
                else:
                    # If name is same as symbol, try to capitalize symbol or use as is
                    display_name_str = (
                        f"{symbol.capitalize()} ({symbol.upper()})"
                        if len(symbol) > 1
                        else symbol.upper()
                    )

                # Adjust formatting for very small prices
                price_display_str = f"{format_currency(last_price)}"
                if 0 < last_price < 0.01:
                    price_display_str = f"${last_price:.8f}"  # Show more precision
                elif last_price == 0:  # Explicitly show $0.00 if it's truly zero after fetch
                    price_display_str = "$0.00"

                price_data_table.append(
                    [
                        f"{theme.ACCENT}{display_name_str}{theme.RESET}",
                        f"{theme.SUCCESS}{price_display_str}{theme.RESET}",
                    ]
                )
            elif (
                custom_coin_data_from_metrics.get("custom_coins_count", 0) > 0
            ):  # Only show N/A if it was intended to be tracked
                display_name_str = symbol
                if name and name.lower() != symbol.lower():
                    display_name_str = f"{name.capitalize()} ({symbol.upper()})"
                else:
                    display_name_str = (
                        f"{symbol.capitalize()} ({symbol.upper()})"
                        if len(symbol) > 1
                        else symbol.upper()
                    )
                price_data_table.append(
                    [
                        f"{theme.ACCENT}{display_name_str}{theme.RESET}",
                        f"{theme.ERROR}No Price{theme.RESET}",
                    ]
                )

        if price_data_table:
            print(
                tabulate(
                    price_data_table,
                    headers=[
                        f"{theme.PRIMARY}Cryptocurrency{theme.RESET}",
                        f"{theme.PRIMARY}Price (USD){theme.RESET}",
                    ],
                    tablefmt="simple",
                    numalign="right",
                    stralign="left",
                )
            )

    # --- Portfolio in Crypto Terms ---
    if adjusted_value > 0 and price_available:
        print(f"\n{theme.PRIMARY}💰 PORTFOLIO VALUE IN CRYPTO{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 28}{theme.RESET}")

        # Create crypto portfolio table with safe division
        crypto_portfolio_data = []
        if btc_price and btc_price > 0:
            crypto_portfolio_data.append(
                [
                    f"{theme.WARNING}Bitcoin{theme.RESET}",
                    f"{theme.ACCENT}{adjusted_value / btc_price:.6f} BTC{theme.RESET}",
                ]
            )
        if eth_price and eth_price > 0:
            crypto_portfolio_data.append(
                [
                    f"{theme.WARNING}Ethereum{theme.RESET}",
                    f"{theme.ACCENT}{adjusted_value / eth_price:.4f} ETH{theme.RESET}",
                ]
            )
        if sol_price and sol_price > 0:
            crypto_portfolio_data.append(
                [
                    f"{theme.WARNING}Solana{theme.RESET}",
                    f"{theme.ACCENT}{adjusted_value / sol_price:.2f} SOL{theme.RESET}",
                ]
            )
        if near_price and near_price > 0:
            crypto_portfolio_data.append(
                [
                    f"{theme.WARNING}NEAR{theme.RESET}",
                    f"{theme.ACCENT}{adjusted_value / near_price:.2f} NEAR{theme.RESET}",
                ]
            )
        if apt_price and apt_price > 0:
            crypto_portfolio_data.append(
                [
                    f"{theme.WARNING}Aptos{theme.RESET}",
                    f"{theme.ACCENT}{adjusted_value / apt_price:.2f} APT{theme.RESET}",
                ]
            )

        if crypto_portfolio_data:
            print(
                tabulate(
                    crypto_portfolio_data,
                    headers=[
                        f"{theme.PRIMARY}Currency{theme.RESET}",
                        f"{theme.PRIMARY}Portfolio Value{theme.RESET}",
                    ],
                    tablefmt="simple",
                    numalign="right",
                    stralign="left",
                )
            )

    # --- Risk Assessment ---
    print(f"\n{theme.PRIMARY}RISK ASSESSMENT{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 17}{theme.RESET}")

    if total_value > 0:
        cex_percentage = (total_cex / total_value) * 100
        if cex_percentage > 80:
            print(
                f"{theme.ERROR}• High CEX concentration ({cex_percentage:.1f}%) - Consider diversification{theme.RESET}"
            )
        elif cex_percentage > 60:
            print(
                f"{theme.WARNING}• Moderate CEX concentration ({cex_percentage:.1f}%){theme.RESET}"
            )
        else:
            print(f"{theme.SUCCESS}• Balanced allocation between CEX and DeFi{theme.RESET}")

        if offset > 0:
            offset_pct = (offset / total_value) * 100
            if offset_pct > 15:
                print(
                    f"{theme.WARNING}• Large offset applied ({offset_pct:.1f}% of total){theme.RESET}"
                )
    else:
        print(f"{theme.SUBTLE}• Portfolio assessment unavailable{theme.RESET}")

    print()  # Final spacing


def display_asset_distribution(metrics: Dict[str, Any]):
    """Clean asset distribution chart with professional styling."""
    print_header("Portfolio Distribution Analysis")

    total_value = metrics.get("total_portfolio_value", 0.0)
    if total_value <= 0:
        print(f"{theme.SUBTLE}No positive asset values to display distribution for.{theme.RESET}")
        return

    portfolio_data = []
    sources = [
        "Binance",
        "OKX",
        "Bybit",
        "Backpack",
        "Ethereum",
        "Bitcoin",
        "NEAR",
        "Aptos",
        "Solana",
        "Hyperliquid",
    ]

    for source in sources:
        key = source.lower()
        balance = metrics.get(key)
        if balance is not None and balance > 1e-3:
            portfolio_data.append((source, balance))

    if not portfolio_data:
        print(f"{theme.SUBTLE}No valid asset data for distribution chart.{theme.RESET}")
        return

    portfolio_data.sort(key=lambda x: x[1], reverse=True)
    included_total = sum(item[1] for item in portfolio_data)

    if included_total <= 0:
        print(f"{theme.SUBTLE}Included asset total is zero, cannot generate chart.{theme.RESET}")
        return

    chart_data = [(name, value, (value / included_total) * 100) for name, value in portfolio_data]

    # Clean header
    print(f"\n{theme.PRIMARY}Portfolio Distribution{theme.RESET}")
    print(f"Total Value: {format_currency(included_total)}")
    print("─" * 60)

    # Create simple table data
    table_data = []

    for label, value, percentage in chart_data:
        # Platform type indicators
        if label in ["Binance", "OKX", "Bybit", "Backpack"]:
            platform_type = "CEX"
        elif label in ["Ethereum", "Bitcoin", "NEAR", "Aptos", "Solana"]:
            platform_type = "L1"
        else:
            platform_type = "DeFi"

        # Clean progress bar
        bar_width = 20
        filled_width = int(percentage * bar_width / 100)
        progress_bar = "█" * filled_width + "░" * (bar_width - filled_width)

        # Format value
        clean_value = f"${value:,.0f}" if value >= 1 else f"${value:.2f}"

        table_data.append(
            [f"{platform_type:>4} {label}", clean_value, progress_bar, f"{percentage:5.1f}%"]
        )

    # Simple table with grid format for perfect alignment
    headers = ["Platform", "Value", "Distribution", "Share"]
    print(f"\n{tabulate(table_data, headers=headers, tablefmt='grid')}")

    # Simple summary
    largest_allocation = max(chart_data, key=lambda x: x[2])
    largest_pct = largest_allocation[2]

    print(f"\nLargest allocation: {largest_allocation[0]} ({largest_pct:.1f}%)")
    if largest_pct > 70:
        print("⚠ Consider diversifying for reduced risk")

    print()


def display_wallet_balances(portfolio_metrics: Dict[str, Any]):
    """Enhanced wallet balances display with improved formatting and theming."""
    print_header("Wallet Platform Balances")

    # Extract wallet platform data from portfolio metrics
    wallet_platform_data = portfolio_metrics.get("wallet_platform_data_raw", [])

    if not wallet_platform_data:
        print(f"{theme.SUBTLE}No wallet data available. Check your configuration.{theme.RESET}")
        return

    # Calculate total balance across all wallets
    total_all_wallets_usd = sum(
        (
            info.get("total_balance_usd", 0.0)
            if info.get("chain") == "solana"
            else info.get("total_balance", 0.0)
        )
        or 0.0
        for info in wallet_platform_data
    )

    # Enhanced header with emoji and better formatting
    print(f"\n{theme.PRIMARY}💼 PLATFORM OVERVIEW{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 19}{theme.RESET}")
    print(
        f"Total Portfolio Value: {theme.SUCCESS}{format_currency(total_all_wallets_usd)}{theme.RESET}"
    )
    print(f"Active Wallets:        {theme.ACCENT}{len(wallet_platform_data)}{theme.RESET}")

    if total_all_wallets_usd == 0:
        print(f"\n{theme.WARNING}⚠️  All wallet balances are zero or unavailable{theme.RESET}")
        return

    # Enhanced table headers
    headers = [
        f"{theme.PRIMARY}Address{theme.RESET}",
        f"{theme.PRIMARY}USD Balance{theme.RESET}",
        f"{theme.PRIMARY}Native Balance{theme.RESET}",
        f"{theme.PRIMARY}% of Total{theme.RESET}",
        f"{theme.PRIMARY}Details{theme.RESET}",
    ]

    table_data = []
    ethereum_wallets = []

    for info in wallet_platform_data:
        chain = info.get("chain", "unknown")
        address = info.get("address", "N/A")

        # Enhanced address formatting for different chains
        address_short = address
        if len(address) > 20:
            if chain in ["ethereum", "solana", "aptos"]:
                address_short = address[:8] + "..." + address[-6:]
            else:
                address_short = address[:8] + "..." + address[-6:]

        # Use the correct balance key depending on the chain
        balance_usd = (
            info.get("total_balance_usd", 0.0)
            if chain == "solana"
            else info.get("total_balance", 0.0)
        )
        # Ensure balance_usd is not None
        balance_usd = balance_usd or 0.0
        percentage = (
            (balance_usd / total_all_wallets_usd) * 100
            if total_all_wallets_usd > 0 and balance_usd
            else 0.0
        )

        # Chain-specific details formatting with enhanced styling
        if chain == "ethereum":
            native_balance_str = f"{theme.ERROR}Not Available{theme.RESET}"
            token_count = info.get("token_count", "?")
            protocol_count = info.get("protocol_count", "?")
            details_str = f"Tokens: {theme.ACCENT}{token_count}{theme.RESET}, Protocols: {theme.ACCENT}{protocol_count}{theme.RESET}"
            ethereum_wallets.append(info)
        elif chain == "bitcoin":
            btc_bal = info.get("balance_btc", 0)
            native_balance_str = f"{theme.WARNING}{btc_bal:.6f} BTC{theme.RESET}"
            tx_count = info.get("transaction_count", "?")
            details_str = f"Transactions: {theme.ACCENT}{tx_count}{theme.RESET}"
        elif chain == "near":
            near_bal = info.get("balance_near", 0)
            native_balance_str = f"{theme.ACCENT}{near_bal:.4f} NEAR{theme.RESET}"
            storage = info.get("storage_usage", "?")
            details_str = f"Storage: {theme.ACCENT}{storage}{theme.RESET} bytes"
        elif chain == "aptos":
            apt_bal = info.get("balance_apt", 0)
            native_balance_str = f"{theme.SUCCESS}{apt_bal:.6f} APT{theme.RESET}"
            token_count = len(info.get("token_balances", {}))
            seq_num = info.get("sequence_number", "?")
            details_str = f"Tokens: {theme.ACCENT}{token_count}{theme.RESET}, Seq: {theme.ACCENT}{seq_num}{theme.RESET}"
        elif chain == "solana":
            sol_bal = info.get("balance_sol", 0)
            native_balance_str = f"{theme.PRIMARY}{sol_bal:.4f} SOL{theme.RESET}"
            token_count = sum(1 for bal in info.get("token_balances", {}).values() if bal > 1e-6)
            details_str = f"SPL Tokens: {theme.ACCENT}{token_count}{theme.RESET}"
        else:
            native_balance_str = f"{theme.SUBTLE}N/A{theme.RESET}"
            source = info.get("source", "N/A")
            details_str = f"Source: {theme.ACCENT}{source}{theme.RESET}"

        table_data.append(
            [
                f"{theme.ACCENT}{address_short}{theme.RESET}",
                f"{theme.SUCCESS}{format_currency(balance_usd)}{theme.RESET}",
                native_balance_str,
                f"{theme.SUBTLE}{percentage:.1f}%{theme.RESET}",
                f"{theme.SUBTLE}{details_str}{theme.RESET}",
                balance_usd,  # For sorting
            ]
        )

    # Sort by balance descending
    table_data.sort(key=lambda row: row[5], reverse=True)
    # Remove raw balance before display
    display_table_data = [row[:-1] for row in table_data]
    print(
        tabulate(
            display_table_data,
            headers=headers,
            tablefmt="rounded_grid",  # Enhanced table style
            numalign="right",
            stralign="left",
        )
    )

    # Add submenu for detailed analysis
    if ethereum_wallets:
        print(f"\n{theme.PRIMARY}📊 DETAILED ANALYSIS OPTIONS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 28}{theme.RESET}")
        print(
            f"{theme.ACCENT}1.{theme.RESET} {theme.PRIMARY}🔗 View Detailed ETH Wallet Breakdown{theme.RESET} {theme.SUBTLE}• Enhanced token & protocol analysis{theme.RESET}"
        )
        print(f"{theme.ACCENT}2.{theme.RESET} {theme.SUBTLE}⬅️ Continue to Main Menu{theme.RESET}")

        choice = input(f"\n{theme.PRIMARY}Select option (1-2): {theme.RESET}").strip()

        if choice == "1":
            _display_detailed_eth_breakdown(ethereum_wallets, portfolio_metrics)

    print()  # Final spacing


def _display_detailed_eth_breakdown(
    ethereum_wallets: List[Dict[str, Any]], portfolio_metrics: Dict[str, Any]
):
    """Display the detailed Ethereum wallet breakdown that was previously shown automatically."""
    from utils.display_theme import theme
    from utils.helpers import format_currency
    from tabulate import tabulate
    import os
    import json
    from pathlib import Path

    # Clear screen for better viewing
    os.system("clear" if os.name == "posix" else "cls")

    print(f"\n{theme.PRIMARY}🔗 ETHEREUM WALLET EXPLORER{theme.RESET}")
    print(f"{theme.SUBTLE}{'=' * 27}{theme.RESET}")

    # Try to load enhanced data from portfolio metrics for detailed display
    try:
        # Check if we have enhanced data in any analysis folders
        enhanced_data = {}

        # Check if we have analysis folder context from past analysis viewing
        analysis_folder = portfolio_metrics.get("_analysis_folder")

        if analysis_folder and Path(analysis_folder).exists():
            # SPECIFIC ANALYSIS SESSION: Load from the exact folder
            analysis_path = Path(analysis_folder)
            json_files = list(analysis_path.glob("wallet_breakdown_0x*.json"))

            if json_files:
                # Load enhanced data for each address
                for json_file in json_files:
                    try:
                        with open(json_file, "r") as f:
                            file_data = json.load(f)

                        # Extract address from file data or filename
                        address = file_data.get("address")
                        if not address:
                            # Try to extract from filename
                            filename = json_file.name
                            if "wallet_breakdown_0x" in filename:
                                address_part = filename.split("wallet_breakdown_")[1].split(
                                    ".json"
                                )[0]
                                # Find matching full address
                                for eth_wallet in ethereum_wallets:
                                    full_addr = eth_wallet.get("address", "")
                                    if full_addr.lower().startswith(address_part.lower()):
                                        address = full_addr
                                        break

                        if address:
                            enhanced_data[address] = file_data

                    except Exception:
                        continue

            # FALLBACK: If no individual files found, try loading from eth_exposure_data in portfolio_metrics
            if not enhanced_data:
                print(
                    f"{theme.INFO}📁 No individual wallet files found, trying eth_exposure_data fallback...{theme.RESET}"
                )
                eth_exposure_data = portfolio_metrics.get("eth_exposure_data", {})
                for address, addr_data in eth_exposure_data.items():
                    if "export_data" in addr_data:
                        enhanced_data[address] = addr_data["export_data"]
                        print(
                            f"{theme.SUCCESS}✅ Loaded fallback data for {address[:8]}...{address[-6:]}{theme.RESET}"
                        )

        else:
            # NO SPECIFIC FOLDER: Search all organized folders (for live analysis or refresh)
            exported_data_path = Path("exported_data")

            if exported_data_path.exists():
                # Search in organized analysis folders first
                analysis_folders = list(exported_data_path.glob("analysis_*/"))
                json_files = []

                for analysis_folder_path in analysis_folders:
                    json_files.extend(analysis_folder_path.glob("wallet_breakdown_0x*.json"))

                # Also check root folder for legacy files
                json_files.extend(exported_data_path.glob("live_analysis_0x*.json"))
                json_files.extend(exported_data_path.glob("wallet_breakdown_0x*.json"))

                # Sort by modification time to get most recent first
                if json_files:
                    json_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

                    # Track which addresses we've actually loaded (not duplicates)
                    loaded_addresses = set()

                    # Load enhanced data for each address
                    for json_file in json_files:
                        try:
                            with open(json_file, "r") as f:
                                file_data = json.load(f)

                            # Extract address from file data or filename
                            address = file_data.get("address")
                            if not address:
                                # Try to extract from filename
                                filename = json_file.name
                                if "wallet_breakdown_0x" in filename:
                                    address_part = filename.split("wallet_breakdown_")[1].split(
                                        ".json"
                                    )[0]
                                elif "live_analysis_0x" in filename:
                                    address_part = filename.split("_")[2]
                                else:
                                    continue

                                # Find matching full address
                                for eth_wallet in ethereum_wallets:
                                    full_addr = eth_wallet.get("address", "")
                                    if full_addr.lower().startswith(address_part.lower()):
                                        address = full_addr
                                        break

                            if address:
                                # Only load for new addresses (not overwrites)
                                if address not in loaded_addresses:
                                    enhanced_data[address] = file_data
                                    loaded_addresses.add(address)
                                else:
                                    # Silently overwrite with more recent data (files are sorted by mod time)
                                    enhanced_data[address] = file_data

                        except Exception:
                            continue
    except Exception:
        enhanced_data = {}

    # Interactive submenu for detailed wallet exploration
    if enhanced_data:
        # Show clean summary of loaded data
        loaded_count = len(enhanced_data)
        total_wallets = len(ethereum_wallets)
        print(
            f"\n{theme.SUCCESS}✅ Enhanced data loaded for {loaded_count}/{total_wallets} Ethereum wallets{theme.RESET}"
        )

        while True:
            print(f"\n{theme.INFO}Select a wallet to view ALL tokens and protocols:{theme.RESET}")

            # Show wallet options
            for i, eth_wallet in enumerate(ethereum_wallets):
                address = eth_wallet.get("address", "Unknown")
                address_short = f"{address[:8]}...{address[-6:]}" if len(address) > 14 else address
                balance_usd = eth_wallet.get("total_balance", 0.0)

                # Check if enhanced data is available
                has_data = address in enhanced_data
                status_icon = "✅" if has_data else "❌"

                print(
                    f"  {theme.ACCENT}{i+1}.{theme.RESET} {status_icon} {address_short} - {format_currency(balance_usd)}"
                )

            print(f"  {theme.ACCENT}0.{theme.RESET} Return to wallet balances")

            try:
                choice = input(
                    f"\n{theme.PRIMARY}Enter your choice (0-{len(ethereum_wallets)}): {theme.RESET}"
                ).strip()

                if choice == "0":
                    break

                wallet_index = int(choice) - 1
                if 0 <= wallet_index < len(ethereum_wallets):
                    selected_wallet = ethereum_wallets[wallet_index]
                    address = selected_wallet.get("address", "")

                    if address in enhanced_data:
                        _display_complete_wallet_details(
                            enhanced_data[address], address, portfolio_metrics
                        )
                    else:
                        print(
                            f"\n{theme.ERROR}❌ No enhanced data available for this wallet{theme.RESET}"
                        )
                        print(
                            f"{theme.SUBTLE}Run live analysis to generate detailed data{theme.RESET}"
                        )
                else:
                    print(
                        f"\n{theme.ERROR}❌ Invalid choice. Please select 0-{len(ethereum_wallets)}{theme.RESET}"
                    )
            except (ValueError, KeyboardInterrupt):
                if choice.lower() in ["q", "quit", "exit"]:
                    break
                print(
                    f"\n{theme.ERROR}❌ Invalid input. Please enter a number or 'q' to quit{theme.RESET}"
                )
            except Exception as e:
                print(f"\n{theme.ERROR}❌ Error: {str(e)}{theme.RESET}")
    else:
        print(f"\n{theme.ERROR}❌ NO ENHANCED DATA AVAILABLE{theme.RESET}")
        print(
            f"{theme.SUBTLE}Run a live analysis to generate enhanced wallet breakdowns{theme.RESET}"
        )


def _display_wallet_summary_stats(tokens: List[Dict[str, Any]], protocols: List[Dict[str, Any]]):
    """Helper function to display summary statistics for a wallet."""
    from utils.display_theme import theme
    from utils.helpers import format_currency

    print(f"\n{theme.PRIMARY}📊 SUMMARY STATISTICS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")

    # --- Enhanced Token Category Breakdown ---
    category_totals = {
        "stable": 0.0,
        "eth_exposure": 0.0,
        "eth_staking": 0.0,
        "other_crypto": 0.0,
        "lp_token": 0.0,
    }

    # Define a comprehensive set of base stablecoin symbols
    stablecoin_bases = {
        "USDC",
        "USDT",
        "DAI",
        "FDUSD",
        "USDE",
        "FRAX",
        "TUSD",
        "PYUSD",
        "GUSD",
        "PAX",
        "BUSD",
        "GHO",
        "CRVUSD",
    }

    for token in tokens:
        symbol = token.get("symbol", "").upper()
        category = token.get("category", "other_crypto")
        value = token.get("usd_value", 0)

        # Check if the token is a stablecoin based on its symbol prefix
        is_stable = False
        for base in stablecoin_bases:
            if symbol.startswith(base):
                is_stable = True
                break

        if is_stable:
            category_totals["stable"] += value
        elif category in category_totals:
            category_totals[category] += value
        else:
            category_totals["other_crypto"] += value

    if category_totals:
        total_categorized = sum(category_totals.values())
        if total_categorized > 0:
            for category, value in sorted(
                category_totals.items(), key=lambda x: x[1], reverse=True
            ):
                if value > 0:
                    percentage = value / total_categorized * 100
                    category_display = {
                        "stable": "🔒 Stablecoins",
                        "eth_exposure": "💎 ETH Exposure",
                        "eth_staking": "🥩 ETH Staking",
                        "lp_token": "🔄 LP Tokens",
                        "other_crypto": "📈 Other Crypto",
                    }.get(category, f"📊 {category.title()}")

                    print(f"  {category_display}: {format_currency(value)} ({percentage:.1f}%)")

    # Token value distribution
    if tokens:
        high_value_tokens = len([t for t in tokens if t.get("usd_value", 0) >= 100])
        medium_value_tokens = len([t for t in tokens if 1 <= t.get("usd_value", 0) < 100])
        low_value_tokens = len([t for t in tokens if 0.01 <= t.get("usd_value", 0) < 1])
        dust_tokens = len([t for t in tokens if t.get("usd_value", 0) < 0.01])

        print(f"\n{theme.INFO}Token Value Distribution:{theme.RESET}")
        print(f"  High Value (≥$100):   {theme.SUCCESS}{high_value_tokens}{theme.RESET}")
        print(f"  Medium Value ($1-$99): {theme.WARNING}{medium_value_tokens}{theme.RESET}")
        print(f"  Low Value ($0.01-$1):  {theme.SUBTLE}{low_value_tokens}{theme.RESET}")
        print(f"  Dust (<$0.01):         {theme.ERROR}{dust_tokens}{theme.RESET}")

    # Show totals
    total_token_value = sum(t.get("usd_value", 0) for t in tokens)
    total_protocol_value = sum(p.get("total_value", p.get("value", 0)) for p in protocols)

    print(f"\n{theme.SUCCESS}Total Token Value: {format_currency(total_token_value)}{theme.RESET}")
    print(
        f"{theme.SUCCESS}Total Protocol Value: {format_currency(total_protocol_value)}{theme.RESET}"
    )


def _display_complete_wallet_details(
    wallet_data: Dict[str, Any], address: str, portfolio_metrics: Dict[str, Any]
):
    """Display complete token and protocol details for a wallet with navigation."""
    from utils.display_theme import theme
    from utils.helpers import format_currency
    from tabulate import tabulate
    import os
    import time
    from datetime import datetime
    from dateutil import tz

    tokens = wallet_data.get("tokens", [])
    protocols = wallet_data.get("protocols", [])

    # Sort data once
    sorted_tokens = sorted(tokens, key=lambda t: t.get("usd_value", 0), reverse=True)
    sorted_protocols = sorted(
        protocols, key=lambda p: p.get("total_value", p.get("value", 0)), reverse=True
    )

    # Navigation state
    token_start = 0
    protocol_start = 0
    page_size = 10
    show_all = False

    while True:
        # 1. Clear screen for a fresh view
        os.system("clear" if os.name == "posix" else "cls")

        # 2. Display wallet header
        address_short = f"{address[:8]}...{address[-6:]}" if len(address) > 14 else address
        total_value = wallet_data.get("total_usd_value", wallet_data.get("total_balance", 0))

        print(f"\n{theme.PRIMARY}🔍 COMPLETE WALLET DETAILS{theme.RESET}")
        print(f"{theme.SUBTLE}{'=' * 27}{theme.RESET}")
        print(f"Address: {theme.ACCENT}{address_short}{theme.RESET}")
        print(f"Total Value: {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}")

        # --- Timestamp Analysis in Local Time ---
        analysis_ts_str = portfolio_metrics.get("timestamp", "N/A")

        try:
            utc_dt = datetime.fromisoformat(analysis_ts_str.replace("Z", "+00:00"))
            local_tz = tz.tzlocal()
            local_dt = utc_dt.astimezone(local_tz)
            timezone_name = local_dt.tzname()
            display_ts = local_dt.strftime(f"%Y-%m-%d %H:%M:%S ({timezone_name})")
            print(f"Analysis Time: {theme.SUBTLE}{display_ts}{theme.RESET}")
        except (ValueError, TypeError, ImportError):
            display_ts = analysis_ts_str  # Fallback to raw string
            print(f"Analysis Time: {theme.SUBTLE}{display_ts}{theme.RESET}")

        # 3. Display tokens section
        if sorted_tokens:
            if show_all:
                showing_tokens = sorted_tokens
                print(f"\n{theme.PRIMARY}🪙 TOKENS ({len(sorted_tokens)} total - All){theme.RESET}")
            else:
                token_end = min(token_start + page_size, len(sorted_tokens))
                showing_tokens = sorted_tokens[token_start:token_end]
                print(
                    f"\n{theme.PRIMARY}🪙 TOKENS (showing {token_start+1}-{token_end} of {len(sorted_tokens)}){theme.RESET}"
                )

            token_table = []
            start_index = 1 if show_all else token_start + 1
            for i, token in enumerate(showing_tokens, start=start_index):
                symbol = token.get("symbol", "Unknown")
                amount = token.get("amount", 0)
                usd_value = token.get("usd_value", 0)
                category = token.get("category", "other_crypto")

                chain = token.get("chain", "n/a").capitalize()
                chain_icon = {
                    "Ethereum": "⟠",
                    "Arbitrum": "🔵",
                    "Polygon": "🟣",
                    "Base": "🔷",
                    "Optimism": "🔴",
                    "Sonic": "⚡",
                    "Soneium": "🟡",
                    "Linea": "🟢",
                    "Ink": "🖋️",
                    "Lisk": "🔶",
                    "Abstract": "🎭",
                    "Gravity": "🌍",
                    "Itze": "⭐",
                    "Rsk": "🟠",
                    "Bsc": "🟨",
                    "Xlayer": "❌",
                    "Mantle": "🧥",
                    "Avalanche": "🏔️",
                    "Fantom": "👻",
                    "Celo": "💚",
                    "Near": "🔺",
                    "Solana": "🌞",
                    "Unichain": "🦄",
                    "Era": "⚡",
                    "Rari": "💎",
                    "Frax": "❄️",
                    "Bera": "🐻",
                    "Lens": "📷",
                    "Metis": "🔴",
                    "Pze": "🔷",
                    "Fuse": "🔥",
                    "Dbk": "🏦",
                    "Blast": "💥",
                    "Taiko": "🥁",
                    "Xdai": "💰",
                    "Core": "⚫",
                    "Dfk": "🏰",
                    "Zora": "🎨",
                    "Mobm": "📱",
                    "Scrl": "📜",
                    "Cyber": "🤖",
                    "Bob": "👤",
                    "Manta": "🐙",
                    "Karak": "🏔️",
                    "Mode": "🎮",
                    "Tlos": "🔺",
                    "Canto": "🎵",
                    "Zeta": "⚡",
                    "Nova": "💫",
                    "Wemix": "🎮",
                    "Sei": "🌊",
                    "Movr": "🌙",
                    "Kava": "☕",
                    "Cfx": "🌊",
                    "Boba": "🧋",
                    "Bb": "🔵",
                    "Astar": "⭐",
                }.get(chain, "🔗")

                cat_icon = {
                    "stable": "🔒",
                    "eth_exposure": "💎",
                    "eth_staking": "🥩",
                    "lp_token": "🔄",
                }.get(category, "📈")
                amount_str = (
                    f"{amount:,.6f}".rstrip("0").rstrip(".")
                    if amount >= 1
                    else f"{amount:.8f}".rstrip("0").rstrip(".")
                )

                token_table.append(
                    [
                        f"{theme.SUBTLE}{i}{theme.RESET}",
                        f"{cat_icon} {theme.ACCENT}{symbol}{theme.RESET}",
                        f"{theme.SUBTLE}{amount_str}{theme.RESET}",
                        f"{theme.PRIMARY}{format_currency(usd_value)}{theme.RESET}",
                        f"{chain_icon} {theme.SUBTLE}{chain}{theme.RESET}",
                        f"{theme.SUBTLE}{category}{theme.RESET}",
                    ]
                )

            print(
                tabulate(
                    token_table,
                    headers=["#", "Token", "Amount", "USD Value", "Chain", "Category"],
                    tablefmt="simple",
                )
            )
        else:
            print(f"\n{theme.SUBTLE}No tokens found{theme.RESET}")

        # 4. Display protocols section
        if sorted_protocols:
            if show_all:
                showing_protocols = sorted_protocols
                print(
                    f"\n{theme.PRIMARY}🏛️ PROTOCOLS ({len(sorted_protocols)} total - All){theme.RESET}"
                )
            else:
                protocol_end = min(protocol_start + page_size, len(sorted_protocols))
                showing_protocols = sorted_protocols[protocol_start:protocol_end]
                print(
                    f"\n{theme.PRIMARY}🏛️ PROTOCOLS (showing {protocol_start+1}-{protocol_end} of {len(sorted_protocols)}){theme.RESET}"
                )

            protocol_table = []
            start_index = 1 if show_all else protocol_start + 1
            for i, protocol in enumerate(showing_protocols, start=start_index):
                name = protocol.get("name", "Unknown")
                total_value_proto = protocol.get("total_value", protocol.get("value", 0))
                chain = protocol.get("chain", "ethereum")
                chain_icon = {
                    "ethereum": "⟠",
                    "arbitrum": "🔵",
                    "polygon": "🟣",
                    "base": "🔷",
                    "optimism": "🔴",
                }.get(chain.lower(), "🔗")
                protocol_table.append(
                    [
                        f"{theme.SUBTLE}{i}{theme.RESET}",
                        f"{theme.ACCENT}{name}{theme.RESET}",
                        f"{theme.PRIMARY}{format_currency(total_value_proto)}{theme.RESET}",
                        f"{chain_icon} {theme.SUBTLE}{chain.capitalize()}{theme.RESET}",
                    ]
                )

            print(
                tabulate(
                    protocol_table,
                    headers=["#", "Protocol", "USD Value", "Chain"],
                    tablefmt="simple",
                )
            )
        else:
            print(f"\n{theme.SUBTLE}No protocols found{theme.RESET}")

        # 5. Intuitive navigation menu
        nav_hints = []
        valid_commands = {}

        if show_all:
            nav_hints.append("(p)aginated view")
            valid_commands["p"] = "toggle_view"
        else:
            # Token navigation
            if len(sorted_tokens) > page_size:
                token_nav_parts = []
                if token_start > 0:
                    token_nav_parts.append("(p)rev")
                    valid_commands["tp"] = "prev_tokens"
                if token_start + page_size < len(sorted_tokens):
                    token_nav_parts.append("(n)ext")
                    valid_commands["tn"] = "next_tokens"
                if token_nav_parts:
                    nav_hints.append(f"[T]okens: {'/'.join(token_nav_parts)}")

            # Protocol navigation
            if len(sorted_protocols) > page_size:
                protocol_nav_parts = []
                if protocol_start > 0:
                    protocol_nav_parts.append("(p)rev")
                    valid_commands["pp"] = "prev_protocols"
                if protocol_start + page_size < len(sorted_protocols):
                    protocol_nav_parts.append("(n)ext")
                    valid_commands["pn"] = "next_protocols"
                if protocol_nav_parts:
                    nav_hints.append(f"[P]rotocols: {'/'.join(protocol_nav_parts)}")

            # Reset command for pagination
            if token_start > 0 or protocol_start > 0:
                nav_hints.append("(r)eset pages")
                valid_commands["r"] = "reset_pages"

            nav_hints.append("(a)ll view")
            valid_commands["a"] = "toggle_view"

        # General commands
        nav_hints.append("(s)ummary")
        valid_commands["s"] = "summary"
        nav_hints.append("(q)uit")
        valid_commands["q"] = "return"

        print(f"\n{theme.PRIMARY}NAVIGATION:{theme.RESET} {' | '.join(nav_hints)}")

        # 6. Get and process user choice
        try:
            choice = input(f"\n{theme.PRIMARY}Enter command: {theme.RESET}").strip().lower()

            if choice in valid_commands:
                action = valid_commands[choice]

                if action == "prev_tokens":
                    token_start = max(0, token_start - page_size)
                elif action == "next_tokens":
                    token_start += page_size
                elif action == "prev_protocols":
                    protocol_start = max(0, protocol_start - page_size)
                elif action == "next_protocols":
                    protocol_start += page_size
                elif action == "reset_pages":
                    token_start = 0
                    protocol_start = 0
                elif action == "toggle_view":
                    show_all = not show_all
                    token_start = 0
                    protocol_start = 0
                elif action == "summary":
                    _display_wallet_summary_stats(tokens, protocols)
                    input(f"\n{theme.SUBTLE}Press Enter to return...{theme.RESET}")
                elif action == "return":
                    break
            elif choice:  # Non-empty but invalid
                print(f"{theme.ERROR}❌ Invalid command '{choice}'{theme.RESET}")
                time.sleep(1.5)

        except (ValueError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"{theme.ERROR}❌ An error occurred: {str(e)}{theme.RESET}")
            time.sleep(2)

    print(f"\n{theme.SUBTLE}Returning to wallet selection...{theme.RESET}")


def display_hyperliquid_positions(portfolio_metrics: Dict[str, Any]):
    """Enhanced Hyperliquid positions display with improved formatting and theming."""
    print_header("Hyperliquid Positions")

    # Extract wallet platform data from portfolio metrics
    wallet_platform_data = portfolio_metrics.get("wallet_platform_data_raw", [])

    hyperliquid_data = [
        info for info in wallet_platform_data if info.get("platform") == "hyperliquid"
    ]
    if not hyperliquid_data:
        print(f"{theme.SUBTLE}No Hyperliquid accounts tracked or no data available.{theme.RESET}")
        return

    total_hyperliquid_balance = sum(info.get("total_balance", 0.0) for info in hyperliquid_data)

    # Enhanced summary with trading icon
    print(f"\n{theme.PRIMARY}⚡ HYPERLIQUID SUMMARY{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 23}{theme.RESET}")
    print(
        f"Total Account Value: {theme.SUCCESS}{format_currency(total_hyperliquid_balance)}{theme.RESET}"
    )
    print(f"Active Accounts:     {theme.ACCENT}{len(hyperliquid_data)}{theme.RESET}")

    for i, account in enumerate(hyperliquid_data):
        account_balance = account.get("total_balance", 0.0)
        address = account.get("address", "N/A")
        address_short = address[:8] + "..." + address[-6:] if address != "N/A" else "N/A"

        print(f"\n{theme.PRIMARY}📊 ACCOUNT {i+1}: {theme.ACCENT}{address_short}{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * (17 + len(address_short))}{theme.RESET}")
        print(f"Account Value: {theme.SUCCESS}{format_currency(account_balance)}{theme.RESET}")

        positions = account.get("open_positions", [])
        if not positions:
            print(f"\n{theme.SUBTLE}No open positions{theme.RESET}")
            continue

        print(f"\n{theme.SUBTLE}Open Positions{theme.RESET}")

        headers = [
            f"{theme.PRIMARY}Asset{theme.RESET}",
            f"{theme.PRIMARY}Position{theme.RESET}",
            f"{theme.PRIMARY}Entry Price{theme.RESET}",
            f"{theme.PRIMARY}Liq. Price{theme.RESET}",
            f"{theme.PRIMARY}Leverage{theme.RESET}",
            f"{theme.PRIMARY}Unrealized PNL{theme.RESET}",
        ]
        table_data = []

        for p in positions:
            size = p.get("size", 0.0)

            # Enhanced position direction display
            if size > 0:
                direction = f"{theme.SUCCESS}📈 Long{theme.RESET}"
                position_display = f"{abs(size):.4f} ({direction})"
            elif size < 0:
                direction = f"{theme.ERROR}📉 Short{theme.RESET}"
                position_display = f"{abs(size):.4f} ({direction})"
            else:
                direction = f"{theme.SUBTLE}➖ Flat{theme.RESET}"
                position_display = f"{abs(size):.4f} ({direction})"

            # Enhanced PNL formatting
            pnl = p.get("unrealized_pnl", 0)
            if pnl is not None:
                if pnl > 0:
                    pnl_formatted = f"{theme.SUCCESS}💰 +{format_currency(pnl)}{theme.RESET}"
                elif pnl < 0:
                    pnl_formatted = f"{theme.ERROR}💸 {format_currency(pnl)}{theme.RESET}"
                else:
                    pnl_formatted = f"{theme.SUBTLE}➖ {format_currency(pnl)}{theme.RESET}"
            else:
                pnl_formatted = f"{theme.SUBTLE}N/A{theme.RESET}"

            # Enhanced liquidation price display
            liq_price = p.get("liquidation_price")
            liq_display = (
                f"{theme.WARNING}⚠️ {format_currency(liq_price)}{theme.RESET}"
                if liq_price
                else f"{theme.SUBTLE}N/A{theme.RESET}"
            )

            table_data.append(
                [
                    f"{theme.ACCENT}{p.get('asset', '?')}{theme.RESET}",
                    position_display,
                    f"{theme.PRIMARY}{format_currency(p.get('entry_price'))}{theme.RESET}",
                    liq_display,
                    f"{theme.SUBTLE}{p.get('leverage', 0.0):.2f}x{theme.RESET}",
                    pnl_formatted,
                ]
            )

        # Sort by unrealized PNL descending (most profitable first)
        table_data.sort(key=lambda row: p.get("unrealized_pnl", 0), reverse=True)
        print(
            tabulate(
                table_data,
                headers=headers,
                tablefmt="rounded_grid",
                numalign="right",
                stralign="left",
            )
        )

    print()  # Final spacing


def display_cex_breakdown(metrics: Dict[str, Any]):
    """Clean centralized exchange breakdown with professional styling."""
    print_header("Centralized Exchange Breakdown")

    binance_total = metrics.get("binance")
    okx_total = metrics.get("okx")
    bybit_total = metrics.get("bybit")
    backpack_total = metrics.get("backpack")
    total_cex = metrics.get("total_cex_balance", 0.0)
    failed_sources = metrics.get("failed_sources", [])

    # Clean summary
    print(f"\n{theme.PRIMARY}Exchange Summary{theme.RESET}")
    print(f"Total CEX Value: {format_currency(total_cex)}")
    active_count = sum(
        1
        for x in [binance_total, okx_total, bybit_total, backpack_total]
        if x is not None and x > 0
    )
    print(f"Active Exchanges: {active_count}/4")

    if failed_sources:
        failed_cex = [s for s in failed_sources if s in ["Binance", "OKX", "Bybit", "Backpack"]]
        if failed_cex:
            print(f"Failed: {', '.join(failed_cex)}")

    print("─" * 50)

    # Clean exchange overview table
    exchange_data = []
    exchanges = [
        ("Binance", binance_total),
        ("OKX", okx_total),
        ("Bybit", bybit_total),
        ("Backpack", backpack_total),
    ]

    for name, balance in exchanges:
        if name in failed_sources:
            exchange_data.append([name, "Connection Failed", "N/A"])
        elif balance is not None and balance > 0:
            percentage = (balance / total_cex * 100) if total_cex > 0 else 0
            clean_value = f"${balance:,.0f}" if balance >= 1 else f"${balance:.2f}"
            exchange_data.append([name, clean_value, f"{percentage:.1f}%"])
        else:
            exchange_data.append([name, "No Balance", "0.0%"])

    headers = ["Exchange", "Balance", "Share"]
    print(f"\n{tabulate(exchange_data, headers=headers, tablefmt='grid')}")

    # Detailed breakdowns with cleaner styling
    if "Binance" not in failed_sources and binance_total is not None and binance_total > 0:
        binance_account_types = metrics.get("detailed_breakdowns", {}).get("binance_account_types")
        if binance_account_types:
            print(f"\n{theme.PRIMARY}Binance Account Types{theme.RESET}")

            account_types = binance_account_types.get("account_types", {})
            total_all = binance_account_types.get("total_all_accounts", 0.0)

            print(f"Total Equity: {format_currency(total_all)}")
            print("─" * 30)

            account_data = []
            for account_type, balance in account_types.items():
                if balance is not None and balance > 0.01:
                    percentage = (balance / total_all * 100) if total_all > 0 else 0
                    clean_value = f"${balance:,.0f}" if balance >= 1 else f"${balance:.2f}"
                    account_data.append([account_type, clean_value, f"{percentage:.1f}%"])
                elif balance is not None and balance == 0.0:
                    account_data.append([account_type, "$0.00", "0.0%"])

            if account_data:
                headers = ["Account Type", "Balance", "Share"]
                print(f"\n{tabulate(account_data, headers=headers, tablefmt='simple')}")
            else:
                print("No account type data available")

        # Show spot account details
        stored_binance_details = metrics.get("detailed_breakdowns", {}).get("binance_details")
        if stored_binance_details:
            display_exchange_detailed_breakdown("Binance", stored_binance_details, failed_sources)

    # Other exchange details
    for exchange, key, total in [
        ("OKX", "okx_details", okx_total),
        ("Bybit", "bybit_details", bybit_total),
        ("Backpack", "backpack_details", backpack_total),
    ]:
        if exchange not in failed_sources and total is not None and total > 0:
            stored_details = metrics.get("detailed_breakdowns", {}).get(key)
            if stored_details:
                display_exchange_detailed_breakdown(exchange, stored_details, failed_sources)

    print()


async def display_market_snapshot(portfolio_analyzer):
    """Displays a market snapshot of major and custom coins with live prices."""
    PRIMARY = Fore.WHITE + Style.BRIGHT
    SUCCESS = Fore.GREEN + Style.BRIGHT
    WARNING = Fore.YELLOW
    ERROR = Fore.RED
    ACCENT = Fore.CYAN
    SUBTLE = Style.DIM
    RESET = Style.RESET_ALL

    print(f"\n{PRIMARY}⚡ REAL-TIME MARKET SNAPSHOT{RESET}")
    print(f"{SUBTLE}{'─' * 30}{RESET}")

    major_coins = (
        SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY  # e.g., ['BTC', 'ETH', 'SOL', 'NEAR', 'APT']
    )

    # Fetch prices for major coins using the portfolio_analyzer's price service
    try:
        # Use portfolio_analyzer.price_service which is enhanced_price_service
        major_coin_prices = await portfolio_analyzer.price_service.get_prices_async(major_coins)
    except Exception as e:
        print_error(f"Error fetching major coin prices: {e}")
        major_coin_prices = {coin: 0.0 for coin in major_coins}

    # Fetch custom coin data and their prices
    custom_coin_tracker = portfolio_analyzer.custom_coin_tracker  # Access via analyzer
    custom_symbols = custom_coin_tracker.get_all_symbols()
    custom_coin_prices = {}
    if custom_symbols:
        try:
            # Use portfolio_analyzer.price_service for custom coins as well
            custom_coin_prices = await portfolio_analyzer.price_service.get_prices_async(
                custom_symbols
            )
        except Exception as e:
            print_error(f"Error fetching custom coin prices: {e}")
            # custom_coin_prices will remain empty or partially filled

    all_coins_data = []

    # Process major coins
    for coin in major_coins:
        price = major_coin_prices.get(coin)
        if price is not None:
            all_coins_data.append({"name": coin, "symbol": coin, "price": price})
        else:
            all_coins_data.append({"name": coin, "symbol": coin, "price": 0.0, "error": True})

    # Process custom coins
    for symbol in custom_symbols:
        coin_detail = custom_coin_tracker.get_coin_data(symbol)
        name = coin_detail.get("name", symbol)
        price = custom_coin_prices.get(symbol)
        if price is not None:
            all_coins_data.append({"name": name, "symbol": symbol, "price": price})
        else:
            # If price fetch failed for a custom coin, display its last known price or error
            last_price = coin_detail.get("last_price")
            if last_price is not None:
                all_coins_data.append(
                    {"name": name, "symbol": symbol, "price": last_price, "stale": True}
                )
            else:
                all_coins_data.append({"name": name, "symbol": symbol, "price": 0.0, "error": True})

    if not all_coins_data:
        print(f"{WARNING}No market data to display.{RESET}")
        return

    # Sort coins: Major coins first, then custom coins alphabetically by name
    def sort_key(item):
        is_major = item["symbol"] in major_coins
        return (not is_major, item["name"].lower())

    sorted_coins = sorted(all_coins_data, key=sort_key)

    table_data = []
    for coin_info in sorted_coins:
        name = coin_info["name"]
        symbol = coin_info["symbol"]
        price = coin_info["price"]

        display_name = f"{name} ({symbol})" if name.lower() != symbol.lower() else symbol

        price_str = format_currency(price, max_precision=True if price < 0.01 else False)

        if coin_info.get("error"):
            price_str = f"{ERROR}Error{RESET}"
        elif coin_info.get("stale"):
            price_str = f"{WARNING}{price_str} (stale){RESET}"
        else:
            price_str = f"{SUCCESS}{price_str}{RESET}"

        table_data.append([f"{ACCENT}{display_name}{theme.RESET}", price_str])

    headers = [f"{PRIMARY}Coin{RESET}", f"{PRIMARY}Price (USD){RESET}"]
    print(
        tabulate(table_data, headers=headers, tablefmt="simple", stralign="left", numalign="right")
    )
    print(f"{SUBTLE}{'─' * 30}{RESET}")
    print(f"{SUBTLE}Tip: Add more coins via 'Manage Custom Coins' menu.{RESET}")


def display_exposure_analysis(portfolio_metrics: Dict[str, Any]):
    """
    Display comprehensive exposure analysis with submenu options including:
    1. Main exposure analysis
    2. Detailed ETH Balance Breakdown (NEW)
    """
    from utils.display_theme import theme

    while True:
        # Clear screen for better visibility
        os.system("clear" if os.name == "posix" else "cls")

        # Display main exposure analysis first
        _display_main_exposure_analysis(portfolio_metrics)

        # Add submenu options
        print(f"\n{theme.PRIMARY}🎯 EXPOSURE ANALYSIS OPTIONS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 28}{theme.RESET}")
        print(
            f"{theme.ACCENT}1.{theme.RESET} {theme.PRIMARY}📊 Detailed ETH Balance Breakdown{theme.RESET} {theme.SUBTLE}• Enhanced vs Standard comparison{theme.RESET}"
        )
        print(f"{theme.ACCENT}2.{theme.RESET} {theme.SUBTLE}⬅️ Back to Analysis Menu{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 50}{theme.RESET}")

        choice = input(f"{theme.PRIMARY}Select option (1-2): {theme.RESET}").strip()

        if choice == "1":
            display_eth_balance_breakdown(portfolio_metrics)
        elif choice == "2":
            break
        else:
            print(f"{theme.ERROR}❌ Invalid choice. Please select 1-2.{theme.RESET}")
            input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")


def _display_main_exposure_analysis(portfolio_metrics: Dict[str, Any]):
    """
    Display the main exposure analysis (extracted from original function).
    """
    from utils.display_theme import theme
    from utils.helpers import format_currency
    from tabulate import tabulate
    import os

    exposure_data = portfolio_metrics.get("exposure_analysis", {})

    if not exposure_data or exposure_data.get("total_portfolio_value", 0) <= 0:
        print(f"\n{theme.ERROR}❌ EXPOSURE ANALYSIS UNAVAILABLE{theme.RESET}")
        print(f"{theme.SUBTLE}No exposure data available for analysis{theme.RESET}")
        return

    print(f"\n{theme.PRIMARY}🎯 PORTFOLIO EXPOSURE ANALYSIS{theme.RESET}")
    print(f"{theme.SUBTLE}{'=' * 35}{theme.RESET}")

    # Main metrics at the top
    total_portfolio_value = exposure_data.get("total_portfolio_value", 0)
    stable_value = exposure_data.get("stable_value", 0)
    non_stable_value = exposure_data.get("non_stable_value", 0)
    neutral_count = exposure_data.get("neutral_asset_count", 0)

    # Calculate actual percentages based on categorized assets only
    categorized_value = stable_value + non_stable_value

    if categorized_value > 0:
        actual_stable_pct = (stable_value / categorized_value) * 100
        actual_non_stable_pct = (non_stable_value / categorized_value) * 100
    else:
        actual_stable_pct = 0
        actual_non_stable_pct = 0

    # Check if we have significant neutral assets (CEX mixed)
    neutral_value = total_portfolio_value - categorized_value
    has_neutral = neutral_count > 0 and neutral_value > 0

    # Risk indicator based on categorized assets
    if actual_non_stable_pct < 30:
        risk_icon = "🟢"
        risk_text = "Conservative"
    elif actual_non_stable_pct < 70:
        risk_icon = "🟡"
        risk_text = "Balanced"
    else:
        risk_icon = "🔴"
        risk_text = "Aggressive"

    # Clean summary box
    print(f"\n{theme.PRIMARY}📊 PORTFOLIO RISK PROFILE{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")
    print(
        f"Total Portfolio:    {theme.ACCENT}{format_currency(total_portfolio_value)}{theme.RESET}"
    )

    if has_neutral:
        print(
            f"Categorized Assets: {theme.ACCENT}{format_currency(categorized_value)}{theme.RESET} {theme.SUBTLE}({categorized_value/total_portfolio_value*100:.1f}% of total){theme.RESET}"
        )
        print(
            f"└─ Stable Assets:   {theme.SUCCESS}{format_currency(stable_value)}{theme.RESET} {theme.SUBTLE}({actual_stable_pct:.1f}% of categorized){theme.RESET}"
        )
        print(
            f"└─ Non-Stable Assets: {theme.WARNING}{format_currency(non_stable_value)}{theme.RESET} {theme.SUBTLE}({actual_non_stable_pct:.1f}% of categorized){theme.RESET}"
        )
        print(
            f"CEX Mixed Assets:   {theme.SUBTLE}{format_currency(neutral_value)}{theme.RESET} {theme.SUBTLE}(composition unknown){theme.RESET}"
        )
    else:
        print(
            f"Stable Assets:      {theme.SUCCESS}{format_currency(stable_value)}{theme.RESET} {theme.SUBTLE}({actual_stable_pct:.1f}%){theme.RESET}"
        )
        print(
            f"Non-Stable Assets:  {theme.WARNING}{format_currency(non_stable_value)}{theme.RESET} {theme.SUBTLE}({actual_non_stable_pct:.1f}%){theme.RESET}"
        )

    if categorized_value > 0:
        print(f"Risk Level:         {risk_icon} {theme.ACCENT}{risk_text}{theme.RESET}")
    else:
        print(f"Risk Level:         {theme.SUBTLE}⚪ Unknown (mostly CEX mixed){theme.RESET}")

    # Asset breakdown - simplified table format
    consolidated_assets = exposure_data.get("consolidated_assets", {})

    if consolidated_assets:
        print(f"\n{theme.PRIMARY}🏦 HOLDINGS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 12}{theme.RESET}")

        # Sort assets by total value (descending)
        sorted_assets = sorted(
            consolidated_assets.items(), key=lambda x: x[1].get("total_value_usd", 0), reverse=True
        )

        # Clean table format - show top 15 with quantity breakdown (increased from 10)
        # Filter out dust tokens (< $1 value)
        table_data = []
        headers = ["Asset", "USD Value", "Total Amount", "Price", "% Portfolio", "Type"]

        assets_displayed = 0
        for symbol, asset_data in sorted_assets:
            value = asset_data.get("total_value_usd", 0)

            # Skip dust tokens with value < $1
            if value < 1.0:
                continue

            # Stop after showing 15 significant assets
            if assets_displayed >= 15:
                break

            assets_displayed += 1
            portfolio_pct = asset_data.get("percentage_of_portfolio", 0)
            is_stable = asset_data.get("is_stable")
            platforms = asset_data.get("platforms", {})

            # Get quantity and price info
            quantity = asset_data.get("total_quantity", 0)
            current_price = asset_data.get("current_price")

            # Asset type indicator
            if is_stable is True:
                stability_icon = "🔒"
                asset_type = f"{theme.SUCCESS}Stable{theme.RESET}"
            elif is_stable is False:
                stability_icon = "📈"
                asset_type = f"{theme.WARNING}Volatile{theme.RESET}"
            else:  # is_stable is None
                stability_icon = "❓"
                asset_type = f"{theme.SUBTLE}Mixed{theme.RESET}"

            # Format quantity display - don't show quantity for stablecoins
            if is_stable is True:
                # For stablecoins, don't repeat the quantity since it's obvious
                qty_display = f"{theme.SUBTLE}—{theme.RESET}"
            elif quantity > 0:
                if quantity >= 1:
                    qty_display = (
                        f"{theme.ACCENT}{quantity:,.4f}".rstrip("0").rstrip(".")
                        + f" {symbol}{theme.RESET}"
                    )
                else:
                    qty_display = (
                        f"{theme.ACCENT}{quantity:.8f}".rstrip("0").rstrip(".")
                        + f" {symbol}{theme.RESET}"
                    )
            else:
                qty_display = f"{theme.SUBTLE}—{theme.RESET}"

            # Format price display - don't show price for stablecoins in breakdown
            if is_stable is True:
                # For stablecoins, don't show price info since it should be ~$1.00
                price_info = ""
            elif current_price is not None and current_price > 0:
                if current_price >= 1:
                    price_info = f" @ ${current_price:,.2f}"
                else:
                    price_info = f" @ ${current_price:.6f}".rstrip("0").rstrip(".")
            else:
                price_info = ""

            table_data.append(
                [
                    f"{stability_icon} {theme.ACCENT}{symbol}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(value)}{theme.RESET}",
                    qty_display,
                    price_info,
                    f"{theme.SUBTLE}{portfolio_pct:.1f}%{theme.RESET}",
                    asset_type,
                ]
            )

        print(tabulate(table_data, headers=headers, tablefmt="simple", stralign="left"))

        # Show detailed platform breakdown for major assets (>3% of portfolio)
        print(f"\n{theme.PRIMARY}📍 MAJOR ASSET BREAKDOWN{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")

        major_assets = [
            (symbol, data)
            for symbol, data in sorted_assets
            if data.get("percentage_of_portfolio", 0) > 3
        ]

        if major_assets:
            for symbol, asset_data in major_assets:
                platforms = asset_data.get("platforms", {})
                quantity = asset_data.get("total_quantity", 0)
                current_price = asset_data.get("current_price")
                portfolio_pct = asset_data.get("percentage_of_portfolio", 0)
                is_stable = asset_data.get("is_stable")

                # Format price display - don't show price for stablecoins in breakdown
                if is_stable is True:
                    # For stablecoins, don't show price info since it should be ~$1.00
                    price_info = ""
                elif current_price is not None and current_price > 0:
                    if current_price >= 1:
                        price_info = f" @ ${current_price:,.2f}"
                    else:
                        price_info = f" @ ${current_price:.6f}".rstrip("0").rstrip(".")
                else:
                    price_info = ""

                print(
                    f"\n{theme.ACCENT}{symbol}{theme.RESET} ({portfolio_pct:.1f}% of portfolio{price_info})"
                )

                # Sort platforms by value
                sorted_platforms = sorted(platforms.items(), key=lambda x: x[1], reverse=True)

                for platform, platform_value in sorted_platforms:
                    # Calculate quantity for this platform (proportional)
                    platform_pct = platform_value / asset_data.get("total_value_usd", 1)
                    platform_quantity = quantity * platform_pct

                    if platform_quantity > 0:
                        if platform_quantity >= 1:
                            qty_str = f"{platform_quantity:,.4f}".rstrip("0").rstrip(".")
                        else:
                            qty_str = f"{platform_quantity:.8f}".rstrip("0").rstrip(".")

                        # For stablecoins, don't show USD value since it's redundant
                        if is_stable is True:
                            # New format: quantity only for stablecoins
                            print(
                                f"  └─ {theme.SUBTLE}{platform:<15}{theme.RESET}: {theme.ACCENT}{qty_str} {symbol}{theme.RESET}"
                            )
                        else:
                            # New format: quantity first, then value in parentheses for non-stablecoins
                            print(
                                f"  └─ {theme.SUBTLE}{platform:<15}{theme.RESET}: {theme.ACCENT}{qty_str} {symbol}{theme.RESET} ({theme.SUCCESS}{format_currency(platform_value)}{theme.RESET})"
                            )
                    else:
                        print(
                            f"  └─ {theme.SUBTLE}{platform:<15}{theme.RESET}: {theme.SUCCESS}{format_currency(platform_value)}{theme.RESET}"
                        )
        else:
            print(f"{theme.SUBTLE}No major assets (>3% portfolio) to break down{theme.RESET}")

        if len(sorted_assets) > 15:
            # Count only non-dust assets for accurate remaining count
            non_dust_assets = [
                asset for _, asset in sorted_assets if asset.get("total_value_usd", 0) >= 1.0
            ]
            if len(non_dust_assets) > 15:
                remaining = len(non_dust_assets) - 15
                remaining_value = sum(
                    asset["total_value_usd"]
                    for _, asset in sorted_assets[15:]
                    if asset.get("total_value_usd", 0) >= 1.0
                )
                print(
                    f"\n{theme.SUBTLE}... and {remaining} more assets worth {format_currency(remaining_value)}{theme.RESET}"
                )

            # Show dust summary separately
            dust_assets = [
                asset for _, asset in sorted_assets if asset.get("total_value_usd", 0) < 1.0
            ]
            if dust_assets:
                dust_count = len(dust_assets)
                dust_value = sum(asset.get("total_value_usd", 0) for asset in dust_assets)
                print(
                    f"{theme.SUBTLE}+ {dust_count} dust tokens worth {format_currency(dust_value)} (hidden){theme.RESET}"
                )

        # Non-stable composition - moved before portfolio validation
        non_stable_assets = exposure_data.get("non_stable_assets", {})

        if non_stable_assets and non_stable_value > 0 and actual_non_stable_pct > 10:
            print(f"\n{theme.PRIMARY}⚡ NON-STABLE ASSET COMPOSITION{theme.RESET}")
            print(
                f"{theme.SUBTLE}Total: {format_currency(non_stable_value)} ({actual_non_stable_pct:.1f}% of portfolio){theme.RESET}"
            )
            print(f"{theme.SUBTLE}{'─' * 30}{theme.RESET}")

            # Sort non-stable assets by their percentage within the non-stable portion
            sorted_non_stable = sorted(
                [(symbol, data) for symbol, data in non_stable_assets.items()],
                key=lambda x: x[1].get("percentage_of_non_stable", 0),
                reverse=True,
            )

            # Enhanced table format for volatile assets
            volatile_table_data = []
            for symbol, asset_data in sorted_non_stable[:8]:  # Show top 8
                non_stable_composition_pct = asset_data.get("percentage_of_non_stable", 0)
                portfolio_pct = asset_data.get("percentage_of_portfolio", 0)
                value = asset_data.get("total_value_usd", 0)

                # Get quantity and price info
                quantity = asset_data.get("total_quantity", 0)
                current_price = asset_data.get("current_price")

                # Concentration warning icons
                if non_stable_composition_pct > 40:
                    risk_icon = f"{theme.ERROR}🔥{theme.RESET}"
                elif non_stable_composition_pct > 25:
                    risk_icon = f"{theme.WARNING}⚠️{theme.RESET}"
                else:
                    risk_icon = f"{theme.SUCCESS}✓{theme.RESET}"

                # Format quantity and price
                qty_price_str = ""
                if quantity > 0:
                    if quantity >= 1:
                        qty_display = f"{quantity:,.4f}".rstrip("0").rstrip(".")
                    else:
                        qty_display = f"{quantity:.8f}".rstrip("0").rstrip(".")

                    if current_price is not None and current_price > 0:
                        if current_price >= 1:
                            price_display = f"${current_price:,.2f}"
                        else:
                            price_display = f"${current_price:.6f}".rstrip("0").rstrip(".")
                        qty_price_str = f"{qty_display} @ {price_display}"
                    else:
                        qty_price_str = f"{qty_display} {symbol.lower()}"
                else:
                    qty_price_str = "—"

                volatile_table_data.append(
                    [
                        f"{theme.ACCENT}{symbol}{theme.RESET}",
                        f"{theme.PRIMARY}{format_currency(value)}{theme.RESET}",
                        f"{theme.WARNING}{non_stable_composition_pct:.1f}%{theme.RESET}",
                        f"{theme.SUBTLE}{portfolio_pct:.1f}%{theme.RESET}",
                        f"{theme.SUBTLE}{qty_price_str}{theme.RESET}",
                        risk_icon,
                    ]
                )

            volatile_headers = ["Asset", "Value", "% Non-Stable", "% Total", "Holdings", "Risk"]
            print(
                tabulate(
                    volatile_table_data,
                    headers=volatile_headers,
                    tablefmt="simple",
                    stralign="left",
                )
            )

            # Summary for volatile assets
            top_volatile = sorted_non_stable[0] if sorted_non_stable else None
            if top_volatile:
                top_symbol, top_data = top_volatile
                top_pct = top_data.get("percentage_of_non_stable", 0)
                if top_pct > 50:
                    print(
                        f"\n{theme.WARNING}⚠️  {top_symbol} dominates non-stable holdings ({top_pct:.1f}%){theme.RESET}"
                    )
                elif len(sorted_non_stable) > 10:
                    print(
                        f"\n{theme.SUCCESS}✓ Well-diversified across {len(sorted_non_stable)} non-stable assets{theme.RESET}"
                    )
                else:
                    print(
                        f"\n{theme.INFO}ℹ️  {len(sorted_non_stable)} non-stable assets tracked{theme.RESET}"
                    )

        # Enhanced portfolio validation with gap analysis
        displayed_total = sum(
            asset_data.get("total_value_usd", 0)
            for _, asset_data in sorted_assets
            if asset_data.get("total_value_usd", 0) >= 1.0
        )  # Only count non-dust assets displayed
        total_all_assets = sum(
            asset_data.get("total_value_usd", 0) for _, asset_data in sorted_assets
        )
        portfolio_gap = total_portfolio_value - total_all_assets

        debug_info = exposure_data.get("debug_info", {})
        scaling_factor = debug_info.get("scaling_factor_applied", 1.0)

        print(f"\n{theme.INFO}📊 PORTFOLIO VALIDATION & GAP ANALYSIS{theme.RESET}")
        print(f"─────────────────────────────────────────")
        print(f"Total Portfolio:      {format_currency(total_portfolio_value)}")
        print(f"Sum of All Assets:    {format_currency(total_all_assets)}")
        print(f"Gap/Difference:       {format_currency(portfolio_gap)}")

        if scaling_factor != 1.0:
            print(f"Scaling Applied:      {theme.WARNING}{scaling_factor:.3f}x{theme.RESET}")

        if abs(portfolio_gap) > 10:  # Alert if gap > $10
            gap_pct = (
                (abs(portfolio_gap) / total_portfolio_value * 100)
                if total_portfolio_value > 0
                else 0
            )
            print(f"Gap Percentage:       {theme.WARNING}⚠️  {gap_pct:.2f}%{theme.RESET}")

            # Provide gap analysis
            print(f"\n{theme.WARNING}🔍 POSSIBLE GAP SOURCES:{theme.RESET}")
            print(f"  • Assets below $0.01 dust threshold")
            print(f"  • Exchange assets without detailed breakdown")
            print(f"  • Untracked DeFi positions or LP tokens")
            print(f"  • Cross-chain bridge assets")
            print(f"  • Manual adjustments or offsets applied")
        else:
            print(
                f"Gap Status:           {theme.SUCCESS}✅ Values match (within tolerance){theme.RESET}"
            )

        # Count only non-dust assets displayed
        non_dust_count = len(
            [asset for _, asset in sorted_assets if asset.get("total_value_usd", 0) >= 1.0]
        )
        displayed_count = min(15, non_dust_count)
        print(
            f"Top {displayed_count} Assets Total: {format_currency(displayed_total)} ({(displayed_total/total_portfolio_value*100):.1f}% of portfolio)"
        )

    # Simple insights - only the most important ones
    print(f"\n{theme.PRIMARY}💡 KEY INSIGHTS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 13}{theme.RESET}")

    # Handle CEX mixed assets warning
    if has_neutral:
        neutral_pct = (neutral_value / total_portfolio_value) * 100
        print(
            f"  {theme.WARNING}• {neutral_pct:.1f}% in CEX mixed assets - breakdown unknown{theme.RESET}"
        )
        if neutral_pct > 50:
            print(
                f"  {theme.SUBTLE}  Consider checking individual exchange holdings for better analysis{theme.RESET}"
            )

    # Risk assessment (only for categorized assets)
    if categorized_value > 0:
        if actual_non_stable_pct > 85:
            print(f"  {theme.ERROR}• High volatility exposure - consider rebalancing{theme.RESET}")
        elif actual_non_stable_pct < 15:
            print(f"  {theme.WARNING}• Very conservative - may limit growth potential{theme.RESET}")
        else:
            print(f"  {theme.SUCCESS}• Risk level appears appropriate for growth{theme.RESET}")

        # Concentration check
        if consolidated_assets:
            top_asset = max(
                consolidated_assets.items(), key=lambda x: x[1].get("percentage_of_portfolio", 0)
            )
            top_asset_pct = top_asset[1].get("percentage_of_portfolio", 0)

            if top_asset_pct > 40:
                print(
                    f"  {theme.WARNING}• High concentration in {top_asset[0]} ({top_asset_pct:.1f}%){theme.RESET}"
                )
            elif top_asset_pct < 5 and len(consolidated_assets) > 15:
                print(
                    f"  {theme.WARNING}• Very fragmented portfolio ({len(consolidated_assets)} assets){theme.RESET}"
                )
            else:
                print(
                    f"  {theme.SUCCESS}• Good diversification across {len(consolidated_assets)} assets{theme.RESET}"
                )
    else:
        print(f"  {theme.SUBTLE}• Cannot assess risk - mostly unclassified CEX assets{theme.RESET}")

    # Simple footer
    asset_count = exposure_data.get("asset_count", 0)
    stable_count = exposure_data.get("stable_asset_count", 0)
    non_stable_count = exposure_data.get("non_stable_asset_count", 0)

    if has_neutral:
        print(
            f"\n{theme.SUBTLE}📈 {asset_count} assets tracked ({stable_count} stable, {non_stable_count} non-stable, {neutral_count} mixed){theme.RESET}"
        )
    else:
        print(
            f"\n{theme.SUBTLE}📈 {asset_count} assets tracked ({stable_count} stable, {non_stable_count} non-stable){theme.RESET}"
        )
    print()


def display_eth_balance_breakdown(portfolio_metrics: Dict[str, Any]):
    """
    EVM Wallet Balance Breakdown - Compare standard vs enhanced data
    Shows detailed analysis mimicking the enhanced debank scraper reports.
    """
    from utils.display_theme import theme
    from utils.helpers import format_currency
    from tabulate import tabulate
    import os
    import json
    from pathlib import Path

    # Clear screen
    os.system("clear" if os.name == "posix" else "cls")

    print(f"\n{theme.PRIMARY}🔗 EVM WALLET BALANCE BREAKDOWN{theme.RESET}")
    print(f"{theme.SUBTLE}{'=' * 35}{theme.RESET}")

    # Get wallet data from portfolio metrics
    wallet_data = portfolio_metrics.get("wallet_platform_data_raw", [])
    eth_exposure_data = portfolio_metrics.get("eth_exposure_data", {})

    # Extract standard DeBankc balances for Ethereum addresses
    standard_eth_balances = {}
    total_standard_eth = 0
    eth_addresses = []

    for wallet_info in wallet_data:
        if wallet_info.get("chain") == "ethereum":
            address = wallet_info.get("address", "Unknown")
            balance = wallet_info.get("total_balance", 0)
            standard_eth_balances[address] = balance
            total_standard_eth += balance
            eth_addresses.append(address)

    if not eth_addresses:
        print(f"\n{theme.WARNING}⚠️ NO ETHEREUM ADDRESSES FOUND{theme.RESET}")
        print(f"{theme.SUBTLE}No Ethereum wallets configured in the system{theme.RESET}")
        input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
        return

    print(f"\n{theme.INFO}📊 Found {len(eth_addresses)} Ethereum addresses{theme.RESET}")
    print(
        f"{theme.SUBTLE}Standard DeBankc Total: {format_currency(total_standard_eth)}{theme.RESET}"
    )

    # Try to load enhanced data from organized folders and legacy files
    enhanced_data = {}

    # Check if we have analysis folder context from past analysis viewing
    analysis_folder = portfolio_metrics.get("_analysis_folder")

    if analysis_folder and Path(analysis_folder).exists():
        # SPECIFIC ANALYSIS SESSION: Load from the exact folder
        print(
            f"\n{theme.INFO}🔍 Loading enhanced data from specific analysis session...{theme.RESET}"
        )
        print(f"{theme.SUCCESS}🎯 Target folder: {analysis_folder}{theme.RESET}")

        analysis_path = Path(analysis_folder)
        json_files = list(analysis_path.glob("wallet_breakdown_0x*.json"))

        if json_files:
            print(f"{theme.SUCCESS}✅ Found {len(json_files)} enhanced wallet files{theme.RESET}")

            # Load enhanced data for each address
            for json_file in json_files:
                try:
                    with open(json_file, "r") as f:
                        file_data = json.load(f)

                    # Extract address from file data or filename
                    address = file_data.get("address")
                    if not address:
                        # Try to extract from filename
                        filename = json_file.name
                        if "wallet_breakdown_0x" in filename:
                            address_part = filename.split("wallet_breakdown_")[1].split(".json")[0]
                            # Find matching full address
                            for full_addr in eth_addresses:
                                if full_addr.lower().startswith(address_part.lower()):
                                    address = full_addr
                                    break

                    if address and address in eth_addresses:
                        enhanced_data[address] = file_data
                        print(
                            f"{theme.SUCCESS}  ✅ Loaded data for {address[:8]}...{address[-6:]}{theme.RESET}"
                        )

                except Exception as e:
                    print(f"{theme.ERROR}  ❌ Error loading {json_file.name}: {e}{theme.RESET}")
                    continue
        else:
            print(
                f"{theme.WARNING}⚠️ No enhanced wallet files found in this analysis session{theme.RESET}"
            )

    else:
        # NO SPECIFIC FOLDER: Search all organized folders (for live analysis or refresh)
        print(
            f"\n{theme.INFO}🔍 Searching for enhanced wallet data in all analysis sessions...{theme.RESET}"
        )
        exported_data_path = Path("exported_data")

        if exported_data_path.exists():
            # Search in organized analysis folders first
            analysis_folders = list(exported_data_path.glob("analysis_*/"))
            json_files = []

            for analysis_folder_path in analysis_folders:
                json_files.extend(analysis_folder_path.glob("wallet_breakdown_0x*.json"))

            # Also check root folder for legacy files
            json_files.extend(exported_data_path.glob("live_analysis_0x*.json"))
            json_files.extend(exported_data_path.glob("wallet_breakdown_0x*.json"))

            # Sort by modification time to get most recent first
            if json_files:
                json_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                print(
                    f"{theme.SUCCESS}✅ Found {len(json_files)} enhanced wallet files{theme.RESET}"
                )

                # Track which addresses we've actually loaded (not duplicates)
                loaded_addresses = set()

                # Load enhanced data for each address
                for json_file in json_files:
                    try:
                        with open(json_file, "r") as f:
                            file_data = json.load(f)

                        # Extract address from file data or filename
                        address = file_data.get("address")
                        if not address:
                            # Try to extract from filename
                            filename = json_file.name
                            if "wallet_breakdown_0x" in filename:
                                address_part = filename.split("wallet_breakdown_")[1].split(
                                    ".json"
                                )[0]
                            elif "live_analysis_0x" in filename:
                                address_part = filename.split("_")[2]
                            else:
                                continue

                            # Find matching full address
                            for full_addr in eth_addresses:
                                if full_addr.lower().startswith(address_part.lower()):
                                    address = full_addr
                                    break

                        if address and address in eth_addresses:
                            # Only show loading message for new addresses (not overwrites)
                            if address not in loaded_addresses:
                                enhanced_data[address] = file_data
                                loaded_addresses.add(address)
                                print(
                                    f"{theme.SUCCESS}  ✅ Loaded data for {address[:8]}...{address[-6:]}{theme.RESET}"
                                )
                            else:
                                # Silently overwrite with more recent data (files are sorted by mod time)
                                enhanced_data[address] = file_data

                    except Exception as e:
                        print(f"{theme.ERROR}  ❌ Error loading {json_file.name}: {e}{theme.RESET}")
                        continue

                # Show summary of what was actually loaded
                if loaded_addresses:
                    duplicate_count = len(json_files) - len(loaded_addresses)
                    if duplicate_count > 0:
                        print(
                            f"{theme.SUBTLE}  📁 {duplicate_count} duplicate files ignored (kept most recent){theme.RESET}"
                        )
            else:
                print(f"{theme.WARNING}⚠️ No enhanced wallet files found{theme.RESET}")
        else:
            print(f"{theme.WARNING}⚠️ exported_data folder not found{theme.RESET}")

    # Analysis and comparison
    if not enhanced_data:
        print(f"\n{theme.ERROR}❌ NO ENHANCED DATA AVAILABLE{theme.RESET}")
        print(
            f"{theme.SUBTLE}Run a live analysis to generate enhanced wallet breakdowns{theme.RESET}"
        )
        input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
        return

    # 1. COMPARISON TABLE
    print(f"\n{theme.PRIMARY}📊 STANDARD vs ENHANCED COMPARISON{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 40}{theme.RESET}")

    comparison_data = []
    headers = [
        "Address",
        "Standard DeBankc",
        "Enhanced Scraper",
        "Difference",
        "Tokens",
        "Protocols",
        "Status",
    ]

    total_enhanced = 0
    successful_addresses = 0

    for address in eth_addresses:
        address_short = f"{address[:8]}...{address[-6:]}"
        standard_balance = standard_eth_balances.get(address, 0)

        if address in enhanced_data:
            enhanced_info = enhanced_data[address]
            enhanced_balance = enhanced_info.get("total_usd_value", 0)
            tokens = enhanced_info.get("tokens", [])
            protocols = enhanced_info.get("protocols", [])

            total_enhanced += enhanced_balance
            successful_addresses += 1

            # Calculate difference
            difference = enhanced_balance - standard_balance

            # Status and color coding
            if abs(difference) < 10:
                diff_color = theme.SUCCESS
                status = "✅"
            elif abs(difference) < 100:
                diff_color = theme.WARNING
                status = "⚠️"
            else:
                diff_color = theme.ERROR
                status = "❌"

            # Format difference with sign
            if difference >= 0:
                diff_display = f"{diff_color}+{format_currency(difference)}{theme.RESET}"
            else:
                diff_display = f"{diff_color}{format_currency(difference)}{theme.RESET}"

            comparison_data.append(
                [
                    f"{theme.ACCENT}{address_short}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(standard_balance)}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(enhanced_balance)}{theme.RESET}",
                    diff_display,
                    f"{theme.SUBTLE}{len(tokens)}{theme.RESET}",
                    f"{theme.SUBTLE}{len(protocols)}{theme.RESET}",
                    status,
                ]
            )
        else:
            comparison_data.append(
                [
                    f"{theme.ACCENT}{address_short}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(standard_balance)}{theme.RESET}",
                    f"{theme.ERROR}No Data{theme.RESET}",
                    f"{theme.ERROR}N/A{theme.RESET}",
                    f"{theme.SUBTLE}—{theme.RESET}",
                    f"{theme.SUBTLE}—{theme.RESET}",
                    "❌",
                ]
            )

    print(tabulate(comparison_data, headers=headers, tablefmt="simple", stralign="left"))

    # 2. SUMMARY STATISTICS
    method_difference = total_enhanced - total_standard_eth

    print(f"\n{theme.PRIMARY}📈 SUMMARY STATISTICS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
    print(f"Total Addresses:        {theme.ACCENT}{len(eth_addresses)}{theme.RESET}")
    print(f"Enhanced Data Available: {theme.SUCCESS}{successful_addresses}{theme.RESET}")
    print(
        f"Coverage:               {theme.ACCENT}{(successful_addresses/len(eth_addresses)*100):.1f}%{theme.RESET}"
    )

    print(f"\n{theme.PRIMARY}💰 BALANCE COMPARISON{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
    print(
        f"Standard DeBankc Total: {theme.PRIMARY}{format_currency(total_standard_eth)}{theme.RESET}"
    )
    print(f"Enhanced Scraper Total: {theme.PRIMARY}{format_currency(total_enhanced)}{theme.RESET}")

    if method_difference >= 0:
        method_diff_display = f"{theme.SUCCESS}+{format_currency(method_difference)}{theme.RESET}"
    else:
        method_diff_display = f"{theme.WARNING}{format_currency(method_difference)}{theme.RESET}"

    print(f"Method Difference:      {method_diff_display}")

    if total_standard_eth > 0:
        method_diff_pct = (method_difference / total_standard_eth) * 100
        print(f"Difference Percentage:  {theme.WARNING}{method_diff_pct:+.2f}%{theme.RESET}")

    # 3. DETAILED ANALYSIS (mimicking enhanced debank scraper)
    if enhanced_data:
        print(f"\n{theme.PRIMARY}🔍 DETAILED WALLET ANALYSIS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")

        # Find the largest wallet for detailed breakdown
        largest_wallet = max(enhanced_data.items(), key=lambda x: x[1].get("total_usd_value", 0))
        largest_addr, largest_data = largest_wallet

        print(
            f"\n{theme.ACCENT}🏆 LARGEST WALLET: {largest_addr[:8]}...{largest_addr[-6:]}{theme.RESET}"
        )
        print(
            f"Total Value: {theme.PRIMARY}{format_currency(largest_data.get('total_usd_value', 0))}{theme.RESET}"
        )

        # Token breakdown
        tokens = largest_data.get("tokens", [])
        if tokens:
            print(f"\n{theme.INFO}🪙 TOKEN BREAKDOWN ({len(tokens)} tokens):{theme.RESET}")

            # Sort tokens by value
            sorted_tokens = sorted(tokens, key=lambda t: t.get("usd_value", 0), reverse=True)

            token_table = []
            for token in sorted_tokens[:10]:  # Show top 10
                symbol = token.get("symbol", "Unknown")
                amount = token.get("amount", 0)
                usd_value = token.get("usd_value", 0)
                category = token.get("category", "other")

                # Category icon
                if category == "stable":
                    cat_icon = "🔒"
                elif category == "eth_exposure":
                    cat_icon = "💎"
                elif category == "eth_staking":
                    cat_icon = "🥩"
                else:
                    cat_icon = "📈"

                token_table.append(
                    [
                        f"{cat_icon} {theme.ACCENT}{symbol}{theme.RESET}",
                        f"{theme.SUBTLE}{amount:,.4f}".rstrip("0").rstrip("."),
                        f"{theme.PRIMARY}{format_currency(usd_value)}{theme.RESET}",
                        f"{theme.SUBTLE}{category}{theme.RESET}",
                    ]
                )

            print(
                tabulate(
                    token_table,
                    headers=["Token", "Amount", "USD Value", "Category"],
                    tablefmt="simple",
                )
            )

        # Protocol breakdown
        protocols = largest_data.get("protocols", [])
        if protocols:
            print(f"\n{theme.INFO}🏛️ PROTOCOL BREAKDOWN ({len(protocols)} protocols):{theme.RESET}")

            # Sort protocols by value
            sorted_protocols = sorted(
                protocols, key=lambda p: p.get("total_value", 0), reverse=True
            )

            protocol_table = []
            for protocol in sorted_protocols[:8]:  # Show top 8
                name = protocol.get("name", "Unknown")
                total_value = protocol.get("total_value", 0)
                chain = protocol.get("chain", "unknown")

                # Chain icon
                chain_icon = "🔗"
                if chain.lower() == "ethereum":
                    chain_icon = "⟠"
                elif chain.lower() == "arbitrum":
                    chain_icon = "🔵"
                elif chain.lower() == "polygon":
                    chain_icon = "🟣"
                elif chain.lower() == "base":
                    chain_icon = "🔷"

                protocol_table.append(
                    [
                        f"{theme.ACCENT}{name}{theme.RESET}",
                        f"{theme.PRIMARY}{format_currency(total_value)}{theme.RESET}",
                        f"{chain_icon} {theme.SUBTLE}{chain}{theme.RESET}",
                    ]
                )

            print(
                tabulate(
                    protocol_table, headers=["Protocol", "USD Value", "Chain"], tablefmt="simple"
                )
            )

        # Show exposure breakdown for largest wallet
        largest_data = max(enhanced_data.values(), key=lambda x: x.get("total_usd_value", 0))

        # Calculate exposure breakdown on-the-fly from raw token data
        exposure_breakdown = {
            "stable": 0.0,
            "eth_exposure": 0.0,
            "eth_staking": 0.0,
            "other_crypto": 0.0,
        }

        for token in largest_data.get("tokens", []):
            category = token.get("category", "other_crypto")
            if category in exposure_breakdown:
                exposure_breakdown[category] += token.get("usd_value", 0)
            else:
                exposure_breakdown["other_crypto"] += token.get("usd_value", 0)

        if exposure_breakdown:
            print(f"\n{theme.PRIMARY}📊 EXPOSURE BREAKDOWN (Largest Wallet){theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * 35}{theme.RESET}")

            total_categorized = sum(exposure_breakdown.values())

            for category, value in exposure_breakdown.items():
                if value > 0:
                    percentage = (value / total_categorized * 100) if total_categorized > 0 else 0
                    category_display = {
                        "stable": "🔒 Stable",
                        "eth_exposure": "💎 ETH Exposure",
                        "eth_staking": "🥩 ETH Staking",
                        "other_crypto": "📈 Other Crypto",
                    }.get(category, category)

                    print(f"  {category_display}: {format_currency(value)} ({percentage:.1f}%)")

    # 4. INSIGHTS AND RECOMMENDATIONS
    print(f"\n{theme.PRIMARY}💡 KEY INSIGHTS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 13}{theme.RESET}")

    if method_difference > 100:
        print(
            f"  {theme.SUCCESS}• Enhanced method captures {format_currency(method_difference)} more value{theme.RESET}"
        )
        print(
            f"  {theme.INFO}• This suggests the enhanced scraper finds additional tokens/protocols{theme.RESET}"
        )
    elif method_difference < -100:
        print(
            f"  {theme.WARNING}• Standard method shows {format_currency(abs(method_difference))} more value{theme.RESET}"
        )
        print(
            f"  {theme.INFO}• This may indicate parsing differences or timing variations{theme.RESET}"
        )
    else:
        print(
            f"  {theme.SUCCESS}• Both methods show similar total values (difference < $100){theme.RESET}"
        )
        print(f"  {theme.INFO}• This indicates good consistency between approaches{theme.RESET}")

    if successful_addresses < len(eth_addresses):
        missing = len(eth_addresses) - successful_addresses
        print(
            f"  {theme.WARNING}• {missing} addresses missing enhanced data - run live analysis to update{theme.RESET}"
        )

    # Show data freshness
    if enhanced_data:
        timestamps = []
        for data in enhanced_data.values():
            timestamp_str = data.get("timestamp", "")
            if timestamp_str:
                try:
                    from datetime import datetime, timezone

                    # Handle both with and without timezone info
                    if timestamp_str.endswith("Z"):
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    elif "+" in timestamp_str or timestamp_str.endswith("UTC"):
                        timestamp = datetime.fromisoformat(timestamp_str)
                    else:
                        # Assume UTC if no timezone info
                        timestamp = datetime.fromisoformat(timestamp_str).replace(
                            tzinfo=timezone.utc
                        )
                    timestamps.append(timestamp)
                except:
                    continue

        if timestamps:
            latest_timestamp = max(timestamps)
            from datetime import datetime, timezone

            # Ensure both datetimes are timezone-aware
            now_utc = datetime.now(timezone.utc)
            if latest_timestamp.tzinfo is None:
                latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)

            age_hours = (now_utc - latest_timestamp).total_seconds() / 3600

            if age_hours < 1:
                freshness_color = theme.SUCCESS
                freshness_text = f"Very fresh (< 1 hour old)"
            elif age_hours < 24:
                freshness_color = theme.WARNING
                freshness_text = f"Recent ({age_hours:.1f} hours old)"
            else:
                freshness_color = theme.ERROR
                freshness_text = f"Stale ({age_hours/24:.1f} days old)"

            print(f"  {freshness_color}• Data freshness: {freshness_text}{theme.RESET}")

    # 4. DOUBLE COUNTING ANALYSIS (permanent warning for users)
    print(f"\n{theme.PRIMARY}🔍 DOUBLE COUNTING ANALYSIS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")

    # Check for potential double counting issues across all wallets
    total_fallback_protocols = 0
    total_fallback_value = 0
    wallets_with_fallback = []
    wallets_with_generic_protocols = []

    for address, wallet_data in enhanced_data.items():
        protocols = wallet_data.get("protocols", [])

        # Check for fallback 'Wallet' protocols that were filtered out
        fallback_count = 0
        fallback_value = 0

        for protocol in protocols:
            # Check for the exact criteria we filter in the enhanced scraper
            if (
                protocol.get("name") == "Wallet"
                and protocol.get("chain") == "unknown"
                and protocol.get("source") == "reverted_simple_parsing"
            ):
                fallback_count += 1
                fallback_value += protocol.get("total_value", 0)
                total_fallback_protocols += 1
                total_fallback_value += protocol.get("total_value", 0)

        if fallback_count > 0:
            wallets_with_fallback.append(
                {"address": address, "count": fallback_count, "value": fallback_value}
            )

        # Also check for other potentially problematic protocols
        generic_protocols = []
        for protocol in protocols:
            if protocol.get("name") in ["Portfolio", "Total", "Balance"]:
                generic_protocols.append(protocol.get("name"))

        if generic_protocols:
            wallets_with_generic_protocols.append(
                {"address": address, "protocols": generic_protocols}
            )

    # Display double counting status
    if total_fallback_protocols > 0:
        print(f"  {theme.WARNING}⚠️  FALLBACK PROTOCOLS DETECTED{theme.RESET}")
        print(
            f"  {theme.ERROR}• {total_fallback_protocols} fallback 'Wallet' protocols worth {format_currency(total_fallback_value)}{theme.RESET}"
        )
        print(
            f"  {theme.SUCCESS}• These protocols have been automatically filtered to prevent double counting{theme.RESET}"
        )
        print(f"  {theme.INFO}• Affected wallets: {len(wallets_with_fallback)}{theme.RESET}")

        # Show details for affected wallets
        for wallet_info in wallets_with_fallback:
            addr_short = f"{wallet_info['address'][:8]}...{wallet_info['address'][-6:]}"
            print(
                f"    {theme.SUBTLE}• {addr_short}: {wallet_info['count']} fallback protocols ({format_currency(wallet_info['value'])}){theme.RESET}"
            )

        print(
            f"  {theme.SUCCESS}✅ Validation: All fallback protocols excluded from totals{theme.RESET}"
        )
    else:
        print(f"  {theme.SUCCESS}✅ NO DOUBLE COUNTING DETECTED{theme.RESET}")
        print(f"  {theme.SUCCESS}• All protocols appear to be legitimate and unique{theme.RESET}")
        print(f"  {theme.INFO}• No fallback 'Wallet' protocols found{theme.RESET}")

    # Check for other potential issues
    if wallets_with_generic_protocols:
        print(f"  {theme.WARNING}⚠️  GENERIC PROTOCOL NAMES DETECTED{theme.RESET}")
        for wallet_info in wallets_with_generic_protocols:
            addr_short = f"{wallet_info['address'][:8]}...{wallet_info['address'][-6:]}"
            protocols_str = ", ".join(wallet_info["protocols"])
            print(f"    {theme.SUBTLE}• {addr_short}: {protocols_str}{theme.RESET}")
        print(
            f"  {theme.INFO}• These may indicate parsing issues but are included in totals{theme.RESET}"
        )

    # 5. INSIGHTS AND RECOMMENDATIONS
    print(f"\n{theme.PRIMARY}💡 KEY INSIGHTS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 13}{theme.RESET}")

    if method_difference > 100:
        print(
            f"  {theme.SUCCESS}• Enhanced method captures {format_currency(method_difference)} more value{theme.RESET}"
        )
        print(
            f"  {theme.INFO}• This suggests the enhanced scraper finds additional tokens/protocols{theme.RESET}"
        )
    elif method_difference < -100:
        print(
            f"  {theme.WARNING}• Standard method shows {format_currency(abs(method_difference))} more value{theme.RESET}"
        )
        print(
            f"  {theme.INFO}• This may indicate parsing differences or timing variations{theme.RESET}"
        )
    else:
        print(
            f"  {theme.SUCCESS}• Both methods show similar total values (difference < $100){theme.RESET}"
        )
        print(f"  {theme.INFO}• This indicates good consistency between approaches{theme.RESET}")

    if successful_addresses < len(eth_addresses):
        missing = len(eth_addresses) - successful_addresses
        print(
            f"  {theme.WARNING}• {missing} addresses missing enhanced data - run live analysis to update{theme.RESET}"
        )

    # Show data freshness
    if enhanced_data:
        timestamps = []
        for data in enhanced_data.values():
            timestamp_str = data.get("timestamp", "")
            if timestamp_str:
                try:
                    from datetime import datetime, timezone

                    # Handle both with and without timezone info
                    if timestamp_str.endswith("Z"):
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    elif "+" in timestamp_str or timestamp_str.endswith("UTC"):
                        timestamp = datetime.fromisoformat(timestamp_str)
                    else:
                        # Assume UTC if no timezone info
                        timestamp = datetime.fromisoformat(timestamp_str).replace(
                            tzinfo=timezone.utc
                        )
                    timestamps.append(timestamp)
                except:
                    continue

        if timestamps:
            latest_timestamp = max(timestamps)
            from datetime import datetime, timezone

            # Ensure both datetimes are timezone-aware
            now_utc = datetime.now(timezone.utc)
            if latest_timestamp.tzinfo is None:
                latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)

            age_hours = (now_utc - latest_timestamp).total_seconds() / 3600

            if age_hours < 1:
                freshness_color = theme.SUCCESS
                freshness_text = f"Very fresh (< 1 hour old)"
            elif age_hours < 24:
                freshness_color = theme.WARNING
                freshness_text = f"Recent ({age_hours:.1f} hours old)"
            else:
                freshness_color = theme.ERROR
                freshness_text = f"Stale ({age_hours/24:.1f} days old)"

            print(f"  {freshness_color}• Data freshness: {freshness_text}{theme.RESET}")

    input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
