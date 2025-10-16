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


def display_wallet_balances(wallet_platform_data: List[Dict[str, Any]]):
    """Enhanced wallet balances display with improved formatting and theming."""
    print_header("Wallet Balances")

    wallets_only_data = [info for info in wallet_platform_data if "chain" in info]
    if not wallets_only_data:
        print(f"{theme.SUBTLE}No wallet data available.{theme.RESET}")
        return

    # Group data by chain
    chain_balances: Dict[str, List[Dict[str, Any]]] = {}
    for info in wallets_only_data:
        chain = info["chain"]
        if chain not in chain_balances:
            chain_balances[chain] = []
        chain_balances[chain].append(info)

    total_all_wallets_usd = sum(
        info.get("total_balance", info.get("total_balance_usd", 0.0)) for info in wallets_only_data
    )

    # Enhanced summary with icons
    print(f"\n{theme.PRIMARY}🏦 WALLET SUMMARY{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 18}{theme.RESET}")
    print(
        f"Total Wallet Value: {theme.SUCCESS}{format_currency(total_all_wallets_usd)}{theme.RESET}"
    )
    print(f"Active Chains:      {theme.ACCENT}{len(chain_balances)}{theme.RESET}")

    # Chain icons mapping
    chain_icons = {"ethereum": "🔷", "bitcoin": "₿", "solana": "◎", "near": "🌌", "aptos": "🏔️"}

    for chain in SUPPORTED_CHAINS:
        wallets = chain_balances.get(chain)
        if not wallets:
            continue

        icon = chain_icons.get(chain, "🔗")

        print(f"\n{theme.PRIMARY}{icon} {chain.upper()} WALLETS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * (len(chain) + 10)}{theme.RESET}")

        headers = [
            f"{theme.PRIMARY}Address{theme.RESET}",
            f"{theme.PRIMARY}USD Value{theme.RESET}",
            f"{theme.PRIMARY}Native Balance{theme.RESET}",
            f"{theme.PRIMARY}Share{theme.RESET}",
            f"{theme.PRIMARY}Details{theme.RESET}",
        ]
        table_data = []

        for info in wallets:
            address_short = info.get("address", "N/A")
            if address_short != "N/A":
                address_short = address_short[:8] + "..." + address_short[-6:]

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
                token_count = sum(
                    1 for bal in info.get("token_balances", {}).values() if bal > 1e-6
                )
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

    print()  # Final spacing


def display_hyperliquid_positions(wallet_platform_data: List[Dict[str, Any]]):
    """Enhanced Hyperliquid positions display with improved formatting and theming."""
    print_header("Hyperliquid Positions")

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
    Displays detailed ETH balance breakdown comparing standard DeBankc data
    with enhanced JSON export data from the exported_data folder.
    """
    import glob
    import json
    from pathlib import Path

    # Clear screen
    os.system("clear" if os.name == "posix" else "cls")

    print(f"\n{theme.PRIMARY}📊 DETAILED ETH BALANCE BREAKDOWN{theme.RESET}")
    print(f"{theme.SUBTLE}{'=' * 35}{theme.RESET}")

    # Get ETH exposure data from portfolio metrics
    eth_exposure_data = portfolio_metrics.get("eth_exposure_data", {})
    wallet_data = portfolio_metrics.get("wallet_platform_data_raw", [])

    # If no ETH exposure data in portfolio metrics, try to load from exported_data folder
    if not eth_exposure_data:
        print(f"\n{theme.INFO}🔍 ETH exposure data not found in analysis file{theme.RESET}")
        print(f"{theme.INFO}Looking for existing data in exported_data folder...{theme.RESET}")

        # Load ETH exposure data from exported_data folder
        exported_data_path = Path("exported_data")
        if exported_data_path.exists():
            json_files = list(exported_data_path.glob("live_analysis_0x*.json"))

            if json_files:
                print(f"{theme.SUCCESS}✅ Found {len(json_files)} ETH exposure files{theme.RESET}")

                # Load each file and extract address from filename
                for json_file in json_files:
                    try:
                        # Extract address from filename: live_analysis_0x60c6c2_20250608_140753.json
                        filename = json_file.name
                        if filename.startswith("live_analysis_0x"):
                            address_part = filename.split("_")[2]  # Gets "0x60c6c2"
                            # Find the full address by matching the start
                            full_address = None
                            for wallet_info in wallet_data:
                                if wallet_info.get("chain") == "ethereum" and wallet_info.get(
                                    "address", ""
                                ).lower().startswith(address_part.lower()):
                                    full_address = wallet_info.get("address")
                                    break

                            if full_address:
                                with open(json_file, "r") as f:
                                    file_data = json.load(f)

                                # Convert to expected format
                                eth_exposure_data[full_address] = {"export_data": file_data}
                            else:
                                print(
                                    f"{theme.WARNING}⚠️ Could not match {address_part} to tracked addresses{theme.RESET}"
                                )

                    except Exception as e:
                        print(f"{theme.ERROR}❌ Error loading {json_file.name}: {e}{theme.RESET}")

                if eth_exposure_data:
                    print(
                        f"{theme.SUCCESS}✅ Loaded ETH exposure data for {len(eth_exposure_data)} addresses{theme.RESET}"
                    )
                else:
                    print(f"{theme.ERROR}❌ Could not load any ETH exposure data{theme.RESET}")
            else:
                print(
                    f"{theme.WARNING}⚠️ No ETH exposure files found in exported_data folder{theme.RESET}"
                )
        else:
            print(f"{theme.WARNING}⚠️ exported_data folder not found{theme.RESET}")

    # If still no data after trying to load from files
    if not eth_exposure_data:
        print(f"\n{theme.ERROR}❌ NO ENHANCED ETH DATA AVAILABLE{theme.RESET}")
        print(f"{theme.SUBTLE}Enhanced ETH exposure data was not found in:{theme.RESET}")
        print(f"{theme.SUBTLE}• Portfolio analysis file{theme.RESET}")
        print(f"{theme.SUBTLE}• exported_data folder{theme.RESET}")
        print(
            f"{theme.SUBTLE}Run a new live analysis to generate enhanced ETH breakdown.{theme.RESET}"
        )
        input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
        return

    # Extract standard DeBankc balances for Ethereum addresses
    standard_eth_balances = {}
    total_standard_eth = 0

    for wallet_info in wallet_data:
        if wallet_info.get("chain") == "ethereum":
            address = wallet_info.get("address", "Unknown")
            balance = wallet_info.get("total_balance", 0)
            standard_eth_balances[address] = balance
            total_standard_eth += balance

    # Process enhanced ETH data
    enhanced_eth_data = {}
    total_enhanced_eth = 0
    total_validation_gaps = 0
    successful_addresses = 0
    failed_addresses = 0

    print(f"\n{theme.PRIMARY}🔍 ENHANCED vs STANDARD COMPARISON{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 35}{theme.RESET}")

    # Create comparison table
    comparison_data = []
    headers = [
        "Address",
        "Standard DeBankc",
        "Enhanced JSON",
        "Difference",
        "Status",
        "Tokens",
        "Protocols",
    ]

    for address, eth_data in eth_exposure_data.items():
        if address == "enhancement_error":
            continue

        address_short = f"{address[:8]}...{address[-6:]}" if len(address) > 20 else address
        standard_balance = standard_eth_balances.get(address, 0)

        if "export_data" in eth_data:
            # Successful enhanced fetch
            export_data = eth_data["export_data"]
            enhanced_balance = export_data["summary"]["total_portfolio_value_usd"]
            validation_gap = export_data["summary"]["validation_difference_usd"]
            token_count = export_data["summary"]["total_tokens"]
            protocol_count = export_data["summary"]["total_protocols"]
            validation_status = export_data["metadata"]["validation_status"]

            enhanced_eth_data[address] = {
                "balance": enhanced_balance,
                "tokens": token_count,
                "protocols": protocol_count,
                "validation_gap": validation_gap,
                "status": validation_status,
            }

            total_enhanced_eth += enhanced_balance
            total_validation_gaps += abs(validation_gap)
            successful_addresses += 1

            # Calculate difference between methods
            method_difference = enhanced_balance - standard_balance

            # Status indicators
            if validation_status == "passed":
                status_icon = f"{theme.SUCCESS}✅{theme.RESET}"
            else:
                status_icon = f"{theme.WARNING}⚠️{theme.RESET}"

            # Difference indicator
            if abs(method_difference) < 10:
                diff_color = theme.SUCCESS
            elif abs(method_difference) < 100:
                diff_color = theme.WARNING
            else:
                diff_color = theme.ERROR

            # Format difference with sign
            if method_difference >= 0:
                diff_display = f"{diff_color}+{format_currency(method_difference)}{theme.RESET}"
            else:
                diff_display = f"{diff_color}{format_currency(method_difference)}{theme.RESET}"

            comparison_data.append(
                [
                    f"{theme.ACCENT}{address_short}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(standard_balance)}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(enhanced_balance)}{theme.RESET}",
                    diff_display,
                    status_icon,
                    f"{theme.SUBTLE}{token_count}{theme.RESET}",
                    f"{theme.SUBTLE}{protocol_count}{theme.RESET}",
                ]
            )

        else:
            # Failed enhanced fetch
            error_msg = eth_data.get("error", "Unknown error")
            failed_addresses += 1

            comparison_data.append(
                [
                    f"{theme.ACCENT}{address_short}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(standard_balance)}{theme.RESET}",
                    f"{theme.ERROR}Failed{theme.RESET}",
                    f"{theme.ERROR}N/A{theme.RESET}",
                    f"{theme.ERROR}❌{theme.RESET}",
                    f"{theme.SUBTLE}—{theme.RESET}",
                    f"{theme.SUBTLE}—{theme.RESET}",
                ]
            )

    print(tabulate(comparison_data, headers=headers, tablefmt="simple", stralign="left"))

    # Summary statistics
    total_addresses = successful_addresses + failed_addresses
    method_difference_total = total_enhanced_eth - total_standard_eth

    print(f"\n{theme.PRIMARY}📈 SUMMARY STATISTICS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
    print(f"Total Addresses:        {theme.ACCENT}{total_addresses}{theme.RESET}")
    print(f"Successful Enhanced:    {theme.SUCCESS}{successful_addresses}{theme.RESET}")
    print(f"Failed Enhanced:        {theme.ERROR}{failed_addresses}{theme.RESET}")
    print(
        f"Success Rate:           {theme.ACCENT}{(successful_addresses/total_addresses*100):.1f}%{theme.RESET}"
    )

    print(f"\n{theme.PRIMARY}💰 BALANCE COMPARISON{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
    print(
        f"Standard DeBankc Total: {theme.PRIMARY}{format_currency(total_standard_eth)}{theme.RESET}"
    )
    print(
        f"Enhanced JSON Total:    {theme.PRIMARY}{format_currency(total_enhanced_eth)}{theme.RESET}"
    )

    # Format method difference with sign
    if method_difference_total >= 0:
        method_diff_display = (
            f"{theme.WARNING}+{format_currency(method_difference_total)}{theme.RESET}"
        )
    else:
        method_diff_display = (
            f"{theme.WARNING}{format_currency(method_difference_total)}{theme.RESET}"
        )

    print(f"Method Difference:      {method_diff_display}")

    if total_standard_eth > 0:
        method_diff_pct = (method_difference_total / total_standard_eth) * 100
        print(f"Difference Percentage:  {theme.WARNING}{method_diff_pct:+.2f}%{theme.RESET}")

    print(f"\n{theme.PRIMARY}🔍 VALIDATION ANALYSIS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
    print(
        f"Total Validation Gaps:  {theme.WARNING}{format_currency(total_validation_gaps)}{theme.RESET}"
    )

    if successful_addresses > 0:
        avg_validation_gap = total_validation_gaps / successful_addresses
        print(
            f"Average Gap per Address: {theme.WARNING}{format_currency(avg_validation_gap)}{theme.RESET}"
        )

        # Gap analysis
        if avg_validation_gap < 10:
            print(f"Gap Assessment:         {theme.SUCCESS}✅ Excellent accuracy{theme.RESET}")
        elif avg_validation_gap < 50:
            print(f"Gap Assessment:         {theme.WARNING}⚠️ Good accuracy{theme.RESET}")
        else:
            print(f"Gap Assessment:         {theme.ERROR}❌ Significant gaps detected{theme.RESET}")

    # Show detailed breakdown for largest address if available
    if enhanced_eth_data:
        largest_address = max(enhanced_eth_data.items(), key=lambda x: x[1]["balance"])
        largest_addr, largest_data = largest_address

        print(f"\n{theme.PRIMARY}🏆 LARGEST ADDRESS BREAKDOWN{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 30}{theme.RESET}")
        print(f"Address:     {theme.ACCENT}{largest_addr[:8]}...{largest_addr[-6:]}{theme.RESET}")
        print(
            f"Balance:     {theme.PRIMARY}{format_currency(largest_data['balance'])}{theme.RESET}"
        )
        print(f"Tokens:      {theme.ACCENT}{largest_data['tokens']}{theme.RESET}")
        print(f"Protocols:   {theme.ACCENT}{largest_data['protocols']}{theme.RESET}")
        print(
            f"Val. Gap:    {theme.WARNING}{format_currency(largest_data['validation_gap'])}{theme.RESET}"
        )
        print(
            f"Status:      {theme.SUCCESS if largest_data['status'] == 'passed' else theme.WARNING}{largest_data['status'].title()}{theme.RESET}"
        )

    # Key insights
    print(f"\n{theme.PRIMARY}💡 KEY INSIGHTS{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 13}{theme.RESET}")

    if method_difference_total > 100:
        print(
            f"  {theme.SUCCESS}• Enhanced method captures {format_currency(method_difference_total)} more value{theme.RESET}"
        )
    elif method_difference_total < -100:
        print(
            f"  {theme.WARNING}• Standard method shows {format_currency(abs(method_difference_total))} more value{theme.RESET}"
        )
    else:
        print(f"  {theme.SUCCESS}• Both methods show similar total values{theme.RESET}")

    if total_validation_gaps > 1000:
        print(
            f"  {theme.WARNING}• Large validation gaps suggest complex DeFi positions{theme.RESET}"
        )
    elif total_validation_gaps < 50:
        print(f"  {theme.SUCCESS}• Low validation gaps indicate accurate extraction{theme.RESET}")

    if failed_addresses > 0:
        print(
            f"  {theme.ERROR}• {failed_addresses} addresses failed enhanced analysis{theme.RESET}"
        )

    input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
