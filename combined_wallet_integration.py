#!/usr/bin/env python3
"""
Combined Wallet Integration
===========================
Integration functions for combined wallet functionality in the portfolio analyzer.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from combine_wallet_data import load_and_combine_wallets, save_combined_data
from ui.display_functions import _display_wallet_summary_stats, _display_complete_wallet_details
from utils.display_theme import theme
from utils.helpers import format_currency, print_success, print_error, print_info
from utils.portfolio_summary_extractor import generate_and_save_portfolio_summary


def generate_combined_wallet_json(analysis_folder: str) -> Optional[str]:
    """
    Generate combined wallet JSON for a given analysis folder.
    Also generates and saves Portfolio Summary Statistics for exposure analysis.

    Args:
        analysis_folder: Path to the analysis folder containing wallet breakdown JSONs

    Returns:
        Path to the generated combined JSON file, or None if failed
    """
    try:
        # Find all wallet breakdown JSON files
        wallet_files = []
        for filename in os.listdir(analysis_folder):
            if filename.startswith("wallet_breakdown_") and filename.endswith(".json"):
                wallet_files.append(os.path.join(analysis_folder, filename))

        if not wallet_files:
            print_error("❌ No wallet breakdown files found in analysis folder")
            return None

        wallet_files.sort()

        print_info(f"🔄 Combining {len(wallet_files)} wallet breakdown files...")

        # Load and combine all wallet data
        combined_data = load_and_combine_wallets(wallet_files)

        # Save combined data
        output_file = os.path.join(analysis_folder, "combined_wallet_breakdown.json")
        if save_combined_data(combined_data, output_file):
            print_success(
                f"✅ Combined wallet data saved: {len(wallet_files)} wallets, ${combined_data['total_usd_value']:,.2f} total value"
            )

            # Generate and save Portfolio Summary Statistics for exposure analysis
            print_info("🔄 Generating Portfolio Summary Statistics for exposure analysis...")
            summary_stats_file = generate_and_save_portfolio_summary(output_file, analysis_folder)

            if summary_stats_file:
                print_success(
                    "✅ Portfolio Summary Statistics saved for exposure analysis integration"
                )
            else:
                print_error(
                    "⚠️  Portfolio Summary Statistics generation failed, but combined wallet data is still available"
                )

            return output_file
        else:
            print_error("❌ Failed to save combined wallet data")
            return None

    except Exception as e:
        print_error(f"❌ Error generating combined wallet JSON: {e}")
        return None


def normalize_combined_data_for_display(combined_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize combined wallet data structure to match individual wallet structure.
    Removes extra fields that might cause issues in display functions.

    Args:
        combined_data: Raw combined wallet data

    Returns:
        Normalized data compatible with display functions
    """
    normalized_data = combined_data.copy()

    # Normalize protocols section
    if "protocols" in normalized_data:
        normalized_protocols = []
        for protocol in normalized_data["protocols"]:
            normalized_protocol = protocol.copy()

            # Remove extra fields that display function doesn't expect
            if "source_wallets" in normalized_protocol:
                del normalized_protocol["source_wallets"]

            # Normalize positions
            if "positions" in normalized_protocol:
                normalized_positions = []
                for position in normalized_protocol["positions"]:
                    normalized_position = position.copy()

                    # Remove extra fields from positions
                    extra_fields = ["qty", "balance", "value", "source_wallets"]
                    for field in extra_fields:
                        if field in normalized_position:
                            del normalized_position[field]

                    normalized_positions.append(normalized_position)

                normalized_protocol["positions"] = normalized_positions

            normalized_protocols.append(normalized_protocol)

        normalized_data["protocols"] = normalized_protocols

    # Normalize tokens section (remove source_wallets)
    if "tokens" in normalized_data:
        normalized_tokens = []
        for token in normalized_data["tokens"]:
            normalized_token = token.copy()
            if "source_wallets" in normalized_token:
                del normalized_token["source_wallets"]
            normalized_tokens.append(normalized_token)

        normalized_data["tokens"] = normalized_tokens

    return normalized_data


def display_combined_wallet_analysis(
    combined_file_path: str, portfolio_metrics: Dict[str, Any]
) -> None:
    """
    Display the combined wallet analysis using our enhanced display functions.

    Args:
        combined_file_path: Path to the combined wallet breakdown JSON
        portfolio_metrics: Portfolio metrics for context
    """
    try:
        # Load the combined data
        with open(combined_file_path, "r", encoding="utf-8") as f:
            combined_data = json.load(f)

        # Normalize data structure for display compatibility
        normalized_data = normalize_combined_data_for_display(combined_data)

        # Clear screen for better viewing
        os.system("clear" if os.name == "posix" else "cls")

        print(f"\n{theme.PRIMARY}🎯 COMBINED PORTFOLIO ANALYSIS{theme.RESET}")
        print(f"{theme.SUBTLE}{'=' * 32}{theme.RESET}")

        # Show overview
        total_value = combined_data.get("total_usd_value", 0)
        wallet_count = combined_data.get("wallet_count", 0)
        token_count = len(combined_data.get("tokens", []))
        protocol_count = len(combined_data.get("protocols", []))

        print(f"\n{theme.INFO}📊 Portfolio Overview:{theme.RESET}")
        print(f"  Total Value: {theme.SUCCESS}{format_currency(total_value)}{theme.RESET}")
        print(f"  Wallets Combined: {theme.ACCENT}{wallet_count}{theme.RESET}")
        print(f"  Unique Tokens: {theme.ACCENT}{token_count}{theme.RESET}")
        print(f"  Protocol Positions: {theme.ACCENT}{protocol_count}{theme.RESET}")

        # Show included wallets
        wallets_included = combined_data.get("wallets_included", [])
        if wallets_included:
            print(f"\n{theme.INFO}📋 Included Wallets:{theme.RESET}")
            for i, wallet in enumerate(wallets_included, 1):
                wallet_short = f"{wallet[:8]}...{wallet[-6:]}" if len(wallet) > 14 else wallet
                print(f"  {i}. {wallet_short}")

        print(f"\n{theme.SUBTLE}{'─' * 60}{theme.RESET}")

        # Use the detailed wallet display function with normalized data
        _display_complete_wallet_details(normalized_data, "Combined Portfolio", portfolio_metrics)

    except Exception as e:
        print_error(f"❌ Error displaying combined wallet analysis: {e}")
        input(f"\n{theme.SUBTLE}Press Enter to continue...{theme.RESET}")


def find_most_recent_analysis_folder() -> Optional[str]:
    """
    Find the most recent analysis folder in exported_data.

    Returns:
        Path to the most recent analysis folder, or None if not found
    """
    try:
        exported_data_path = Path("exported_data")
        if not exported_data_path.exists():
            return None

        # Find all analysis folders
        analysis_folders = []
        for item in exported_data_path.iterdir():
            if item.is_dir() and item.name.startswith("analysis_"):
                analysis_folders.append(item)

        if not analysis_folders:
            return None

        # Sort by modification time, most recent first
        analysis_folders.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        return str(analysis_folders[0])

    except Exception:
        return None


def generate_combined_for_current_analysis(portfolio_metrics: Dict[str, Any]) -> Optional[str]:
    """
    Generate combined wallet JSON for the current analysis session.

    Args:
        portfolio_metrics: Portfolio metrics containing analysis folder info

    Returns:
        Path to the generated combined JSON file, or None if failed
    """
    try:
        # Try to get analysis folder from portfolio metrics
        analysis_folder = portfolio_metrics.get("_analysis_folder")

        if not analysis_folder:
            # Fall back to most recent analysis folder
            analysis_folder = find_most_recent_analysis_folder()

        if not analysis_folder:
            print_error("❌ No analysis folder found")
            return None

        return generate_combined_wallet_json(analysis_folder)

    except Exception as e:
        print_error(f"❌ Error generating combined analysis: {e}")
        return None


def check_combined_wallet_availability(analysis_folder: str) -> bool:
    """
    Check if combined wallet data is available for an analysis folder.

    Args:
        analysis_folder: Path to the analysis folder

    Returns:
        True if combined data exists or can be generated, False otherwise
    """
    try:
        # Check if combined file already exists
        combined_file = os.path.join(analysis_folder, "combined_wallet_breakdown.json")
        if os.path.exists(combined_file):
            return True

        # Check if wallet breakdown files exist to generate combined data
        wallet_files = []
        for filename in os.listdir(analysis_folder):
            if filename.startswith("wallet_breakdown_") and filename.endswith(".json"):
                wallet_files.append(filename)

        return len(wallet_files) > 0

    except Exception:
        return False


def get_combined_wallet_file_path(analysis_folder: str) -> Optional[str]:
    """
    Get the path to the combined wallet file, generating it if needed.

    Args:
        analysis_folder: Path to the analysis folder

    Returns:
        Path to the combined wallet file, or None if not available
    """
    try:
        combined_file = os.path.join(analysis_folder, "combined_wallet_breakdown.json")

        # If file exists, return it
        if os.path.exists(combined_file):
            return combined_file

        # Try to generate it
        return generate_combined_wallet_json(analysis_folder)

    except Exception:
        return None
