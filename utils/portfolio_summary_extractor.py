#!/usr/bin/env python3
"""
Portfolio Summary Statistics Extractor
=====================================
Extracts Portfolio Summary Statistics from combined wallet data and saves it
for integration with exposure analysis.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from utils.helpers import print_success, print_error, print_info, format_currency


def extract_portfolio_summary_stats(
    tokens: List[Dict[str, Any]], protocols: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Extract Portfolio Summary Statistics from combined wallet tokens and protocols data.

    Args:
        tokens: List of token data from combined wallet
        protocols: List of protocol data from combined wallet

    Returns:
        Dictionary containing structured portfolio summary statistics
    """
    # Define stable asset detection
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

    def is_token_stable(symbol, category):
        for base in stable_bases:
            if symbol.startswith(base):
                return True
        for pattern in stable_patterns:
            if pattern in symbol:
                return True
        if category == "stable":
            return True
        return False

    def is_pool_stable(symbol: str) -> bool:
        if "+" in symbol:
            parts = [p.strip() for p in symbol.split("+")]
            return all(is_token_stable(part, "other_crypto") for part in parts)
        return is_token_stable(symbol, "other_crypto")

    # Calculate stable total from tokens and protocols
    stable_total = 0.0

    # From tokens
    for token in tokens:
        symbol = token.get("symbol", "").upper()
        value = token.get("usd_value", 0)
        category = token.get("category", "other_crypto")
        if is_token_stable(symbol, category):
            stable_total += value

    # From protocols
    skip_protocols = {"hyperliquid", "lighter"}

    for proto in protocols:
        proto_name = proto.get("name", "")
        if proto_name and proto_name.strip().lower() in skip_protocols:
            continue
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
                if is_borrowed:
                    stable_total -= usd
                else:
                    stable_total += usd

    # Calculate non-stable assets with netting logic
    merged_nonstables = {}

    # Process tokens
    for token in tokens:
        symbol = token.get("symbol", "").upper()
        value = token.get("usd_value", 0)
        amount = token.get("amount", 0)
        category = token.get("category", "other_crypto")
        chain = token.get("chain", "unknown").capitalize()

        # Skip stable tokens
        if is_token_stable(symbol, category):
            continue

        if symbol not in merged_nonstables:
            merged_nonstables[symbol] = {}
        if chain not in merged_nonstables[symbol]:
            merged_nonstables[symbol][chain] = {"usd": 0.0, "amt": 0.0}

        merged_nonstables[symbol][chain]["usd"] += value
        merged_nonstables[symbol][chain]["amt"] += amount

    # Process protocols
    for proto in protocols:
        proto_name = proto.get("name", "")
        if proto_name and proto_name.strip().lower() in skip_protocols:
            continue
        chain = proto.get("chain", "unknown").capitalize()
        for pos in proto.get("positions", []):
            raw = (pos.get("asset") or pos.get("label") or "").strip()
            parts = raw.split()
            if len(parts) > 1 and any(ch.isdigit() for ch in parts[0]):
                symbol = parts[-1].upper()
            else:
                symbol = raw.upper()

            # Skip stable assets
            if is_pool_stable(symbol):
                continue

            usd = pos.get("usd_value", pos.get("value", 0)) or 0
            try:
                usd = float(usd)
            except Exception:
                usd = 0

            amount = pos.get("amount", pos.get("qty", pos.get("balance", 0))) or 0
            try:
                amount = float(amount)
            except Exception:
                amount = 0

            ptype = pos.get("header_type", "-") or "-"
            is_borrowed = str(ptype).lower() == "borrowed"

            if symbol not in merged_nonstables:
                merged_nonstables[symbol] = {}
            if chain not in merged_nonstables[symbol]:
                merged_nonstables[symbol][chain] = {"usd": 0.0, "amt": 0.0}

            if is_borrowed:
                merged_nonstables[symbol][chain]["usd"] -= usd
                merged_nonstables[symbol][chain]["amt"] -= amount
            else:
                merged_nonstables[symbol][chain]["usd"] += usd
                merged_nonstables[symbol][chain]["amt"] += amount

    # Calculate total non-stable value
    total_nonstables = sum(
        sum(chain_data["usd"] for chain_data in chains.values())
        for chains in merged_nonstables.values()
    )

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

    # Filter for major positions above $250 threshold
    major_positions = {}
    other_positions_total = 0.0
    other_positions_count = 0

    for symbol, net_value in net_symbol_totals.items():
        if abs(net_value) >= 250:
            # Calculate combined amount for base symbol (including wrapped versions)
            total_amount = 0.0
            symbols_to_check = [symbol] + [k for k, v in wrapped_mappings.items() if v == symbol]

            for check_symbol in symbols_to_check:
                if check_symbol in merged_nonstables:
                    total_amount += sum(
                        chain_data["amt"] for chain_data in merged_nonstables[check_symbol].values()
                    )

            major_positions[symbol] = {
                "amount": total_amount,
                "usd_value": net_value,
                "is_borrowed": net_value < 0,
            }
        else:
            other_positions_total += net_value
            other_positions_count += 1

    # Calculate total portfolio value
    calculated_nonstable_total = sum(net_symbol_totals.values())
    total_portfolio_value = stable_total + calculated_nonstable_total

    # Chain analysis
    chain_totals = {}

    # Add non-stable token values by chain
    for symbol, chains in merged_nonstables.items():
        for chain, data in chains.items():
            if chain not in chain_totals:
                chain_totals[chain] = 0
            chain_totals[chain] += data["usd"]

    # Add stable token values by chain
    for token in tokens:
        symbol = token.get("symbol", "").upper()
        chain = token.get("chain", "unknown").capitalize()
        value = token.get("usd_value", 0)
        category = token.get("category", "other_crypto")
        if is_token_stable(symbol, category):
            if chain not in chain_totals:
                chain_totals[chain] = 0
            chain_totals[chain] += value

    # Add stable protocol values by chain
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

    # Find primary chain
    primary_chain = None
    primary_chain_value = 0
    primary_chain_percentage = 0

    if chain_totals and total_portfolio_value > 0:
        top_chain = max(chain_totals.items(), key=lambda x: abs(x[1]))
        primary_chain = top_chain[0]
        primary_chain_value = top_chain[1]
        primary_chain_percentage = abs(top_chain[1]) / total_portfolio_value * 100

    # Build the structured data
    portfolio_summary_stats = {
        "timestamp": datetime.now().isoformat(),
        "total_portfolio_value": total_portfolio_value,
        "stable_total": stable_total,
        "non_stable_total": calculated_nonstable_total,
        "stable_percentage": (
            (stable_total / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
        ),
        "non_stable_percentage": (
            (calculated_nonstable_total / total_portfolio_value * 100)
            if total_portfolio_value > 0
            else 0
        ),
        "major_non_stable_positions": major_positions,
        "other_positions": {
            "total_value": other_positions_total,
            "count": other_positions_count,
            "percentage": (
                (abs(other_positions_total) / total_portfolio_value * 100)
                if total_portfolio_value > 0
                else 0
            ),
        },
        "primary_chain": {
            "name": primary_chain,
            "value": primary_chain_value,
            "percentage": primary_chain_percentage,
        },
        "chain_breakdown": chain_totals,
    }

    return portfolio_summary_stats


def save_portfolio_summary_stats(
    summary_stats: Dict[str, Any], analysis_folder: str
) -> Optional[str]:
    """
    Save Portfolio Summary Statistics to JSON file in the analysis folder.

    Args:
        summary_stats: Portfolio summary statistics data
        analysis_folder: Path to the analysis folder

    Returns:
        Path to the saved file, or None if failed
    """
    try:
        output_file = os.path.join(analysis_folder, "portfolio_summary_stats.json")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary_stats, f, indent=2, default=str)

        print_success(f"✅ Portfolio Summary Statistics saved to: {os.path.basename(output_file)}")
        return output_file

    except Exception as e:
        print_error(f"❌ Error saving Portfolio Summary Statistics: {e}")
        return None


def generate_and_save_portfolio_summary(
    combined_wallet_file: str, analysis_folder: str
) -> Optional[str]:
    """
    Generate and save Portfolio Summary Statistics from a combined wallet JSON file.

    Args:
        combined_wallet_file: Path to the combined wallet breakdown JSON file
        analysis_folder: Path to the analysis folder to save the summary stats

    Returns:
        Path to the saved summary stats file, or None if failed
    """
    try:
        # Load combined wallet data
        with open(combined_wallet_file, "r", encoding="utf-8") as f:
            combined_data = json.load(f)

        tokens = combined_data.get("tokens", [])
        protocols = combined_data.get("protocols", [])

        if not tokens and not protocols:
            print_error("❌ No tokens or protocols found in combined wallet data")
            return None

        print_info(
            f"🔄 Extracting Portfolio Summary Statistics from {len(tokens)} tokens and {len(protocols)} protocols..."
        )

        # Extract portfolio summary statistics
        summary_stats = extract_portfolio_summary_stats(tokens, protocols)

        # Add metadata
        summary_stats.update(
            {
                "source_file": os.path.basename(combined_wallet_file),
                "tokens_processed": len(tokens),
                "protocols_processed": len(protocols),
                "wallet_count": combined_data.get("wallet_count", 0),
                "wallets_included": combined_data.get("wallets_included", []),
            }
        )

        # Save to file
        return save_portfolio_summary_stats(summary_stats, analysis_folder)

    except Exception as e:
        print_error(f"❌ Error generating Portfolio Summary Statistics: {e}")
        return None


def load_portfolio_summary_stats(analysis_folder: str) -> Optional[Dict[str, Any]]:
    """
    Load Portfolio Summary Statistics from the analysis folder.

    Args:
        analysis_folder: Path to the analysis folder

    Returns:
        Portfolio summary statistics data, or None if not found
    """
    try:
        summary_file = os.path.join(analysis_folder, "portfolio_summary_stats.json")

        if not os.path.exists(summary_file):
            return None

        with open(summary_file, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print_error(f"❌ Error loading Portfolio Summary Statistics: {e}")
        return None
