#!/usr/bin/env python3
"""
Exposure Recalculator Utility
-----------------------------
Recalculates exposure analysis from saved portfolio analysis JSON files.
Useful for debugging, testing, and updating historical data with new exposure logic.
"""

import json
import os
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.exposure_tracker import ExposureTracker, get_exposure_summary
from utils.helpers import print_success, print_error, print_info, print_warning, format_currency
from colorama import Fore, Style


class ExposureRecalculator:
    """Utility class for recalculating exposure analysis from saved data."""

    def __init__(self):
        self.exposure_tracker = ExposureTracker()

    def get_available_analysis_files(self) -> List[str]:
        """Get list of available analysis files."""
        try:
            files = glob.glob("data/analysis/portfolio_analysis_*.json")
            files.sort(reverse=True)  # Newest first
            return files
        except Exception as e:
            print_error(f"Error finding analysis files: {e}")
            return []

    def load_analysis_file(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Load portfolio analysis data from JSON file."""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            print_error(f"File not found: {filepath}")
            return None
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON in {filepath}: {e}")
            return None
        except Exception as e:
            print_error(f"Error loading {filepath}: {e}")
            return None

    def extract_portfolio_data_for_exposure(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the portfolio data structure needed for exposure analysis."""
        return {
            "adjusted_value": analysis_data.get("adjusted_portfolio_value", 0),
            "total_value": analysis_data.get("total_portfolio_value", 0),
            "wallet_platform_data_raw": analysis_data.get("wallet_platform_data_raw", []),
            "detailed_exchange_data": analysis_data.get("detailed_breakdowns", {}),
            # Add individual balance mappings for fallback processing
            "binance_balance": analysis_data.get("binance", 0) or 0,
            "okx_balance": analysis_data.get("okx", 0) or 0,
            "bybit_balance": analysis_data.get("bybit", 0) or 0,
            "backpack_balance": analysis_data.get("backpack", 0) or 0,
            "ethereum_balance": analysis_data.get("ethereum", 0) or 0,
            "bitcoin_balance": analysis_data.get("bitcoin", 0) or 0,
            "solana_balance": analysis_data.get("solana", 0) or 0,
            "hyperliquid_balance": analysis_data.get("hyperliquid", 0) or 0,
        }

    def recalculate_exposure(
        self, filepath: str, save_back: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Recalculate exposure analysis for a saved portfolio analysis file.

        Args:
            filepath: Path to the portfolio analysis JSON file
            save_back: Whether to save the updated exposure data back to the file

        Returns:
            The new exposure analysis data, or None if failed
        """
        print_info(f"🔄 Recalculating exposure for: {os.path.basename(filepath)}")

        # Load the analysis file
        analysis_data = self.load_analysis_file(filepath)
        if not analysis_data:
            return None

        # Extract portfolio data
        portfolio_data_for_exposure = self.extract_portfolio_data_for_exposure(analysis_data)

        # Show what we're working with
        total_value = portfolio_data_for_exposure.get("total_value", 0)
        print_info(f"💰 Portfolio value: {format_currency(total_value)}")

        # Recalculate exposure
        try:
            new_exposure_analysis = self.exposure_tracker.analyze_portfolio_exposure(
                portfolio_data_for_exposure
            )
            new_exposure_summary = get_exposure_summary(new_exposure_analysis)

            # Display results
            self.display_exposure_comparison(analysis_data, new_exposure_analysis)

            # Save back if requested
            if save_back:
                analysis_data["exposure_analysis"] = new_exposure_analysis
                analysis_data["exposure_summary"] = new_exposure_summary

                try:
                    with open(filepath, "w") as f:
                        json.dump(analysis_data, f, indent=2, default=str)
                    print_success(f"✅ Updated exposure data saved to {os.path.basename(filepath)}")
                except Exception as e:
                    print_error(f"Failed to save updated data: {e}")

            return new_exposure_analysis

        except Exception as e:
            print_error(f"❌ Failed to recalculate exposure: {e}")
            import traceback

            traceback.print_exc()
            return None

    def display_exposure_comparison(
        self, analysis_data: Dict[str, Any], new_exposure: Dict[str, Any]
    ):
        """Display comparison between old and new exposure data."""
        PRIMARY = Fore.WHITE + Style.BRIGHT
        SUCCESS = Fore.GREEN + Style.BRIGHT
        WARNING = Fore.YELLOW
        ERROR = Fore.RED
        ACCENT = Fore.CYAN
        SUBTLE = Style.DIM
        RESET = Style.RESET_ALL

        print(f"\n{PRIMARY}📊 EXPOSURE ANALYSIS RESULTS{RESET}")
        print(f"{SUBTLE}{'=' * 35}{RESET}")

        # Get old exposure data if it exists
        old_exposure = analysis_data.get("exposure_analysis", {})

        # Compare key metrics
        new_non_stable_pct = new_exposure.get("non_stable_percentage", 0)
        new_asset_count = new_exposure.get("asset_count", 0)
        new_stable_count = new_exposure.get("stable_asset_count", 0)
        new_non_stable_count = new_exposure.get("non_stable_asset_count", 0)

        if old_exposure:
            old_non_stable_pct = old_exposure.get("non_stable_percentage", 0)
            old_asset_count = old_exposure.get("asset_count", 0)

            print(f"{ACCENT}COMPARISON WITH PREVIOUS CALCULATION:{RESET}")
            print(
                f"  Assets found:     {old_asset_count} → {new_asset_count} {SUCCESS if new_asset_count > old_asset_count else ''}{'(improved!)' if new_asset_count > old_asset_count else ''}{RESET}"
            )
            print(f"  Non-stable %:     {old_non_stable_pct:.1f}% → {new_non_stable_pct:.1f}%")
            print()

        print(f"{PRIMARY}NEW EXPOSURE ANALYSIS:{RESET}")
        print(
            f"  Total Assets:     {ACCENT}{new_asset_count}{RESET} ({SUCCESS}{new_stable_count} stable{RESET}, {WARNING}{new_non_stable_count} volatile{RESET})"
        )
        print(f"  Non-stable %:     {WARNING}{new_non_stable_pct:.1f}%{RESET}")
        print(
            f"  Stable value:     {SUCCESS}{format_currency(new_exposure.get('stable_value', 0))}{RESET}"
        )
        print(
            f"  Non-stable value: {WARNING}{format_currency(new_exposure.get('non_stable_value', 0))}{RESET}"
        )

        # Show top assets
        consolidated_assets = new_exposure.get("consolidated_assets", {})
        if consolidated_assets:
            print(f"\n{ACCENT}TOP ASSETS:{RESET}")

            # Sort by value
            sorted_assets = sorted(
                consolidated_assets.items(),
                key=lambda x: x[1].get("total_value_usd", 0),
                reverse=True,
            )

            for i, (symbol, asset_data) in enumerate(sorted_assets[:8]):  # Top 8
                value = asset_data.get("total_value_usd", 0)
                portfolio_pct = asset_data.get("percentage_of_portfolio", 0)
                is_stable = asset_data.get("is_stable", False)
                platforms = asset_data.get("platforms", {})

                stability_icon = "🔒" if is_stable else "📈"
                color = SUCCESS if is_stable else WARNING

                platform_str = ", ".join(platforms.keys())
                if len(platform_str) > 30:
                    platform_str = platform_str[:27] + "..."

                print(
                    f"  {stability_icon} {symbol:<8} {color}{format_currency(value):>12}{RESET} "
                    f"{SUBTLE}({portfolio_pct:.1f}%) - {platform_str}{RESET}"
                )

            if len(sorted_assets) > 8:
                remaining = len(sorted_assets) - 8
                remaining_value = sum(asset["total_value_usd"] for _, asset in sorted_assets[8:])
                print(
                    f"  {SUBTLE}... and {remaining} more assets ({format_currency(remaining_value)}){RESET}"
                )

    def recalculate_multiple(
        self, file_pattern: str = None, save_back: bool = False, limit: int = None
    ):
        """Recalculate exposure for multiple files."""
        files = self.get_available_analysis_files()

        if file_pattern:
            files = [f for f in files if file_pattern in f]

        if limit:
            files = files[:limit]

        if not files:
            print_warning("No matching analysis files found.")
            return

        print_info(f"🔄 Recalculating exposure for {len(files)} files...")

        success_count = 0
        for i, filepath in enumerate(files, 1):
            print(f"\n{Fore.CYAN}[{i}/{len(files)}]{Style.RESET_ALL}", end=" ")

            result = self.recalculate_exposure(filepath, save_back)
            if result:
                success_count += 1

        print(
            f"\n{SUCCESS}✅ Successfully recalculated {success_count}/{len(files)} files{Style.RESET_ALL}"
        )


def main():
    """Interactive CLI for exposure recalculation."""
    recalculator = ExposureRecalculator()

    PRIMARY = Fore.WHITE + Style.BRIGHT
    SUCCESS = Fore.GREEN + Style.BRIGHT
    WARNING = Fore.YELLOW
    ERROR = Fore.RED
    ACCENT = Fore.CYAN
    SUBTLE = Style.DIM
    RESET = Style.RESET_ALL

    print(f"\n{PRIMARY}🎯 EXPOSURE RECALCULATOR{RESET}")
    print(f"{SUBTLE}{'=' * 25}{RESET}")

    files = recalculator.get_available_analysis_files()

    if not files:
        print_error("No analysis files found in data/analysis/")
        return

    print(f"{ACCENT}Available analysis files:{RESET}")
    for i, filepath in enumerate(files[:10], 1):  # Show last 10
        basename = os.path.basename(filepath)

        # Extract timestamp for display
        try:
            ts_part = basename.replace("portfolio_analysis_", "").replace(".json", "")
            dt_obj = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
            display_ts = dt_obj.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            display_ts = "Unknown time"

        # Check file size
        try:
            file_size = os.path.getsize(filepath) / 1024  # KB
            size_str = f"[{file_size:.1f} KB]"
        except OSError:
            size_str = "[Error]"

        print(f"  {ACCENT}{i:2d}.{RESET} {basename} {SUBTLE}({display_ts}) {size_str}{RESET}")

    if len(files) > 10:
        print(f"  {SUBTLE}... and {len(files) - 10} more files{RESET}")

    print(f"\n{PRIMARY}OPTIONS:{RESET}")
    print(f"  {ACCENT}[number]{RESET} - Recalculate specific file (e.g., '1')")
    print(f"  {ACCENT}[number] save{RESET} - Recalculate and save back (e.g., '1 save')")
    print(f"  {ACCENT}all{RESET} - Recalculate all files (display only)")
    print(f"  {ACCENT}all save{RESET} - Recalculate all files and save")
    print(f"  {ACCENT}latest{RESET} - Recalculate latest file only")
    print(f"  {ACCENT}q{RESET} - Quit")

    while True:
        choice = input(f"\n{PRIMARY}Choice: {RESET}").strip().lower()

        if choice == "q":
            break
        elif choice == "latest":
            if files:
                recalculator.recalculate_exposure(files[0], save_back=False)
        elif choice == "all":
            recalculator.recalculate_multiple(save_back=False, limit=5)  # Limit to 5 for demo
        elif choice == "all save":
            confirm = input(f"{WARNING}Save changes to all files? (y/N): {RESET}")
            if confirm.lower() == "y":
                recalculator.recalculate_multiple(save_back=True, limit=5)
        elif choice.endswith(" save"):
            try:
                num = int(choice.split()[0])
                if 1 <= num <= len(files):
                    recalculator.recalculate_exposure(files[num - 1], save_back=True)
                else:
                    print_error(f"Invalid file number. Use 1-{len(files)}")
            except ValueError:
                print_error("Invalid format. Use '[number] save'")
        else:
            try:
                num = int(choice)
                if 1 <= num <= len(files):
                    recalculator.recalculate_exposure(files[num - 1], save_back=False)
                else:
                    print_error(f"Invalid file number. Use 1-{len(files)}")
            except ValueError:
                print_error("Invalid choice. Use number, 'all', 'latest', or 'q'")


if __name__ == "__main__":
    main()
