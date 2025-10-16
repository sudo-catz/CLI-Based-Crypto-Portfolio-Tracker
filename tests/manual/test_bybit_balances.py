#!/usr/bin/env python3
"""
Manual Bybit Balance Inspector
------------------------------
Runs the Bybit balance fetcher across supported account types and prints
the aggregated results. Useful for verifying funding/unified accounts
without running the full live analysis.
"""

import argparse
import hmac
import json
import sys
import time
from collections import OrderedDict
from hashlib import sha256
from pprint import pprint
from typing import Any, Dict, List
from urllib.parse import urlencode

import requests

from api_clients.exchange_balances import get_bybit_detailed_balance
from api_clients.exchange_manager import ExchangeManager
from api_clients.api_manager import api_key_manager


class _DummyAPIModule:
    """Minimal stub to satisfy ExchangeManager's legacy API requirements."""

    pass


def build_exchange_manager() -> ExchangeManager:
    """Instantiate an ExchangeManager suitable for manual testing."""
    return ExchangeManager(api_module=_DummyAPIModule(), encryption_manager=None)


def _sign_request(
    api_key: str,
    api_secret: str,
    method: str,
    path: str,
    query: str,
    body: str,
    recv_window: str = "5000",
) -> Dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    prehash = timestamp + api_key + recv_window + query + body
    signature = hmac.new(api_secret.encode(), prehash.encode(), sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
    }


def fetch_all_balance_raw(api_key: str, api_secret: str, account_type: str = "") -> Dict[str, Any]:
    """
    Call Bybit's /v5/asset/all-balance endpoint directly.
    When account_type is empty, Bybit returns all account classes.
    """
    url_path = "/v5/asset/all-balance"
    base_url = "https://api.bybit.com"
    payload: Dict[str, Any] = {}
    if account_type:
        payload["accountType"] = account_type
    body = json.dumps(payload, separators=(",", ":"))
    headers = _sign_request(api_key, api_secret, "POST", url_path, "", body)
    response = requests.post(base_url + url_path, headers=headers, data=body, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_transfer_balance_raw(
    api_key: str,
    api_secret: str,
    account_type: str,
    coin: str = "",
    with_bonus: bool = False,
) -> Dict[str, Any]:
    """
    Call Bybit's /v5/asset/transfer/query-account-coins-balance endpoint directly.
    """
    url_path = "/v5/asset/transfer/query-account-coins-balance"
    base_url = "https://api.bybit.com"
    params = OrderedDict()
    params["accountType"] = account_type
    if coin:
        params["coin"] = coin
    if with_bonus:
        params["withBonus"] = "1"
    query = urlencode(list(params.items()))
    headers = _sign_request(api_key, api_secret, "GET", url_path, query, "")
    url = f"{base_url}{url_path}?{query}"
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Bybit balances across all account types.")
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top assets (by USD value) to display (default: 10)",
    )
    parser.add_argument(
        "--raw-account-type",
        type=str,
        default="",
        help="Optional accountType to pass to /v5/asset/all-balance (e.g. UNIFIED, CONTRACT, FUND).",
    )
    parser.add_argument(
        "--transfer-account-types",
        type=str,
        default="",
        help="Comma-separated list of account types to query via /v5/asset/transfer/query-account-coins-balance",
    )
    parser.add_argument(
        "--transfer-coin",
        type=str,
        default="",
        help="Optional coin or comma-separated coins for transfer balance query (e.g. USDC,USDT).",
    )
    parser.add_argument(
        "--with-bonus",
        action="store_true",
        help="Include bonus balances when calling the transfer balance endpoint.",
    )
    args = parser.parse_args()

    manager = build_exchange_manager()
    balance_info = get_bybit_detailed_balance(manager)
    if not balance_info:
        print("⚠️  No Bybit balance data returned.")
        return 1

    total_equity = balance_info.get("total_equity", 0.0)
    assets = balance_info.get("assets", [])

    print("\nBYBIT BALANCE SUMMARY")
    print("=====================")
    print(f"Total equity (USD): {total_equity:,.2f}")
    print(f"Assets returned:    {len(assets)}")

    if not assets:
        return 0

    print("\nTop assets by USD value:")
    print("------------------------")
    top_n = max(1, args.top)
    for idx, asset in enumerate(assets[:top_n], start=1):
        coin = asset.get("coin", "N/A")
        usd_value = asset.get("usd_value", 0.0)
        total = asset.get("total", asset.get("wallet_balance", 0.0))
        free = asset.get("free", asset.get("available", 0.0))
        used = asset.get("used", asset.get("locked", 0.0))
        print(
            f"{idx:>2}. {coin:<10} | USD: {usd_value:>12,.2f} "
            f"| total: {total:>12,.6f} | free: {free:>12,.6f} | used: {used:>12,.6f}"
        )

    remaining = assets[top_n:]
    if remaining:
        remainder_value = sum(asset.get("usd_value", 0.0) for asset in remaining)
        print(f"\n… {len(remaining)} additional assets worth {remainder_value:,.2f} USD")

    print("\nRaw aggregated payload:")
    print("-----------------------")
    pprint(balance_info)

    credentials = api_key_manager.get_credentials("bybit")
    if credentials:
        try:
            raw_balance = fetch_all_balance_raw(
                credentials.api_key, credentials.api_secret, args.raw_account_type
            )
            print("\nRaw /v5/asset/all-balance response:")
            print("------------------------------------")
            print(json.dumps(raw_balance, indent=2))
        except requests.HTTPError as http_err:
            print(f"\nHTTP error calling /v5/asset/all-balance: {http_err}")
            if http_err.response is not None:
                try:
                    print(http_err.response.json())
                except ValueError:
                    print(http_err.response.text)
        except Exception as err:
            print(f"\nError calling /v5/asset/all-balance: {err}")

        transfer_types: List[str] = []
        if args.transfer_account_types:
            transfer_types = [
                part.strip() for part in args.transfer_account_types.split(",") if part.strip()
            ]
        for account_type in transfer_types:
            try:
                transfer_balance = fetch_transfer_balance_raw(
                    credentials.api_key,
                    credentials.api_secret,
                    account_type,
                    args.transfer_coin,
                    args.with_bonus,
                )
                print(f"\nRaw transfer balance ({account_type}):")
                print("------------------------------------")
                print(json.dumps(transfer_balance, indent=2))
            except requests.HTTPError as http_err:
                print(f"\nHTTP error calling transfer balance for {account_type}: {http_err}")
                if http_err.response is not None:
                    try:
                        print(http_err.response.json())
                    except ValueError:
                        print(http_err.response.text)
            except Exception as err:
                print(f"\nError calling transfer balance for {account_type}: {err}")
    else:
        print("\n⚠️  Bybit credentials not available; skipping /v5/asset/all-balance test.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
