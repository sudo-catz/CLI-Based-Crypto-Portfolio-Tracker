#!/usr/bin/env python3
"""
Wallet Data Combiner
====================
Combines multiple wallet JSON data structures into a single aggregated structure
for unified portfolio analysis across all wallets.
"""

import json
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime


def combine_wallet_data(
    wallet_data_list: List[Dict[str, Any]], wallet_addresses: List[str]
) -> Dict[str, Any]:
    """
    Combine multiple wallet data structures into a single aggregated structure.

    Args:
        wallet_data_list: List of wallet data dictionaries
        wallet_addresses: List of wallet addresses corresponding to the data

    Returns:
        Combined wallet data structure
    """
    if not wallet_data_list:
        return {
            "tokens": [],
            "protocols": [],
            "total_usd_value": 0.0,
            "timestamp": datetime.now().isoformat(),
            "wallets_included": [],
            "wallet_count": 0,
        }

    # Initialize combined data structure
    combined_tokens = {}  # key: (symbol, chain) -> token data
    combined_protocols = {}  # key: (protocol_name, chain) -> protocol data
    combined_positions = defaultdict(list)  # key: (protocol_name, chain) -> list of positions
    combined_protocol_total_values = defaultdict(
        float
    )  # key: (protocol_name, chain) -> cumulative total_value

    total_value = 0.0
    latest_timestamp = None

    # Process each wallet
    for i, wallet_data in enumerate(wallet_data_list):
        if not isinstance(wallet_data, dict):
            continue

        wallet_address = wallet_addresses[i] if i < len(wallet_addresses) else f"wallet_{i}"
        wallet_value = wallet_data.get("total_usd_value", wallet_data.get("total_balance", 0))

        # Add wallet value to total (this gives us the actual portfolio value)
        total_value += wallet_value

        # Track latest timestamp
        wallet_timestamp = wallet_data.get("timestamp")
        if wallet_timestamp:
            if latest_timestamp is None or wallet_timestamp > latest_timestamp:
                latest_timestamp = wallet_timestamp

        # Combine tokens
        tokens = wallet_data.get("tokens", [])
        for token in tokens:
            if not isinstance(token, dict):
                continue

            symbol = token.get("symbol", "").upper()
            chain = token.get("chain", "unknown").capitalize()
            key = (symbol, chain)

            if key in combined_tokens:
                # Combine with existing token
                combined_tokens[key]["amount"] += token.get("amount", 0)
                combined_tokens[key]["usd_value"] += token.get("usd_value", 0)
                # Keep track of which wallets have this token
                if "source_wallets" not in combined_tokens[key]:
                    combined_tokens[key]["source_wallets"] = []
                combined_tokens[key]["source_wallets"].append(wallet_address)
            else:
                # Add new token
                combined_tokens[key] = {
                    "symbol": symbol,
                    "chain": chain,
                    "amount": token.get("amount", 0),
                    "usd_value": token.get("usd_value", 0),
                    "category": token.get("category", "other_crypto"),
                    "source_wallets": [wallet_address],
                }

        # Combine protocols
        protocols = wallet_data.get("protocols", [])
        for protocol in protocols:
            if not isinstance(protocol, dict):
                continue

            protocol_name = protocol.get("name", "Unknown")
            chain = protocol.get("chain", "unknown").capitalize()
            key = (protocol_name, chain)

            # Track the reported total value for the protocol so we can preserve collateral/residuals
            proto_total_value = protocol.get("total_value", protocol.get("value", 0)) or 0
            try:
                proto_total_value = float(proto_total_value)
            except (TypeError, ValueError):
                proto_total_value = 0.0
            combined_protocol_total_values[key] += proto_total_value

            # Collect all positions for this protocol/chain combination
            positions = protocol.get("positions", [])
            for position in positions:
                if not isinstance(position, dict):
                    continue

                # Add wallet source to position
                position_copy = position.copy()
                position_copy["source_wallet"] = wallet_address
                combined_positions[key].append(position_copy)

            # Update protocol metadata
            if key not in combined_protocols:
                combined_protocols[key] = {
                    "name": protocol_name,
                    "chain": chain,
                    "total_value": 0.0,
                    "positions": [],
                    "source_wallets": [],
                }

            # Add wallet to source list
            if wallet_address not in combined_protocols[key]["source_wallets"]:
                combined_protocols[key]["source_wallets"].append(wallet_address)

    # Process combined positions to aggregate duplicates
    for (protocol_name, chain), positions in combined_positions.items():
        key = (protocol_name, chain)

        # Group positions by (asset, header_type) to combine duplicates
        position_groups = defaultdict(list)
        for pos in positions:
            asset = pos.get("asset", pos.get("label", ""))
            header_type = pos.get("header_type", "-")
            pos_key = (asset, header_type)
            position_groups[pos_key].append(pos)

        # Combine grouped positions
        aggregated_positions = []
        total_protocol_value = 0.0

        for (asset, header_type), pos_list in position_groups.items():
            if not pos_list:
                continue

            # Use first position as template
            combined_pos = pos_list[0].copy()

            # Aggregate amounts and values
            total_amount = 0.0
            position_total_value = 0.0  # Renamed to avoid conflict with main total_value
            source_wallets = []

            for pos in pos_list:
                amount = pos.get("amount", pos.get("qty", pos.get("balance", 0)))
                value = pos.get("usd_value", pos.get("value", 0))

                try:
                    total_amount += float(amount) if amount else 0.0
                    position_total_value += float(value) if value else 0.0
                except (ValueError, TypeError):
                    pass

                source_wallet = pos.get("source_wallet")
                if source_wallet and source_wallet not in source_wallets:
                    source_wallets.append(source_wallet)

            # Update combined position
            combined_pos.update(
                {
                    "amount": total_amount,
                    "qty": total_amount,
                    "balance": total_amount,
                    "usd_value": position_total_value,
                    "value": position_total_value,
                    "source_wallets": source_wallets,
                }
            )

            # Remove single source_wallet field
            combined_pos.pop("source_wallet", None)

            aggregated_positions.append(combined_pos)
            total_protocol_value += position_total_value

        # Update protocol with aggregated positions
        combined_protocols[key]["positions"] = aggregated_positions
        combined_protocols[key]["total_value"] = combined_protocol_total_values.get(
            key, total_protocol_value
        )

    # Convert to final format
    final_tokens = list(combined_tokens.values())
    final_protocols = list(combined_protocols.values())

    # Sort by value (descending)
    final_tokens.sort(key=lambda x: x.get("usd_value", 0), reverse=True)
    final_protocols.sort(key=lambda x: x.get("total_value", 0), reverse=True)

    return {
        "tokens": final_tokens,
        "protocols": final_protocols,
        "total_usd_value": total_value,
        "timestamp": latest_timestamp or datetime.now().isoformat(),
        "wallets_included": wallet_addresses[: len(wallet_data_list)],
        "wallet_count": len(wallet_data_list),
    }


def load_and_combine_wallets(wallet_files: List[str]) -> Dict[str, Any]:
    """
    Load wallet data from JSON files and combine them.

    Args:
        wallet_files: List of file paths to wallet JSON files

    Returns:
        Combined wallet data structure
    """
    wallet_data_list = []
    wallet_addresses = []

    for file_path in wallet_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                wallet_data_list.append(data)

                # Extract address from filename or data
                if "address" in data:
                    wallet_addresses.append(data["address"])
                else:
                    # Extract from filename (assuming format like "wallet_0x123...json")
                    import os

                    filename = os.path.basename(file_path)
                    if filename.startswith("wallet_"):
                        addr = filename.replace("wallet_", "").replace(".json", "")
                        wallet_addresses.append(addr)
                    else:
                        wallet_addresses.append(f"wallet_from_{filename}")

        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"Error loading {file_path}: {e}")
            continue

    return combine_wallet_data(wallet_data_list, wallet_addresses)


def save_combined_data(combined_data: Dict[str, Any], output_file: str) -> bool:
    """
    Save combined wallet data to JSON file.

    Args:
        combined_data: Combined wallet data structure
        output_file: Output file path

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(combined_data, f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error saving combined data: {e}")
        return False


# Example usage and testing
if __name__ == "__main__":
    # Example: Combine wallet files
    wallet_files = ["wallet_data_1.json", "wallet_data_2.json", "wallet_data_3.json"]

    print("Combining wallet data...")
    combined_data = load_and_combine_wallets(wallet_files)

    print(f"Combined {combined_data['wallet_count']} wallets")
    print(f"Total value: ${combined_data['total_usd_value']:,.2f}")
    print(f"Total tokens: {len(combined_data['tokens'])}")
    print(f"Total protocols: {len(combined_data['protocols'])}")

    # Save combined data
    if save_combined_data(combined_data, "combined_wallet_data.json"):
        print("Combined data saved to combined_wallet_data.json")

    # Display summary
    print("\nTop 5 tokens by value:")
    for i, token in enumerate(combined_data["tokens"][:5]):
        print(f"  {i+1}. {token['symbol']} ({token['chain']}): ${token['usd_value']:,.2f}")

    print("\nTop 5 protocols by value:")
    for i, protocol in enumerate(combined_data["protocols"][:5]):
        print(f"  {i+1}. {protocol['name']} ({protocol['chain']}): ${protocol['total_value']:,.2f}")
