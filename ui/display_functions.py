# -*- coding: utf-8 -*-
"""
Display Functions Module
------------------------
Contains all display/UI functions for the portfolio tracker.
"""

from typing import Dict, Any, List, Optional, Tuple
from copy import deepcopy
from colorama import Fore, Style
from tabulate import tabulate
from utils.helpers import (
    format_currency,
    print_header,
    print_error,
    get_menu_choice,
    safe_float_convert,
)
from utils.display_theme import theme
from utils.enhanced_price_service import enhanced_price_service
from models.custom_coins import CustomCoinTracker
from datetime import datetime
from config.constants import SUPPORTED_CHAINS, SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY
import os
from pathlib import Path
import json
from collections import defaultdict


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

    # Prepare aggregation of account-type breakdown (if available) so holdings reflect total amounts
    aggregated_holdings: Dict[str, Dict[str, float]] = {}

    def _merge_asset_row(row: Dict[str, Any], *, is_account_summary: bool = False) -> None:
        if not isinstance(row, dict):
            return
        coin = (row.get("coin") or row.get("asset") or row.get("symbol") or "").upper()
        if not coin:
            return

        balance_val = safe_float_convert(
            row.get("balance")
            or row.get("equity")
            or row.get("total")
            or row.get("amount")
            or row.get("value")
            or 0
        )
        available_val = safe_float_convert(
            row.get("available") or row.get("free") or row.get("cashBalance") or 0
        )
        usd_val = safe_float_convert(
            row.get("usd_value")
            or row.get("usdValue")
            or row.get("valueUsd")
            or row.get("notionalUsd")
            or balance_val
        )

        entry = aggregated_holdings.setdefault(
            coin, {"balance": 0.0, "available": 0.0, "usd_value": 0.0}
        )
        entry["balance"] += balance_val
        if is_account_summary:
            # Account summaries (e.g., funding balances) typically already represent available amounts
            entry["available"] += balance_val if available_val == 0 else available_val
        else:
            entry["available"] += available_val
        entry["usd_value"] += usd_val

    # Merge aggregated holdings derived from detailed assets
    assets = detailed_data.get("assets", [])
    for asset in assets:
        _merge_asset_row(asset)

    # Merge funding or supplemental holdings if provided
    supplemental_assets = detailed_data.get("supplemental_assets") or detailed_data.get(
        "funding_assets"
    )
    if isinstance(supplemental_assets, list):
        for asset in supplemental_assets:
            _merge_asset_row(asset, is_account_summary=True)

    # If we have aggregated data but original assets list is empty, synthesize from aggregation
    if not assets and aggregated_holdings:
        synthesized_assets = []
        for coin, values in aggregated_holdings.items():
            synthesized_assets.append(
                {
                    "coin": coin,
                    "balance": values["balance"],
                    "usd_value": values["usd_value"],
                    "available": values["available"],
                }
            )
        assets = synthesized_assets

    # If aggregated holdings exist but don't match the reported total equity, distribute the delta
    if aggregated_holdings:
        holdings_total_usd = sum(values["usd_value"] for values in aggregated_holdings.values())
        equity_diff = safe_float_convert(total_equity) - holdings_total_usd
        if abs(equity_diff) > 0.01:
            stable_candidates = {"USDT", "USDC", "USD", "FDUSD", "TUSD", "USDP", "DAI"}
            target_symbol = None
            for symbol in aggregated_holdings.keys():
                if symbol.upper() in stable_candidates:
                    target_symbol = symbol
                    break
            if target_symbol is None and aggregated_holdings:
                target_symbol = next(iter(aggregated_holdings))
            if target_symbol:
                target_entry = aggregated_holdings[target_symbol]
                balance = safe_float_convert(target_entry.get("balance"))
                usd_value = safe_float_convert(target_entry.get("usd_value"))
                price = (usd_value / balance) if balance not in (0.0, 0) else 1.0
                if price == 0:
                    price = 1.0
                balance_adjustment = equity_diff / price
                target_entry["usd_value"] += equity_diff
                target_entry["balance"] += balance_adjustment
                target_entry["available"] += balance_adjustment

    # If we merged values, rebuild the asset list sorted by USD value
    if aggregated_holdings:
        merged_assets = []
        for coin, values in aggregated_holdings.items():
            merged_assets.append(
                {
                    "coin": coin,
                    "balance": values["balance"],
                    "usd_value": values["usd_value"],
                    "available": values["available"],
                }
            )
        assets = sorted(merged_assets, key=lambda x: x.get("usd_value", 0.0), reverse=True)[:10]

    assets = assets[:10]

    if assets:
        print("\nHoldings")
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
            for asset in assets:
                coin = asset.get("coin", "N/A")
                balance_val = safe_float_convert(asset.get("balance", asset.get("equity", 0) or 0))
                usd_value = safe_float_convert(asset.get("usd_value", balance_val))
                clean_equity = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append([coin, format_balance(balance_val), clean_equity])

        elif exchange_name.lower() == "binance":
            for asset in assets:
                coin = asset.get("coin", "N/A")
                total_val = safe_float_convert(
                    asset.get(
                        "balance",
                        asset.get("total", asset.get("walletBalance", asset.get("equity", 0))),
                    )
                )
                usd_value = safe_float_convert(
                    asset.get("usd_value", asset.get("usdValue", asset.get("equity", total_val)))
                )
                clean_usd = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append(
                    [
                        coin,
                        format_balance(total_val),
                        clean_usd,
                    ]
                )

        elif exchange_name.lower() == "bybit":
            for asset in assets:
                coin = asset.get("coin", "N/A")
                total_val = safe_float_convert(
                    asset.get(
                        "balance",
                        asset.get("total", asset.get("equity", asset.get("walletBalance", 0))),
                    )
                )
                usd_value = safe_float_convert(
                    asset.get("usd_value", asset.get("usdValue", asset.get("equity", 0)))
                )
                clean_usd = f"${usd_value:,.0f}" if usd_value >= 1 else f"${usd_value:.3f}"

                table_data.append([coin, format_balance(total_val), clean_usd])

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


def display_binance_futures_positions(positions_data: Optional[Dict[str, Any]]):
    """Display Binance futures positions with P&L information."""
    if not isinstance(positions_data, dict):
        return

    sections = [
        ("USD-M Futures", positions_data.get("usd_m")),
        ("Coin-M Futures", positions_data.get("coin_m")),
    ]

    timestamp_ms = positions_data.get("timestamp")
    timestamp_info = ""
    if isinstance(timestamp_ms, (int, float)) and timestamp_ms > 0:
        try:
            from datetime import datetime

            ts_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            timestamp_info = f"{theme.SUBTLE}Snapshot: {ts_str}{theme.RESET}"
        except Exception:
            timestamp_info = ""

    for section_title, raw_positions in sections:
        if not isinstance(raw_positions, list) or not raw_positions:
            continue

        print(f"\n{theme.PRIMARY}Binance {section_title} Positions{theme.RESET}")
        if timestamp_info:
            print(timestamp_info)
        print(f"{theme.SUBTLE}{'-' * 40}{theme.RESET}")

        table_rows = []
        for position in raw_positions:
            if not isinstance(position, dict):
                continue
            symbol = (position.get("symbol") or "UNKNOWN").upper()
            raw_size = safe_float_convert(position.get("size", 0))
            direction = "Long" if raw_size >= 0 else "Short"
            size_abs = abs(raw_size)
            if size_abs < 1e-9:
                continue
            if size_abs >= 1:
                size_display = f"{size_abs:,.4f}".rstrip("0").rstrip(".")
            elif size_abs > 0:
                size_display = f"{size_abs:.8f}".rstrip("0").rstrip(".")
            else:
                size_display = "0"

            entry_price = safe_float_convert(position.get("entry_price", 0))
            mark_price = safe_float_convert(position.get("mark_price", 0))
            liquidation_price = safe_float_convert(position.get("liquidation_price", 0))
            margin_used = safe_float_convert(
                position.get("margin") or position.get("initial_margin") or 0
            )
            unrealized_pnl = safe_float_convert(position.get("unrealized_pnl", 0))
            pnl_color = theme.SUCCESS if unrealized_pnl >= 0 else theme.ERROR

            table_rows.append(
                [
                    symbol,
                    direction,
                    size_display,
                    f"${entry_price:,.2f}" if entry_price else "—",
                    f"${mark_price:,.2f}" if mark_price else "—",
                    f"${liquidation_price:,.2f}" if liquidation_price else "—",
                    format_currency(margin_used) if margin_used else "$0.00",
                    f"{pnl_color}{format_currency(unrealized_pnl)}{theme.RESET}",
                ]
            )

        if table_rows:
            headers = ["Symbol", "Side", "Size", "Entry", "Mark", "Liq.", "Margin", "P&L"]
            print(
                tabulate(
                    table_rows,
                    headers=headers,
                    tablefmt="simple",
                    stralign="left",
                    numalign="right",
                )
            )
        else:
            print(f"{theme.SUBTLE}No open positions{theme.RESET}")


def _display_generic_futures_positions(title: str, positions_data: Any):
    """Helper to render futures/perp positions for exchanges other than Binance."""
    if positions_data is None:
        return

    if isinstance(positions_data, dict):
        positions = positions_data.get("positions", [])
        timestamp_ms = positions_data.get("timestamp")
    elif isinstance(positions_data, list):
        positions = positions_data
        timestamp_ms = None
    else:
        return

    if not positions:
        return

    timestamp_info = ""
    if isinstance(timestamp_ms, (int, float)) and timestamp_ms > 0:
        try:
            ts_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            timestamp_info = f"{theme.SUBTLE}Snapshot: {ts_str}{theme.RESET}"
        except Exception:
            timestamp_info = ""

    print(f"\n{theme.PRIMARY}{title}{theme.RESET}")
    if timestamp_info:
        print(timestamp_info)
    print(f"{theme.SUBTLE}{'-' * 40}{theme.RESET}")

    table_rows = []
    for position in positions:
        if not isinstance(position, dict):
            continue

        symbol = (position.get("symbol") or "UNKNOWN").upper()
        raw_size = safe_float_convert(position.get("size") or 0)
        if raw_size == 0:
            continue

        direction = "Long" if raw_size >= 0 else "Short"
        abs_size = abs(raw_size)
        if abs_size >= 1:
            size_display = f"{abs_size:,.4f}".rstrip("0").rstrip(".")
        else:
            size_display = f"{abs_size:.8f}".rstrip("0").rstrip(".")

        entry_price = safe_float_convert(position.get("entry_price") or 0)
        mark_price = safe_float_convert(position.get("mark_price") or 0)
        liquidation_price = safe_float_convert(position.get("liquidation_price") or 0)
        notional_value = safe_float_convert(position.get("position_value") or 0)
        margin_used = safe_float_convert(
            position.get("margin") or position.get("initial_margin") or 0
        )
        unrealized = safe_float_convert(position.get("unrealized_pnl") or 0)
        pnl_color = theme.SUCCESS if unrealized >= 0 else theme.ERROR

        table_rows.append(
            [
                symbol,
                direction,
                size_display,
                f"${entry_price:,.2f}" if entry_price else "—",
                f"${mark_price:,.2f}" if mark_price else "—",
                f"${liquidation_price:,.2f}" if liquidation_price else "—",
                format_currency(notional_value) if notional_value else "—",
                format_currency(margin_used) if margin_used else "—",
                f"{pnl_color}{format_currency(unrealized)}{theme.RESET}",
            ]
        )

    if table_rows:
        headers = [
            "Instrument",
            "Side",
            "Size",
            "Entry",
            "Mark",
            "Liq.",
            "Notional",
            "Margin",
            "P&L",
        ]
        print(
            tabulate(
                table_rows,
                headers=headers,
                tablefmt="simple",
                stralign="left",
                numalign="right",
            )
        )
    else:
        print(f"{theme.SUBTLE}No open positions{theme.RESET}")


def display_okx_futures_positions(positions_data: Optional[Dict[str, Any]]):
    _display_generic_futures_positions("OKX Futures Positions", positions_data)


def display_bybit_futures_positions(positions_data: Optional[Dict[str, Any]]):
    _display_generic_futures_positions("Bybit Futures Positions", positions_data)


def _compute_margin_breakdown(
    exposure_data: Dict[str, Any],
) -> Tuple[float, List[Dict[str, Any]], float, float]:
    """Return (non_margin_non_stable, margin_breakdown, total_margin_exposure, total_unrealized_pnl)."""
    non_margin_non_stable = 0.0
    margin_position_details: List[Dict[str, Any]] = []
    margin_symbol_net_qty: Dict[str, float] = {}
    margin_symbol_size_weight: Dict[str, float] = {}
    margin_symbol_price_weight: Dict[str, float] = {}
    margin_symbol_pnl_totals: Dict[str, float] = {}

    consolidated_assets = exposure_data.get("consolidated_assets") or {}
    crypto_prices_snapshot = exposure_data.get("crypto_prices_snapshot", {})
    crypto_prices_live = exposure_data.get("crypto_prices", {})

    included_platform_tokens = ("binance", "bybit")

    for asset_symbol, asset_info in consolidated_assets.items():
        metadata = (asset_info.get("metadata") or {}) if isinstance(asset_info, dict) else {}
        asset_is_stable = asset_info.get("is_stable") if isinstance(asset_info, dict) else None
        is_margin_asset = metadata.get("is_margin_position") or metadata.get("is_margin_reserve")
        value_usd = safe_float_convert(
            asset_info.get("total_value_usd", 0) if isinstance(asset_info, dict) else 0
        )

        if not asset_is_stable and not is_margin_asset:
            non_margin_non_stable += value_usd

        if is_margin_asset:
            for detail in metadata.get("margin_underlying_details", []) or []:
                if not isinstance(detail, dict):
                    continue
                detail_entry = detail.copy()
                detail_entry["platform"] = detail_entry.get("platform") or metadata.get(
                    "source_platform"
                )
                platform_label = str(detail_entry["platform"]).lower()
                detail_entry["_include_pnl"] = any(
                    token in platform_label for token in included_platform_tokens
                )
                margin_position_details.append(detail_entry)
                symbol_key = (detail_entry.get("symbol") or "UNKNOWN").upper()
                pnl_val = safe_float_convert(detail_entry.get("unrealized_pnl", 0))
                margin_symbol_pnl_totals[symbol_key] = (
                    margin_symbol_pnl_totals.get(symbol_key, 0.0) + pnl_val
                )

                size = safe_float_convert(
                    detail_entry.get("size", detail_entry.get("position", 0)), 0.0
                )
                if size == 0:
                    abs_size = safe_float_convert(detail_entry.get("abs_size", 0.0), 0.0)
                    direction_sign = detail_entry.get("direction_sign")
                    if direction_sign in (None, 0):
                        direction = (detail_entry.get("direction") or "").lower()
                        if "short" in direction:
                            direction_sign = -1
                        elif "long" in direction:
                            direction_sign = 1
                        else:
                            direction_sign = 1
                    size = abs_size * (direction_sign if direction_sign not in (None, 0) else 1)

                abs_size = abs(size)
                price = safe_float_convert(
                    detail_entry.get("mark_price")
                    or detail_entry.get("entry_price")
                    or detail_entry.get("market_price")
                    or detail_entry.get("price"),
                    0.0,
                )
                if price <= 0 and abs_size > 0:
                    notional_guess = safe_float_convert(detail_entry.get("notional_value", 0.0))
                    if abs(notional_guess) > 0:
                        price = abs(notional_guess) / abs_size
                if price <= 0:
                    price = safe_float_convert(crypto_prices_snapshot.get(symbol_key, 0), 0.0)
                if price <= 0:
                    price = safe_float_convert(crypto_prices_live.get(symbol_key, 0), 0.0)

                margin_symbol_net_qty[symbol_key] = (
                    margin_symbol_net_qty.get(symbol_key, 0.0) + size
                )
                if abs_size > 0 and price > 0:
                    margin_symbol_price_weight[symbol_key] = (
                        margin_symbol_price_weight.get(symbol_key, 0.0) + price * abs_size
                    )
                    margin_symbol_size_weight[symbol_key] = (
                        margin_symbol_size_weight.get(symbol_key, 0.0) + abs_size
                    )

    margin_breakdown: List[Dict[str, Any]] = []
    total_margin_exposure = 0.0
    total_margin_unrealized_pnl = 0.0

    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for detail in margin_position_details:
        platform = detail.get("platform") or "Perp DEX"
        symbol = (detail.get("symbol") or "UNKNOWN").upper()
        key = (platform, symbol)
        group = grouped.setdefault(
            key,
            {
                "platform": platform,
                "symbol": symbol,
                "net_qty": 0.0,
                "abs_qty": 0.0,
                "price_weight": 0.0,
                "size_weight": 0.0,
                "margin": 0.0,
                "notional": 0.0,
                "pnl": 0.0,
            },
        )

        size = safe_float_convert(detail.get("size", detail.get("position", 0)), 0.0)
        if size == 0:
            abs_size = safe_float_convert(detail.get("abs_size", 0.0), 0.0)
            direction_sign = detail.get("direction_sign")
            if direction_sign in (None, 0):
                direction = (detail.get("direction") or "").lower()
                if "short" in direction:
                    direction_sign = -1
                elif "long" in direction:
                    direction_sign = 1
                else:
                    direction_sign = 1
            size = abs_size * (direction_sign if direction_sign not in (None, 0) else 1)
        abs_size = abs(size)

        price = safe_float_convert(
            detail.get("mark_price")
            or detail.get("entry_price")
            or detail.get("market_price")
            or detail.get("price"),
            0.0,
        )
        if price <= 0 and abs_size > 0:
            notional_guess = safe_float_convert(detail.get("notional_value", 0.0))
            if abs(notional_guess) > 0:
                price = abs(notional_guess) / abs_size
        if price <= 0:
            price = safe_float_convert(crypto_prices_snapshot.get(symbol, 0), 0.0)
        if price <= 0:
            price = safe_float_convert(crypto_prices_live.get(symbol, 0), 0.0)

        margin_value = safe_float_convert(
            detail.get("margin_value") or detail.get("margin") or detail.get("margin_used"),
            0.0,
        )
        if margin_value <= 0:
            notional_guess = safe_float_convert(detail.get("notional_value", 0.0))
            leverage_guess = safe_float_convert(detail.get("leverage", 0.0))
            if notional_guess > 0 and leverage_guess > 0:
                margin_value = notional_guess / leverage_guess
            elif notional_guess > 0:
                margin_value = notional_guess
        margin_value = max(margin_value, 0.0)

        notional_value = safe_float_convert(detail.get("notional_value", 0.0))
        if notional_value <= 0 and abs_size > 0 and price > 0:
            notional_value = abs_size * price

        group["net_qty"] += size
        group["abs_qty"] += abs_size
        group["margin"] += margin_value
        group["notional"] += max(notional_value, 0.0)
        if detail.get("_include_pnl"):
            group["pnl"] += safe_float_convert(detail.get("unrealized_pnl", 0.0))

        if abs_size > 0 and price > 0:
            group["price_weight"] += price * abs_size
            group["size_weight"] += abs_size
            group.setdefault("_details", []).append(detail)

    consolidated_groups: Dict[str, Dict[str, Any]] = {}
    for group in grouped.values():
        consolidated = consolidated_groups.setdefault(
            group["symbol"],
            {
                "symbol": group["symbol"],
                "net_qty": 0.0,
                "abs_qty": 0.0,
                "price_weight": 0.0,
                "size_weight": 0.0,
                "margin": 0.0,
                "notional": 0.0,
                "pnl": 0.0,
                "platforms": [],
                "_details": [],
            },
        )
        consolidated["net_qty"] += group["net_qty"]
        consolidated["abs_qty"] += group["abs_qty"]
        consolidated["price_weight"] += group["price_weight"]
        consolidated["size_weight"] += group["size_weight"]
        consolidated["margin"] += group["margin"]
        consolidated["notional"] += group["notional"]
        consolidated["pnl"] += group["pnl"]
        if abs(group["net_qty"]) > 1e-6 or abs(group["pnl"]) > 1e-6:
            consolidated["platforms"].append(group["platform"])
        consolidated["_details"].extend(group.get("_details", []))

    for consolidated in consolidated_groups.values():
        net_qty = consolidated["net_qty"]
        if abs(net_qty) <= 1e-6:
            continue

        size_weight = consolidated["size_weight"]
        avg_price = consolidated["price_weight"] / size_weight if size_weight > 0 else 0.0
        exposure_value = (
            consolidated["notional"] if consolidated["notional"] > 0 else consolidated["margin"]
        )
        total_margin_exposure += exposure_value
        total_margin_unrealized_pnl += consolidated["pnl"]

        margin_breakdown.append(
            {
                "symbol": consolidated["symbol"],
                "net_qty": net_qty,
                "abs_qty": consolidated["abs_qty"],
                "avg_price": avg_price,
                "margin": consolidated["margin"],
                "notional": consolidated["notional"],
                "exposure": exposure_value,
                "pnl": consolidated["pnl"],
                "platforms": consolidated["platforms"],
                "details": consolidated["_details"],
            }
        )

    return (
        non_margin_non_stable,
        margin_breakdown,
        total_margin_exposure,
        total_margin_unrealized_pnl,
    )


def display_comprehensive_overview(metrics: Dict[str, Any], source_info: str = "Live Data"):
    """Enhanced portfolio overview with improved visual design."""
    print_header(f"Portfolio Overview • {source_info}")

    total_value = metrics.get("total_portfolio_value", 0.0)
    exposure_data = metrics.get("exposure_analysis") or {}
    total_value_with_pnl = metrics.get("total_portfolio_value_with_pnl")
    total_unrealized_pnl = metrics.get("total_unrealized_pnl")
    adjusted_value = metrics.get("adjusted_portfolio_value", 0.0)
    adjusted_value_with_pnl = metrics.get("adjusted_portfolio_value_with_pnl")
    offset = metrics.get("balance_offset", 0.0)
    crypto_prices = metrics.get("crypto_prices", {})
    timestamp_str = metrics.get("timestamp", "N/A")
    failed_sources = metrics.get("failed_sources", [])

    try:
        dt_obj = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        display_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        display_ts = timestamp_str

    # Remove the timestamp display line as requested by user

    if crypto_prices:
        print(f"\n{theme.SUBTLE}📊 Market data captured at time of analysis{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 60}{theme.RESET}")
    else:
        print(f"\n{theme.SUBTLE}{'─' * 60}{theme.RESET}")

    # Failure Summary with better visibility
    if failed_sources:
        print(
            f"\n{theme.WARNING}⚠  Data Issues: {', '.join(failed_sources)} (totals may be incomplete){theme.RESET}"
        )
        print(f"{theme.SUBTLE}{'─' * 60}{theme.RESET}")

    # Enhanced Portfolio Values Section
    print(f"\n{theme.PRIMARY}💰 PORTFOLIO VALUE{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")

    recomputed_pnl = total_unrealized_pnl
    if exposure_data:
        try:
            _, margin_breakdown, _, margin_total_pnl = _compute_margin_breakdown(exposure_data)
            recomputed_pnl = margin_total_pnl
        except Exception:
            pass
    if recomputed_pnl is None:
        recomputed_pnl = 0.0
    if exposure_data:
        total_value_with_pnl = total_value + recomputed_pnl
        adjusted_value_with_pnl = adjusted_value + recomputed_pnl

    # ------------------------------------------------------------------
    # Detailed portfolio value output.
    print(f"Total Value (spot):      {theme.ACCENT}{format_currency(total_value)}{theme.RESET}")
    if total_value_with_pnl is not None:
        print(
            f"Total Value (with PnL):  {theme.ACCENT}{format_currency(total_value_with_pnl)}{theme.RESET}"
        )
        if abs(recomputed_pnl) > 1e-6:
            pnl_color = theme.SUCCESS if recomputed_pnl >= 0 else theme.ERROR
            print(f"  └─ Unrealized PnL: {pnl_color}{format_currency(recomputed_pnl)}{theme.RESET}")

    if offset > 0:
        print(f"Applied Offset:          {theme.WARNING}-{format_currency(offset)}{theme.RESET}")
        print(f"Net Portfolio (spot):    {theme.SUCCESS}{format_currency(adjusted_value)}{theme.RESET}")
        if adjusted_value_with_pnl is not None:
            print(
                f"Net Portfolio (with PnL): {theme.SUCCESS}{format_currency(adjusted_value_with_pnl)}{theme.RESET}"
            )
    else:
        print(f"Applied Offset:          {theme.SUBTLE}{format_currency(offset)}{theme.RESET}")
        print(f"Net Portfolio (spot):    {theme.SUCCESS}{format_currency(adjusted_value)}{theme.RESET}")
        if adjusted_value_with_pnl is not None:
            print(
                f"Net Portfolio (with PnL): {theme.SUCCESS}{format_currency(adjusted_value_with_pnl)}{theme.RESET}"
            )
    # ------------------------------------------------------------------

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
        "Solana",
        "Hyperliquid",
        "Lighter",
        "Polymarket",
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
            elif source in ["Ethereum", "Bitcoin", "Solana"]:
                platform_color = theme.SUCCESS
            else:  # Derivatives platforms
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

    # Get custom coin data for integration
    custom_coin_data_from_metrics = metrics.get("custom_coin_data", {})  # Renamed to avoid conflict
    custom_coin_prices = metrics.get("custom_coin_prices", {})

    # Ensure custom_coins_data is a dictionary
    custom_coins_list = custom_coin_data_from_metrics.get("custom_coins_data", {})
    if not isinstance(custom_coins_list, dict):
        custom_coins_list = {}

    # Display market prices with more prominence and all supported currencies
    price_available = any(
        [btc_price and btc_price > 0, eth_price and eth_price > 0, sol_price and sol_price > 0]
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
        "Solana",
        "Hyperliquid",
        "Lighter",
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
        elif label in ["Ethereum", "Bitcoin", "Solana"]:
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
    wallet_platform_data_raw = portfolio_metrics.get("wallet_platform_data_raw", [])

    if not wallet_platform_data_raw:
        print(f"{theme.SUBTLE}No wallet data available. Check your configuration.{theme.RESET}")
        return

    # Keep only chain-specific wallet entries for the main table
    wallet_platform_data = [entry for entry in wallet_platform_data_raw if entry.get("chain")]

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

    def _wallet_balance(info: Dict[str, Any]) -> float:
        if info.get("chain") == "solana":
            return safe_float_convert(info.get("total_balance_usd", 0.0))
        return safe_float_convert(info.get("total_balance", 0.0))

    wallet_platform_data_sorted = sorted(wallet_platform_data, key=_wallet_balance, reverse=True)

    for info in wallet_platform_data_sorted:
        chain = info.get("chain", "unknown")
        address = info.get("address", "N/A")

        # Enhanced address formatting for different chains
        address_short = address
        if len(address) > 20:
            if chain in ["ethereum", "solana"]:
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
            eth_info = info.copy()
            eth_info["total_balance"] = balance_usd
            ethereum_wallets.append(eth_info)
        elif chain == "bitcoin":
            btc_bal = info.get("balance_btc", 0)
            native_balance_str = f"{theme.WARNING}{btc_bal:.6f} BTC{theme.RESET}"
            tx_count = info.get("transaction_count", "?")
            details_str = f"Transactions: {theme.ACCENT}{tx_count}{theme.RESET}"
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
    quick_mode = False
    try:
        quick_mode = portfolio_metrics.get("quick_mode", False)
    except Exception:
        quick_mode = False

    if ethereum_wallets and not quick_mode:
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
    from utils.helpers import format_currency, safe_float_convert
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

            # Check if combined analysis is available
            analysis_folder = portfolio_metrics.get("_analysis_folder")
            combined_available = False
            if analysis_folder:
                try:
                    from combined_wallet_integration import check_combined_wallet_availability

                    combined_available = check_combined_wallet_availability(analysis_folder)
                except Exception:
                    combined_available = False

            # Add combined portfolio option if available
            if combined_available:
                print(
                    f"  {theme.ACCENT}{len(ethereum_wallets)+1}.{theme.RESET} 🎯 {theme.PRIMARY}Combined Portfolio View{theme.RESET} {theme.SUBTLE}• All wallets aggregated{theme.RESET}"
                )

            print(f"  {theme.ACCENT}0.{theme.RESET} Return to wallet balances")

            max_choice = len(ethereum_wallets) + (1 if combined_available else 0)

            try:
                choice = input(
                    f"\n{theme.PRIMARY}Enter your choice (0-{max_choice}): {theme.RESET}"
                ).strip()

                if choice == "0":
                    break

                # Check if it's the combined portfolio option
                if combined_available and choice == str(len(ethereum_wallets) + 1):
                    try:
                        from combined_wallet_integration import (
                            get_combined_wallet_file_path,
                            display_combined_wallet_analysis,
                        )

                        if analysis_folder:  # Type check to ensure it's not None
                            combined_file = get_combined_wallet_file_path(analysis_folder)
                            if combined_file:
                                display_combined_wallet_analysis(combined_file, portfolio_metrics)
                            else:
                                print(
                                    f"\n{theme.ERROR}❌ Failed to load combined portfolio data{theme.RESET}"
                                )
                                input(f"{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                        else:
                            print(f"\n{theme.ERROR}❌ No analysis folder available{theme.RESET}")
                            input(f"{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                    except Exception as e:
                        print(
                            f"\n{theme.ERROR}❌ Error loading combined portfolio: {str(e)}{theme.RESET}"
                        )
                        input(f"{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                    continue

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
                        f"\n{theme.ERROR}❌ Invalid choice. Please select 0-{max_choice}{theme.RESET}"
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


def _display_wallet_summary_stats(
    tokens: List[Dict[str, Any]],
    protocols: List[Dict[str, Any]],
    show_detailed_breakdown: bool = True,
    show_summary: bool = True,
    show_stable_breakdown: bool = True,
):
    """Helper function to display summary statistics for a wallet."""
    from utils.display_theme import theme
    from utils.helpers import format_currency

    # Initialize variable to prevent UnboundLocalError
    has_negative_protocols = False

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

    # Additional stablecoin detection patterns
    stablecoin_patterns = ["USD"]

    # Track individual stablecoins for detailed breakdown, organized by chain
    stablecoin_breakdown = {}
    # Track chains for stablecoins
    stablecoin_chains = {}

    # Track non-stable tokens for detailed breakdown
    nonstable_breakdown = {}
    nonstable_chains = {}
    nonstable_amounts = {}  # Track token amounts
    nonstable_amounts_by_chain = {}  # Track token amounts per chain

    def _is_mixed_symbol(symbol: str) -> bool:
        clean = (symbol or "").replace(" ", "").upper()
        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            if parts and all(
                part in stablecoin_bases or any(pattern in part for pattern in stablecoin_patterns)
                for part in parts
            ):
                return False
        return any(sep in clean for sep in ["/", "+", "-"])

    for token in tokens:
        symbol = token.get("symbol", "").upper()
        category = token.get("category", "other_crypto")
        value = token.get("usd_value", 0)
        chain = token.get("chain", "unknown").capitalize()

        # Check if the token is a stablecoin based on its symbol prefix or category
        is_stable = False
        if not _is_mixed_symbol(symbol):
            # Method 1: Check if token starts with known stablecoin bases
            for base in stablecoin_bases:
                if symbol.startswith(base):
                    is_stable = True
                    break

            # Method 2: Check if token has "USD" anywhere in the name
            if not is_stable:
                for pattern in stablecoin_patterns:
                    if pattern in symbol:
                        is_stable = True
                        break

        # Method 3: Check if token category is explicitly marked as stable
        if not is_stable and category == "stable":
            is_stable = True

        if is_stable:
            # Add to stablecoin breakdown with chain info
            chain_key = f"{symbol}_{chain}"
            if chain_key in stablecoin_breakdown:
                stablecoin_breakdown[chain_key] += value
            else:
                stablecoin_breakdown[chain_key] = value
                stablecoin_chains[chain_key] = chain

            # Add to category totals
            category_totals["stable"] += value
        elif category in category_totals and category != "other_crypto":
            # Handle specific non-stable categories
            chain_key = f"{symbol}_{chain}"
            if chain_key in nonstable_breakdown:
                nonstable_breakdown[chain_key] += value
            else:
                nonstable_breakdown[chain_key] = value
                nonstable_chains[chain_key] = chain

            # Track token amounts for the symbol, breakdown and totals handled above
            if symbol in nonstable_amounts:
                nonstable_amounts[symbol] += token.get("amount", 0)
            else:
                nonstable_amounts[symbol] = token.get("amount", 0)

            # Track token amount per chain for detailed breakdown of eth_exposure and similar categories
            nonstable_amounts_by_chain[chain_key] = nonstable_amounts_by_chain.get(
                chain_key, 0
            ) + token.get("amount", 0)

            # Add to category totals for this specific category (e.g. eth_exposure, eth_staking, lp_token)
            category_totals[category] += value
        else:
            # Add to non-stable token breakdown
            chain_key = f"{symbol}_{chain}"
            if chain_key in nonstable_breakdown:
                nonstable_breakdown[chain_key] += value
            else:
                nonstable_breakdown[chain_key] = value
                nonstable_chains[chain_key] = chain

            # Track token amounts for the symbol
            if symbol in nonstable_amounts:
                nonstable_amounts[symbol] += token.get("amount", 0)
            else:
                nonstable_amounts[symbol] = token.get("amount", 0)

            # Track token amounts per chain
            nonstable_amounts_by_chain[chain_key] = nonstable_amounts_by_chain.get(
                chain_key, 0
            ) + token.get("amount", 0)

            category_totals["other_crypto"] += value

    # Track for summary: eth_total and other_total as computed from tokens
    eth_total_for_summary = sum(
        v for k, v in nonstable_breakdown.items() if k.startswith("ETH_") and v >= 0.1
    )
    # Calculate non-stable total (all categories except stables)
    non_stable_total_direct = sum(category_totals.values()) - category_totals["stable"]
    other_total_for_summary = max(non_stable_total_direct - eth_total_for_summary, 0)

    # If nothing found (edge-case), fall back to None so later logic can overwrite
    if eth_total_for_summary == 0:
        eth_total_for_summary = None
    if other_total_for_summary == 0 and non_stable_total_direct == 0:
        other_total_for_summary = None

    # Display detailed stablecoin breakdown if any stablecoins exist
    if show_detailed_breakdown and show_stable_breakdown and stablecoin_breakdown:
        print(f"\n{theme.INFO}Stablecoin Breakdown:{theme.RESET}")

        # Group by symbol first
        symbol_totals = {}
        dust_stables_total = 0.0

        for chain_key, value in stablecoin_breakdown.items():
            symbol = chain_key.split("_")[0]
            # Skip dust amounts in the symbol totals calculation
            if value < 0.1:
                dust_stables_total += value
                continue

            if symbol in symbol_totals:
                symbol_totals[symbol] += value
            else:
                symbol_totals[symbol] = value

        # Show symbol totals first (excluding dust)
        for symbol, value in sorted(symbol_totals.items(), key=lambda x: x[1], reverse=True):
            stable_percentage = (
                (value / category_totals["stable"] * 100) if category_totals["stable"] > 0 else 0
            )
            # Determine chains for this symbol
            chains_for_symbol = [
                ck
                for ck, cv in stablecoin_breakdown.items()
                if ck.startswith(f"{symbol}_") and cv >= 0.1
            ]
            if len(chains_for_symbol) == 1:
                # Single-chain: symbol with chain info in parentheses
                chain_key = chains_for_symbol[0]
                chain = stablecoin_chains[chain_key]
                chain_icon = {
                    "Ethereum": "⟠",
                    "Arbitrum": "🔵",
                    "Polygon": "🟣",
                    "Base": "🔷",
                    "Optimism": "🔴",
                    "Solana": "🌞",
                }.get(chain, "🔗")
                # Format: SYMBOL (ICON Chain): VALUE (PERCENT)
                print(
                    f"  {symbol} ({chain_icon} {chain}): {theme.SUCCESS}{format_currency(value)}{theme.RESET} ({stable_percentage:.1f}%)"
                )
            else:
                # Multi-chain: print summary and breakdown
                print(
                    f"  {symbol}: {theme.SUCCESS}{format_currency(value)}{theme.RESET} ({stable_percentage:.1f}%)"
                )
                for chain_key, chain_value in sorted(
                    stablecoin_breakdown.items(), key=lambda x: x[1], reverse=True
                ):
                    if chain_key.startswith(f"{symbol}_") and chain_value >= 0.1:
                        chain = stablecoin_chains[chain_key]
                        chain_percentage = (chain_value / value * 100) if value > 0 else 0
                        chain_icon = {
                            "Ethereum": "⟠",
                            "Arbitrum": "🔵",
                            "Polygon": "🟣",
                            "Base": "🔷",
                            "Optimism": "🔴",
                            "Solana": "🌞",
                        }.get(chain, "🔗")
                        print(
                            f"    {chain_icon} {chain}: {theme.SUBTLE}{format_currency(chain_value)}{theme.RESET} ({chain_percentage:.1f}%)"
                        )

        # Show dust stables total if any
        if dust_stables_total > 0:
            dust_percentage = (
                (dust_stables_total / category_totals["stable"] * 100)
                if category_totals["stable"] > 0
                else 0
            )
            print(
                f"  {theme.SUBTLE}Dust stables (<$0.1): {format_currency(dust_stables_total)} ({dust_percentage:.1f}%){theme.RESET}"
            )

        print(
            f"  {theme.ACCENT}Total Stables: {format_currency(category_totals['stable'])}{theme.RESET}"
        )

    # Display detailed non-stable token breakdown
    if show_detailed_breakdown and nonstable_breakdown:
        non_stable_total = sum(category_totals.values()) - category_totals["stable"]
        print(f"\n{theme.INFO}Non-Stable Token Breakdown:{theme.RESET}")

        # Group by symbol first
        symbol_totals = {}
        dust_tokens_total = 0.0

        for chain_key, value in nonstable_breakdown.items():
            symbol = chain_key.split("_")[0]
            # Skip dust amounts in the symbol totals calculation
            if value < 0.1:
                dust_tokens_total += value
                continue

            if symbol in symbol_totals:
                symbol_totals[symbol] += value
            else:
                symbol_totals[symbol] = value

        # Fix percentage calculation: Use positive-only base when there are negative values
        # This ensures positive token percentages add up to 100% instead of over 100%
        symbol_totals_positive = sum(value for value in symbol_totals.values() if value > 0)
        has_negative_values = any(value < 0 for value in symbol_totals.values())
        if has_negative_values:
            # When there are negative values, use only positive values + positive dust for percentage base
            percentage_base = symbol_totals_positive + max(0, dust_tokens_total)
        else:
            # When all values are positive, use the original calculation
            percentage_base = non_stable_total if non_stable_total > 0 else symbol_totals_positive

        # Show all non-stable tokens sorted by value
        for symbol, value in sorted(symbol_totals.items(), key=lambda x: (x[1] < 0, -abs(x[1]))):
            # Skip tokens under $5 and aggregate into dust
            if abs(value) < 5:  # Use absolute value for dust threshold
                dust_tokens_total += value
                continue

            # Check if token has negative total value
            is_negative_token = value < 0
            token_percentage = (
                (value / percentage_base * 100) if percentage_base and not is_negative_token else 0
            )
            amount = nonstable_amounts.get(symbol, 0)
            amount_str = (
                f"{amount:.6f}".rstrip("0").rstrip(".")
                if amount < 1
                else f"{amount:,.4f}".rstrip("0").rstrip(".")
            )
            # Determine token's chains
            chains_for_symbol = [
                ck
                for ck, cv in nonstable_breakdown.items()
                if ck.startswith(f"{symbol}_") and cv >= 0.1
            ]
            if len(chains_for_symbol) == 1:
                # Single-chain: symbol with chain info in parentheses
                chain_key = chains_for_symbol[0]
                chain = nonstable_chains[chain_key]
                chain_icon = {
                    "Ethereum": "⟠",
                    "Arbitrum": "🔵",
                    "Polygon": "🟣",
                    "Base": "🔷",
                    "Optimism": "🔴",
                    "Solana": "🌞",
                }.get(chain, "🔗")
                # Format: SYMBOL (ICON Chain): AMOUNT - VALUE (PERCENT)
                if is_negative_token:
                    print(
                        f"  {symbol} ({chain_icon} {chain}): {amount_str} - {format_currency(value)}"
                    )
                else:
                    print(
                        f"  {symbol} ({chain_icon} {chain}): {amount_str} - {theme.SUCCESS}{format_currency(value)}{theme.RESET} ({token_percentage:.1f}%)"
                    )
            else:
                # Multi-chain: print summary then each breakdown
                if is_negative_token:
                    print(f"  {symbol}: {amount_str} {symbol} - {format_currency(value)}")
                else:
                    print(
                        f"  {symbol}: {amount_str} {symbol} - {theme.SUCCESS}{format_currency(value)}{theme.RESET} ({token_percentage:.1f}%)"
                    )
                # Aggregate per-symbol chain dust (<$1)
                chain_dust_total = 0.0
                for chain_key in chains_for_symbol:
                    # Skip minor chains (<$1) and accumulate dust
                    if nonstable_breakdown[chain_key] < 1:
                        chain_dust_total += nonstable_breakdown[chain_key]
                        continue
                    chain = nonstable_chains[chain_key]
                    chain_value = nonstable_breakdown[chain_key]
                    chain_percentage = (
                        (chain_value / value * 100) if value > 0 and not is_negative_token else 0
                    )
                    chain_icon = {
                        "Ethereum": "⟠",
                        "Arbitrum": "🔵",
                        "Polygon": "🟣",
                        "Base": "🔷",
                        "Optimism": "🔴",
                        "Solana": "🌞",
                    }.get(chain, "🔗")
                    amount_chain = nonstable_amounts_by_chain.get(chain_key, 0)
                    amount_chain_str = (
                        f"{amount_chain:,.6f}".rstrip("0").rstrip(".")
                        if amount_chain < 1
                        else f"{amount_chain:,.4f}".rstrip("0").rstrip(".")
                    )
                    if is_negative_token:
                        print(
                            f"    {chain_icon} {chain}: {theme.ACCENT}{amount_chain_str} {symbol}{theme.RESET} - {format_currency(chain_value)}"
                        )
                    else:
                        print(
                            f"    {chain_icon} {chain}: {theme.ACCENT}{amount_chain_str} {symbol}{theme.RESET} - {theme.SUBTLE}{format_currency(chain_value)}{theme.RESET} ({chain_percentage:.1f}%)"
                        )
                # Print per-symbol chain dust if any
                if chain_dust_total > 0:
                    dust_pct = (
                        (chain_dust_total / value * 100)
                        if value > 0 and not is_negative_token
                        else 0
                    )
                    if is_negative_token:
                        print(
                            f"    {theme.SUBTLE}Other chains: {format_currency(chain_dust_total)}{theme.RESET}"
                        )
                    else:
                        print(
                            f"    {theme.SUBTLE}Other chains: {format_currency(chain_dust_total)} ({dust_pct:.1f}%){theme.RESET}"
                        )

        # Show dust tokens total if any
        if dust_tokens_total > 0:
            dust_percentage = (
                (dust_tokens_total / percentage_base * 100)
                if percentage_base and dust_tokens_total > 0
                else 0
            )
            print(
                f"  {theme.SUBTLE}Dust tokens (<$5): {format_currency(dust_tokens_total)} ({dust_percentage:.1f}%){theme.RESET}"
            )

        print(f"  {theme.ACCENT}Total Non-Stable: {format_currency(non_stable_total)}{theme.RESET}")
        # Add category-specific breakdown lines
        eth_total = symbol_totals.get("ETH", 0)
        print(f"  {theme.ACCENT}💎 ETH Exposure: {format_currency(eth_total)}{theme.RESET}")
        # Compute Other Crypto as total non-stable minus ETH exposure
        other_total = non_stable_total - eth_total
        print(f"  {theme.ACCENT}📈 Other Crypto: {format_currency(other_total)}{theme.RESET}")
        # --- Store for summary ---
        eth_total_for_summary = eth_total
        other_total_for_summary = other_total

    # SUMMARY STATISTICS (print after breakdown so we have the correct values)
    if show_summary:
        print(f"\n{theme.PRIMARY}📊 SUMMARY STATISTICS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 20}{theme.RESET}")
        # Prepare summary values with overrides
        summary_totals = category_totals.copy()
        if eth_total_for_summary is not None:
            summary_totals["eth_exposure"] = eth_total_for_summary
        if other_total_for_summary is not None:
            summary_totals["other_crypto"] = other_total_for_summary

        total_categorized = sum(summary_totals.values())
        if total_categorized > 0:
            for category, value in sorted(summary_totals.items(), key=lambda x: x[1], reverse=True):
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
    from collections import defaultdict

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
    wallet_breakdown_view = False  # New state for wallet breakdown view
    breakdown_mode = "token"  # or 'protocol'
    proto_index = 0  # for protocol navigation
    proto_show_all = False  # toggle between paginated and all protocols view
    proto_group_mode = False  # False = list by protocol, True = group by token type (stable / non)

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

        # --- Timestamp Analysis - Use portfolio_metrics timestamp for consistency ---
        # When viewing past analysis, we want to show the same timestamp as the overview
        # This ensures consistency between "Portfolio Overview • Saved 2025-06-10 12:11:41"
        # and "Analysis Time: 2025-06-10 12:11:41" in wallet details
        analysis_ts_str = portfolio_metrics.get("timestamp", wallet_data.get("timestamp", "N/A"))

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

        # Wallet breakdown views
        if wallet_breakdown_view:
            if breakdown_mode == "token":
                _display_wallet_summary_stats(tokens, protocols, show_summary=False)
                print(
                    f"\n{theme.PRIMARY}NAVIGATION:{theme.RESET} (p)rotocol breakdown | (b)ack | (q)uit"
                )
            else:  # protocol mode
                # Handle grouped-by-token view first
                if proto_group_mode:
                    # --- Group protocol positions by token and chain ---
                    stable_bases = {
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
                    stable_patterns = ["USD"]
                    chain_icons = {
                        "Ethereum": "⟠",
                        "Arbitrum": "🔵",
                        "Polygon": "🟣",
                        "Base": "🔷",
                        "Optimism": "🔴",
                        "Solana": "🌞",
                    }

                    def _normalize_symbol(symbol: str) -> str:
                        return (symbol or "").replace(" ", "").upper()

                    # Helper to detect if a single token is a stablecoin
                    def _is_base_stable(token: str) -> bool:
                        clean = _normalize_symbol(token)
                        if not clean:
                            return False
                        if clean in stable_bases:
                            return True
                        for pat in stable_patterns:
                            if pat in clean:
                                return True
                        return False

                    # Helper to detect stablecoins (supports composite symbols)
                    def is_stable(symbol: str) -> bool:
                        clean = _normalize_symbol(symbol)
                        if "+" in clean:
                            parts = [part for part in clean.split("+") if part]
                            return bool(parts) and all(_is_base_stable(part) for part in parts)
                        if "/" in clean or "-" in clean:
                            return False
                        return _is_base_stable(clean)

                    # Helper to detect if a pool is stable (all parts stable)
                    def is_pool_stable(symbol: str) -> bool:
                        clean = _normalize_symbol(symbol)
                        if "+" in clean:
                            parts = [part for part in clean.split("+") if part]
                            return bool(parts) and all(_is_base_stable(part) for part in parts)
                        if "/" in clean or "-" in clean:
                            return False
                        return _is_base_stable(clean)

                    # Aggregate by (symbol, chain)
                    token_protocols = defaultdict(
                        lambda: defaultdict(set)
                    )  # symbol -> chain -> set of (protocol, type)
                    token_protocols_usd = defaultdict(
                        lambda: defaultdict(lambda: defaultdict(float))
                    )  # symbol -> chain -> (protocol, type) -> usd
                    token_chain_totals = defaultdict(lambda: {"usd": 0, "amt": 0})
                    token_totals = defaultdict(
                        lambda: {
                            "usd": 0,
                            "amt": 0,
                            "chains": defaultdict(lambda: {"usd": 0, "amt": 0}),
                        }
                    )

                    for proto in protocols:
                        chain = proto.get("chain", "unknown").capitalize()
                        proto_name = proto.get("name", "Unknown")
                        for pos in proto.get("positions", []):
                            raw = (pos.get("asset") or pos.get("label") or "").strip()
                            parts = raw.split()
                            if len(parts) > 1 and any(ch.isdigit() for ch in parts[0]):
                                symbol = parts[-1].upper()
                            else:
                                symbol = raw.upper()
                            amt = pos.get("amount") or pos.get("qty") or pos.get("balance") or 0
                            try:
                                amt = float(amt)
                            except Exception:
                                amt = 0
                            usd = pos.get("usd_value", pos.get("value", 0)) or 0
                            try:
                                usd = float(usd)
                            except Exception:
                                usd = 0
                            ptype = pos.get("header_type", "-") or "-"
                            is_borrowed = str(ptype).lower() == "borrowed"
                            token_protocols[symbol][chain].add((proto_name, ptype))
                            # If symbol contains '+', check if any part is non-stable; if so, treat as non-stable
                            if "+" in symbol:
                                parts = symbol.split("+")
                                if any(not is_stable(part.strip()) for part in parts):
                                    # Treat as non-stable
                                    target_totals = token_totals
                                else:
                                    # All parts are stable, treat as stable
                                    target_totals = token_totals
                            else:
                                target_totals = token_totals
                            if is_borrowed:
                                token_protocols_usd[symbol][chain][(proto_name, ptype)] -= usd
                                target_totals[symbol]["usd"] -= usd
                                target_totals[symbol]["amt"] -= amt
                                target_totals[symbol]["chains"][chain]["usd"] -= usd
                                target_totals[symbol]["chains"][chain]["amt"] -= amt
                            else:
                                token_protocols_usd[symbol][chain][(proto_name, ptype)] += usd
                                target_totals[symbol]["usd"] += usd
                                target_totals[symbol]["amt"] += amt
                                target_totals[symbol]["chains"][chain]["usd"] += usd
                                target_totals[symbol]["chains"][chain]["amt"] += amt

                    # Split into stables and non-stables
                    stables = {k: v for k, v in token_totals.items() if is_pool_stable(k)}
                    nonstables = {k: v for k, v in token_totals.items() if not is_pool_stable(k)}

                    # Only show grouped breakdowns if proto_group_mode is True
                    if proto_group_mode:
                        while True:
                            os.system("clear" if os.name == "posix" else "cls")
                            # Print Stablecoin Breakdown
                            print(f"\n{theme.INFO}Stablecoin Breakdown:{theme.RESET}")
                            stables_filtered = {
                                k: v
                                for k, v in stables.items()
                                if isinstance(v, dict)
                                and isinstance(v.get("usd", None), (int, float))
                            }
                            # Calculate total excluding negative values for percentage calculation
                            total_stables_positive = sum(
                                v["usd"] for v in stables_filtered.values() if v["usd"] > 0
                            )
                            total_stables = sum(v["usd"] for v in stables_filtered.values())
                            dust_stables = 0
                            for symbol, data in sorted(
                                stables_filtered.items(),
                                key=lambda x: (
                                    -abs(x[1]["usd"])
                                    if isinstance(x[1], dict)
                                    and isinstance(x[1].get("usd"), (int, float))
                                    else 0
                                ),
                            ):
                                if not isinstance(data, dict):
                                    continue
                                if abs(data["usd"]) < 10:
                                    dust_stables += data["usd"]
                                    continue

                                # Check if token has negative total value
                                is_negative_token = data["usd"] < 0

                                pct = (
                                    (data["usd"] / total_stables_positive * 100)
                                    if total_stables_positive and not is_negative_token
                                    else 0
                                )
                                chains_for_symbol = (
                                    list(data["chains"].keys())
                                    if isinstance(data["chains"], dict)
                                    else []
                                )
                                if len(chains_for_symbol) == 1:
                                    chain = chains_for_symbol[0]
                                    icon = chain_icons.get(chain, "🔗")
                                    protos_types_usd = token_protocols_usd[symbol][chain]
                                    if len(protos_types_usd) == 1:
                                        (pname, ptype), p_usd = next(iter(protos_types_usd.items()))
                                        if is_negative_token:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {format_currency(data['usd'])} \u2190 {pname} [{ptype}]"
                                            )
                                        else:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {format_currency(data['usd'])} ({pct:.1f}%) \u2190 {pname} [{ptype}]"
                                            )
                                    else:
                                        if is_negative_token:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {format_currency(data['usd'])}"
                                            )
                                        else:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {format_currency(data['usd'])} ({pct:.1f}%)"
                                            )
                                        for (pname, ptype), p_usd in sorted(
                                            protos_types_usd.items(), key=lambda x: -x[1]
                                        ):
                                            has_negative_protocols = any(
                                                p < 0 for p in protos_types_usd.values()
                                            )
                                            if is_negative_token or has_negative_protocols:
                                                print(
                                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)}"
                                                )
                                            else:
                                                p_pct = (
                                                    (p_usd / data["usd"] * 100)
                                                    if data["usd"]
                                                    else 0
                                                )
                                                print(
                                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                                )
                                else:
                                    if is_negative_token:
                                        print(f"  {symbol}: {format_currency(data['usd'])}")
                                    else:
                                        print(
                                            f"  {symbol}: {format_currency(data['usd'])} ({pct:.1f}%)"
                                        )
                                    if isinstance(data["chains"], dict):
                                        for chain, cdata in sorted(
                                            data["chains"].items(),
                                            key=lambda x: (
                                                -x[1]["usd"] if isinstance(x[1], dict) else 0
                                            ),
                                        ):
                                            if not isinstance(cdata, dict):
                                                continue
                                            cpct = (
                                                (cdata["usd"] / data["usd"] * 100)
                                                if data["usd"] and not is_negative_token
                                                else 0
                                            )
                                            icon = chain_icons.get(chain, "🔗")
                                            protos_types_usd = token_protocols_usd[symbol][chain]
                                            if len(protos_types_usd) == 1:
                                                (pname, ptype), p_usd = next(
                                                    iter(protos_types_usd.items())
                                                )
                                                if is_negative_token:
                                                    print(
                                                        f"    {icon} {chain}: {format_currency(cdata['usd'])}  \u2190 {pname} [{ptype}]"
                                                    )
                                                else:
                                                    print(
                                                        f"    {icon} {chain}: {format_currency(cdata['usd'])} ({cpct:.1f}%)  \u2190 {pname} [{ptype}]"
                                                    )
                                            else:
                                                if is_negative_token:
                                                    print(
                                                        f"    {icon} {chain}: {format_currency(cdata['usd'])}"
                                                    )
                                                else:
                                                    print(
                                                        f"    {icon} {chain}: {format_currency(cdata['usd'])} ({cpct:.1f}%)"
                                                    )
                                                for (pname, ptype), p_usd in sorted(
                                                    protos_types_usd.items(), key=lambda x: -x[1]
                                                ):
                                                    has_negative_protocols = any(
                                                        p < 0 for p in protos_types_usd.values()
                                                    )
                                                    if is_negative_token or has_negative_protocols:
                                                        print(
                                                            f"      • {pname} [{ptype}]: {format_currency(p_usd)}"
                                                        )
                                                    else:
                                                        p_pct = (
                                                            (p_usd / data["usd"] * 100)
                                                            if data["usd"]
                                                            else 0
                                                        )
                                                        print(
                                                            f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                                        )
                            if dust_stables > 0:
                                dust_percentage = (
                                    (dust_stables / total_stables_positive * 100)
                                    if total_stables_positive and dust_stables > 0
                                    else 0
                                )
                                print(
                                    f"  {theme.SUBTLE}Dust stables (<$10): {format_currency(dust_stables)} ({dust_percentage:.1f}%){theme.RESET}"
                                )
                            print(
                                f"  {theme.ACCENT}Total Stables: {format_currency(total_stables)}{theme.RESET}"
                            )

                            # Print Non-Stable Token Breakdown
                            print(f"\n{theme.INFO}Non-Stable Token Breakdown:{theme.RESET}")
                            nonstables_filtered = {
                                k: v
                                for k, v in nonstables.items()
                                if isinstance(v, dict)
                                and isinstance(v.get("usd", None), (int, float))
                            }

                            # Calculate total excluding negative values for percentage calculation
                            total_nonstables_positive = sum(
                                v["usd"] for v in nonstables_filtered.values() if v["usd"] > 0
                            )
                            total_nonstables = sum(v["usd"] for v in nonstables_filtered.values())

                            # Fix percentage calculation: Use positive-only base when there are negative values
                            # This ensures positive token percentages add up to 100% instead of over 100%
                            has_negative_values = any(
                                v["usd"] < 0 for v in nonstables_filtered.values()
                            )
                            if has_negative_values:
                                # When there are negative values, use only positive values for percentage base
                                percentage_base = total_nonstables_positive
                            else:
                                # When all values are positive, use full total (original behavior)
                                percentage_base = (
                                    total_nonstables
                                    if total_nonstables > 0
                                    else total_nonstables_positive
                                )
                            dust_nonstables = 0
                            for symbol, data in sorted(
                                nonstables_filtered.items(),
                                key=lambda x: (
                                    (x[1]["usd"] < 0, -abs(x[1]["usd"]))
                                    if isinstance(x[1], dict)
                                    and isinstance(x[1].get("usd"), (int, float))
                                    else (True, 0)
                                ),
                            ):
                                if not isinstance(data, dict):
                                    continue
                                if abs(data["usd"]) < 5:  # Use absolute value for dust threshold
                                    dust_nonstables += data["usd"]
                                    continue

                                # Check if token has negative total value
                                is_negative_token = data["usd"] < 0

                                # Use positive total for percentage calculation
                                pct = (
                                    round(data["usd"] / percentage_base * 100, 1)
                                    if percentage_base and not is_negative_token
                                    else 0
                                )
                                amt = data["amt"]
                                amt_str = (
                                    f"{amt:.6f}".rstrip("0").rstrip(".")
                                    if isinstance(amt, (int, float)) and amt < 1
                                    else f"{amt:,.4f}".rstrip("0").rstrip(".")
                                )
                                chains_for_symbol = (
                                    list(data["chains"].keys())
                                    if isinstance(data["chains"], dict)
                                    else []
                                )
                                if len(chains_for_symbol) == 1:
                                    chain = chains_for_symbol[0]
                                    icon = chain_icons.get(chain, "🔗")
                                    protos_types_usd = token_protocols_usd[symbol][chain]
                                    if len(protos_types_usd) == 1:
                                        (pname, ptype), p_usd = next(iter(protos_types_usd.items()))
                                        if is_negative_token:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(data['usd'])} \u2190 {pname} [{ptype}]"
                                            )
                                        else:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(data['usd'])} ({pct:.1f}%) \u2190 {pname} [{ptype}]"
                                            )
                                    else:
                                        if is_negative_token:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(data['usd'])}"
                                            )
                                        else:
                                            print(
                                                f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(data['usd'])} ({pct:.1f}%)"
                                            )
                                        for (pname, ptype), p_usd in sorted(
                                            protos_types_usd.items(), key=lambda x: -x[1]
                                        ):
                                            # Check if this token has any negative protocol positions
                                            has_negative_protocols = any(
                                                p < 0 for p in protos_types_usd.values()
                                            )
                                            if is_negative_token or has_negative_protocols:
                                                print(
                                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)}"
                                                )
                                            else:
                                                p_pct = (
                                                    (p_usd / data["usd"] * 100)
                                                    if data["usd"]
                                                    else 0
                                                )
                                                print(
                                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                                )
                                else:
                                    if is_negative_token:
                                        print(
                                            f"  {symbol}: {amt_str} - {format_currency(data['usd'])}"
                                        )
                                    else:
                                        print(
                                            f"  {symbol}: {amt_str} - {format_currency(data['usd'])} ({pct:.1f}%)"
                                        )
                                    if isinstance(data["chains"], dict):
                                        for chain, cdata in sorted(
                                            data["chains"].items(),
                                            key=lambda x: (
                                                -x[1]["usd"] if isinstance(x[1], dict) else 0
                                            ),
                                        ):
                                            if not isinstance(cdata, dict):
                                                continue
                                            if cdata["usd"] == 0:
                                                continue
                                            cpct = (
                                                (cdata["usd"] / data["usd"] * 100)
                                                if data["usd"] and not is_negative_token
                                                else 0
                                            )
                                            icon = chain_icons.get(chain, "🔗")
                                            camt = cdata["amt"]
                                            camt_str = (
                                                f"{camt:.6f}".rstrip("0").rstrip(".")
                                                if camt < 1
                                                else f"{camt:,.4f}".rstrip("0").rstrip(".")
                                            )
                                            protos_types_usd = token_protocols_usd[symbol][chain]
                                            if len(protos_types_usd) == 1:
                                                (pname, ptype), p_usd = next(
                                                    iter(protos_types_usd.items())
                                                )
                                                if is_negative_token:
                                                    print(
                                                        f"    {icon} {chain}: {camt_str} - {format_currency(cdata['usd'])}  \u2190 {pname} [{ptype}]"
                                                    )
                                                else:
                                                    print(
                                                        f"    {icon} {chain}: {camt_str} - {format_currency(cdata['usd'])} ({cpct:.1f}%)  \u2190 {pname} [{ptype}]"
                                                    )
                                            else:
                                                chain_has_negative = any(
                                                    p < 0 for p in protos_types_usd.values()
                                                )
                                                if is_negative_token or chain_has_negative:
                                                    print(
                                                        f"    {icon} {chain}: {camt_str} - {format_currency(cdata['usd'])}"
                                                    )
                                                else:
                                                    print(
                                                        f"    {icon} {chain}: {camt_str} - {format_currency(cdata['usd'])} ({cpct:.1f}%)"
                                                    )
                                                for (pname, ptype), p_usd in sorted(
                                                    protos_types_usd.items(), key=lambda x: -x[1]
                                                ):
                                                    if is_negative_token or chain_has_negative:
                                                        print(
                                                            f"      • {pname} [{ptype}]: {format_currency(p_usd)}"
                                                        )
                                                    else:
                                                        p_pct = (
                                                            (p_usd / data["usd"] * 100)
                                                            if data["usd"]
                                                            else 0
                                                        )
                                                        print(
                                                            f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                                        )
                            if dust_nonstables > 0:
                                dust_percentage = (
                                    (dust_nonstables / percentage_base * 100)
                                    if percentage_base and dust_nonstables > 0
                                    else 0
                                )
                                print(
                                    f"  Dust tokens (<$5): {format_currency(dust_nonstables)} ({dust_percentage:.1f}%)"
                                )
                            print(f"  Total Non-Stable: {format_currency(total_nonstables)}")

                            print(
                                f"\n{theme.PRIMARY}NAVIGATION:{theme.RESET} (g) protocol list | (b)ack | (q)uit"
                            )
                            try:
                                choice = (
                                    input(f"\n{theme.PRIMARY}Enter command: {theme.RESET}")
                                    .strip()
                                    .lower()
                                )
                                if choice == "g":
                                    proto_group_mode = False
                                    break
                                elif choice == "b":
                                    wallet_breakdown_view = False
                                    breakdown_mode = "token"
                                    proto_index = 0
                                    break
                                elif choice == "q":
                                    return
                                else:
                                    print(
                                        f"{theme.ERROR}❌ Invalid command '{choice}'{theme.RESET}"
                                    )
                                    time.sleep(1.5)
                            except (ValueError, KeyboardInterrupt):
                                break
                            except Exception as e:
                                print(f"{theme.ERROR}❌ An error occurred: {str(e)}{theme.RESET}")
                                time.sleep(2)
                        continue  # restart main loop

                # Detailed protocol breakdown – paginated or all-view
                from tabulate import tabulate as _tab

                print(f"\n{theme.INFO}Protocol Breakdown:{theme.RESET}")

                dust_total = 0.0
                total_proto_val = 0.0

                sorted_protos = sorted(
                    protocols, key=lambda p: p.get("total_value", p.get("value", 0)), reverse=True
                )

                # Pre-compute aggregate totals (exact values) for persistence across pages
                dust_total_all = 0.0
                total_proto_val_all = 0.0

                # Helper to compute exact value of a protocol
                def _protocol_exact_val(proto_dict):
                    positions_ = proto_dict.get("positions", [])
                    if not positions_:
                        return proto_dict.get("total_value", proto_dict.get("value", 0))
                    total_ = 0.0
                    for _pos in positions_:
                        v_ = _pos.get("usd_value", _pos.get("value", 0)) or 0
                        if str(_pos.get("header_type", "")).lower() == "borrowed":
                            total_ -= v_
                        else:
                            total_ += v_
                    return total_

                for _proto in sorted_protos:
                    val = _protocol_exact_val(_proto)
                    if val < 10:
                        dust_total_all += val
                    else:
                        total_proto_val_all += val

                # Build list of protocols that will actually be shown (value ≥ $10)
                display_protos = [p for p in sorted_protos if _protocol_exact_val(p) >= 10]

                # Guard against empty list
                if not display_protos:
                    print(f"{theme.SUBTLE}No protocols to display{theme.RESET}")
                else:
                    # Determine which protocols to render this cycle
                    protos_to_show = (
                        display_protos  # all protocols on one page
                        if proto_show_all
                        else display_protos[proto_index : proto_index + 5]
                    )

                    for proto in protos_to_show:
                        # Compute exact value by summing positions (borrowed negative)
                        positions = proto.get("positions", [])
                        if positions:
                            pos_total = 0.0
                            for pos in positions:
                                v = pos.get("usd_value", pos.get("value", 0)) or 0
                                if str(pos.get("header_type", "")).lower() == "borrowed":
                                    pos_total -= v
                                else:
                                    pos_total += v
                            exact_val = pos_total
                        else:
                            exact_val = proto.get("total_value", proto.get("value", 0))

                        if exact_val < 10:
                            # Skip displaying dust protocol (aggregated later)
                            continue
                        # Display protocol and accumulate to page-level total (not strictly needed)

                        name = proto.get("name", "Unknown")
                        chain = proto.get("chain", "unknown").capitalize()

                        print(
                            f"\n{theme.ACCENT}{name}{theme.RESET} • {chain} — {theme.PRIMARY}{format_currency(exact_val)}{theme.RESET}"
                        )

                        if positions:
                            rows = []
                            for pos in positions:
                                label = pos.get("label", "")
                                asset = pos.get("asset", "")
                                ptype = pos.get("header_type", "") or "-"
                                usd_val = pos.get("usd_value", pos.get("value", 0))
                                rows.append([label, asset, ptype, format_currency(usd_val)])
                            print(
                                _tab(
                                    rows,
                                    headers=["Label", "Asset / Amount", "Type", "USD Value"],
                                    tablefmt="simple",
                                )
                            )
                        else:
                            print(f"{theme.SUBTLE}No positions found{theme.RESET}")

                    # When showing single protocol, accumulate dust/total later outside loop

                # Show aggregated dust protocols and totals
                if dust_total_all > 0:
                    print(
                        f"\n  {theme.SUBTLE}Others (<$10): {format_currency(dust_total_all)}{theme.RESET}"
                    )

                print(
                    f"  {theme.ACCENT}Total Protocols: {format_currency(total_proto_val_all + dust_total_all)}{theme.RESET}"
                )

                # ------------------- Navigation footer -------------------
                if proto_group_mode:
                    # In grouped view we only allow return to list
                    nav_line = ""
                    toggle_label = "(g) protocol list"
                else:
                    if proto_show_all:
                        nav_line = ""  # no prev/next in all view
                        toggle_label = "(p)aginated view | (g)roup by type"
                    else:
                        nav_parts = []
                        if proto_index > 0:
                            nav_parts.append("(p)rev")
                        if proto_index + 5 < len(display_protos):
                            nav_parts.append("(n)ext")
                        nav_line = " / ".join(nav_parts)
                        toggle_label = "(a)ll view | (g)roup by type"

                sep = " | " if nav_line else ""
                print(
                    f"\n{theme.PRIMARY}NAVIGATION:{theme.RESET} {nav_line}{sep}{toggle_label} | (t)oken breakdown | (b)ack | (q)uit"
                )

            try:
                choice = input(f"\n{theme.PRIMARY}Enter command: {theme.RESET}").strip().lower()
                if choice == "b":
                    # exit wallet breakdown view entirely
                    wallet_breakdown_view = False
                    breakdown_mode = "token"
                    proto_index = 0  # reset to first protocol
                elif choice == "q":
                    break
                elif choice == "p" and breakdown_mode == "token":
                    breakdown_mode = "protocol"
                    proto_index = 0  # reset to first protocol
                elif choice == "t" and breakdown_mode == "protocol":
                    breakdown_mode = "token"
                # Protocol navigation (paginated mode only)
                elif (
                    breakdown_mode == "protocol"
                    and not proto_group_mode
                    and not proto_show_all
                    and choice == "n"
                ):
                    proto_index = proto_index + 5
                    if proto_index >= len(display_protos):
                        proto_index = 0  # wrap to beginning
                elif (
                    breakdown_mode == "protocol"
                    and not proto_group_mode
                    and not proto_show_all
                    and choice == "p"
                ):
                    if proto_index == 0:
                        # wrap to last full page
                        proto_index = max(0, len(display_protos) - (len(display_protos) % 5 or 5))
                    else:
                        proto_index -= 5
                elif breakdown_mode == "protocol" and proto_show_all and choice == "p":
                    # switch back to paginated view
                    proto_show_all = False
                    proto_index = 0
                elif breakdown_mode == "protocol" and not proto_group_mode and choice == "a":
                    proto_show_all = True
                    proto_index = 0
                elif breakdown_mode == "protocol" and not proto_group_mode and choice == "g":
                    proto_group_mode = True
                elif choice:
                    print(f"{theme.ERROR}❌ Invalid command '{choice}'{theme.RESET}")
                    time.sleep(1.5)
            except (ValueError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"{theme.ERROR}❌ An error occurred: {str(e)}{theme.RESET}")
                time.sleep(2)
            continue  # restart loop

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
        nav_hints.append("(w)allet breakdown")
        valid_commands["w"] = "wallet_breakdown"
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
                    # Combined summary: token breakdown and protocol (grouped by token) breakdown
                    os.system("clear" if os.name == "posix" else "cls")
                    print(f"\n{theme.PRIMARY}🔍 WALLET SUMMARY BREAKDOWN{theme.RESET}")
                    print(f"{theme.SUBTLE}{'=' * 27}{theme.RESET}")
                    print(f"Address: {theme.ACCENT}{address_short}{theme.RESET}")
                    print(
                        f"Total Value: {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}"
                    )
                    analysis_ts_str = portfolio_metrics.get(
                        "timestamp", wallet_data.get("timestamp", "N/A")
                    )
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

                    # Display merged stable breakdown (combines token and protocol data)
                    stable_total = _display_merged_stable_breakdown(tokens, protocols)

                    # Display merged non-stable token breakdown (combines token and protocol data)
                    _display_merged_nonstable_breakdown(
                        tokens, protocols, stable_total=stable_total
                    )

                    input(f"\n{theme.SUBTLE}Press Enter to return...{theme.RESET}")
                elif action == "wallet_breakdown":
                    wallet_breakdown_view = True
                    breakdown_mode = "token"
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

    # Show totals
    total_token_value = sum(t.get("usd_value", 0) for t in tokens)
    total_protocol_value = sum(p.get("total_value", p.get("value", 0)) for p in protocols)

    print(f"\n{theme.SUCCESS}Total Token Value: {format_currency(total_token_value)}{theme.RESET}")
    print(
        f"{theme.SUCCESS}Total Protocol Value: {format_currency(total_protocol_value)}{theme.RESET}"
    )


def display_perp_dex_positions(portfolio_metrics: Dict[str, Any]):
    """Combined view for Hyperliquid and Lighter perpetual DEX positions with interactive navigation."""
    wallet_platform_data = portfolio_metrics.get("wallet_platform_data_raw", []) or []

    hyperliquid_accounts = [
        info for info in wallet_platform_data if info.get("platform") == "hyperliquid"
    ]
    lighter_accounts = [info for info in wallet_platform_data if info.get("platform") == "lighter"]

    def _render_hyperliquid_section(accounts: List[Dict[str, Any]]):
        total_balance = sum(info.get("total_balance", 0.0) for info in accounts)
        print(f"\n{theme.PRIMARY}⚡ HYPERLIQUID SUMMARY{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 23}{theme.RESET}")
        print(f"Total Account Value: {theme.SUCCESS}{format_currency(total_balance)}{theme.RESET}")
        print(f"Active Accounts:     {theme.ACCENT}{len(accounts)}{theme.RESET}")

        for i, account in enumerate(accounts, start=1):
            account_balance = account.get("total_balance", 0.0)
            address = account.get("address", "N/A")
            address_short = address[:8] + "..." + address[-6:] if address != "N/A" else "N/A"

            print(f"\n{theme.PRIMARY}📊 ACCOUNT {i}: {theme.ACCENT}{address_short}{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * (17 + len(address_short))}{theme.RESET}")
            print(f"Account Value: {theme.SUCCESS}{format_currency(account_balance)}{theme.RESET}")

            positions = account.get("open_positions", account.get("positions", [])) or []
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

            sortable_rows: List[Tuple[float, List[str]]] = []

            for position in positions:
                if not isinstance(position, dict):
                    continue

                size = safe_float_convert(position.get("size", position.get("position", 0.0)))
                if size > 0:
                    direction = f"{theme.SUCCESS}📈 Long{theme.RESET}"
                elif size < 0:
                    direction = f"{theme.ERROR}📉 Short{theme.RESET}"
                else:
                    direction = f"{theme.SUBTLE}➖ Flat{theme.RESET}"

                pnl = safe_float_convert(position.get("unrealized_pnl", 0))
                if pnl > 0:
                    pnl_formatted = f"{theme.SUCCESS}💰 +{format_currency(pnl)}{theme.RESET}"
                elif pnl < 0:
                    pnl_formatted = f"{theme.ERROR}💸 {format_currency(pnl)}{theme.RESET}"
                else:
                    pnl_formatted = f"{theme.SUBTLE}➖ {format_currency(pnl)}{theme.RESET}"

                liq_price = safe_float_convert(position.get("liquidation_price", 0))
                liq_display = (
                    f"{theme.WARNING}⚠️ {format_currency(liq_price)}{theme.RESET}"
                    if liq_price
                    else f"{theme.SUBTLE}N/A{theme.RESET}"
                )

                entry_price = safe_float_convert(position.get("entry_price", 0))
                leverage = safe_float_convert(position.get("leverage", 0))

                row = [
                    f"{theme.ACCENT}{position.get('asset', '?')}{theme.RESET}",
                    f"{abs(size):.4f} ({direction})",
                    f"{theme.PRIMARY}{format_currency(entry_price)}{theme.RESET}",
                    liq_display,
                    (
                        f"{theme.SUBTLE}{leverage:.2f}x{theme.RESET}"
                        if leverage
                        else f"{theme.SUBTLE}—{theme.RESET}"
                    ),
                    pnl_formatted,
                ]
                sortable_rows.append((pnl, row))

            if sortable_rows:
                sortable_rows.sort(key=lambda item: item[0], reverse=True)
                table_rows = [row for _, row in sortable_rows]
                print(
                    tabulate(
                        table_rows,
                        headers=headers,
                        tablefmt="rounded_grid",
                        numalign="right",
                        stralign="left",
                    )
                )
            else:
                print(f"{theme.SUBTLE}No open positions{theme.RESET}")

    def _render_lighter_section(accounts: List[Dict[str, Any]]):
        total_value = sum(info.get("total_balance", 0.0) for info in accounts)
        print(f"\n{theme.PRIMARY}🪙 LIGHTER SUMMARY{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 21}{theme.RESET}")
        print(f"Total Asset Value: {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}")
        print(f"Tracked Accounts:  {theme.ACCENT}{len(accounts)}{theme.RESET}")

        for idx, account in enumerate(accounts, start=1):
            address = account.get("address", "N/A")
            short_addr = address[:8] + "..." + address[-6:] if address != "N/A" else "N/A"
            account_value = account.get("total_balance", 0.0)
            available = account.get("available_balance", 0.0)
            collateral = account.get("collateral", 0.0)

            print(f"\n{theme.PRIMARY}📊 ACCOUNT {idx}: {theme.ACCENT}{short_addr}{theme.RESET}")
            print(f"{theme.SUBTLE}{'─' * (17 + len(short_addr))}{theme.RESET}")
            print(f"Asset Value:    {theme.SUCCESS}{format_currency(account_value)}{theme.RESET}")
            print(f"Available:      {theme.ACCENT}{format_currency(available)}{theme.RESET}")
            print(f"Collateral:     {theme.ACCENT}{format_currency(collateral)}{theme.RESET}")

            positions = account.get("positions", []) or []
            if not positions:
                print(f"\n{theme.SUBTLE}No open positions{theme.RESET}")
                continue

            print(f"\n{theme.SUBTLE}Open Positions{theme.RESET}")
            headers = [
                f"{theme.PRIMARY}Asset{theme.RESET}",
                f"{theme.PRIMARY}Position{theme.RESET}",
                f"{theme.PRIMARY}Entry Price{theme.RESET}",
                f"{theme.PRIMARY}Position Value{theme.RESET}",
                f"{theme.PRIMARY}Liq. Price{theme.RESET}",
                f"{theme.PRIMARY}Unrealized PNL{theme.RESET}",
            ]
            table_data = []

            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                symbol = pos.get("symbol", "N/A")
                position_size = safe_float_convert(pos.get("position", 0.0))
                position_value = safe_float_convert(pos.get("position_value", 0.0))
                entry_price = safe_float_convert(pos.get("avg_entry_price", 0.0))
                liq_price = safe_float_convert(pos.get("liquidation_price", 0.0))
                pnl = safe_float_convert(pos.get("unrealized_pnl", 0.0))

                if position_size > 0:
                    direction = f"{theme.SUCCESS}📈 Long{theme.RESET}"
                elif position_size < 0:
                    direction = f"{theme.ERROR}📉 Short{theme.RESET}"
                else:
                    direction = f"{theme.SUBTLE}➖ Flat{theme.RESET}"

                if pnl > 0:
                    pnl_fmt = f"{theme.SUCCESS}+{format_currency(pnl)}{theme.RESET}"
                elif pnl < 0:
                    pnl_fmt = f"{theme.ERROR}{format_currency(pnl)}{theme.RESET}"
                else:
                    pnl_fmt = f"{theme.SUBTLE}{format_currency(pnl)}{theme.RESET}"

                table_data.append(
                    [
                        f"{theme.ACCENT}{symbol}{theme.RESET}",
                        f"{abs(position_size):.4f} ({direction})",
                        f"{entry_price:,.2f}",
                        format_currency(position_value),
                        f"{liq_price:,.2f}" if liq_price else "—",
                        pnl_fmt,
                    ]
                )

            print(
                tabulate(
                    table_data,
                    headers=headers,
                    tablefmt="rounded_grid",
                    numalign="right",
                    stralign="left",
                )
            )

    if not hyperliquid_accounts and not lighter_accounts:
        print_header("Perp DEX Positions")
        print(f"{theme.SUBTLE}No perpetual DEX accounts tracked or no data available.{theme.RESET}")
        return

    def _count_positions(accounts: List[Dict[str, Any]]) -> int:
        count = 0
        for account in accounts:
            positions = account.get("open_positions") or account.get("positions") or []
            count += sum(1 for pos in positions if isinstance(pos, dict))
        return count

    def render_summary():
        print_header("Perp DEX Positions")
        print(f"\n{theme.PRIMARY}Perp DEX Summary{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 24}{theme.RESET}")
        table_data: List[List[str]] = []
        if hyperliquid_accounts:
            total_value = sum(
                safe_float_convert(info.get("total_balance", info.get("account_value", 0.0)))
                for info in hyperliquid_accounts
            )
            table_data.append(
                [
                    "Hyperliquid",
                    format_currency(total_value),
                    str(len(hyperliquid_accounts)),
                    str(_count_positions(hyperliquid_accounts)),
                ]
            )
        if lighter_accounts:
            total_value = sum(
                safe_float_convert(info.get("total_balance", 0.0)) for info in lighter_accounts
            )
            table_data.append(
                [
                    "Lighter",
                    format_currency(total_value),
                    str(len(lighter_accounts)),
                    str(_count_positions(lighter_accounts)),
                ]
            )
        headers = ["Platform", "Total Value", "Accounts", "Open Positions"]
        print(
            tabulate(
                table_data, headers=headers, tablefmt="grid", stralign="left", numalign="right"
            )
        )
        print(
            f"\n{theme.SUBTLE}Choose a platform for details or press Enter to return.{theme.RESET}"
        )

    render_summary()

    detail_views: List[Tuple[str, Any]] = []

    if hyperliquid_accounts:

        def show_hyperliquid():
            print(f"\n{theme.PRIMARY}Hyperliquid Details{theme.RESET}")
            _render_hyperliquid_section(hyperliquid_accounts)

        detail_views.append(("Hyperliquid", show_hyperliquid))

    if lighter_accounts:

        def show_lighter():
            print(f"\n{theme.PRIMARY}Lighter Details{theme.RESET}")
            _render_lighter_section(lighter_accounts)

        detail_views.append(("Lighter", show_lighter))

    if detail_views:
        while True:
            print(f"\n{theme.PRIMARY}Perp DEX Details Menu{theme.RESET}")
            for idx, (name, _) in enumerate(detail_views, start=1):
                print(f"{theme.ACCENT}{idx}.{theme.RESET} {name}")
            print(f"{theme.ACCENT}0.{theme.RESET} Back")

            choice = input(
                f"{theme.PRIMARY}Select platform for details (Enter to return): {theme.RESET}"
            ).strip()
            if choice in ("", "0", "q", "Q"):
                break
            if not choice.isdigit():
                print(f"{theme.ERROR}❌ Invalid choice. Please enter a number.{theme.RESET}")
                continue
            idx = int(choice)
            if 1 <= idx <= len(detail_views):
                _, render_fn = detail_views[idx - 1]
                render_fn()
                input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                render_summary()
            else:
                print(f"{theme.ERROR}❌ Invalid option. Try again.{theme.RESET}")

    print()  # Final spacing


def display_polymarket_positions(portfolio_metrics: Dict[str, Any]):
    """Display Polymarket prediction market positions grouped by owner."""
    wallet_platform_data = portfolio_metrics.get("wallet_platform_data_raw", []) or []
    polymarket_accounts = [
        info for info in wallet_platform_data if info.get("platform") == "polymarket"
    ]

    if not polymarket_accounts:
        print_header("Polymarket Positions")
        print(
            f"{theme.SUBTLE}No Polymarket proxies configured or no positions available.{theme.RESET}"
        )
        print(
            f"{theme.INFO}💡 Configure proxies via Manage Wallets → Configure Polymarket to enable tracking.{theme.RESET}"
        )
        return

    valid_accounts = [acct for acct in polymarket_accounts if not acct.get("error")]
    total_value = sum(
        safe_float_convert(acct.get("total_balance", 0.0)) for acct in valid_accounts
    )
    print_header("Polymarket Positions")
    print(f"\n{theme.PRIMARY}🎯 POLYMARKET SUMMARY{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 26}{theme.RESET}")
    print(f"Tracked Owners:    {theme.ACCENT}{len(polymarket_accounts)}{theme.RESET}")
    print(f"Active Portfolios: {theme.ACCENT}{len(valid_accounts)}{theme.RESET}")
    print(f"Total Value:       {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}")

    missing_proxy_count = sum(
        1 for acct in polymarket_accounts if acct.get("error") == "proxy_not_configured"
    )
    if missing_proxy_count:
        print(
            f"{theme.WARNING}⚠️  {missing_proxy_count} wallet(s) missing proxy configuration.{theme.RESET}"
        )

    for idx, account in enumerate(polymarket_accounts, start=1):
        owner = account.get("address", "N/A") or "N/A"
        proxy = account.get("proxy") or account.get("proxy_address") or "N/A"
        owner_short = owner[:8] + "..." + owner[-6:] if owner != "N/A" else owner
        proxy_short = proxy[:8] + "..." + proxy[-6:] if proxy != "N/A" else proxy
        error_state = account.get("error")

        print(
            f"\n{theme.PRIMARY}📊 OWNER {idx}: {theme.ACCENT}{owner_short}{theme.RESET} "
            f"{theme.SUBTLE}(Proxy {proxy_short}){theme.RESET}"
        )
        print(f"{theme.SUBTLE}{'─' * (20 + len(owner_short))}{theme.RESET}")

        if error_state:
            if error_state == "proxy_not_configured":
                print(
                    f"{theme.WARNING}⚠️  Proxy not configured. Add the proxy wallet in Manage Wallets → Configure Polymarket.{theme.RESET}"
                )
            else:
                print(
                    f"{theme.WARNING}⚠️  Unable to load data for this proxy. Please retry later.{theme.RESET}"
                )
            continue

        total_balance = safe_float_convert(account.get("total_balance", 0.0))
        usdc_balance = safe_float_convert(account.get("usdc_balance", 0.0))
        positions_value = safe_float_convert(account.get("positions_value", 0.0))
        metadata = account.get("metadata", {}) or {}
        cash_pnl_total = safe_float_convert(metadata.get("cash_pnl", 0.0))
        unrealized_pnl = safe_float_convert(metadata.get("unrealized_pnl", 0.0))

        print(f"Total Value:     {theme.SUCCESS}{format_currency(total_balance)}{theme.RESET}")
        print(f"Positions Value: {theme.ACCENT}{format_currency(positions_value)}{theme.RESET}")
        print(f"USDC Balance:    {theme.ACCENT}{format_currency(usdc_balance)}{theme.RESET}")
        show_realized = (
            abs(cash_pnl_total) > 1e-6 and abs(cash_pnl_total - unrealized_pnl) > 1e-6
        )
        if show_realized:
            pnl_color = theme.SUCCESS if cash_pnl_total >= 0 else theme.ERROR
            print(f"Realized PnL:   {pnl_color}{format_currency(cash_pnl_total)}{theme.RESET}")
        unrealized_color = theme.SUCCESS if unrealized_pnl >= 0 else theme.ERROR
        print(f"Unrealized PnL: {unrealized_color}{format_currency(unrealized_pnl)}{theme.RESET}")

        positions = account.get("positions", []) or []
        if not positions:
            print(f"\n{theme.SUBTLE}No active Polymarket positions{theme.RESET}")
            continue

        headers = [
            f"{theme.PRIMARY}Market{theme.RESET}",
            f"{theme.PRIMARY}Outcome{theme.RESET}",
            f"{theme.PRIMARY}Size{theme.RESET}",
            f"{theme.PRIMARY}Avg Price{theme.RESET}",
            f"{theme.PRIMARY}Mark{theme.RESET}",
            f"{theme.PRIMARY}Current Value{theme.RESET}",
            f"{theme.PRIMARY}Cash PnL{theme.RESET}",
            f"{theme.PRIMARY}Status{theme.RESET}",
        ]
        table_rows: List[List[str]] = []

        for position in positions:
            title = position.get("title") or position.get("slug") or "Unknown Market"
            outcome = position.get("outcome", "—")
            size = safe_float_convert(position.get("size", 0.0))
            avg_price = safe_float_convert(position.get("avg_price", 0.0))
            current_price = safe_float_convert(position.get("current_price", 0.0))
            current_value = safe_float_convert(position.get("current_value", 0.0))
            cash_pnl = safe_float_convert(position.get("cash_pnl", 0.0))
            redeemable = bool(position.get("redeemable"))
            end_date = position.get("end_date")

            status_parts = []
            if redeemable:
                status_parts.append("Redeemable")
            elif current_value > 0:
                status_parts.append("Active")
            else:
                status_parts.append("Settled")
            if end_date:
                status_parts.append(end_date)
            status = " • ".join(status_parts)

            table_rows.append(
                [
                    f"{theme.ACCENT}{title}{theme.RESET}",
                    outcome,
                    f"{size:,.3f}",
                    f"{avg_price:.4f}",
                    f"{current_price:.4f}",
                    format_currency(current_value),
                    format_currency(cash_pnl),
                    status,
                ]
            )

        print(
            tabulate(
                table_rows,
                headers=headers,
                tablefmt="rounded_grid",
                numalign="right",
                stralign="left",
            )
        )

    print()


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


def display_lighter_positions(portfolio_metrics: Dict[str, Any]):
    """Display positions for Lighter perp DEX accounts."""
    print_header("Lighter Positions")

    wallet_platform_data = portfolio_metrics.get("wallet_platform_data_raw", [])
    lighter_accounts = [info for info in wallet_platform_data if info.get("platform") == "lighter"]

    if not lighter_accounts:
        print(f"{theme.SUBTLE}No Lighter accounts tracked or no data available.{theme.RESET}")
        return

    total_value = sum(info.get("total_balance", 0.0) for info in lighter_accounts)

    print(f"\n{theme.PRIMARY}🪙 LIGHTER SUMMARY{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 21}{theme.RESET}")
    print(f"Total Asset Value: {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}")
    print(f"Tracked Accounts:  {theme.ACCENT}{len(lighter_accounts)}{theme.RESET}")

    for idx, account in enumerate(lighter_accounts, start=1):
        address = account.get("address", "N/A")
        short_addr = address[:8] + "..." + address[-6:] if address != "N/A" else "N/A"
        account_value = account.get("total_balance", 0.0)
        available = account.get("available_balance", 0.0)
        collateral = account.get("collateral", 0.0)

        print(f"\n{theme.PRIMARY}📊 ACCOUNT {idx}: {theme.ACCENT}{short_addr}{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * (17 + len(short_addr))}{theme.RESET}")
        print(f"Asset Value:    {theme.SUCCESS}{format_currency(account_value)}{theme.RESET}")
        print(f"Available:      {theme.ACCENT}{format_currency(available)}{theme.RESET}")
        print(f"Collateral:     {theme.ACCENT}{format_currency(collateral)}{theme.RESET}")

        positions = account.get("positions", [])
        if not positions:
            print(f"\n{theme.SUBTLE}No open positions{theme.RESET}")
            continue

        print(f"\n{theme.SUBTLE}Open Positions{theme.RESET}")
        headers = [
            f"{theme.PRIMARY}Asset{theme.RESET}",
            f"{theme.PRIMARY}Position{theme.RESET}",
            f"{theme.PRIMARY}Entry Price{theme.RESET}",
            f"{theme.PRIMARY}Position Value{theme.RESET}",
            f"{theme.PRIMARY}Liq. Price{theme.RESET}",
            f"{theme.PRIMARY}Unrealized PNL{theme.RESET}",
        ]
        table_data = []

        for pos in positions:
            symbol = pos.get("symbol", "N/A")
            position_size = safe_float_convert(pos.get("position", 0.0))
            position_value = safe_float_convert(pos.get("position_value", 0.0))
            entry_price = safe_float_convert(pos.get("avg_entry_price", 0.0))
            liq_price = safe_float_convert(pos.get("liquidation_price", 0.0))
            pnl = safe_float_convert(pos.get("unrealized_pnl", 0.0))

            if position_size > 0:
                direction = f"{theme.SUCCESS}📈 Long{theme.RESET}"
            elif position_size < 0:
                direction = f"{theme.ERROR}📉 Short{theme.RESET}"
            else:
                direction = f"{theme.SUBTLE}➖ Flat{theme.RESET}"

            pnl_fmt = (
                f"{theme.SUCCESS}+{format_currency(pnl)}{theme.RESET}"
                if pnl > 0
                else (
                    f"{theme.ERROR}{format_currency(pnl)}{theme.RESET}"
                    if pnl < 0
                    else f"{theme.SUBTLE}{format_currency(pnl)}{theme.RESET}"
                )
            )

            table_data.append(
                [
                    f"{theme.ACCENT}{symbol}{theme.RESET}",
                    f"{abs(position_size):.4f} ({direction})",
                    f"{entry_price:,.2f}",
                    format_currency(position_value),
                    f"{liq_price:,.2f}",
                    pnl_fmt,
                ]
            )

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
    binance_total = metrics.get("binance")
    okx_total = metrics.get("okx")
    bybit_total = metrics.get("bybit")
    backpack_total = metrics.get("backpack")
    total_cex = metrics.get("total_cex_balance", 0.0)
    failed_sources = metrics.get("failed_sources", [])

    def render_summary():
        print_header("Centralized Exchange Breakdown")

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

    render_summary()

    # Detailed views with interactive selection
    detail_views: List[Tuple[str, Any]] = []

    if "Binance" not in failed_sources and binance_total is not None and binance_total > 0:
        binance_account_types = metrics.get("detailed_breakdowns", {}).get("binance_account_types")
        stored_binance_details = metrics.get("detailed_breakdowns", {}).get("binance_details")
        binance_futures_positions = metrics.get("detailed_breakdowns", {}).get(
            "binance_futures_positions"
        )

        def render_binance_details(
            account_types=binance_account_types,
            spot_details=stored_binance_details,
            futures_positions=binance_futures_positions,
        ):
            print(f"\n{theme.PRIMARY}Binance Details{theme.RESET}")
            if account_types:
                acct_map = account_types.get("account_types", {})
                total_all = safe_float_convert(account_types.get("total_all_accounts", 0.0))
                print(f"Total Equity: {format_currency(total_all)}")
                print("─" * 30)
                rows = []
                for account_type, balance in acct_map.items():
                    if balance is None:
                        continue
                    balance_val = safe_float_convert(balance)
                    percentage = (balance_val / total_all * 100) if total_all > 0 else 0
                    clean_value = (
                        f"${balance_val:,.0f}" if balance_val >= 1 else f"${balance_val:.2f}"
                    )
                    rows.append([account_type, clean_value, f"{percentage:.1f}%"])
                if rows:
                    print(
                        tabulate(
                            rows, headers=["Account Type", "Balance", "Share"], tablefmt="simple"
                        )
                    )
                else:
                    print(f"{theme.SUBTLE}No account type data available{theme.RESET}")
            else:
                print(f"{theme.SUBTLE}No account type data available{theme.RESET}")

            if spot_details:
                display_exchange_detailed_breakdown("Binance", spot_details, failed_sources)
            if futures_positions:
                display_binance_futures_positions(futures_positions)

        detail_views.append(("Binance", render_binance_details))

    if "OKX" not in failed_sources and okx_total is not None and okx_total > 0:
        stored_okx_details = metrics.get("detailed_breakdowns", {}).get("okx_details")
        okx_positions = metrics.get("detailed_breakdowns", {}).get("okx_futures_positions")
        okx_account_types = metrics.get("detailed_breakdowns", {}).get("okx_account_types")

        def render_okx_details(
            account_types=okx_account_types,
            spot_details=stored_okx_details,
            futures_positions=okx_positions,
        ):
            print(f"\n{theme.PRIMARY}OKX Details{theme.RESET}")
            if account_types:
                acct_map = account_types.get("account_types", {})
                total_all = safe_float_convert(account_types.get("total_all_accounts", 0.0))
                print(f"Total Equity: {format_currency(total_all)}")
                print("─" * 30)
                rows = []
                for acct_name, balance in acct_map.items():
                    balance_val = safe_float_convert(balance)
                    percentage = (balance_val / total_all * 100) if total_all > 0 else 0
                    clean_value = (
                        f"${balance_val:,.0f}" if balance_val >= 1 else f"${balance_val:.2f}"
                    )
                    rows.append([acct_name, clean_value, f"{percentage:.1f}%"])
                if rows:
                    print(
                        tabulate(
                            rows, headers=["Account Type", "Balance", "Share"], tablefmt="simple"
                        )
                    )
                else:
                    print(f"{theme.SUBTLE}No account type data available{theme.RESET}")
            else:
                print(f"{theme.SUBTLE}No account type data available{theme.RESET}")

            if spot_details:
                display_exchange_detailed_breakdown("OKX", spot_details, failed_sources)
            else:
                print(f"{theme.SUBTLE}No spot balance details available{theme.RESET}")
            if futures_positions:
                display_okx_futures_positions(futures_positions)

        detail_views.append(("OKX", render_okx_details))

    if "Bybit" not in failed_sources and bybit_total is not None and bybit_total > 0:
        stored_bybit_details = metrics.get("detailed_breakdowns", {}).get("bybit_details")
        bybit_positions = metrics.get("detailed_breakdowns", {}).get("bybit_futures_positions")

        bybit_account_types = metrics.get("detailed_breakdowns", {}).get("bybit_account_types")

        def render_bybit_details(
            account_types=bybit_account_types,
            spot_details=stored_bybit_details,
            futures_positions=bybit_positions,
        ):
            print(f"\n{theme.PRIMARY}Bybit Details{theme.RESET}")
            if account_types:
                acct_map = account_types.get("account_types", {})
                total_all = safe_float_convert(account_types.get("total_all_accounts", 0.0))
                print(f"Total Equity: {format_currency(total_all)}")
                print("─" * 30)
                rows = []
                for acct_name, balance in acct_map.items():
                    balance_val = safe_float_convert(balance)
                    percentage = (balance_val / total_all * 100) if total_all > 0 else 0
                    clean_value = (
                        f"${balance_val:,.0f}" if balance_val >= 1 else f"${balance_val:.2f}"
                    )
                    rows.append([acct_name, clean_value, f"{percentage:.1f}%"])
                if rows:
                    print(
                        tabulate(
                            rows, headers=["Account Type", "Balance", "Share"], tablefmt="simple"
                        )
                    )
                else:
                    print(f"{theme.SUBTLE}No account type data available{theme.RESET}")
            else:
                print(f"{theme.SUBTLE}No account type data available{theme.RESET}")

            if spot_details:
                display_exchange_detailed_breakdown("Bybit", spot_details, failed_sources)
            else:
                print(f"{theme.SUBTLE}No spot balance details available{theme.RESET}")
            if futures_positions:
                display_bybit_futures_positions(futures_positions)

        detail_views.append(("Bybit", render_bybit_details))

    if "Backpack" not in failed_sources and backpack_total is not None and backpack_total > 0:
        stored_backpack_details = metrics.get("detailed_breakdowns", {}).get("backpack_details")

        def render_backpack_details(spot_details=stored_backpack_details):
            print(f"\n{theme.PRIMARY}Backpack Details{theme.RESET}")
            if spot_details:
                display_exchange_detailed_breakdown("Backpack", spot_details, failed_sources)
            else:
                print(f"{theme.SUBTLE}No detailed data available{theme.RESET}")

        detail_views.append(("Backpack", render_backpack_details))

    if detail_views:
        while True:
            print(f"\n{theme.PRIMARY}Exchange Details Menu{theme.RESET}")
            for idx, (name, _) in enumerate(detail_views, start=1):
                print(f"{theme.ACCENT}{idx}.{theme.RESET} {name}")
            print(f"{theme.ACCENT}0.{theme.RESET} Back")

            choice = input(
                f"{theme.PRIMARY}Select exchange for details (Enter to return): {theme.RESET}"
            ).strip()
            if choice in ("", "0", "q", "Q"):
                break
            if not choice.isdigit():
                print(f"{theme.ERROR}❌ Invalid choice. Please enter a number.{theme.RESET}")
                continue
            idx = int(choice)
            if 1 <= idx <= len(detail_views):
                _, render_fn = detail_views[idx - 1]
                render_fn()
                input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")
                render_summary()
            else:
                print(f"{theme.ERROR}❌ Invalid option. Try again.{theme.RESET}")
    else:
        print(f"\n{theme.SUBTLE}No detailed exchange data available.{theme.RESET}")

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

    major_coins = SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY  # e.g., ['BTC', 'ETH', 'SOL']

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
    """Display comprehensive exposure analysis with simple return option."""
    from utils.display_theme import theme

    while True:
        # Clear screen for better visibility
        os.system("clear" if os.name == "posix" else "cls")

        # Display main exposure analysis first
        _display_main_exposure_analysis(portfolio_metrics)

        # Add submenu options
        print(f"\n{theme.PRIMARY}🎯 EXPOSURE ANALYSIS OPTIONS{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 28}{theme.RESET}")
        print(f"{theme.ACCENT}1.{theme.RESET} {theme.SUBTLE}⬅️ Back to Analysis Menu{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 50}{theme.RESET}")

        choice = input(f"{theme.PRIMARY}Select option (1): {theme.RESET}").strip()

        if choice in ("", "1", "b", "B"):
            break
        else:
            print(f"{theme.ERROR}❌ Invalid choice. Please press 1 or Enter.{theme.RESET}")
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

    # Prepare aggregated views for margin platforms (Hyperliquid + Lighter)
    perp_margin_symbols = {
        "MARGIN_HYPERLIQUID",
        "MARGIN_LIGHTER",
        "MARGIN_BINANCE_USDM",
        "MARGIN_BINANCE_COINM",
        "MARGIN_OKX_FUTURES",
        "MARGIN_BYBIT_FUTURES",
    }
    consolidated_assets_raw = exposure_data.get("consolidated_assets", {}) or {}
    non_stable_assets_raw = exposure_data.get("non_stable_assets", {}) or {}
    stable_assets_raw = exposure_data.get("stable_assets", {}) or {}
    reserve_assets_raw = exposure_data.get("reserve_assets", {}) or {}

    def aggregate_perp_positions(
        source_dict: Dict[str, Any], include_non_stable: bool = False
    ) -> Dict[str, Any]:
        """
        Aggregate perpetual margin positions into grouped CEX/DEX summaries while preserving
        non-margin assets unchanged.
        """
        cex_tokens = {
            "binance",
            "bybit",
            "okx",
            "bitget",
            "kucoin",
            "mexc",
            "bingx",
            "gate",
            "coinbase",
            "kraken",
            "huobi",
        }

        symbol_map = {
            "dex": "PERP_DEX_POSITIONS",
            "cex": "PERP_CEX_POSITIONS",
        }
        display_map = {
            "dex": "Perp DEX Positions",
            "cex": "Perp CEX Positions",
        }

        def _new_group() -> Dict[str, Any]:
            return {
                "total_value": 0.0,
                "total_quantity": 0.0,
                "pct_portfolio": 0.0,
                "pct_non_stable": 0.0,
                "platforms": {},
                "meta": {
                    "is_margin_position": True,
                    "margin_underlyings": {},
                    "margin_underlying_details": [],
                    "platform_unrealized_pnl": {},
                    "total_unrealized_pnl": 0.0,
                    "delta_neutral": None,
                    "perp_sources": set(),
                },
                "is_stable": True,
                "max_net_ratio": 0.0,
            }

        groups: Dict[str, Dict[str, Any]] = {}
        new_dict: Dict[str, Any] = {}

        for symbol, original_data in source_dict.items():
            data = deepcopy(original_data)
            if symbol not in perp_margin_symbols or not isinstance(data, dict):
                new_dict[symbol] = data
                continue

            metadata = data.get("metadata", {}) or {}
            if bool(metadata.get("delta_neutral")):
                continue
            source_platform = metadata.get("source_platform") or symbol
            platform_lower = str(source_platform).lower()
            category = "cex" if any(token in platform_lower for token in cex_tokens) else "dex"
            group = groups.setdefault(category, _new_group())

            value_usd = safe_float_convert(data.get("total_value_usd", 0.0))
            group["total_value"] += value_usd
            group["total_quantity"] += safe_float_convert(data.get("total_quantity", 0.0))
            group["pct_portfolio"] += safe_float_convert(data.get("percentage_of_portfolio", 0.0))
            if include_non_stable:
                group["pct_non_stable"] += safe_float_convert(
                    data.get("percentage_of_non_stable", 0.0)
                )
            if data.get("is_stable") is False:
                group["is_stable"] = False

            for platform_name, amount in (data.get("platforms") or {}).items():
                group["platforms"][platform_name] = group["platforms"].get(
                    platform_name, 0.0
                ) + safe_float_convert(amount, 0.0)

            meta = group["meta"]
            meta["perp_sources"].add(source_platform)

            for underlying_symbol, underlying_value in (
                metadata.get("margin_underlyings") or {}
            ).items():
                meta["margin_underlyings"][underlying_symbol] = meta["margin_underlyings"].get(
                    underlying_symbol, 0.0
                ) + safe_float_convert(underlying_value, 0.0)

            for detail in metadata.get("margin_underlying_details", []) or []:
                meta["margin_underlying_details"].append(deepcopy(detail))

            for platform_name, pnl_val in (metadata.get("platform_unrealized_pnl") or {}).items():
                meta["platform_unrealized_pnl"][platform_name] = meta[
                    "platform_unrealized_pnl"
                ].get(platform_name, 0.0) + safe_float_convert(pnl_val, 0.0)

            meta["total_unrealized_pnl"] += safe_float_convert(
                metadata.get("total_unrealized_pnl", 0.0)
            )

            delta_flag = metadata.get("delta_neutral")
            if delta_flag is False:
                meta["delta_neutral"] = False
            elif delta_flag is True and meta["delta_neutral"] is not False:
                meta["delta_neutral"] = True

            net_ratio = safe_float_convert(metadata.get("net_exposure_ratio", 0.0))
            if net_ratio > group["max_net_ratio"]:
                group["max_net_ratio"] = net_ratio

        for category, group in groups.items():
            if group["total_value"] <= 0:
                continue

            meta = group["meta"]
            meta["perp_sources"] = sorted(meta["perp_sources"])
            meta["net_exposure_ratio"] = group["max_net_ratio"]
            display_name = display_map.get(category, "Perp Positions")
            meta["display_name"] = display_name
            meta["is_margin_position"] = True
            meta["source_platform"] = display_name
            meta["force_is_stable"] = False

            if meta.get("delta_neutral") is False:
                group["is_stable"] = False

            symbol_key = symbol_map.get(category, "PERP_MARGIN_POSITIONS")
            aggregated_entry = {
                "symbol": symbol_key,
                "total_quantity": group["total_quantity"],
                "current_price": None,
                "market_price": None,
                "implied_price": None,
                "total_value_usd": group["total_value"],
                "percentage_of_portfolio": group["pct_portfolio"],
                "platforms": group["platforms"] or {display_name: group["total_value"]},
                "is_stable": group["is_stable"],
                "platform_count": len(group["platforms"]) if group["platforms"] else 1,
                "metadata": meta,
            }
            if include_non_stable:
                aggregated_entry["percentage_of_non_stable"] = group["pct_non_stable"]

            new_dict[symbol_key] = aggregated_entry

        return new_dict

    _PLATFORM_ACCOUNT_MAP = {
        "binance usdm futures": "CEX_Binance",
        "binance coinm futures": "CEX_Binance",
        "binance futures": "CEX_Binance",
        "okx futures": "CEX_OKX",
        "okx perpetual": "CEX_OKX",
        "bybit futures": "CEX_Bybit",
        "bybit unified": "CEX_Bybit",
        "backpack perps": "CEX_Backpack",
    }
    _UNIFIED_PLATFORM_TOKENS = {"bybit", "okx", "backpack"}
    _COLLATERAL_TOKENS = [
        "USDC",
        "USDT",
        "USD",
        "FDUSD",
        "BUSD",
        "TUSD",
        "USDP",
        "USDE",
        "USDC.E",
    ]

    def _guess_collateral_symbol(detail: Dict[str, Any]) -> Optional[str]:
        collateral = (
            detail.get("collateral") or detail.get("collateral_asset") or detail.get("settleCoin")
        )
        if collateral:
            return str(collateral).upper()
        symbol_text = str(detail.get("symbol") or "").upper()
        for token in _COLLATERAL_TOKENS:
            if token in symbol_text:
                return token.replace(".", "")
        quote = detail.get("quote") or detail.get("quote_symbol")
        if quote:
            return str(quote).upper()
        return None

    def _collect_cex_margin_offsets(
        asset_map: Dict[str, Any], reserve_map: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        entry = asset_map.get("PERP_CEX_POSITIONS")
        if not isinstance(entry, dict):
            return {}
        metadata = entry.get("metadata") or {}
        details = metadata.get("margin_underlying_details") or []
        offsets: Dict[str, Dict[str, Any]] = {}
        for detail in details:
            if not isinstance(detail, dict):
                continue
            margin_value = safe_float_convert(
                detail.get("margin_value")
                or detail.get("margin")
                or detail.get("marginUsed")
                or detail.get("marginCollateral")
                or 0.0
            )
            if margin_value <= 0:
                continue
            collateral_symbol = _guess_collateral_symbol(detail)
            if not collateral_symbol:
                continue
            platform_label = str(
                detail.get("platform") or metadata.get("source_platform") or ""
            ).lower()
            if not platform_label:
                continue
            if not any(token in platform_label for token in _UNIFIED_PLATFORM_TOKENS):
                continue
            account_key = _PLATFORM_ACCOUNT_MAP.get(platform_label)
            if account_key is None:
                for token, mapped_key in [
                    ("binance", "CEX_Binance"),
                    ("okx", "CEX_OKX"),
                    ("bybit", "CEX_Bybit"),
                    ("backpack", "CEX_Backpack"),
                ]:
                    if token in platform_label:
                        account_key = mapped_key
                        break
            entry_offsets = offsets.setdefault(collateral_symbol, {"total": 0.0, "accounts": {}})
            entry_offsets["total"] += margin_value
            if account_key:
                accounts_map = entry_offsets["accounts"]
                accounts_map[account_key] = accounts_map.get(account_key, 0.0) + margin_value
        # merge reserve assets for unified platforms
        for symbol, reserve_entry in reserve_map.items():
            if not isinstance(reserve_entry, dict):
                continue
            metadata = reserve_entry.get("metadata") or {}
            if not metadata.get("is_margin_reserve"):
                continue
            source_platform = str(metadata.get("source_platform") or "").lower()
            if not source_platform:
                continue
            if not any(token in source_platform for token in _UNIFIED_PLATFORM_TOKENS):
                continue
            total_value = safe_float_convert(reserve_entry.get("total_value_usd", 0.0))
            if total_value <= 0:
                continue
            collateral_symbol = "USDC"
            inferred = _guess_collateral_symbol({"symbol": reserve_entry.get("symbol")})
            if inferred:
                collateral_symbol = inferred
            account_key = _PLATFORM_ACCOUNT_MAP.get(source_platform)
            if account_key is None:
                for token, mapped_key in [
                    ("okx", "CEX_OKX"),
                    ("bybit", "CEX_Bybit"),
                    ("backpack", "CEX_Backpack"),
                ]:
                    if token in source_platform:
                        account_key = mapped_key
                        break
            entry_offsets = offsets.setdefault(collateral_symbol, {"total": 0.0, "accounts": {}})
            entry_offsets["total"] += total_value
            if account_key:
                accounts_map = entry_offsets["accounts"]
                accounts_map[account_key] = accounts_map.get(account_key, 0.0) + total_value

        return offsets

    def _apply_margin_offsets(
        asset_map: Dict[str, Any],
        offsets: Dict[str, Dict[str, Any]],
        total_portfolio_value: float,
    ) -> None:
        if not isinstance(asset_map, dict):
            return
        for collateral_symbol, data in offsets.items():
            entry = asset_map.get(collateral_symbol)
            if not isinstance(entry, dict):
                continue
            total_offset = safe_float_convert(data.get("total", 0.0))
            if total_offset <= 0:
                continue
            current_value = safe_float_convert(entry.get("total_value_usd", 0.0))
            new_value = max(current_value - total_offset, 0.0)
            entry["total_value_usd"] = new_value

            quantity = safe_float_convert(entry.get("total_quantity", 0.0))
            if quantity > 0:
                price = safe_float_convert(
                    entry.get("current_price")
                    or entry.get("implied_price")
                    or (current_value / quantity if quantity > 0 else 1.0),
                    1.0,
                )
                if price <= 0:
                    price = 1.0
                adjusted_qty = max(quantity - (total_offset / price), 0.0)
                entry["total_quantity"] = adjusted_qty

            if total_portfolio_value > 0:
                pct_value = safe_float_convert(entry.get("percentage_of_portfolio", 0.0))
                pct_offset = (total_offset / total_portfolio_value) * 100.0
                entry["percentage_of_portfolio"] = max(pct_value - pct_offset, 0.0)

                pct_non_stable = safe_float_convert(entry.get("percentage_of_non_stable", 0.0))
                entry["percentage_of_non_stable"] = max(pct_non_stable - pct_offset, 0.0)

            platforms_map = entry.get("platforms")
            if isinstance(platforms_map, dict) and platforms_map:
                account_amounts = data.get("accounts", {})
                accounted_total = 0.0
                for account_key, amount in account_amounts.items():
                    accounted_total += amount
                    current_platform_val = safe_float_convert(platforms_map.get(account_key, 0.0))
                    updated_val = max(current_platform_val - amount, 0.0)
                    if updated_val <= 1e-9:
                        platforms_map.pop(account_key, None)
                    else:
                        platforms_map[account_key] = updated_val

                remaining = max(total_offset - accounted_total, 0.0)
                if remaining > 1e-6 and platforms_map:
                    total_platform_value = sum(
                        safe_float_convert(v, 0.0) for v in platforms_map.values()
                    )
                    if total_platform_value > 0:
                        for key in list(platforms_map.keys()):
                            share = (
                                safe_float_convert(platforms_map.get(key, 0.0))
                                / total_platform_value
                            )
                            deduction = remaining * share
                            updated_val = max(
                                safe_float_convert(platforms_map.get(key, 0.0)) - deduction, 0.0
                            )
                            if updated_val <= 1e-9:
                                platforms_map.pop(key, None)
                            else:
                                platforms_map[key] = updated_val

                entry["platform_count"] = len(platforms_map)

    consolidated_assets = aggregate_perp_positions(consolidated_assets_raw)
    non_stable_assets = aggregate_perp_positions(non_stable_assets_raw, include_non_stable=True)
    stable_assets = {symbol: deepcopy(data) for symbol, data in stable_assets_raw.items()}
    reserve_assets = {symbol: deepcopy(data) for symbol, data in reserve_assets_raw.items()}

    # Main metrics at the top
    total_portfolio_value = safe_float_convert(exposure_data.get("total_portfolio_value", 0))
    stable_value = safe_float_convert(exposure_data.get("stable_value", 0))
    non_stable_value = safe_float_convert(exposure_data.get("non_stable_value", 0))
    neutral_count = int(exposure_data.get("neutral_asset_count", 0) or 0)

    # Calculate actual percentages based on categorized assets only
    categorized_value = stable_value + non_stable_value

    if categorized_value > 0:
        actual_stable_pct = (stable_value / categorized_value) * 100
        actual_non_stable_pct = (non_stable_value / categorized_value) * 100
    else:
        actual_stable_pct = 0
        actual_non_stable_pct = 0

    # Check if we have significant neutral assets (CEX mixed)
    margin_offsets = _collect_cex_margin_offsets(consolidated_assets, reserve_assets)
    if margin_offsets:
        _apply_margin_offsets(consolidated_assets, margin_offsets, total_portfolio_value)
        _apply_margin_offsets(non_stable_assets, margin_offsets, total_portfolio_value)
        _apply_margin_offsets(stable_assets, margin_offsets, total_portfolio_value)
        stable_value = max(
            stable_value
            - sum(safe_float_convert(info.get("total", 0.0)) for info in margin_offsets.values()),
            0.0,
        )
        categorized_value = stable_value + non_stable_value
        if categorized_value > 0:
            actual_stable_pct = (stable_value / categorized_value) * 100
            actual_non_stable_pct = (non_stable_value / categorized_value) * 100
        else:
            actual_stable_pct = 0
            actual_non_stable_pct = 0

    neutral_value = safe_float_convert(total_portfolio_value - categorized_value)
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

    # Clean summary box - use offset-adjusted values
    print(f"\n{theme.PRIMARY}📊 PORTFOLIO RISK PROFILE{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")

    # Get offset-adjusted values from portfolio metrics
    adjusted_portfolio_value = safe_float_convert(
        portfolio_metrics.get("adjusted_portfolio_value", total_portfolio_value)
    )
    balance_offset_raw = portfolio_metrics.get("balance_offset", 0.0)
    balance_offset = (
        safe_float_convert(balance_offset_raw) if balance_offset_raw is not None else 0.0
    )

    # If offset not found in portfolio_metrics, try loading from offset file
    if balance_offset == 0.0:
        try:
            import json
            import os

            with open("refer/portfolio_offset.json", "r") as f:
                offset_data = json.load(f)
                balance_offset = offset_data.get("balance_offset", 0.0)
                # Calculate adjusted value if not available
                if adjusted_portfolio_value == total_portfolio_value and balance_offset != 0:
                    adjusted_portfolio_value = total_portfolio_value - balance_offset
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Use defaults

    # If offset exists (positive or negative), treat absolute value as additional stable assets on obscure chains
    # Negative offset means adjusted portfolio is smaller, but we still account for the obscure chain assets
    adjusted_stable_value = (
        stable_value + abs(balance_offset) if balance_offset != 0 else stable_value
    )

    # Calculate portfolio sum as: Stable Assets + Non-Stable Assets + Offset (very simple as requested)
    portfolio_sum = safe_float_convert(stable_value + non_stable_value + abs(balance_offset))

    # Recalculate percentages based on portfolio sum
    if portfolio_sum > 0:
        adjusted_stable_pct = (adjusted_stable_value / portfolio_sum) * 100
        adjusted_non_stable_pct = (non_stable_value / portfolio_sum) * 100
        if has_neutral:
            adjusted_neutral_pct = (neutral_value / portfolio_sum) * 100
    else:
        adjusted_stable_pct = 0
        adjusted_non_stable_pct = 0
        adjusted_neutral_pct = 0 if has_neutral else 0

    offset = safe_float_convert(balance_offset)

    print(f"Portfolio Sum:      {theme.ACCENT}{format_currency(portfolio_sum)}{theme.RESET}")

    if balance_offset != 0:
        print(
            f"Stable Assets (offset adjusted): {theme.SUCCESS}{format_currency(adjusted_stable_value)}{theme.RESET} {theme.SUBTLE}({safe_float_convert(adjusted_stable_pct):.1f}%){theme.RESET}"
        )
        print(f"  └─ Includes {format_currency(abs(balance_offset))} from offsets")
    else:
        print(
            f"Stable Assets:      {theme.SUCCESS}{format_currency(adjusted_stable_value)}{theme.RESET} {theme.SUBTLE}({safe_float_convert(adjusted_stable_pct):.1f}%){theme.RESET}"
        )

    if offset != 0:
        offset_prefix = "-" if offset > 0 else "+"
        print(
            f"{offset_prefix} Offsets: {format_currency(abs(offset), color=theme.WARNING if offset > 0 else theme.SUCCESS)}"
        )

    print(
        f"Non-Stable Assets:  {theme.WARNING}{format_currency(non_stable_value)}{theme.RESET} {theme.SUBTLE}({safe_float_convert(adjusted_non_stable_pct):.1f}%){theme.RESET}"
    )
    if has_neutral:
        print(
            f"CEX Mixed Assets:   {theme.SUBTLE}{format_currency(neutral_value)}{theme.RESET} {theme.SUBTLE}(composition unknown){theme.RESET}"
        )

    (
        non_margin_non_stable,
        margin_exposure_breakdown,
        total_margin_exposure,
        total_margin_unrealized_pnl,
    ) = _compute_margin_breakdown(exposure_data)

    margin_exposure_breakdown.sort(key=lambda entry: entry.get("exposure", 0.0), reverse=True)

    polymarket_entry = (
        consolidated_assets.get("POLYMARKET_POSITIONS")
        or non_stable_assets.get("POLYMARKET_POSITIONS")
    )
    polymarket_exposure = safe_float_convert(
        polymarket_entry.get("total_value_usd", 0.0) if polymarket_entry else 0.0
    )
    polymarket_exposure = max(polymarket_exposure, 0.0)

    total_exposure = non_margin_non_stable + total_margin_exposure
    total_exposure_ex_poly = max(total_exposure - polymarket_exposure, 0.0)
    total_exposure_pct = (total_exposure / portfolio_sum * 100) if portfolio_sum > 0 else 0.0
    total_exposure_ex_poly_pct = (
        (total_exposure_ex_poly / portfolio_sum * 100) if portfolio_sum > 0 else 0.0
    )
    print(
        f"Total Exposure:     {theme.ACCENT}{format_currency(total_exposure)}{theme.RESET} "
        f"{theme.SUBTLE}({total_exposure_pct:.1f}% of portfolio){theme.RESET}"
    )
    if polymarket_exposure > 0:
        print(
            f"{theme.SUBTLE}   ↳ Excl. Polymarket:{theme.RESET} "
            f"{theme.ACCENT}{format_currency(total_exposure_ex_poly)}{theme.RESET} "
            f"{theme.SUBTLE}({total_exposure_ex_poly_pct:.1f}% of portfolio){theme.RESET}"
        )
    if non_margin_non_stable > 0 or margin_exposure_breakdown:
        print(f"{theme.SUBTLE}   Exposure Breakdown:{theme.RESET}")
        if non_margin_non_stable > 0:
            print(
                f"    • Spot & other: {theme.ACCENT}{format_currency(non_margin_non_stable)}{theme.RESET}"
            )
            if polymarket_exposure > 0:
                other_spot = max(non_margin_non_stable - polymarket_exposure, 0.0)
                print(
                    f"      ├─ Polymarket markets: {theme.ACCENT}{format_currency(polymarket_exposure)}{theme.RESET}"
                )
                print(
                    f"      └─ Other spot assets: {theme.ACCENT}{format_currency(other_spot)}{theme.RESET}"
                )
        for entry in margin_exposure_breakdown:
            net_qty = safe_float_convert(entry.get("net_qty", 0.0))
            abs_qty = safe_float_convert(entry.get("abs_qty", 0.0))
            platform_sources = entry.get("platforms") or []
            platform_label = ", ".join(platform_sources) if platform_sources else "Perp"
            symbol = entry.get("symbol") or "UNKNOWN"
            price_ref = safe_float_convert(entry.get("avg_price", 0.0))
            margin_value = max(safe_float_convert(entry.get("margin", 0.0)), 0.0)
            notional_value = max(safe_float_convert(entry.get("notional", 0.0)), 0.0)
            pnl_value = safe_float_convert(entry.get("pnl", 0.0))
            exposure_value = safe_float_convert(entry.get("exposure", 0.0))
            if exposure_value <= 0 and margin_value <= 0:
                continue

            if abs(net_qty) <= 1e-6:
                direction_word = "Hedged"
                units_display = f"{abs_qty:,.4f}".rstrip("0").rstrip(".")
            else:
                direction_word = "Short" if net_qty < 0 else "Long"
                units_display = f"{abs(net_qty):,.4f}".rstrip("0").rstrip(".")

            if price_ref > 0:
                price_text = f"(@ ${price_ref:,.4f})"
            else:
                price_text = "(@ N/A)"

            if abs(pnl_value) > 1e-6:
                pnl_color = theme.SUCCESS if pnl_value >= 0 else theme.ERROR
                pnl_str = f" ({pnl_color}{format_currency(pnl_value)}{theme.RESET})"
            else:
                pnl_str = f" ({theme.SUBTLE}$0.00{theme.RESET})"

            if direction_word == "Hedged":
                direction_text = f"{theme.SUBTLE}{direction_word} ({units_display}){theme.RESET}"
            else:
                direction_text = f"{theme.ACCENT}{direction_word} {units_display}{theme.RESET}"

            breakdown_line = (
                f"    • {platform_label} {symbol}: {direction_text} "
                f"{theme.SUBTLE}{price_text}{theme.RESET} → "
                f"{theme.SUBTLE}Notional{theme.RESET} {theme.ACCENT}{format_currency(exposure_value)}{theme.RESET}{pnl_str}"
            )
            if margin_value > 0:
                breakdown_line += f" {theme.SUBTLE}[Margin Collateral {format_currency(margin_value)}]{theme.RESET}"
            if notional_value > 0 and abs(notional_value - exposure_value) > 1e-6:
                breakdown_line += f" {theme.SUBTLE}[Gross Notional {format_currency(notional_value)}]{theme.RESET}"
            print(breakdown_line)

    # Update risk assessment based on adjusted percentages
    if categorized_value > 0:
        # Use adjusted non-stable percentage for risk calculation
        effective_non_stable_pct = adjusted_non_stable_pct
        if effective_non_stable_pct < 30:
            updated_risk_icon = "🟢"
            updated_risk_text = "Conservative"
        elif effective_non_stable_pct < 70:
            updated_risk_icon = "🟡"
            updated_risk_text = "Balanced"
        else:
            updated_risk_icon = "🔴"
            updated_risk_text = "Aggressive"

        print(
            f"Risk Level:         {updated_risk_icon} {theme.ACCENT}{updated_risk_text}{theme.RESET}"
        )
    else:
        print(f"Risk Level:         {theme.SUBTLE}⚪ Unknown (mostly CEX mixed){theme.RESET}")

    # Asset breakdown - simplified table format
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
        headers = ["Asset", "USD Value", "Total Amount", "Price", "% Portfolio", "Type", "PnL"]

        assets_displayed = 0
        for symbol, asset_data in sorted_assets:
            value = safe_float_convert(asset_data.get("total_value_usd", 0))

            # Skip dust tokens with value < $1
            if value < 1.0:
                continue

            metadata = asset_data.get("metadata", {}) or {}
            is_margin_position = bool(metadata.get("is_margin_position"))
            is_margin_reserve = bool(metadata.get("is_margin_reserve"))
            if is_margin_reserve and value < 10.0:
                continue

            # Stop after showing 15 significant assets
            if assets_displayed >= 15:
                break

            assets_displayed += 1
            portfolio_pct = safe_float_convert(asset_data.get("percentage_of_portfolio", 0))
            is_stable = asset_data.get("is_stable")
            platforms = asset_data.get("platforms", {})
            is_margin_asset = is_margin_position or is_margin_reserve
            base_label = metadata.get("display_name") or symbol
            if is_margin_position:
                display_symbol = f"{base_label} (Margin)"
            elif is_margin_reserve:
                display_symbol = f"{base_label} (Margin Reserve)"
            else:
                display_symbol = base_label

            # Get quantity and price info
            quantity_raw = asset_data.get("total_quantity", 0)
            quantity = safe_float_convert(quantity_raw)
            price_raw = asset_data.get("current_price")
            current_price = None if price_raw in (None, "") else safe_float_convert(price_raw)

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

            if is_margin_asset:
                asset_type = f"{theme.ACCENT}{'Margin Reserve' if is_margin_reserve else 'Margin'}{theme.RESET}"

            # Format quantity display - don't show quantity for stablecoins
            if is_margin_asset or is_stable is True:
                # For stablecoins or margin entries, don't repeat the quantity
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
            if is_margin_asset or is_stable is True:
                # For stablecoins/margin entries, don't show price info
                price_info = ""
            elif current_price is not None and current_price > 0:
                if current_price >= 1:
                    price_info = f" @ ${current_price:,.2f}"
                else:
                    price_info = f" @ ${current_price:.6f}".rstrip("0").rstrip(".")
            else:
                price_info = ""

            margin_details = metadata.get("margin_underlying_details") or []
            margin_total_pnl = sum(
                safe_float_convert(item.get("unrealized_pnl", 0)) for item in margin_details
            )
            if is_margin_asset:
                if abs(margin_total_pnl) < 1e-6:
                    pnl_display = f"{theme.SUBTLE}$0.00{theme.RESET}"
                else:
                    pnl_color = theme.SUCCESS if margin_total_pnl >= 0 else theme.ERROR
                    pnl_display = f"{pnl_color}{format_currency(margin_total_pnl)}{theme.RESET}"
            else:
                pnl_display = f"{theme.SUBTLE}—{theme.RESET}"

            table_data.append(
                [
                    f"{stability_icon} {theme.ACCENT}{display_symbol}{theme.RESET}",
                    f"{theme.PRIMARY}{format_currency(value)}{theme.RESET}",
                    qty_display,
                    price_info,
                    f"{theme.SUBTLE}{portfolio_pct:.1f}%{theme.RESET}",
                    asset_type,
                    pnl_display,
                ]
            )

        print(tabulate(table_data, headers=headers, tablefmt="simple", stralign="left"))

        # Show detailed platform breakdown for significant assets (>$1 value)
        print(f"\n{theme.PRIMARY}📍 MAJOR ASSET BREAKDOWN{theme.RESET}")
        print(f"{theme.SUBTLE}{'─' * 25}{theme.RESET}")

        major_assets = [
            (symbol, data) for symbol, data in sorted_assets if data.get("total_value_usd", 0) > 1
        ]

        if major_assets:
            for symbol, asset_data in major_assets:
                platforms = asset_data.get("platforms", {})
                asset_value = safe_float_convert(asset_data.get("total_value_usd", 0))
                quantity = safe_float_convert(asset_data.get("total_quantity", 0))
                price_raw = asset_data.get("current_price")
                current_price = (
                    safe_float_convert(price_raw) if price_raw not in (None, "") else None
                )
                portfolio_pct = safe_float_convert(asset_data.get("percentage_of_portfolio", 0))
                is_stable = asset_data.get("is_stable")
                metadata = asset_data.get("metadata", {}) or {}
                is_margin_position = bool(metadata.get("is_margin_position"))
                is_margin_reserve = bool(metadata.get("is_margin_reserve"))
                if is_margin_reserve and asset_value < 10.0:
                    continue
                is_margin_asset = is_margin_position or is_margin_reserve
                base_label = metadata.get("display_name") or symbol
                if is_margin_position:
                    display_symbol = f"{base_label} (Margin)"
                elif is_margin_reserve:
                    display_symbol = f"{base_label} (Margin Reserve)"
                else:
                    display_symbol = base_label

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

                margin_header_pnl = ""
                if is_margin_position:
                    margin_details = metadata.get("margin_underlying_details") or []
                    total_margin_pnl = sum(
                        safe_float_convert(item.get("unrealized_pnl", 0)) for item in margin_details
                    )
                    if abs(total_margin_pnl) < 1e-6:
                        margin_header_pnl = f" | P&L {theme.SUBTLE}$0.00{theme.RESET}"
                    else:
                        pnl_color = theme.SUCCESS if total_margin_pnl >= 0 else theme.ERROR
                        margin_header_pnl = (
                            f" | P&L {pnl_color}{format_currency(total_margin_pnl)}{theme.RESET}"
                        )
                print(
                    f"\n{theme.ACCENT}{display_symbol}{theme.RESET} ({portfolio_pct:.1f}% of portfolio{price_info}){margin_header_pnl}"
                )
                if is_margin_position and metadata.get("perp_sources"):
                    sources_str = ", ".join(metadata.get("perp_sources"))
                    print(f"    {theme.SUBTLE}Sources: {sources_str}{theme.RESET}")

                # Sort platforms by value
                sorted_platforms = sorted(
                    platforms.items(), key=lambda x: safe_float_convert(x[1]), reverse=True
                )

                for platform, platform_value in sorted_platforms:
                    # Calculate quantity for this platform (proportional)
                    platform_value = safe_float_convert(platform_value)
                    total_asset_value = asset_value if asset_value > 0 else 1
                    platform_pct = platform_value / total_asset_value
                    platform_quantity = quantity * platform_pct

                    if is_margin_asset:
                        label = "Margin" if is_margin_position else "Margin Reserve"
                        print(
                            f"  └─ {theme.SUBTLE}{platform:<15}{theme.RESET}: {theme.ACCENT}{label} {format_currency(platform_value)}{theme.RESET}"
                        )
                        continue

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

                if is_margin_position:
                    detailed_positions = metadata.get("margin_underlying_details") or []
                    margin_details = metadata.get("margin_underlyings", {}) or {}
                    if detailed_positions:
                        print(f"    {theme.SUBTLE}Underlying Positions:{theme.RESET}")
                        sorted_positions = sorted(
                            detailed_positions,
                            key=lambda item: -abs(safe_float_convert(item.get("margin_value", 0))),
                        )
                        max_details = 6
                        for detail in sorted_positions[:max_details]:
                            symbol = detail.get("symbol") or "UNKNOWN"
                            platform_name = (
                                detail.get("platform") or metadata.get("source_platform") or "Perp"
                            )
                            platform_tag = f"{theme.SUBTLE}[{platform_name}]{theme.RESET}"
                            direction_label = (detail.get("direction") or "").lower()
                            if direction_label == "long":
                                direction_display = f"{theme.SUCCESS}Long{theme.RESET}"
                            elif direction_label == "short":
                                direction_display = f"{theme.ERROR}Short{theme.RESET}"
                            else:
                                direction_display = None

                            size_value = detail.get("abs_size")
                            if size_value is None:
                                size_value = detail.get("size") or detail.get("position")
                            abs_size = abs(safe_float_convert(size_value, 0.0))
                            if abs_size >= 1:
                                size_str = f"{abs_size:,.4f}".rstrip("0").rstrip(".")
                            elif abs_size > 0:
                                size_str = f"{abs_size:.8f}".rstrip("0").rstrip(".")
                            else:
                                size_str = None

                            notional = abs(safe_float_convert(detail.get("notional_value", 0)))
                            if notional <= 0 and abs_size > 0:
                                price_hint = safe_float_convert(
                                    detail.get("mark_price")
                                    or detail.get("entry_price")
                                    or detail.get("market_price")
                                    or detail.get("price"),
                                    0.0,
                                )
                                if price_hint > 0:
                                    notional = abs_size * price_hint

                            margin_value = safe_float_convert(detail.get("margin_value", 0))
                            pnl_value = safe_float_convert(detail.get("unrealized_pnl", 0))

                            primary_parts: List[str] = []
                            if direction_display:
                                primary_parts.append(direction_display)
                            if size_str:
                                primary_parts.append(f"{size_str} {symbol}")
                            else:
                                primary_parts.append(symbol)
                            primary_text = " ".join(part for part in primary_parts if part).strip()

                            extras: List[str] = []
                            if notional > 0:
                                extras.append(f"≈ {format_currency(notional)}")
                            if margin_value > 0:
                                extras.append(f"margin {format_currency(margin_value)}")
                            if abs(pnl_value) >= 1e-6:
                                pnl_color = theme.SUCCESS if pnl_value >= 0 else theme.ERROR
                                extras.append(
                                    f"P&L {pnl_color}{format_currency(pnl_value)}{theme.RESET}"
                                )

                            if extras:
                                print(
                                    f"      • {platform_tag} {primary_text} | {' • '.join(extras)}"
                                )
                            else:
                                print(f"      • {platform_tag} {primary_text}")
                        if len(sorted_positions) > max_details:
                            remaining = len(sorted_positions) - max_details
                            print(
                                f"      • … {remaining} additional position{'s' if remaining != 1 else ''}"
                            )
                    elif margin_details:
                        print(f"    {theme.SUBTLE}Underlying Positions:{theme.RESET}")
                        for underlying, underlying_value in sorted(
                            margin_details.items(), key=lambda x: -abs(x[1])
                        ):
                            print(f"      • {underlying}: {format_currency(underlying_value)}")
        else:
            print(f"{theme.SUBTLE}No significant assets (>$1 value) to break down{theme.RESET}")

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
        stable_assets_map = stable_assets
        if stable_assets_map and stable_value > 0:
            stable_pct_of_total = (
                (stable_value / total_portfolio_value * 100) if total_portfolio_value else 0
            )
            print(f"\n{theme.PRIMARY}🔒 STABLE ASSET COMPOSITION{theme.RESET}")
            print(
                f"{theme.SUBTLE}Total: {format_currency(stable_value)} ({stable_pct_of_total:.1f}% of portfolio){theme.RESET}"
            )
            print(f"{theme.SUBTLE}{'─' * 30}{theme.RESET}")

            sorted_stable = sorted(
                [(symbol, data) for symbol, data in stable_assets_map.items()],
                key=lambda x: x[1].get("total_value_usd", 0),
                reverse=True,
            )

            stable_table = []
            for symbol, asset_data in sorted_stable[:12]:
                value = safe_float_convert(asset_data.get("total_value_usd", 0))
                if value <= 0:
                    continue
                metadata = asset_data.get("metadata", {}) or {}
                if bool(metadata.get("is_margin_reserve")) and value < 10.0:
                    continue
                stable_pct = (value / stable_value * 100) if stable_value > 0 else 0
                portfolio_pct = safe_float_convert(asset_data.get("percentage_of_portfolio", 0))
                quantity = safe_float_convert(asset_data.get("total_quantity", 0))
                if quantity > 0:
                    if quantity >= 1:
                        qty_display = f"{quantity:,.2f}".rstrip("0").rstrip(".")
                    else:
                        qty_display = f"{quantity:.6f}".rstrip("0").rstrip(".")
                    quantity_str = f"{theme.ACCENT}{qty_display} {symbol}{theme.RESET}"
                else:
                    quantity_str = f"{theme.SUBTLE}—{theme.RESET}"

                stable_table.append(
                    [
                        f"{theme.ACCENT}{symbol}{theme.RESET}",
                        f"{theme.PRIMARY}{format_currency(value)}{theme.RESET}",
                        quantity_str,
                        f"{theme.SUCCESS}{stable_pct:.1f}%{theme.RESET}",
                        f"{theme.SUBTLE}{portfolio_pct:.1f}%{theme.RESET}",
                    ]
                )

            if stable_table:
                stable_headers = ["Asset", "Value", "Holdings", "% of Stable", "% of Portfolio"]
                print(
                    tabulate(
                        stable_table, headers=stable_headers, tablefmt="simple", stralign="left"
                    )
                )
                if len(sorted_stable) > 12:
                    remaining = len(sorted_stable) - 12
                    remaining_value = sum(
                        data.get("total_value_usd", 0) for _, data in sorted_stable[12:]
                    )
                    print(
                        f"{theme.SUBTLE}... and {remaining} smaller stable assets worth {format_currency(remaining_value)}{theme.RESET}"
                    )
            else:
                print(
                    f"{theme.SUBTLE}No stable assets above the $1 threshold to display{theme.RESET}"
                )

        if non_stable_assets and non_stable_value > 0:
            print(f"\n{theme.PRIMARY}⚡ NON-STABLE ASSET COMPOSITION{theme.RESET}")
            print(
                f"{theme.SUBTLE}Total: {format_currency(non_stable_value)} ({actual_non_stable_pct:.1f}% of portfolio){theme.RESET}"
            )
            print(f"{theme.SUBTLE}{'─' * 30}{theme.RESET}")
            if actual_non_stable_pct <= 10:
                print(
                    f"{theme.SUBTLE}Note: Non-stable allocation is below 10%, showing full details for clarity{theme.RESET}"
                )

            # Sort non-stable assets by their percentage within the non-stable portion
            sorted_non_stable = sorted(
                [(symbol, data) for symbol, data in non_stable_assets.items()],
                key=lambda x: x[1].get("percentage_of_non_stable", 0),
                reverse=True,
            )

            # Enhanced table format for volatile assets
            volatile_table_data = []
            for symbol, asset_data in sorted_non_stable[:12]:  # Show top 12
                non_stable_composition_pct = safe_float_convert(
                    asset_data.get("percentage_of_non_stable", 0)
                )
                portfolio_pct = safe_float_convert(asset_data.get("percentage_of_portfolio", 0))
                value = safe_float_convert(asset_data.get("total_value_usd", 0))
                metadata = asset_data.get("metadata", {}) or {}
                is_margin_position = bool(metadata.get("is_margin_position"))
                base_label = metadata.get("display_name") or symbol
                display_symbol = f"{base_label} (Margin)" if is_margin_position else base_label

                # Get quantity and price info
                quantity = safe_float_convert(asset_data.get("total_quantity", 0))
                price_raw = asset_data.get("current_price")
                current_price = (
                    safe_float_convert(price_raw) if price_raw not in (None, "") else None
                )

                # Concentration warning icons
                if non_stable_composition_pct > 40:
                    risk_icon = f"{theme.ERROR}🔥{theme.RESET}"
                elif non_stable_composition_pct > 25:
                    risk_icon = f"{theme.WARNING}⚠️{theme.RESET}"
                else:
                    risk_icon = f"{theme.SUCCESS}✓{theme.RESET}"

                # Format quantity and price
                qty_price_str = ""
                if is_margin_position:
                    qty_price_str = f"Margin {format_currency(value)}"
                elif quantity > 0:
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
                        qty_price_str = f"{qty_display} {base_label.lower()}"
                else:
                    qty_price_str = "—"

                volatile_table_data.append(
                    [
                        f"{theme.ACCENT}{display_symbol}{theme.RESET}",
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
                top_metadata = top_data.get("metadata", {}) or {}
                top_base_label = top_metadata.get("display_name") or top_symbol
                top_display_symbol = (
                    f"{top_base_label} (Margin)"
                    if top_metadata.get("is_margin_position")
                    else top_base_label
                )
                top_pct = top_data.get("percentage_of_non_stable", 0)
                if top_pct > 50:
                    print(
                        f"\n{theme.WARNING}⚠️  {top_display_symbol} dominates non-stable holdings ({top_pct:.1f}%){theme.RESET}"
                    )
                elif len(sorted_non_stable) > 10:
                    print(
                        f"\n{theme.SUCCESS}✓ Well-diversified across {len(sorted_non_stable)} non-stable assets{theme.RESET}"
                    )
                else:
                    print(
                        f"\n{theme.INFO}ℹ️  {len(sorted_non_stable)} non-stable assets tracked{theme.RESET}"
                    )

        # # Enhanced portfolio validation with gap analysis (temporarily disabled)
        # displayed_total = sum(
        #     asset_data.get('total_value_usd', 0)
        #     for _, asset_data in sorted_assets
        #     if asset_data.get('total_value_usd', 0) >= 1.0
        # )  # Only count non-dust assets displayed
        # total_all_assets = sum(
        #     asset_data.get('total_value_usd', 0) for _, asset_data in sorted_assets
        # )
        # portfolio_gap = total_portfolio_value - total_all_assets
        #
        # debug_info = exposure_data.get('debug_info', {})
        # scaling_factor_raw = debug_info.get('scaling_factor_applied', 1.0)
        # scaling_factor = safe_float_convert(scaling_factor_raw, 1.0)
        #
        # print(f"\n{theme.INFO}📊 PORTFOLIO VALIDATION & GAP ANALYSIS{theme.RESET}")
        # print(f"─────────────────────────────────────────")
        # print(f"Total Portfolio:      {format_currency(total_portfolio_value)}")
        # print(f"Sum of All Assets:    {format_currency(total_all_assets)}")
        # print(f"Gap/Difference:       {format_currency(portfolio_gap)}")
        #
        # if scaling_factor != 1.0:
        #     print(f"Scaling Applied:      {theme.WARNING}{scaling_factor:.3f}x{theme.RESET}")
        #
        # if abs(portfolio_gap) > 10:  # Alert if gap > $10
        #     gap_pct = (
        #         (abs(portfolio_gap) / total_portfolio_value * 100)
        #         if total_portfolio_value > 0
        #         else 0
        #     )
        #     print(f"Gap Percentage:       {theme.WARNING}⚠️  {gap_pct:.2f}%{theme.RESET}")
        #
        #     # Provide gap analysis
        #     print(f"\n{theme.WARNING}🔍 POSSIBLE GAP SOURCES:{theme.RESET}")
        #     print(f"  • Assets below $0.01 dust threshold")
        #    print(f"  • Exchange assets without detailed breakdown")
        #     print(f"  • Untracked DeFi positions or LP tokens")
        #     print(f"  • Cross-chain bridge assets")
        #     print(f"  • Manual adjustments or offsets applied")
        # else:
        #     print(f"Gap Status:           {theme.SUCCESS}✅ Values match (within tolerance){theme.RESET}")
        #
        # # Count only non-dust assets displayed
        # non_dust_count = len(
        #     [asset for _, asset in sorted_assets if asset.get('total_value_usd', 0) >= 1.0]
        # )
        # displayed_count = min(15, non_dust_count)
        # print(
        #     f"Top {displayed_count} Assets Total: {format_currency(displayed_total)} "
        #     f"({(displayed_total/total_portfolio_value*100):.1f}% of portfolio)"
        # )

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
            top_asset_pct = safe_float_convert(top_asset[1].get("percentage_of_portfolio", 0))
            top_metadata = top_asset[1].get("metadata", {}) or {}
            top_base_label = top_metadata.get("display_name") or top_asset[0]
            top_display_symbol = (
                f"{top_base_label} (Margin)"
                if top_metadata.get("is_margin_position")
                else top_base_label
            )

            if top_asset_pct > 40:
                print(
                    f"  {theme.WARNING}• High concentration in {top_display_symbol} ({top_asset_pct:.1f}%){theme.RESET}"
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


# -------------------------
# Helper: Detailed protocol view
# -------------------------


def _display_protocol_details(protocol: Dict[str, Any]):
    """Display detailed positions for a single protocol."""
    from utils.display_theme import theme
    from utils.helpers import format_currency
    from tabulate import tabulate
    import os

    # Clear screen for a focused view
    os.system("clear" if os.name == "posix" else "cls")

    name = protocol.get("name", "Unknown")
    chain = protocol.get("chain", "unknown").capitalize()
    total_val = protocol.get("total_value", protocol.get("value", 0))

    print(f"{theme.PRIMARY}🏛️ PROTOCOL DETAILS{theme.RESET}")
    print(f"{theme.ACCENT}{name}{theme.RESET} on {chain}")
    print(f"Total Value: {theme.SUCCESS}{format_currency(total_val)}{theme.RESET}\n")

    positions = protocol.get("positions", [])

    if positions:
        pos_table = []
        for pos in positions:
            label = pos.get("label", "")
            asset = pos.get("asset", "")
            usd_val = pos.get("usd_value", pos.get("value", 0))
            header_type = pos.get("header_type", "")
            pos_table.append(
                [
                    label,
                    asset,
                    header_type if header_type else "-",
                    format_currency(usd_val),
                ]
            )

        print(
            tabulate(
                pos_table, headers=["Label", "Asset/Amount", "Type", "USD Value"], tablefmt="simple"
            )
        )
    else:
        print(f"{theme.SUBTLE}No position information available{theme.RESET}")

    input(f"\n{theme.SUBTLE}Press Enter to return...{theme.RESET}")


def _display_merged_stable_breakdown(tokens: List[Dict[str, Any]], protocols: List[Dict[str, Any]]):
    """Helper function to display merged stable breakdown from both token and protocol data."""
    from utils.display_theme import theme
    from utils.helpers import format_currency

    stable_bases = {
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
    stable_patterns = ["USD"]
    chain_icons = {
        "Ethereum": "⟠",
        "Arbitrum": "🔵",
        "Polygon": "🟣",
        "Base": "🔷",
        "Optimism": "🔴",
        "Solana": "🌞",
        "Sonic": "⚡",
        "Soneium": "🟡",
        "Linea": "🟢",
        "Ink": "🖋️",
        "Lisk": "🔶",
        "Unichain": "🦄",
        "Gravity": "🌍",
        "Lens": "📷",
    }

    def _normalize_symbol(symbol: str) -> str:
        return (symbol or "").replace(" ", "").upper()

    def _is_base_stable(token: str) -> bool:
        clean = _normalize_symbol(token)
        if not clean:
            return False
        if clean in stable_bases:
            return True
        for pat in stable_patterns:
            if pat in clean:
                return True
        return False

    def is_stable(symbol: str) -> bool:
        clean = _normalize_symbol(symbol)
        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            return bool(parts) and all(_is_base_stable(part) for part in parts)
        if "/" in clean or "-" in clean:
            return False
        return _is_base_stable(clean)

    def is_pool_stable(symbol: str) -> bool:
        clean = _normalize_symbol(symbol)
        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            return bool(parts) and all(_is_base_stable(part) for part in parts)
        if "/" in clean or "-" in clean:
            return False
        return _is_base_stable(clean)

    # 1. Collect stable tokens from token breakdown
    token_stables = {}  # symbol -> {chain -> usd}
    for token in tokens:
        symbol = token.get("symbol", "").upper()
        chain = token.get("chain", "unknown").capitalize()
        value = token.get("usd_value", 0)
        category = token.get("category", "other_crypto")
        is_token_stable = is_stable(symbol) or category == "stable"
        if is_token_stable:
            if symbol not in token_stables:
                token_stables[symbol] = {}
            if chain not in token_stables[symbol]:
                token_stables[symbol][chain] = 0
            token_stables[symbol][chain] += value

    # 2. Collect stable tokens from protocol breakdown
    protocol_stables = {}  # symbol -> {chain -> {(protocol, type) -> usd}}
    protocol_stable_totals = {}  # symbol -> {chain -> total_usd}
    for proto in protocols:
        chain = proto.get("chain", "unknown").capitalize()
        proto_name = proto.get("name", "Unknown")
        positions = proto.get("positions", []) or []
        position_total_value = 0.0
        for pos in positions:
            raw = (pos.get("asset") or pos.get("label") or "").strip()
            parts = raw.split()
            if len(parts) > 1 and any(ch.isdigit() for ch in parts[0]):
                symbol = parts[-1].upper()
            else:
                symbol = raw.upper()
            usd = pos.get("usd_value", pos.get("value", 0)) or 0
            try:
                usd = float(usd)
            except Exception:
                usd = 0
            position_total_value += usd
            ptype = pos.get("header_type", "-") or "-"
            is_borrowed = str(ptype).lower() == "borrowed"
            if is_pool_stable(symbol):
                if symbol not in protocol_stables:
                    protocol_stables[symbol] = {}
                    protocol_stable_totals[symbol] = {}
                if chain not in protocol_stables[symbol]:
                    protocol_stables[symbol][chain] = {}
                    protocol_stable_totals[symbol][chain] = 0
                if is_borrowed:
                    protocol_stables[symbol][chain][(proto_name, ptype)] = (
                        protocol_stables[symbol][chain].get((proto_name, ptype), 0) - usd
                    )
                    protocol_stable_totals[symbol][chain] -= usd
                else:
                    protocol_stables[symbol][chain][(proto_name, ptype)] = (
                        protocol_stables[symbol][chain].get((proto_name, ptype), 0) + usd
                    )
                    protocol_stable_totals[symbol][chain] += usd

        if (proto_name or "").lower() == "hyperliquid":
            total_value = proto.get("total_value", proto.get("value", 0)) or 0
            residual = total_value - position_total_value
            if residual > 0.01:
                symbol = "USDC"
                if symbol not in protocol_stables:
                    protocol_stables[symbol] = {}
                    protocol_stable_totals[symbol] = {}
                if chain not in protocol_stables[symbol]:
                    protocol_stables[symbol][chain] = {}
                    protocol_stable_totals[symbol][chain] = 0
                label = f"{proto_name} Collateral"
                protocol_stables[symbol][chain][(label, "Collateral")] = (
                    protocol_stables[symbol][chain].get((label, "Collateral"), 0) + residual
                )
                protocol_stable_totals[symbol][chain] += residual

    # 3. Merge both datasets by summing values for each (symbol, chain)
    merged_stables = (
        {}
    )  # symbol -> {chain -> {"usd": float, "protocols": dict, "has_protocol_data": bool, "token_usd": float}}
    all_symbols = set(token_stables.keys()) | set(protocol_stables.keys())
    for symbol in all_symbols:
        merged_stables[symbol] = {}
        chains = set(token_stables.get(symbol, {}).keys()) | set(
            protocol_stables.get(symbol, {}).keys()
        )
        for chain in chains:
            token_usd = token_stables.get(symbol, {}).get(chain, 0)
            proto_usd = protocol_stable_totals.get(symbol, {}).get(chain, 0)
            total_usd = token_usd + proto_usd
            has_protocol_data = chain in protocol_stables.get(symbol, {}) and bool(
                protocol_stables[symbol][chain]
            )
            protocols_dict = (
                protocol_stables.get(symbol, {}).get(chain, {}) if has_protocol_data else {}
            )
            merged_stables[symbol][chain] = {
                "usd": total_usd,
                "protocols": protocols_dict,
                "has_protocol_data": has_protocol_data,
                "token_usd": token_usd,  # Store token-only value for display
            }

    # 4. Display merged stable breakdown
    if merged_stables:
        print(f"\n{theme.INFO}Stablecoin Breakdown (Merged):{theme.RESET}")
        symbol_totals = {}
        dust_stables_total = 0.0
        for symbol in merged_stables:
            symbol_total = sum(chain_data["usd"] for chain_data in merged_stables[symbol].values())
            if abs(symbol_total) < 10:  # Use absolute value for dust threshold
                dust_stables_total += symbol_total
            else:
                symbol_totals[symbol] = symbol_total

        # Calculate total excluding negative values for percentage calculation
        total_stables_positive = sum(value for value in symbol_totals.values() if value > 0)
        total_stables = sum(symbol_totals.values()) + dust_stables_total

        for symbol, symbol_total in sorted(
            symbol_totals.items(), key=lambda x: (x[1] < 0, -abs(x[1]))
        ):
            # Check if token has negative total value
            is_negative_token = symbol_total < 0
            symbol_pct = (
                round(symbol_total / total_stables_positive * 100, 1)
                if total_stables_positive and not is_negative_token
                else 0
            )
            chains_for_symbol = list(merged_stables[symbol].keys())
            if len(chains_for_symbol) == 1:
                chain = chains_for_symbol[0]
                chain_data = merged_stables[symbol][chain]
                icon = chain_icons.get(chain, "🔗")
                if chain_data["has_protocol_data"] and chain_data["protocols"]:
                    if len(chain_data["protocols"]) == 1:
                        (pname, ptype), p_usd = next(iter(chain_data["protocols"].items()))
                        # Check if we also have token data to show
                        token_only_usd = chain_data["token_usd"]
                        if token_only_usd > 0:
                            if is_negative_token:
                                print(
                                    f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])}"
                                )
                                print(f"    • {pname} [{ptype}]: {format_currency(p_usd)}")
                                print(f"    • {symbol}: {format_currency(token_only_usd)}")
                            else:
                                print(
                                    f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                                )
                                p_pct = (
                                    (p_usd / chain_data["usd"] * 100) if chain_data["usd"] else 0
                                )
                                token_pct = (
                                    (token_only_usd / chain_data["usd"] * 100)
                                    if chain_data["usd"]
                                    else 0
                                )
                                print(
                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                )
                                print(
                                    f"    • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                )
                        else:
                            if is_negative_token:
                                print(
                                    f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])} ← {pname} [{ptype}]"
                                )
                            else:
                                print(
                                    f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)  ← {pname} [{ptype}]"
                                )
                    else:
                        if is_negative_token:
                            print(
                                f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])}"
                            )
                        else:
                            print(
                                f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                            )
                        for (pname, ptype), p_usd in sorted(
                            chain_data["protocols"].items(), key=lambda x: -x[1]
                        ):
                            has_negative_protocols = any(
                                (
                                    p_data < 0
                                    if isinstance(p_data, (int, float))
                                    else (
                                        p_data.get("usd", 0) if isinstance(p_data, dict) else p_data
                                    )
                                    < 0
                                )
                                for p_data in chain_data["protocols"].values()
                            )
                            if is_negative_token or has_negative_protocols:
                                print(f"    • {pname} [{ptype}]: {format_currency(p_usd)}")
                            else:
                                p_pct = (
                                    (p_usd / chain_data["usd"] * 100) if chain_data["usd"] else 0
                                )
                                print(
                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                )
                        # Show token-only value if it exists
                        token_only_usd = chain_data["token_usd"]
                        if token_only_usd > 0:
                            if is_negative_token:
                                print(f"    • {symbol}: {format_currency(token_only_usd)}")
                            else:
                                token_pct = (
                                    (token_only_usd / chain_data["usd"] * 100)
                                    if chain_data["usd"]
                                    else 0
                                )
                                print(
                                    f"    • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                )
                else:
                    if is_negative_token:
                        print(f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])}")
                    else:
                        print(
                            f"  {symbol} ({icon} {chain}): {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                        )
            else:
                if is_negative_token:
                    print(f"  {symbol}: {format_currency(symbol_total)}")
                else:
                    print(f"  {symbol}: {format_currency(symbol_total)} ({symbol_pct:.1f}%)")
                for chain in sorted(
                    chains_for_symbol, key=lambda c: merged_stables[symbol][c]["usd"], reverse=True
                ):
                    chain_data = merged_stables[symbol][chain]
                    chain_usd = chain_data["usd"]
                    if chain_usd <= 0:
                        continue
                    chain_pct = (
                        (chain_usd / symbol_total * 100)
                        if symbol_total and not is_negative_token
                        else 0
                    )
                    icon = chain_icons.get(chain, "🔗")
                    if chain_data["has_protocol_data"] and chain_data["protocols"]:
                        if len(chain_data["protocols"]) == 1:
                            (pname, ptype), p_usd = next(iter(chain_data["protocols"].items()))
                            # Check if we also have token data to show
                            token_only_usd = chain_data["token_usd"]
                            if token_only_usd > 0:
                                if is_negative_token:
                                    print(f"    {icon} {chain}: {format_currency(chain_usd)}")
                                    print(f"      • {pname} [{ptype}]: {format_currency(p_usd)}")
                                    print(f"      • {symbol}: {format_currency(token_only_usd)}")
                                else:
                                    print(
                                        f"    {icon} {chain}: {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                                    )
                                    p_pct = (p_usd / chain_usd * 100) if chain_usd else 0
                                    token_pct = (
                                        (token_only_usd / chain_usd * 100) if chain_usd else 0
                                    )
                                    print(
                                        f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                    )
                                    print(
                                        f"      • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                    )
                            else:
                                if is_negative_token:
                                    print(
                                        f"    {icon} {chain}: {format_currency(chain_usd)} ← {pname} [{ptype}]"
                                    )
                                else:
                                    print(
                                        f"    {icon} {chain}: {format_currency(chain_usd)} ({chain_pct:.1f}%) ← {pname} [{ptype}]"
                                    )
                        else:
                            if is_negative_token:
                                print(f"    {icon} {chain}: {format_currency(chain_usd)}")
                            else:
                                print(
                                    f"    {icon} {chain}: {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                                )
                            # Show protocol entries
                            for (pname, ptype), p_data in sorted(
                                chain_data["protocols"].items(),
                                key=lambda x: -x[1]["usd"] if isinstance(x[1], dict) else -x[1],
                            ):
                                # Extract USD value from p_data
                                p_usd = p_data["usd"] if isinstance(p_data, dict) else p_data
                                has_negative_protocols = any(
                                    (
                                        p_data < 0
                                        if isinstance(p_data, (int, float))
                                        else (
                                            p_data.get("usd", 0)
                                            if isinstance(p_data, dict)
                                            else p_data
                                        )
                                        < 0
                                    )
                                    for p_data in chain_data["protocols"].values()
                                )
                                if is_negative_token or has_negative_protocols:
                                    print(f"      • {pname} [{ptype}]: {format_currency(p_usd)}")
                                else:
                                    p_pct = (p_usd / chain_usd * 100) if chain_usd else 0
                                    print(
                                        f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                    )
                            # Show token-only value if it exists
                            token_only_usd = chain_data["token_usd"]
                            if token_only_usd > 0:
                                if is_negative_token:
                                    print(f"      • {symbol}: {format_currency(token_only_usd)}")
                                else:
                                    token_pct = (
                                        (token_only_usd / chain_usd * 100) if chain_usd else 0
                                    )
                                    print(
                                        f"      • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                    )
                    else:
                        if is_negative_token:
                            print(f"    {icon} {chain}: {format_currency(chain_usd)}")
                        else:
                            print(
                                f"    {icon} {chain}: {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                            )
        if dust_stables_total > 0:
            dust_percentage = (
                (dust_stables_total / total_stables_positive * 100)
                if total_stables_positive and dust_stables_total > 0
                else 0
            )
            print(
                f"  {theme.SUBTLE}Dust stables (<$10): {format_currency(dust_stables_total)} ({dust_percentage:.1f}%){theme.RESET}"
            )
        print(f"  {theme.ACCENT}Total Stables: {format_currency(total_stables)}{theme.RESET}")
        return total_stables
    return 0


def _display_merged_nonstable_breakdown(
    tokens: List[Dict[str, Any]],
    protocols: List[Dict[str, Any]],
    *,
    stable_total: Optional[float] = None,
):
    """Helper function to display merged non-stable breakdown from both token and protocol data."""
    from utils.display_theme import theme
    from utils.helpers import format_currency

    stable_bases = {
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
    stable_patterns = ["USD"]
    chain_icons = {
        "Ethereum": "⟠",
        "Arbitrum": "🔵",
        "Polygon": "🟣",
        "Base": "🔷",
        "Optimism": "🔴",
        "Solana": "🌞",
        "Sonic": "⚡",
        "Soneium": "🟡",
        "Linea": "🟢",
        "Ink": "🖋️",
        "Lisk": "🔶",
        "Unichain": "🦄",
        "Gravity": "🌍",
        "Lens": "📷",
    }

    def _normalize_symbol(symbol: str) -> str:
        return (symbol or "").replace(" ", "").upper()

    def _is_base_stable(token: str) -> bool:
        clean = _normalize_symbol(token)
        if not clean:
            return False
        if clean in stable_bases:
            return True
        for pat in stable_patterns:
            if pat in clean:
                return True
        return False

    def is_stable(symbol: str) -> bool:
        clean = _normalize_symbol(symbol)
        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            return bool(parts) and all(_is_base_stable(part) for part in parts)
        if "/" in clean or "-" in clean:
            return False
        return _is_base_stable(clean)

    def is_pool_stable(symbol: str) -> bool:
        clean = _normalize_symbol(symbol)
        if "+" in clean:
            parts = [part for part in clean.split("+") if part]
            return bool(parts) and all(_is_base_stable(part) for part in parts)
        if "/" in clean or "-" in clean:
            return False
        return _is_base_stable(clean)

    compute_stable_total = stable_total is None
    computed_stable_total = 0.0

    # 1. Collect non-stable tokens from token breakdown
    token_nonstables = {}  # symbol -> {chain -> {"usd": float, "amt": float}}
    for token in tokens:
        symbol = token.get("symbol", "").upper()
        chain = token.get("chain", "unknown").capitalize()
        value = token.get("usd_value", 0)
        amount = token.get("amount", 0)
        category = token.get("category", "other_crypto")

        # Check if token is stable
        token_is_stable = is_stable(symbol) or category == "stable"

        # Only collect non-stable tokens
        if token_is_stable:
            if compute_stable_total:
                computed_stable_total += value
            continue

        if symbol not in token_nonstables:
            token_nonstables[symbol] = {}
        if chain not in token_nonstables[symbol]:
            token_nonstables[symbol][chain] = {"usd": 0, "amt": 0}
        token_nonstables[symbol][chain]["usd"] += value
        token_nonstables[symbol][chain]["amt"] += amount

    # 2. Collect non-stable tokens from protocol breakdown
    protocol_nonstables = {}  # symbol -> {chain -> {(protocol, type) -> usd}}
    protocol_nonstable_totals = {}  # symbol -> {chain -> total_usd}
    for proto in protocols:
        chain = proto.get("chain", "unknown").capitalize()
        proto_name = proto.get("name", "Unknown")
        for pos in proto.get("positions", []):
            raw = (pos.get("asset") or pos.get("label") or "").strip()
            parts = raw.split()
            if len(parts) > 1 and any(ch.isdigit() for ch in parts[0]):
                symbol = parts[-1].upper()
            else:
                symbol = raw.upper()
            usd = pos.get("usd_value", pos.get("value", 0)) or 0
            try:
                usd = float(usd)
            except Exception:
                usd = 0

            # Extract amount from protocol position
            amount = pos.get("amount", 0) or 0
            try:
                amount = float(amount)
            except Exception:
                amount = 0

            ptype = pos.get("header_type", "-") or "-"
            is_borrowed = str(ptype).lower() == "borrowed"

            if is_pool_stable(symbol):
                if compute_stable_total:
                    adjustment = -usd if is_borrowed else usd
                    computed_stable_total += adjustment
                continue

            if symbol not in protocol_nonstables:
                protocol_nonstables[symbol] = {}
                protocol_nonstable_totals[symbol] = {}
            if chain not in protocol_nonstables[symbol]:
                protocol_nonstables[symbol][chain] = {}
                protocol_nonstable_totals[symbol][chain] = {"usd": 0, "amt": 0}
            if is_borrowed:
                protocol_nonstables[symbol][chain][(proto_name, ptype)] = protocol_nonstables[
                    symbol
                ][chain].get((proto_name, ptype), {"usd": 0, "amt": 0})
                protocol_nonstables[symbol][chain][(proto_name, ptype)]["usd"] -= usd
                protocol_nonstables[symbol][chain][(proto_name, ptype)]["amt"] -= amount
                protocol_nonstable_totals[symbol][chain]["usd"] -= usd
                protocol_nonstable_totals[symbol][chain]["amt"] -= amount
            else:
                protocol_nonstables[symbol][chain][(proto_name, ptype)] = protocol_nonstables[
                    symbol
                ][chain].get((proto_name, ptype), {"usd": 0, "amt": 0})
                protocol_nonstables[symbol][chain][(proto_name, ptype)]["usd"] += usd
                protocol_nonstables[symbol][chain][(proto_name, ptype)]["amt"] += amount
                protocol_nonstable_totals[symbol][chain]["usd"] += usd
                protocol_nonstable_totals[symbol][chain]["amt"] += amount

    if compute_stable_total:
        stable_total = computed_stable_total
    stable_total = stable_total or 0.0

    # 3. Merge both datasets by summing values for each (symbol, chain)
    merged_nonstables = (
        {}
    )  # symbol -> {chain -> {"usd": float, "amt": float, "protocols": dict, "has_protocol_data": bool, "token_usd": float, "token_amt": float}}
    all_symbols = set(token_nonstables.keys()) | set(protocol_nonstables.keys())
    for symbol in all_symbols:
        merged_nonstables[symbol] = {}
        chains = set(token_nonstables.get(symbol, {}).keys()) | set(
            protocol_nonstables.get(symbol, {}).keys()
        )
        for chain in chains:
            token_data = token_nonstables.get(symbol, {}).get(chain, {"usd": 0, "amt": 0})
            token_usd = token_data["usd"]
            token_amt = token_data["amt"]
            proto_data = protocol_nonstable_totals.get(symbol, {}).get(chain, {"usd": 0, "amt": 0})
            proto_usd = proto_data["usd"]
            proto_amt = proto_data["amt"]
            total_usd = token_usd + proto_usd
            total_amt = token_amt + proto_amt
            has_protocol_data = chain in protocol_nonstables.get(symbol, {}) and bool(
                protocol_nonstables[symbol][chain]
            )
            protocols_dict = (
                protocol_nonstables.get(symbol, {}).get(chain, {}) if has_protocol_data else {}
            )
            merged_nonstables[symbol][chain] = {
                "usd": total_usd,
                "amt": total_amt,
                "protocols": protocols_dict,
                "has_protocol_data": has_protocol_data,
                "token_usd": token_usd,
                "token_amt": token_amt,
            }

    # 4. Display merged non-stable breakdown
    if merged_nonstables:
        print(f"\n{theme.INFO}Non-Stable Token Breakdown (Merged):{theme.RESET}")
        symbol_totals = {}
        dust_nonstables_total = 0.0
        for symbol in merged_nonstables:
            symbol_total = sum(
                chain_data["usd"] for chain_data in merged_nonstables[symbol].values()
            )
            if abs(symbol_total) < 10:  # Use absolute value for dust threshold - increased to $10
                dust_nonstables_total += symbol_total
            else:
                symbol_totals[symbol] = symbol_total

        # Calculate total excluding negative values for percentage calculation
        total_nonstables_positive = sum(value for value in symbol_totals.values() if value > 0)
        total_nonstables = sum(symbol_totals.values()) + dust_nonstables_total

        # Fix percentage calculation: Use positive-only base when there are negative values
        # This ensures positive token percentages add up to 100% instead of over 100%
        has_negative_values = any(value < 0 for value in symbol_totals.values())
        if has_negative_values:
            # When there are negative values, use only positive values for percentage base
            percentage_base = total_nonstables_positive + max(0, dust_nonstables_total)
        else:
            # When all values are positive, use the full total
            percentage_base = (
                total_nonstables if total_nonstables > 0 else total_nonstables_positive
            )

        for symbol, symbol_total in sorted(
            symbol_totals.items(), key=lambda x: (x[1] < 0, -abs(x[1]))
        ):
            # Check if token has negative total value
            is_negative_token = symbol_total < 0
            symbol_pct = (
                round(symbol_total / percentage_base * 100, 1)
                if percentage_base and not is_negative_token
                else 0
            )

            # Calculate total amount for this symbol across all chains
            total_amt = sum(chain_data["amt"] for chain_data in merged_nonstables[symbol].values())
            amt_str = (
                f"{total_amt:.6f}".rstrip("0").rstrip(".")
                if total_amt < 1
                else f"{total_amt:,.4f}".rstrip("0").rstrip(".")
            )

            chains_for_symbol = list(merged_nonstables[symbol].keys())
            if len(chains_for_symbol) == 1:
                chain = chains_for_symbol[0]
                chain_data = merged_nonstables[symbol][chain]
                icon = chain_icons.get(chain, "🔗")
                if chain_data["has_protocol_data"] and chain_data["protocols"]:
                    if len(chain_data["protocols"]) == 1:
                        (pname, ptype), p_data = next(iter(chain_data["protocols"].items()))
                        p_usd = p_data["usd"] if isinstance(p_data, dict) else p_data
                        # Check if we also have token data to show
                        token_only_usd = chain_data["token_usd"]
                        if token_only_usd > 0:
                            if is_negative_token:
                                print(
                                    f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                                )
                                print(f"    • {pname} [{ptype}]: {format_currency(p_usd)}")
                                print(f"    • {symbol}: {format_currency(token_only_usd)}")
                            else:
                                print(
                                    f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                                )
                                p_pct = (
                                    (p_usd / chain_data["usd"] * 100) if chain_data["usd"] else 0
                                )
                                token_pct = (
                                    (token_only_usd / chain_data["usd"] * 100)
                                    if chain_data["usd"]
                                    else 0
                                )
                                print(
                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                )
                                print(
                                    f"    • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                )
                        else:
                            if is_negative_token:
                                print(
                                    f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ← {pname} [{ptype}]"
                                )
                            else:
                                print(
                                    f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%) ← {pname} [{ptype}]"
                                )
                    else:
                        print(
                            f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                        )
                        for (pname, ptype), p_data in sorted(
                            chain_data["protocols"].items(),
                            key=lambda x: -x[1]["usd"] if isinstance(x[1], dict) else -x[1],
                        ):
                            p_usd = p_data["usd"] if isinstance(p_data, dict) else p_data
                            if is_negative_token:
                                print(f"    • {pname} [{ptype}]: {format_currency(p_usd)}")
                            else:
                                p_pct = (
                                    (p_usd / chain_data["usd"] * 100) if chain_data["usd"] else 0
                                )
                                print(
                                    f"    • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                )
                        # Show token-only value if it exists
                        token_only_usd = chain_data["token_usd"]
                        if token_only_usd > 0:
                            if is_negative_token:
                                print(f"    • {symbol}: {format_currency(token_only_usd)}")
                            else:
                                token_pct = (
                                    (token_only_usd / chain_data["usd"] * 100)
                                    if chain_data["usd"]
                                    else 0
                                )
                                print(
                                    f"    • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                )
                else:
                    if is_negative_token:
                        print(
                            f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])}"
                        )
                    else:
                        print(
                            f"  {symbol} ({icon} {chain}): {amt_str} - {format_currency(chain_data['usd'])} ({symbol_pct:.1f}%)"
                        )
            else:
                print(
                    f"  {symbol}: {amt_str} - {format_currency(symbol_total)} ({symbol_pct:.1f}%)"
                )

                # Separate chains into displayed and "other" chains
                displayed_chains = []
                other_chains_usd = 0
                other_chains_amt = 0

                for chain in sorted(
                    chains_for_symbol,
                    key=lambda c: merged_nonstables[symbol][c]["usd"],
                    reverse=True,
                ):
                    chain_data = merged_nonstables[symbol][chain]
                    chain_usd = chain_data["usd"]
                    if chain_usd == 0:  # Only skip if exactly zero, not negative
                        continue

                    # Show top chains individually, group small ones as "Other chains"
                    # For negative positions, always show them individually
                    if len(displayed_chains) < 10 and (abs(chain_usd) >= 1 or chain_usd < 0):
                        displayed_chains.append(chain)
                    else:
                        other_chains_usd += chain_usd
                        other_chains_amt += chain_data["amt"]

                # Display individual chains
                for chain in displayed_chains:
                    chain_data = merged_nonstables[symbol][chain]
                    chain_usd = chain_data["usd"]
                    chain_pct = (
                        (chain_usd / symbol_total * 100)
                        if symbol_total and not is_negative_token
                        else 0
                    )
                    icon = chain_icons.get(chain, "🔗")
                    chain_amt = chain_data["amt"]
                    camt_str = (
                        f"{chain_amt:.6f}".rstrip("0").rstrip(".")
                        if chain_amt < 1
                        else f"{chain_amt:,.4f}".rstrip("0").rstrip(".")
                    )

                    if chain_data["has_protocol_data"] and chain_data["protocols"]:
                        if len(chain_data["protocols"]) == 1:
                            (pname, ptype), p_data = next(iter(chain_data["protocols"].items()))
                            p_usd = p_data["usd"] if isinstance(p_data, dict) else p_data
                            # Check if we also have token data to show
                            token_only_usd = chain_data["token_usd"]
                            if token_only_usd > 0:
                                if is_negative_token:
                                    print(
                                        f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)}"
                                    )
                                    print(f"      • {pname} [{ptype}]: {format_currency(p_usd)}")
                                    print(f"      • {symbol}: {format_currency(token_only_usd)}")
                                else:
                                    print(
                                        f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                                    )
                                    p_pct = (p_usd / chain_usd * 100) if chain_usd else 0
                                    token_pct = (
                                        (token_only_usd / chain_usd * 100) if chain_usd else 0
                                    )
                                    print(
                                        f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                    )
                                    print(
                                        f"      • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                    )
                            else:
                                if is_negative_token:
                                    print(
                                        f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)} ← {pname} [{ptype}]"
                                    )
                                else:
                                    print(
                                        f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)} ({chain_pct:.1f}%) ← {pname} [{ptype}]"
                                    )
                        else:
                            if is_negative_token:
                                print(
                                    f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)}"
                                )
                            else:
                                print(
                                    f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                                )
                            # Show protocol entries
                            for (pname, ptype), p_data in sorted(
                                chain_data["protocols"].items(),
                                key=lambda x: -x[1]["usd"] if isinstance(x[1], dict) else -x[1],
                            ):
                                p_usd = p_data["usd"] if isinstance(p_data, dict) else p_data
                                has_negative_protocols = any(
                                    (
                                        p_data < 0
                                        if isinstance(p_data, (int, float))
                                        else (
                                            p_data.get("usd", 0)
                                            if isinstance(p_data, dict)
                                            else p_data
                                        )
                                        < 0
                                    )
                                    for p_data in chain_data["protocols"].values()
                                )
                                if is_negative_token or has_negative_protocols:
                                    print(f"      • {pname} [{ptype}]: {format_currency(p_usd)}")
                                else:
                                    p_pct = (p_usd / chain_usd * 100) if chain_usd else 0
                                    print(
                                        f"      • {pname} [{ptype}]: {format_currency(p_usd)} ({p_pct:.1f}%)"
                                    )
                            # Show token-only value if it exists
                            token_only_usd = chain_data["token_usd"]
                            if token_only_usd > 0:
                                if is_negative_token:
                                    print(f"      • {symbol}: {format_currency(token_only_usd)}")
                                else:
                                    token_pct = (
                                        (token_only_usd / chain_usd * 100) if chain_usd else 0
                                    )
                                    print(
                                        f"      • {symbol}: {format_currency(token_only_usd)} ({token_pct:.1f}%)"
                                    )
                    else:
                        if is_negative_token:
                            print(f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)}")
                        else:
                            print(
                                f"    {icon} {chain}: {camt_str} - {format_currency(chain_usd)} ({chain_pct:.1f}%)"
                            )

                # Display "Other chains" if there are any
                if other_chains_usd > 0:
                    if is_negative_token:
                        print(f"    Other chains: {format_currency(other_chains_usd)}")
                    else:
                        other_pct = (other_chains_usd / symbol_total * 100) if symbol_total else 0
                        print(
                            f"    Other chains: {format_currency(other_chains_usd)} ({other_pct:.1f}%)"
                        )

        if dust_nonstables_total > 0:
            dust_percentage = (
                round(dust_nonstables_total / percentage_base * 100, 1)
                if percentage_base and dust_nonstables_total > 0
                else 0
            )
            print(
                f"  {theme.SUBTLE}Dust tokens (<$10): {format_currency(dust_nonstables_total)} ({dust_percentage:.1f}%){theme.RESET}"
            )
        print(f"  {theme.ACCENT}Total Non-Stable: {format_currency(total_nonstables)}{theme.RESET}")

        # New Summary Statistics replacing the old non-stable summary
        print(f"\n{theme.INFO}📊 Portfolio Summary Statistics:{theme.RESET}")

        total_non_stable_value = total_nonstables
        total_portfolio_value = stable_total + total_non_stable_value

        # Portfolio Breakdown Summary
        print(f"\n  📈 Portfolio Breakdown Summary:")

        # Calculate net values for non-stable tokens with ETH/WETH netting
        net_symbol_totals = {}

        # Define wrapped token mappings
        wrapped_mappings = {
            "WETH": "ETH",
            "WBTC": "BTC",
            "WMATIC": "MATIC",
            "WBNB": "BNB",
            "WAVAX": "AVAX",
            "WFTM": "FTM",
            "WONE": "ONE",
        }

        # First, get all symbols and their net values (including borrowed positions)
        for symbol, chains in merged_nonstables.items():
            net_value = 0.0
            net_amount = 0.0
            for chain, data in chains.items():
                net_value += data["usd"]
                net_amount += data["amt"]

            # Map wrapped tokens to their base tokens
            base_symbol = wrapped_mappings.get(symbol, symbol)

            # Only include if net value is meaningful
            if abs(net_value) >= 0.01:  # Avoid dust
                if base_symbol in net_symbol_totals:
                    net_symbol_totals[base_symbol] += net_value
                else:
                    net_symbol_totals[base_symbol] = net_value

        # Filter for tokens above $250 threshold (using absolute value for filtering but keeping sign)
        filtered_nonstables = {
            symbol: value for symbol, value in net_symbol_totals.items() if abs(value) >= 250
        }

        if filtered_nonstables:
            print(f"\n    📈 Major Non-Stable Positions (>$250):")
            for symbol, net_value in sorted(
                filtered_nonstables.items(), key=lambda x: abs(x[1]), reverse=True
            ):
                if total_portfolio_value > 0:
                    portfolio_percentage = abs(net_value) / total_portfolio_value * 100

                    # Calculate combined amount for base symbol (including wrapped versions)
                    total_amount = 0.0
                    symbols_to_check = [symbol] + [
                        k for k, v in wrapped_mappings.items() if v == symbol
                    ]

                    for check_symbol in symbols_to_check:
                        if check_symbol in merged_nonstables:
                            total_amount += sum(
                                chain_data["amt"]
                                for chain_data in merged_nonstables[check_symbol].values()
                            )

                    amount_str = (
                        f"{total_amount:.6f}".rstrip("0").rstrip(".")
                        if total_amount < 1
                        else f"{total_amount:,.4f}".rstrip("0").rstrip(".")
                    )

                    # Handle borrowed/negative positions
                    if net_value < 0:
                        print(
                            f"      • {symbol}: {amount_str} - {format_currency(net_value)} ({portfolio_percentage:.1f}% borrowed)"
                        )
                    else:
                        print(
                            f"      • {symbol}: {amount_str} - {format_currency(net_value)} ({portfolio_percentage:.1f}%)"
                        )
        else:
            print(f"\n    📈 Major Non-Stable Positions (>$250): None")

        # Calculate other tokens (below $250 threshold) accounting for borrowed positions
        other_tokens_total = sum(
            value for symbol, value in net_symbol_totals.items() if abs(value) < 250
        )
        if abs(other_tokens_total) > 0.01:
            other_tokens_count = len([v for v in net_symbol_totals.values() if abs(v) < 250])
            if total_portfolio_value > 0:
                other_portfolio_percentage = abs(other_tokens_total) / total_portfolio_value * 100
                if other_tokens_total < 0:
                    print(
                        f"    📊 Other tokens (<$250): {other_tokens_count} positions - {format_currency(other_tokens_total)} ({other_portfolio_percentage:.1f}% net borrowed)"
                    )
                else:
                    print(
                        f"    📊 Other tokens (<$250): {other_tokens_count} positions - {format_currency(other_tokens_total)} ({other_portfolio_percentage:.1f}%)"
                    )

        # Portfolio Distribution Summary
        if total_portfolio_value > 0:
            stable_percentage = stable_total / total_portfolio_value * 100
            nonstable_percentage = total_non_stable_value / total_portfolio_value * 100
            calculated_nonstable_total = sum(net_symbol_totals.values()) or total_non_stable_value
            calculated_total = stable_total + calculated_nonstable_total

            print(f"\n    💰 Portfolio Distribution Summary:")
            print(
                f"      🔒 Stablecoins: {format_currency(stable_total)} ({stable_percentage:.1f}%)"
            )
            print(
                f"      📈 Non-Stable: {format_currency(calculated_nonstable_total)} ({nonstable_percentage:.1f}%)"
            )
            print(f"      📊 Total Portfolio: {format_currency(calculated_total)}")

        # Additional useful summaries
        print(f"\n  🎯 Additional Insights:")

        # Chain diversification insight (portfolio-relative)
        chain_totals = {}

        # Add non-stable token values by chain
        for symbol, chains in merged_nonstables.items():
            for chain, data in chains.items():
                if chain not in chain_totals:
                    chain_totals[chain] = 0
                chain_totals[chain] += data["usd"]

        # Add stable token values by chain (recalculate from tokens and protocols)
        # From tokens
        for token in tokens:
            symbol = token.get("symbol", "").upper()
            chain = token.get("chain", "unknown").capitalize()
            value = token.get("usd_value", 0)
            category = token.get("category", "other_crypto")
            if is_stable(symbol) or category == "stable":
                if chain not in chain_totals:
                    chain_totals[chain] = 0
                chain_totals[chain] += value

        # From protocols
        for proto in protocols:
            chain = proto.get("chain", "unknown").capitalize()
            for pos in proto.get("positions", []):
                raw = (pos.get("asset") or pos.get("label") or "").strip()
                parts = raw.split()
                if len(parts) > 1 and any(ch.isdigit() for ch in parts[0]):
                    symbol = parts[-1].upper()
                else:
                    symbol = raw.upper()
                usd = pos.get("usd_value", pos.get("value", 0)) or 0
                try:
                    usd = float(usd)
                except Exception:
                    usd = 0
                ptype = pos.get("header_type", "-") or "-"
                is_borrowed = str(ptype).lower() == "borrowed"
                if is_pool_stable(symbol):
                    if chain not in chain_totals:
                        chain_totals[chain] = 0
                    if is_borrowed:
                        chain_totals[chain] -= usd
                    else:
                        chain_totals[chain] += usd

        if chain_totals and total_portfolio_value > 0:
            top_chain = max(chain_totals.items(), key=lambda x: abs(x[1]))
            chain_percentage = abs(top_chain[1]) / total_portfolio_value * 100
            chain_icon = {
                "Ethereum": "⟠",
                "Arbitrum": "🔵",
                "Polygon": "🟣",
                "Base": "🔷",
                "Optimism": "🔴",
                "Solana": "🌞",
                "Sonic": "⚡",
                "Soneium": "🟡",
                "Linea": "🟢",
                "Ink": "🖋️",
                "Lisk": "🔶",
                "Unichain": "🦄",
                "Gravity": "🌍",
                "Lens": "📷",
            }.get(top_chain[0], "🔗")
            print(
                f"    • Primary Chain: {chain_icon} {top_chain[0]} ({format_currency(top_chain[1])}, {chain_percentage:.1f}% of portfolio)"
            )

        return total_nonstables
