# -*- coding: utf-8 -*-
"""
Blockchain API Clients for Multi-Chain Portfolio Tracker with Enhanced Solana Failover
"""
import json
import requests
import time
from typing import Dict, Any, Optional, List

# Import constants and utilities
from config.constants import (
    SOLANA_RPC_URL,
    SOLANA_TOKEN_PROGRAM_ID,
    SOLANA_NATIVE_MINT,
    JUPITER_PRICE_API,
)
from utils.helpers import print_error, print_warning, print_info, print_success, safe_float_convert
from utils.rate_limiter import solana_retry, coingecko_retry

# Enhanced Solana RPC endpoints for failover
SOLANA_RPC_ENDPOINTS = [
    "https://solana-rpc.publicnode.com",  # PublicNode - tested working
    "https://api.mainnet-beta.solana.com",  # Official Solana
    "https://rpc.ankr.com/solana",  # Ankr (may have rate limits but worth trying)
    "https://solana-mainnet.g.alchemy.com/v2/demo",  # Alchemy demo endpoint
    "https://rpc.helius.xyz/?api-key=",  # Helius (empty key for basic access)
]

# Simple endpoint rotation state
_current_endpoint_index = 0
_endpoint_failures = {}


def get_next_solana_endpoint():
    """Get next available Solana RPC endpoint"""
    global _current_endpoint_index

    # Try each endpoint
    for i in range(len(SOLANA_RPC_ENDPOINTS)):
        endpoint = SOLANA_RPC_ENDPOINTS[_current_endpoint_index]

        # Check if endpoint failed recently (skip for 5 minutes)
        if endpoint in _endpoint_failures:
            time_since_failure = time.time() - _endpoint_failures[endpoint]
            if time_since_failure < 300:  # 5 minutes
                _current_endpoint_index = (_current_endpoint_index + 1) % len(SOLANA_RPC_ENDPOINTS)
                continue

        return endpoint

    # All endpoints failed recently, use the first one anyway
    return SOLANA_RPC_ENDPOINTS[0]


def mark_solana_endpoint_failed(endpoint):
    """Mark endpoint as failed"""
    global _endpoint_failures
    _endpoint_failures[endpoint] = time.time()
    endpoint_display = endpoint.split("?")[0] + ("..." if "?" in endpoint else "")
    print_warning(f"⚠️ Marked Solana RPC as failed: {endpoint_display}")


def rotate_solana_endpoint():
    """Rotate to next endpoint"""
    global _current_endpoint_index
    _current_endpoint_index = (_current_endpoint_index + 1) % len(SOLANA_RPC_ENDPOINTS)


# Enhanced Solana RPC request with failover
def make_solana_json_rpc_request(method: str, params: list) -> Optional[Dict[str, Any]]:
    """Makes a JSON-RPC request to Solana RPC with automatic endpoint failover."""

    for attempt in range(len(SOLANA_RPC_ENDPOINTS)):
        endpoint = get_next_solana_endpoint()
        endpoint_display = endpoint.split("?")[0] + ("..." if "?" in endpoint else "")

        try:
            # Only log on first attempt per batch of requests
            if attempt == 0 and method == "getBalance":  # Log once per wallet scan
                print_info(f"📡 Solana RPC: {endpoint_display}")

            headers = {"Content-Type": "application/json"}
            data = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

            response = requests.post(endpoint, headers=headers, data=json.dumps(data), timeout=10)

            # Handle 429 rate limit specifically
            if response.status_code == 429:
                print_warning(f"🔄 Rate limited on {endpoint_display}, trying next endpoint...")
                mark_solana_endpoint_failed(endpoint)
                rotate_solana_endpoint()
                continue

            # Handle 403 forbidden
            if response.status_code == 403:
                print_warning(f"🚫 Access forbidden on {endpoint_display}, trying next endpoint...")
                mark_solana_endpoint_failed(endpoint)
                rotate_solana_endpoint()
                continue

            response.raise_for_status()  # Raise for other HTTP errors
            result = response.json()

            # Check for JSON-RPC errors
            if result and "error" in result:
                error_msg = result["error"].get("message", "Unknown RPC error")
                print_error(f"Solana RPC error on {endpoint_display}: {error_msg}")
                rotate_solana_endpoint()
                continue

            # Success! Only log on first successful connection
            if attempt == 0 and method == "getBalance":
                print_success(f"✅ Solana RPC connected: {endpoint_display}")
            return result

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code in [429, 403]:
                print_warning(f"🔄 HTTP {e.response.status_code} on {endpoint_display}")
                mark_solana_endpoint_failed(endpoint)
            else:
                print_error(f"HTTP error on {endpoint_display}: {e}")
                mark_solana_endpoint_failed(endpoint)
            rotate_solana_endpoint()

        except (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            # Check if this is a DNS resolution error
            error_str = str(e).lower()
            if "name resolution" in error_str or "resolve" in error_str:
                print_warning(
                    f"🔍 DNS resolution error on {endpoint_display}: Failed to resolve hostname"
                )
            else:
                if attempt == 0:  # Only log connection errors on first attempt
                    print_warning(f"🔗 Connection error on {endpoint_display}: {type(e).__name__}")
            mark_solana_endpoint_failed(endpoint)
            rotate_solana_endpoint()

        except Exception as e:
            print_error(f"Unexpected error on {endpoint_display}: {e}")
            mark_solana_endpoint_failed(endpoint)
            rotate_solana_endpoint()

    # All endpoints failed - provide helpful feedback
    print_error("❌ All Solana RPC endpoints failed!")
    print_info("💡 This might be due to:")
    print_info("   • Network connectivity issues")
    print_info("   • All endpoints being rate-limited")
    print_info("   • DNS resolution problems")
    print_info("   • Consider using a paid RPC service for production")
    return None


def get_solana_token_accounts(address: str) -> List[Dict[str, Any]]:
    """Fetches token accounts owned by a Solana address with failover support."""
    response = make_solana_json_rpc_request(
        "getTokenAccountsByOwner",
        [address, {"programId": SOLANA_TOKEN_PROGRAM_ID}, {"encoding": "jsonParsed"}],
    )
    if response and "result" in response and "value" in response["result"]:
        return response["result"]["value"]
    elif response and "error" in response:
        print_error(
            f"Error fetching token accounts for {address}: {response['error'].get('message', 'Unknown RPC error')}"
        )
    return []


@coingecko_retry
def get_solana_token_exchange_rate(token_address: str) -> float:
    """Fetches the exchange rate of a Solana token against native SOL using Jupiter API with smart retry."""
    params = {"ids": token_address, "vsToken": SOLANA_NATIVE_MINT}
    response = requests.get(JUPITER_PRICE_API, params=params, timeout=10)
    response.raise_for_status()  # This will raise HTTPError for 429 and other HTTP errors

    data = response.json()

    if "data" in data and token_address in data["data"] and "price" in data["data"][token_address]:
        rate = safe_float_convert(data["data"][token_address]["price"])
        return rate
    else:
        print_warning(f"Could not find price data for {token_address} in Jupiter response.")
        return 1.0  # Fallback
