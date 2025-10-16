# -*- coding: utf-8 -*-
"""
Exchange Balance Functions
--------------------------
Functions for fetching detailed balance information from various exchanges.
"""

import time
import hmac
import requests
from hashlib import sha256
from collections import OrderedDict
from urllib.parse import urlencode
from typing import Dict, Any, Optional, List, Set, Tuple
import ccxt
from utils.helpers import (
    safe_float_convert,
    print_warning,
    print_error,
    print_info,
    print_success,
    format_currency,
)
from config.constants import (
    BACKPACK_API_URL,
    BACKPACK_WINDOW,
    BINANCE_BASE_URL,
    BINANCE_WALLET_BALANCE_ENDPOINT,
)
from api_clients.okx_client import OkxClient
from api_clients.exchange_manager import sign_backpack_request_custom
from api_clients.api_manager import api_key_manager
from utils.rate_limiter import bybit_retry, okx_retry, backpack_retry, binance_retry

# API key manager will handle credentials now - no need for api module

_BYBIT_STABLE_COINS = {"USDT", "USDC", "USD", "FDUSD", "USDE", "USDC.E"}
_OKX_STABLE_COINS = {"USDT", "USDC", "USD", "USDK", "DAI", "USDP", "TUSD", "FDUSD"}
_BINANCE_STABLE_COINS = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP"}
_OKX_PRICE_CLIENT: Optional[ccxt.Exchange] = None
_BINANCE_PRICE_CLIENT: Optional[ccxt.Exchange] = None


def _bybit_sign_request(
    api_key: str,
    api_secret: str,
    method: str,
    path: str,
    query: str,
    body: str,
    recv_window: str = "5000",
) -> Dict[str, str]:
    """Generate Bybit request headers using the V5 signing scheme."""
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


def _bybit_convert_to_usd(exchange: ccxt.Exchange, symbol: str, amount: float) -> float:
    """Convert a Bybit asset amount to USD, using market data when needed."""
    if amount <= 0:
        return 0.0

    symbol_upper = (symbol or "").upper()
    if symbol_upper in _BYBIT_STABLE_COINS:
        return amount

    try:
        if not getattr(exchange, "markets", None):
            exchange.load_markets()
        ticker_symbol = f"{symbol_upper}/USDT"
        if ticker_symbol in exchange.markets:
            ticker = exchange.fetch_ticker(ticker_symbol)
            last_price = safe_float_convert(ticker.get("last"), 0.0)
            if last_price > 0:
                return amount * last_price
    except Exception:
        pass

    return amount


def _ensure_okx_price_client() -> Optional[ccxt.Exchange]:
    """Create or return a reused ccxt OKX client for price lookups."""
    global _OKX_PRICE_CLIENT
    if _OKX_PRICE_CLIENT is not None:
        return _OKX_PRICE_CLIENT
    try:
        client = ccxt.okx()
        client.load_markets()
        _OKX_PRICE_CLIENT = client
        return client
    except Exception:
        return None


def _okx_convert_to_usd(symbol: str, amount: float) -> float:
    """Convert an OKX asset amount to USD using public market data."""
    if amount <= 0 or not symbol:
        return 0.0

    symbol_upper = symbol.upper()
    if symbol_upper in _OKX_STABLE_COINS:
        return amount

    client = _ensure_okx_price_client()
    if client is None:
        return 0.0

    candidate_pairs = [f"{symbol_upper}/USDT", f"{symbol_upper}/USD"]
    try:
        for pair in candidate_pairs:
            if pair not in client.markets:
                continue
            ticker = client.fetch_ticker(pair)
            last_price = safe_float_convert(
                ticker.get("last")
                or ticker.get("close")
                or ticker.get("info", {}).get("last")
                or ticker.get("info", {}).get("close")
                or 0.0
            )
            if last_price > 0:
                return amount * last_price
    except Exception:
        return 0.0

    return 0.0


def _ensure_binance_price_client() -> Optional[ccxt.Exchange]:
    """Create or reuse a ccxt Binance client for price lookups."""
    global _BINANCE_PRICE_CLIENT
    if _BINANCE_PRICE_CLIENT is not None:
        return _BINANCE_PRICE_CLIENT
    try:
        client = ccxt.binance({"enableRateLimit": True})
        client.load_markets()
        _BINANCE_PRICE_CLIENT = client
        return client
    except Exception:
        return None


def _binance_convert_to_usd(symbol: str, amount: float) -> float:
    """Convert a Binance asset amount to USD using public market data."""
    if amount <= 0 or not symbol:
        return 0.0

    symbol_upper = symbol.upper()
    if symbol_upper in _BINANCE_STABLE_COINS:
        return amount

    client = _ensure_binance_price_client()
    if client is None:
        return 0.0

    candidate_pairs = [
        f"{symbol_upper}/USDT",
        f"{symbol_upper}/BUSD",
        f"{symbol_upper}/USDC",
        f"{symbol_upper}/USD",
    ]

    try:
        for pair in candidate_pairs:
            if pair not in client.markets:
                continue
            ticker = client.fetch_ticker(pair)
            last_price = safe_float_convert(
                ticker.get("last")
                or ticker.get("close")
                or ticker.get("info", {}).get("last")
                or ticker.get("info", {}).get("close")
                or 0.0
            )
            if last_price > 0:
                return amount * last_price
    except Exception:
        return 0.0

    return 0.0


def _bybit_extract_total_equity_from_balance(
    exchange: ccxt.Exchange, balance: Optional[Dict[str, Any]]
) -> Tuple[float, Set[str]]:
    """
    Extract total equity in USD from a Bybit balance payload and track which account types it covers.
    Returns (total_usd, account_types_seen).
    """
    if not isinstance(balance, dict):
        return 0.0, set()

    accounted_types: Set[str] = set()
    info = balance.get("info", {})
    result = info.get("result", {}) if isinstance(info, dict) else {}

    total_from_list = 0.0
    if isinstance(result, dict):
        entries = result.get("list")
        if isinstance(entries, list) and entries:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                account_type = (
                    entry.get("accountType")
                    or entry.get("account_type")
                    or entry.get("account", "")
                )
                if account_type:
                    accounted_types.add(str(account_type).upper())
                total_from_list += safe_float_convert(
                    entry.get("totalEquity")
                    or entry.get("total_equity")
                    or entry.get("total")
                    or entry.get("walletBalance")
                    or 0.0
                )
            if total_from_list > 0:
                return total_from_list, accounted_types

    total_usd = 0.0
    for currency, data in balance.items():
        if currency in {"info", "free", "used", "total", "timestamp", "datetime"}:
            continue

        if isinstance(data, dict):
            total_amount = safe_float_convert(
                data.get("total")
                or data.get("walletBalance")
                or data.get("wallet_balance")
                or data.get("equity")
                or 0.0
            )
            usd_value = safe_float_convert(data.get("usdValue") or data.get("equity") or 0.0)
        elif isinstance(data, (int, float, str)):
            total_amount = safe_float_convert(data)
            usd_value = 0.0
        else:
            continue

        if total_amount <= 0 and usd_value <= 0:
            continue

        if usd_value <= 0:
            usd_value = _bybit_convert_to_usd(exchange, currency, total_amount)

        total_usd += usd_value

    return total_usd, accounted_types


def _bybit_fetch_transfer_total(exchange: ccxt.Exchange, account_type: str) -> float:
    """
    Fetch Bybit transfer balances for a specific account type using the v5 API and
    return the total USD-equivalent value.
    """
    creds = None
    try:
        if not api_key_manager.authenticate():
            return []
        creds = api_key_manager.get_credentials("bybit")
    except Exception:
        creds = None

    if not creds or not getattr(creds, "api_key", None) or not getattr(creds, "api_secret", None):
        return 0.0

    params = OrderedDict()
    params["accountType"] = account_type
    query = urlencode(list(params.items()))

    try:
        headers = _bybit_sign_request(
            creds.api_key,
            creds.api_secret,
            "GET",
            "/v5/asset/transfer/query-account-coins-balance",
            query,
            "",
        )
    except Exception as err:
        print_warning(f"Failed to sign Bybit transfer balance request: {err}")
        return 0.0

    url = f"https://api.bybit.com/v5/asset/transfer/query-account-coins-balance?{query}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as http_err:
        msg = str(http_err)
        if "accountType" in msg and "only support" in msg:
            return 0.0
        print_warning(f"Bybit transfer balance HTTP error ({account_type}): {http_err}")
        return 0.0
    except Exception as err:
        print_warning(f"Bybit transfer balance error ({account_type}): {err}")
        return 0.0

    if not isinstance(data, dict) or data.get("retCode") != 0:
        print_warning(
            f"Bybit transfer balance returned retCode {data.get('retCode')} for {account_type}"
        )
        return 0.0

    result = data.get("result", {})
    balances = result.get("balance", [])
    if not isinstance(balances, list):
        return 0.0

    total_value = 0.0
    for item in balances:
        if not isinstance(item, dict):
            continue

        coin = item.get("coin") or ""
        wallet_balance = safe_float_convert(item.get("walletBalance", 0))
        if wallet_balance == 0:
            continue

        usd_value = safe_float_convert(item.get("usdValue", 0))
        if usd_value == 0 and wallet_balance != 0:
            usd_value = _bybit_convert_to_usd(exchange, coin, wallet_balance)

        total_value += usd_value

    return total_value


def _okx_sum_account_equity(balance_payload: Optional[Dict[str, Any]]) -> float:
    """Sum trading account equity reported by OKX account balance endpoint."""
    if not isinstance(balance_payload, dict) or balance_payload.get("code") not in (None, "0"):
        return 0.0

    data = balance_payload.get("data") or []
    total = 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        entry_total = safe_float_convert(
            entry.get("totalEq") or entry.get("eqUsd") or entry.get("eqUSDT") or 0.0
        )
        if entry_total > 0:
            total += entry_total
            continue

        details = entry.get("details", [])
        if not isinstance(details, list):
            continue

        detail_sum = 0.0
        for asset_detail in details:
            if not isinstance(asset_detail, dict):
                continue
            coin = asset_detail.get("ccy", "")
            balance = safe_float_convert(asset_detail.get("eq", asset_detail.get("bal", 0)))
            if balance <= 0:
                continue
            usd_value = safe_float_convert(asset_detail.get("eqUsd", 0.0))
            if usd_value <= 0:
                currency = (coin or "").upper()
                if currency in _OKX_STABLE_COINS:
                    usd_value = balance
                else:
                    price = safe_float_convert(asset_detail.get("pxUsd", 0.0))
                    if price <= 0:
                        price = safe_float_convert(asset_detail.get("avgPx", 0.0))
                    if price > 0:
                        usd_value = balance * price
                    else:
                        usd_value = _okx_convert_to_usd(currency, balance)
            detail_sum += max(usd_value, 0.0)

        total += detail_sum

    return max(total, 0.0)


def _okx_sum_funding_equity(asset_payload: Optional[Dict[str, Any]]) -> float:
    """Sum funding account equity reported by OKX asset balance endpoint."""
    if not isinstance(asset_payload, dict) or asset_payload.get("code") not in (None, "0"):
        return 0.0

    data = asset_payload.get("data") or []
    total = 0.0
    for item in data:
        if not isinstance(item, dict):
            continue
        balance = safe_float_convert(item.get("bal", 0.0))
        eq_usd = safe_float_convert(item.get("eqUsd", 0.0))
        if eq_usd <= 0 and balance > 0:
            currency = (item.get("ccy") or "").upper()
            if currency in _OKX_STABLE_COINS:
                eq_usd = balance
            else:
                price = safe_float_convert(item.get("pxUsd", 0.0))
                if price <= 0:
                    price = safe_float_convert(item.get("avgPx", 0.0))
                if price > 0:
                    eq_usd = balance * price
                else:
                    eq_usd = _okx_convert_to_usd(currency, balance)
        total += max(eq_usd, 0.0)
    return max(total, 0.0)


@okx_retry
async def get_okx_detailed_balance() -> Optional[Dict[str, Any]]:
    """Get detailed OKX balance breakdown by asset."""
    try:
        # Get OKX credentials from API key manager
        if not api_key_manager.authenticate():
            print_warning("API key manager authentication failed, skipping OKX detailed breakdown")
            return None

        credentials = api_key_manager.get_credentials("okx")
        if not credentials or not credentials.passphrase:
            print_warning(
                "OKX API credentials not found or missing passphrase, skipping detailed breakdown"
            )
            return None

        client = OkxClient(credentials.api_key, credentials.api_secret, credentials.passphrase)
        try:
            account_data = await client.get_account_balance()
            funding_data = await client.get_asset_balances()
        finally:
            await client.close()

        aggregated_assets: Dict[str, Dict[str, float]] = {}

        def accumulate_asset(
            symbol: str,
            *,
            balance: float,
            available: float,
            frozen: float,
            usd_value: float,
        ) -> None:
            if not symbol:
                return
            entry = aggregated_assets.setdefault(
                symbol,
                {"coin": symbol, "balance": 0.0, "available": 0.0, "frozen": 0.0, "usd_value": 0.0},
            )
            entry["balance"] += max(balance, 0.0)
            entry["available"] += max(available, 0.0)
            entry["frozen"] += max(frozen, 0.0)
            entry["usd_value"] += max(usd_value, 0.0)

        if isinstance(account_data, dict) and account_data.get("code") in (None, "0"):
            for account in account_data.get("data", []) or []:
                if not isinstance(account, dict):
                    continue
                for asset_detail in account.get("details", []) or []:
                    if not isinstance(asset_detail, dict):
                        continue
                    coin = asset_detail.get("ccy", "")
                    balance = safe_float_convert(asset_detail.get("eq", asset_detail.get("bal", 0)))
                    if balance <= 0.000001:
                        continue
                    available = safe_float_convert(asset_detail.get("availEq", 0))
                    frozen = safe_float_convert(asset_detail.get("frozenBal", 0))
                    usd_value = safe_float_convert(asset_detail.get("eqUsd", 0.0))
                    if usd_value <= 0:
                        currency = (coin or "").upper()
                        if currency in _OKX_STABLE_COINS:
                            usd_value = balance
                        else:
                            price = safe_float_convert(asset_detail.get("pxUsd", 0.0))
                            if price <= 0:
                                price = safe_float_convert(asset_detail.get("avgPx", 0.0))
                            if price > 0:
                                usd_value = balance * price
                            else:
                                usd_value = _okx_convert_to_usd(currency, balance)
                    accumulate_asset(
                        coin,
                        balance=balance,
                        available=available,
                        frozen=frozen,
                        usd_value=usd_value,
                    )

        if isinstance(funding_data, dict) and funding_data.get("code") in (None, "0"):
            for asset in funding_data.get("data", []) or []:
                if not isinstance(asset, dict):
                    continue
                coin = asset.get("ccy", "")
                balance = safe_float_convert(asset.get("bal", 0))
                if balance <= 0.000001:
                    continue
                available = safe_float_convert(asset.get("availBal", asset.get("availEq", balance)))
                frozen = safe_float_convert(asset.get("frozenBal", asset.get("frozen", 0)))
                usd_value = safe_float_convert(asset.get("eqUsd", 0.0))
                if usd_value <= 0:
                    currency = (coin or "").upper()
                    if currency in _OKX_STABLE_COINS:
                        usd_value = balance
                    else:
                        price = safe_float_convert(asset.get("pxUsd", 0.0))
                        if price <= 0:
                            price = safe_float_convert(asset.get("avgPx", 0.0))
                        if price > 0:
                            usd_value = balance * price
                        else:
                            usd_value = _okx_convert_to_usd(currency, balance)
                accumulate_asset(
                    coin,
                    balance=balance,
                    available=available,
                    frozen=frozen,
                    usd_value=usd_value,
                )

        if not aggregated_assets:
            return None

        total_equity = sum(entry.get("usd_value", 0.0) for entry in aggregated_assets.values())

        asset_breakdown = sorted(
            aggregated_assets.values(),
            key=lambda x: x.get("usd_value", 0.0),
            reverse=True,
        )

        return {
            "total_equity": total_equity,
            "assets": asset_breakdown,
        }

    except Exception as e:
        print_warning(f"Could not fetch OKX detailed breakdown: {e}")
        return None


async def get_okx_futures_positions() -> Optional[Dict[str, Any]]:
    """Fetch open OKX futures positions (SWAP) with normalized fields."""
    try:
        if not api_key_manager.authenticate():
            print_warning("API key manager authentication failed, skipping OKX futures positions")
            return None

        credentials = api_key_manager.get_credentials("okx")
        if not credentials or not credentials.passphrase:
            print_warning("OKX API credentials missing or incomplete, skipping futures positions")
            return None

        client = OkxClient(credentials.api_key, credentials.api_secret, credentials.passphrase)
        try:
            response = await client.get_positions("SWAP")
        finally:
            await client.close()

        if not response or response.get("code") != "0":
            return None

        positions = response.get("data", [])
        if not isinstance(positions, list) or not positions:
            return {"positions": [], "timestamp": int(time.time() * 1000)}

        normalized: List[Dict[str, Any]] = []
        for pos in positions:
            if not isinstance(pos, dict):
                continue

            inst_id = pos.get("instId") or pos.get("instSymbol") or ""
            if not inst_id:
                continue

            pos_side = (pos.get("posSide") or pos.get("posType") or "").lower()
            raw_contracts = safe_float_convert(pos.get("pos") or pos.get("position", 0))
            if raw_contracts == 0:
                continue

            entry_price = safe_float_convert(pos.get("avgPx") or pos.get("avgPxCcy") or 0)
            mark_price = safe_float_convert(pos.get("markPx") or pos.get("markPxCcy") or 0)
            liquidation_price = safe_float_convert(pos.get("liqPx") or 0)
            leverage = safe_float_convert(pos.get("lever") or 0)
            unrealized = safe_float_convert(pos.get("upl") or 0)
            margin_mode = pos.get("mgnMode")
            margin_used = safe_float_convert(pos.get("margin") or pos.get("imr") or 0)
            initial_margin = safe_float_convert(pos.get("imr") or 0)

            # Work out a meaningful notionals/size pairing
            reference_price = mark_price if mark_price > 0 else entry_price
            contract_value = safe_float_convert(
                pos.get("ctVal") or pos.get("ctMult") or pos.get("info", {}).get("ctVal") or 0
            )
            raw_notional = safe_float_convert(pos.get("notionalUsd") or pos.get("notionalCcy") or 0)
            # Derive a human-readable position size in underlying units rather than contract count
            base_size = safe_float_convert(
                pos.get("baseSz")
                or pos.get("baseSize")
                or pos.get("info", {}).get("baseSz")
                or pos.get("info", {}).get("baseSize")
                or 0
            )

            if base_size == 0 and abs(raw_notional) > 0 and reference_price > 0:
                base_size = abs(raw_notional) / reference_price
            if base_size == 0 and contract_value > 0:
                base_size = abs(raw_contracts) * contract_value
            if base_size == 0:
                base_size = abs(raw_contracts)

            if raw_notional == 0 and base_size > 0 and reference_price > 0:
                raw_notional = base_size * reference_price
            elif raw_notional == 0 and contract_value > 0 and reference_price > 0:
                raw_notional = abs(raw_contracts) * contract_value * reference_price

            if pos_side == "short":
                size = -base_size
            elif pos_side == "long":
                size = base_size
            else:
                direction = -1 if raw_contracts < 0 else 1
                size = base_size * direction

            normalized.append(
                {
                    "symbol": inst_id,
                    "size": size,
                    "entry_price": entry_price if entry_price > 0 else None,
                    "mark_price": mark_price if mark_price > 0 else None,
                    "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                    "position_value": abs(raw_notional) if abs(raw_notional) > 0 else None,
                    "unrealized_pnl": unrealized,
                    "margin": margin_used if margin_used > 0 else None,
                    "initial_margin": initial_margin if initial_margin > 0 else None,
                    "margin_mode": margin_mode,
                    "leverage": leverage if leverage > 0 else None,
                    "timestamp": safe_float_convert(pos.get("uTime") or pos.get("updateTime") or 0),
                }
            )

        return {"positions": normalized, "timestamp": int(time.time() * 1000)}

    except Exception as e:
        print_warning(f"Could not fetch OKX futures positions: {e}")
        return None


@bybit_retry
def get_bybit_detailed_balance(exchange_manager) -> Optional[Dict[str, Any]]:
    """Get detailed Bybit balance breakdown by asset."""
    try:
        exchange = exchange_manager.initialize_bybit()
        if not exchange:
            return None

        aggregated_assets: Dict[str, Dict[str, float]] = {}
        total_equity = 0.0

        def update_asset(
            coin: str,
            *,
            total: float = 0.0,
            free: float = 0.0,
            used: float = 0.0,
            usd_value: float = 0.0,
        ) -> None:
            if not coin:
                return
            entry = aggregated_assets.setdefault(
                coin,
                {"coin": coin, "total": 0.0, "free": 0.0, "used": 0.0, "usd_value": 0.0},
            )
            entry["total"] += total
            entry["free"] += free
            entry["used"] += used
            entry["usd_value"] += usd_value

        def process_balance_dataset(balance_data: Dict[str, Any]) -> Tuple[bool, Set[str]]:
            nonlocal total_equity
            entries_added = False
            if not balance_data:
                return entries_added, set()

            account_types_found: Set[str] = set()

            processed = False
            result = (
                balance_data.get("info", {}).get("result", {})
                if isinstance(balance_data, dict)
                else {}
            )
            if isinstance(result, dict) and "list" in result and result["list"]:
                for account_data in result["list"]:
                    account_label = (
                        account_data.get("accountType")
                        or account_data.get("account_type")
                        or account_data.get("account")
                        or ""
                    )
                    if account_label:
                        account_types_found.add(str(account_label).upper())
                    coins = account_data.get("coin", [])
                    for coin in coins:
                        currency = coin.get("coin") or coin.get("asset") or ""
                        wallet_balance = safe_float_convert(
                            coin.get("walletBalance", coin.get("wallet_balance", 0))
                        )
                        equity = safe_float_convert(coin.get("equity", wallet_balance))
                        transfer_balance = safe_float_convert(
                            coin.get("transferBalance", coin.get("transfer_balance", 0))
                        )
                        available_raw = safe_float_convert(
                            coin.get("availableToWithdraw", coin.get("availableBalance", 0))
                        )
                        locked_raw = safe_float_convert(coin.get("locked", 0))

                        effective_total = wallet_balance
                        if effective_total <= 0:
                            effective_total = equity
                        if effective_total <= 0:
                            effective_total = transfer_balance

                        available = (
                            available_raw if available_raw > 0 else max(transfer_balance, 0.0)
                        )
                        if available <= 0:
                            available = max(equity, 0.0)
                        if available <= 0:
                            available = effective_total
                        if effective_total > 0:
                            available = min(available, effective_total)
                        used = max(effective_total - available, 0.0) + max(locked_raw, 0.0)

                        usd_value = safe_float_convert(coin.get("usdValue", 0))
                        if usd_value <= 0 and equity > 0:
                            usd_value = equity
                        if usd_value <= 0 and effective_total > 0:
                            usd_value = _bybit_convert_to_usd(exchange, currency, effective_total)

                        update_asset(
                            currency,
                            total=effective_total,
                            free=available,
                            used=used,
                            usd_value=usd_value,
                        )
                        total_equity += usd_value
                        processed = True
                        entries_added = True

            if processed:
                return entries_added, account_types_found

            for coin, data in balance_data.items():
                if coin in {"info", "free", "used", "total", "timestamp", "datetime"}:
                    continue
                if isinstance(data, (int, float)):
                    total_val = safe_float_convert(data)
                    free_val = total_val
                    used_val = 0.0
                elif isinstance(data, dict):
                    total_val = safe_float_convert(data.get("total", data.get("walletBalance", 0)))
                    free_val = safe_float_convert(data.get("free", data.get("available", 0)))
                    used_val = safe_float_convert(data.get("used", data.get("locked", 0)))
                else:
                    continue

                if total_val <= 0:
                    continue

                usd_value = safe_float_convert(
                    (data.get("usdValue") if isinstance(data, dict) else None)
                    or (data.get("equity") if isinstance(data, dict) else None)
                    or total_val
                )

                if usd_value == 0 and total_val > 0:
                    usd_value = _bybit_convert_to_usd(exchange, coin, total_val)

                update_asset(
                    coin,
                    total=total_val,
                    free=free_val,
                    used=used_val,
                    usd_value=usd_value,
                )
                total_equity += usd_value
                entries_added = True

            return entries_added, account_types_found

        fetched_account_types: set[str] = set()

        def fetch_transfer_balance(account_type: str) -> bool:
            nonlocal total_equity
            creds = None
            try:
                creds = api_key_manager.get_credentials("bybit")
            except Exception:
                creds = None
            if (
                not creds
                or not getattr(creds, "api_key", None)
                or not getattr(creds, "api_secret", None)
            ):
                return False

            params = OrderedDict()
            params["accountType"] = account_type
            query = urlencode(list(params.items()))

            try:
                headers = _bybit_sign_request(
                    creds.api_key,
                    creds.api_secret,
                    "GET",
                    "/v5/asset/transfer/query-account-coins-balance",
                    query,
                    "",
                )
            except Exception as err:
                print_warning(f"Failed to sign Bybit transfer balance request: {err}")
                return False

            url = f"https://api.bybit.com/v5/asset/transfer/query-account-coins-balance?{query}"
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
            except requests.HTTPError as http_err:
                msg = str(http_err)
                if "accountType" in msg and "only support" in msg:
                    return False
                print_warning(f"Bybit transfer balance HTTP error ({account_type}): {http_err}")
                return False
            except Exception as err:
                print_warning(f"Bybit transfer balance error ({account_type}): {err}")
                return False

            if not isinstance(data, dict) or data.get("retCode") != 0:
                print_warning(
                    f"Bybit transfer balance returned retCode {data.get('retCode')} for {account_type}"
                )
                return False

            result = data.get("result", {})
            balances = result.get("balance", [])
            if not isinstance(balances, list):
                return False

            entries_added = False

            for item in balances:
                if not isinstance(item, dict):
                    continue

                coin = item.get("coin") or ""
                wallet_balance = safe_float_convert(item.get("walletBalance", 0))
                transfer_balance = safe_float_convert(
                    item.get("transferBalance", item.get("availableBalance", wallet_balance))
                )
                effective_balance = wallet_balance if wallet_balance > 0 else transfer_balance

                if effective_balance == 0 and transfer_balance == 0:
                    continue

                usd_value = safe_float_convert(item.get("usdValue", 0))
                if usd_value == 0 and effective_balance > 0:
                    usd_value = _bybit_convert_to_usd(exchange, coin, effective_balance)

                update_asset(
                    coin,
                    total=effective_balance,
                    free=transfer_balance if transfer_balance > 0 else effective_balance,
                    used=max(effective_balance - max(transfer_balance, 0.0), 0.0),
                    usd_value=usd_value,
                )
                total_equity += usd_value
                entries_added = True

            if entries_added:
                fetched_account_types.add(f"{account_type}-transfer")
            return entries_added

        def process_raw_transfer_balance(account_type: str) -> bool:
            """
            Use Bybit asset transfer endpoint to pull balances for specific account types
            such as FUND, SPOT, CONTRACT, etc. Returns True if balances were added.
            """
            nonlocal total_equity

            method = getattr(
                exchange,
                "private_get_asset_v3_private_transfer_account_coins_balance_query",
                None,
            )
            if method is None:
                return False

            try:
                response = method({"accountType": account_type})
            except ccxt.BadRequest as err:
                msg = str(err)
                if "accountType" in msg and "only support" in msg:
                    return False
                print_warning(f"Bybit {account_type} transfer balance unavailable: {err}")
                return False
            except ccxt.AuthenticationError:
                raise
            except Exception as err:
                print_warning(f"Bybit {account_type} transfer balance error: {err}")
                return False

            result = response.get("result", {}) if isinstance(response, dict) else {}
            balances = result.get("balance") or result.get("list") or []
            if not isinstance(balances, list):
                return False

            entries_added = False
            for item in balances:
                if not isinstance(item, dict):
                    continue
                coin = item.get("coin") or item.get("tokenId") or ""
                wallet_balance = safe_float_convert(
                    item.get("walletBalance", item.get("totalBalance", 0))
                )
                available = safe_float_convert(
                    item.get("availableBalance", item.get("available", wallet_balance))
                )
                effective_balance = wallet_balance if wallet_balance > 0 else available
                used = max(effective_balance - available, 0.0)
                usd_value = safe_float_convert(item.get("usdValue", 0))
                if usd_value == 0 and effective_balance != 0:
                    usd_value = _bybit_convert_to_usd(exchange, coin, effective_balance)

                if effective_balance == 0 and usd_value == 0:
                    continue

                update_asset(
                    coin,
                    total=effective_balance,
                    free=available,
                    used=used,
                    usd_value=usd_value,
                )
                total_equity += usd_value
                entries_added = True

            if entries_added:
                fetched_account_types.add(f"{account_type}-transfer")
            return entries_added

        def attempt_fetch(account_type: Optional[str]) -> None:
            params: Dict[str, Any] = {}
            label = account_type or "DEFAULT"
            if label in fetched_account_types:
                return
            if account_type:
                params["accountType"] = account_type
            try:
                balance = exchange.fetch_balance(params)
            except Exception as err:
                msg = str(err)
                if account_type and "accountType only support" in msg:
                    return
                if account_type:
                    print_warning(f"Bybit {account_type} balance unavailable: {err}")
                    fetch_transfer_balance(account_type)
                return
            entries_added, account_types_found = process_balance_dataset(balance)
            if entries_added:
                fetched_account_types.add(label)
                if account_type and account_type.upper() not in account_types_found:
                    fetch_transfer_balance(account_type)
                return

            if account_type:
                fetch_transfer_balance(account_type)

        account_type_candidates = ["UNIFIED", "FUND"]
        for account_type in account_type_candidates:
            attempt_fetch(account_type)

        # Guarantee FUND transfer balances are merged even if ccxt omits the account type.
        if "FUND-transfer" not in fetched_account_types:
            fetch_transfer_balance("FUND")

        if not aggregated_assets:
            attempt_fetch(None)

        if not aggregated_assets:
            return None

        asset_breakdown = sorted(
            aggregated_assets.values(),
            key=lambda x: x.get("usd_value", 0.0),
            reverse=True,
        )

        return {
            "total_equity": total_equity,
            "assets": asset_breakdown,
        }

    except Exception as e:
        print_error(f"Error fetching Bybit detailed balance: {e}")
        raise  # Let the retry decorator handle exceptions
        return None


@bybit_retry
def get_bybit_futures_positions(exchange_manager) -> Optional[Dict[str, Any]]:
    """Fetch Bybit futures/perpetual positions using ccxt unified account."""
    try:
        exchange = exchange_manager.initialize_bybit()
        if not exchange:
            return None

        normalized_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        def _normalize_position(pos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if not isinstance(pos, dict):
                return None

            symbol = pos.get("symbol") or pos.get("info", {}).get("symbol") or "UNKNOWN"
            side = (pos.get("side") or pos.get("info", {}).get("side") or "").lower()
            size_raw = safe_float_convert(
                pos.get("contracts")
                or pos.get("size")
                or pos.get("info", {}).get("size")
                or pos.get("qty")
                or pos.get("info", {}).get("qty")
                or 0
            )
            contracts_raw = safe_float_convert(
                pos.get("contracts") or pos.get("qty") or pos.get("info", {}).get("qty") or 0
            )
            if size_raw == 0 and contracts_raw == 0:
                return None

            entry_price = safe_float_convert(
                pos.get("entryPrice")
                or pos.get("avgPrice")
                or pos.get("avgEntryPrice")
                or pos.get("info", {}).get("avgPrice")
                or 0
            )
            mark_price = safe_float_convert(
                pos.get("markPrice")
                or pos.get("lastPrice")
                or pos.get("info", {}).get("markPrice")
                or 0
            )
            liquidation_price = safe_float_convert(
                pos.get("liquidationPrice")
                or pos.get("liqPrice")
                or pos.get("info", {}).get("liqPrice")
                or 0
            )
            leverage = safe_float_convert(
                pos.get("leverage") or pos.get("info", {}).get("leverage") or 0
            )
            unrealized = safe_float_convert(
                pos.get("unrealizedPnl")
                or pos.get("unrealisedPnl")
                or pos.get("info", {}).get("unrealisedPnl")
                or 0
            )
            margin_mode = pos.get("marginMode") or pos.get("info", {}).get("tradeMode")
            initial_margin = safe_float_convert(
                pos.get("initialMargin")
                or pos.get("positionIM")
                or pos.get("info", {}).get("positionIM")
                or 0
            )
            margin_used = safe_float_convert(
                pos.get("collateral")
                or pos.get("positionMM")
                or pos.get("info", {}).get("positionMM")
                or initial_margin
            )
            notional = safe_float_convert(
                pos.get("notional")
                or pos.get("positionValue")
                or pos.get("info", {}).get("positionValue")
                or pos.get("positionValueAbs")
                or pos.get("info", {}).get("positionValueAbs")
                or pos.get("positionValueCoin")
                or 0
            )

            reference_price = mark_price if mark_price > 0 else entry_price
            base_size = size_raw
            if base_size == 0 and abs(notional) > 0 and reference_price > 0:
                base_size = abs(notional) / reference_price
            elif base_size != 0 and abs(notional) > 0 and reference_price > 0:
                estimated = abs(notional) / reference_price
                if estimated > 0 and abs(base_size) / estimated > 5:
                    base_size = estimated
            elif base_size == 0 and contracts_raw != 0 and reference_price > 0:
                base_size = abs(contracts_raw)
                if abs(notional) > 0:
                    base_size = abs(notional) / reference_price

            if base_size == 0:
                base_size = abs(contracts_raw) or abs(size_raw)
            if base_size == 0:
                return None

            if side in {"sell", "short"}:
                size = -base_size
            else:
                size = base_size

            if abs(notional) == 0 and reference_price > 0:
                notional = base_size * reference_price

            return {
                "symbol": symbol,
                "size": size,
                "entry_price": entry_price if entry_price > 0 else None,
                "mark_price": mark_price if mark_price > 0 else None,
                "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                "position_value": abs(notional) if abs(notional) > 0 else None,
                "unrealized_pnl": unrealized,
                "margin": margin_used if margin_used > 0 else None,
                "initial_margin": initial_margin if initial_margin > 0 else None,
                "margin_mode": margin_mode,
                "leverage": leverage if leverage > 0 else None,
            }

        def _store_position(candidate: Dict[str, Any]) -> None:
            normalized_pos = _normalize_position(candidate)
            if not normalized_pos:
                return
            key_symbol = (normalized_pos.get("symbol") or "UNKNOWN").upper()
            size_value = safe_float_convert(normalized_pos.get("size"), 0.0)
            direction = "long" if size_value >= 0 else "short"
            normalized_map[(key_symbol, direction)] = normalized_pos

        def _collect_from_positions(payload: Any) -> None:
            if isinstance(payload, list):
                for pos in payload:
                    _store_position(pos)

        # Attempt better coverage with ccxt: try category- and settle-specific calls first
        categories_to_try = ["linear", "inverse"]
        try:
            if not getattr(exchange, "markets", None):
                exchange.load_markets()
        except Exception:
            pass

        param_candidates: List[Dict[str, Any]] = [{}]
        param_candidates.extend({"category": cat} for cat in categories_to_try)
        param_candidates.extend(
            {"category": "linear", "settleCoin": coin} for coin in ("USDT", "USDC", "USD")
        )
        param_candidates.extend({"settleCoin": coin} for coin in ("USDT", "USDC"))

        seen_param_keys: Set[Tuple[Tuple[str, Any], ...]] = set()
        for params in param_candidates:
            key = tuple(sorted(params.items()))
            if key in seen_param_keys:
                continue
            seen_param_keys.add(key)
            try:
                if params:
                    positions = exchange.fetch_positions(None, params)
                else:
                    positions = exchange.fetch_positions()
            except Exception:
                continue
            if not isinstance(positions, list):
                continue
            _collect_from_positions(positions)

        # Fallback to default fetch_positions (legacy accounts) if nothing yet
        if not normalized_map:
            try:
                fallback_positions = exchange.fetch_positions()
                if isinstance(fallback_positions, list):
                    _collect_from_positions(fallback_positions)
            except Exception as err:
                print_warning(f"Bybit fetch_positions fallback failed: {err}")

        # Final fallback: hit raw V5 position endpoint for broader coverage
        if not normalized_map:
            raw_method = None
            for attr in (
                "privateGetV5PositionList",
                "v5PrivateGetPositionList",
                "private_get_v5_position_list",
            ):
                raw_method = getattr(exchange, attr, None)
                if raw_method:
                    break

            def _extract_payload(response: Any) -> List[Dict[str, Any]]:
                if not response:
                    return []
                if isinstance(response, list):
                    return response
                if isinstance(response, dict):
                    for key in ("result", "retData", "data"):
                        if key in response:
                            candidate = response[key]
                            if isinstance(candidate, list):
                                return candidate
                            if isinstance(candidate, dict):
                                for inner_key in ("list", "positions", "data"):
                                    inner = candidate.get(inner_key)
                                    if isinstance(inner, list):
                                        return inner
                    return []
                return []

            if raw_method:
                raw_param_sets = [
                    {"category": "linear"},
                    {"category": "linear", "settleCoin": "USDT"},
                    {"category": "linear", "settleCoin": "USDC"},
                    {"category": "inverse"},
                ]
                for raw_params in raw_param_sets:
                    try:
                        response = raw_method(raw_params)
                    except Exception:
                        continue
                    for item in _extract_payload(response):
                        _store_position(item)

        if not normalized_map:
            return None

        normalized = list(normalized_map.values())
        normalized.sort(
            key=lambda p: (p.get("symbol") or "", safe_float_convert(p.get("size"), 0)),
            reverse=False,
        )

        return {"positions": normalized, "timestamp": int(time.time() * 1000)}

    except ccxt.AuthenticationError:
        print_error("Bybit authentication failed while fetching futures positions.")
        raise
    except ccxt.NetworkError as e:
        print_error(f"Bybit network error fetching futures positions: {e}")
        raise
    except Exception as e:
        print_error(f"Error fetching Bybit futures positions: {e}")
        raise
    return None


@backpack_retry
def get_backpack_detailed_balance() -> Optional[Dict[str, Any]]:
    """Get detailed Backpack balance breakdown by asset using collateral endpoint."""
    try:
        # Import SigningKey only when needed
        try:
            from nacl.signing import SigningKey
        except ImportError:
            print_warning("Backpack support not available: PyNaCl library not installed.")
            return None

        # Get Backpack credentials from API key manager
        if not api_key_manager.authenticate():
            print_warning(
                "API key manager authentication failed, skipping Backpack detailed breakdown"
            )
            return None

        credentials = api_key_manager.get_credentials("backpack")
        if not credentials:
            print_warning("Backpack API credentials not found, skipping detailed breakdown")
            return None

        api_key = credentials.api_key
        api_secret = credentials.api_secret

        ts = int(time.time() * 1000)

        # Use collateral endpoint (the balances endpoint doesn't exist)
        collateral_msg = f"instruction=collateralQuery&timestamp={ts}&window={BACKPACK_WINDOW}"
        collateral_sig = sign_backpack_request_custom(api_secret, collateral_msg)

        headers = {
            "X-API-Key": api_key,
            "X-Signature": collateral_sig,
            "X-Timestamp": str(ts),
            "X-Window": str(BACKPACK_WINDOW),
            "Content-Type": "application/json",
        }

        print_info("Fetching Backpack asset breakdown via collateral endpoint...")

        # Use the collateral endpoint which provides individual asset breakdown
        resp = requests.get(BACKPACK_API_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            print_warning("Backpack collateral endpoint returned empty data")
            return None

        # Extract individual asset breakdowns from collateral data
        asset_breakdown = []
        total_equity = safe_float_convert(data.get("assetsValue", 0))

        # Get individual asset breakdowns from collateral array
        collateral_assets = data.get("collateral", [])
        for asset in collateral_assets:
            symbol = asset.get("symbol", "")
            total_quantity = safe_float_convert(asset.get("totalQuantity", 0))
            available_quantity = safe_float_convert(asset.get("availableQuantity", 0))
            lend_quantity = safe_float_convert(asset.get("lendQuantity", 0))
            balance_notional = safe_float_convert(asset.get("balanceNotional", 0))  # USD value

            if total_quantity > 0.000001:  # Only show assets with meaningful value
                asset_breakdown.append(
                    {
                        "coin": symbol,
                        "total": total_quantity,
                        "available": available_quantity,
                        "locked": lend_quantity,  # lendQuantity represents locked/staked amount
                        "usd_value": balance_notional,
                    }
                )

        print_success(
            f"Backpack detailed balance: Found {len(asset_breakdown)} assets, total: ${total_equity:.2f}"
        )

        return {
            "total_equity": total_equity,
            "assets": sorted(asset_breakdown, key=lambda x: x["usd_value"], reverse=True),
        }

    except requests.exceptions.HTTPError as e:
        print_error(
            f"HTTP Error fetching Backpack collateral data: {e.response.status_code} - {e.response.text}"
        )
        return None
    except Exception as e:
        print_error(f"Error fetching Backpack detailed balance: {e}")
        return None


@binance_retry
def fetch_binance_single_account_balance(
    api_key: str, api_secret: str
) -> Optional[List[Dict[str, Any]]]:
    """Fetches wallet balances for a single Binance account. Returns None on failure."""
    from utils.helpers import get_current_timestamp_ms
    from urllib.parse import urlencode
    import hmac
    import hashlib
    import json

    endpoint = f"{BINANCE_BASE_URL}{BINANCE_WALLET_BALANCE_ENDPOINT}"
    timestamp = get_current_timestamp_ms()
    params = {"timestamp": timestamp}
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    headers = {"X-MBX-APIKEY": api_key}
    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        else:
            # Handle Binance error format { "code": -..., "msg": "..." }
            error_msg = data.get("msg", "Unexpected response format")
            print_error(
                f"Fetching Binance balance for key {api_key[:5]}...: {error_msg} (Code: {data.get('code', 'N/A')})"
            )
            return None
    except requests.exceptions.HTTPError as e:
        # More specific HTTP error handling
        print_error(
            f"HTTP Error fetching Binance balance for key {api_key[:5]}...: {e.response.status_code} - {e.response.text}"
        )
    except requests.exceptions.RequestException as e:
        is_network = isinstance(
            e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        )
        print_error(
            f"Network Error fetching Binance balance for key {api_key[:5]}...: {e}",
            is_network_issue=is_network,
        )
    except json.JSONDecodeError as e:
        print_error(f"JSON decode error fetching Binance balance for key {api_key[:5]}...: {e}")
    except Exception as e:
        print_error(f"Unexpected error fetching Binance balance for key {api_key[:5]}...: {e}")
    return None


@okx_retry
async def get_okx_total_balance_async() -> Optional[float]:
    """Get total balance from OKX exchange using async client."""
    try:
        # Get OKX credentials from API key manager
        if not api_key_manager.authenticate():
            print_warning("API key manager authentication failed, skipping OKX")
            return None

        credentials = api_key_manager.get_credentials("okx")
        if not credentials or not credentials.passphrase:
            print_warning("OKX API credentials not found or missing passphrase, skipping")
            return None

        client = OkxClient(credentials.api_key, credentials.api_secret, credentials.passphrase)
        try:
            account_data = await client.get_account_balance()
            funding_data = await client.get_asset_balances()
        finally:
            await client.close()

        trading_equity = _okx_sum_account_equity(account_data)
        funding_equity = _okx_sum_funding_equity(funding_data)
        total_equity = trading_equity + funding_equity

        if total_equity < 0:
            return None

        print_success(
            "OKX balance fetching completed. "
            f"Trading: {format_currency(trading_equity)} | "
            f"Funding: {format_currency(funding_equity)} | "
            f"Total: {format_currency(total_equity)}"
        )
        return total_equity if total_equity > 0 else 0.0

    except Exception as e:
        print_error(f"Error fetching OKX balance: {e}")
        raise  # Re-raise the exception to let the decorator handle it


@okx_retry
async def get_okx_account_types_breakdown() -> Optional[Dict[str, Any]]:
    """Return OKX trading vs funding balances for account breakdown displays."""
    try:
        if not api_key_manager.authenticate():
            print_warning("API key manager authentication failed, skipping OKX account breakdown")
            return None

        credentials = api_key_manager.get_credentials("okx")
        if not credentials or not credentials.passphrase:
            print_warning("OKX API credentials missing for account breakdown")
            return None

        client = OkxClient(credentials.api_key, credentials.api_secret, credentials.passphrase)
        try:
            account_data = await client.get_account_balance()
            funding_data = await client.get_asset_balances()
        finally:
            await client.close()

        trading_equity = _okx_sum_account_equity(account_data)
        funding_equity = _okx_sum_funding_equity(funding_data)
        account_types = {
            "Trading": trading_equity,
            "Funding": funding_equity,
        }
        total = sum(max(safe_float_convert(value), 0.0) for value in account_types.values())

        return {
            "total_all_accounts": total,
            "account_types": account_types,
        }

    except Exception as e:
        print_error(f"Error fetching OKX account type breakdown: {e}")
        return None


@bybit_retry
def get_bybit_total_balance(exchange_manager) -> Optional[float]:
    """Get total balance from Bybit exchange."""
    try:
        exchange = exchange_manager.initialize_bybit()
        if not exchange:
            return None

        total_equity = 0.0
        accounted_types: Set[str] = set()

        def accumulate_from_balance(balance_payload: Optional[Dict[str, Any]]) -> float:
            subtotal, seen_types = _bybit_extract_total_equity_from_balance(
                exchange, balance_payload
            )
            if seen_types:
                accounted_types.update({acct for acct in seen_types if acct})
            return subtotal

        # Default unified balance call
        try:
            base_balance = exchange.fetch_balance()
        except Exception as err:
            print_warning(f"Bybit default balance unavailable: {err}")
            base_balance = None

        if base_balance:
            subtotal = accumulate_from_balance(base_balance)
            if subtotal:
                total_equity += subtotal

        account_type_candidates = ["UNIFIED", "FUND"]

        for account_type in account_type_candidates:
            if account_type in accounted_types:
                continue

            subtotal = 0.0
            try:
                balance = exchange.fetch_balance({"accountType": account_type})
            except Exception as err:
                msg = str(err)
                if "accountType only support" in msg:
                    pass
                else:
                    print_warning(f"Bybit {account_type} balance unavailable: {err}")
                subtotal = _bybit_fetch_transfer_total(exchange, account_type)
            else:
                subtotal = accumulate_from_balance(balance)
                if subtotal == 0:
                    subtotal = _bybit_fetch_transfer_total(exchange, account_type)

            if subtotal:
                total_equity += subtotal
                accounted_types.add(account_type)

        if total_equity > 0:
            print_success(
                f"Bybit balance fetching completed. Balance: {format_currency(total_equity)}"
            )
            return total_equity

        return None

    except Exception as e:
        print_error(f"Error fetching Bybit balance: {e}")
        raise  # Let the retry decorator handle exceptions
        return None


@bybit_retry
def get_bybit_account_types_breakdown(exchange_manager) -> Optional[Dict[str, Any]]:
    """Return Bybit unified vs funding balances for account breakdown displays."""
    try:
        exchange = exchange_manager.initialize_bybit()
        if not exchange:
            return None

        account_types: Dict[str, float] = {}
        total_all = 0.0

        def compute_total(label: str, account_type: Optional[str]) -> float:
            subtotal = 0.0
            if account_type:
                try:
                    balance_payload = exchange.fetch_balance({"accountType": account_type})
                except Exception as err:
                    msg = str(err)
                    if "accountType only support" not in msg:
                        print_warning(f"Bybit {account_type} balance unavailable: {err}")
                    subtotal = _bybit_fetch_transfer_total(exchange, account_type)
                else:
                    subtotal, _ = _bybit_extract_total_equity_from_balance(
                        exchange, balance_payload
                    )
                    if subtotal == 0:
                        subtotal = _bybit_fetch_transfer_total(exchange, account_type)
            else:
                try:
                    balance_payload = exchange.fetch_balance()
                except Exception as err:
                    print_warning(f"Bybit default balance unavailable: {err}")
                    subtotal = 0.0
                else:
                    subtotal, _ = _bybit_extract_total_equity_from_balance(
                        exchange, balance_payload
                    )
            return max(subtotal, 0.0)

        unified_total = compute_total("Unified", "UNIFIED")
        if unified_total <= 0:
            unified_total = compute_total("Unified", None)
        account_types["Unified"] = unified_total
        total_all += unified_total

        funding_total = compute_total("Funding", "FUND")
        account_types["Funding"] = funding_total
        total_all += funding_total

        return {
            "total_all_accounts": total_all,
            "account_types": account_types,
        }

    except Exception as e:
        print_error(f"Error fetching Bybit account type breakdown: {e}")
        return None


def get_binance_account_types_breakdown() -> Optional[Dict[str, Any]]:
    """Get Binance balance breakdown by account types (Spot, USD-M Futures, etc.)."""
    try:
        from api_clients.api_manager import api_key_manager

        # Get Binance credentials from API key manager
        if not api_key_manager.authenticate():
            print_warning(
                "API key manager authentication failed, skipping Binance account types breakdown"
            )
            return None

        credentials = api_key_manager.get_credentials("binance")
        if not credentials:
            print_warning("Binance API credentials not found, skipping account types breakdown")
            return None

        api_key = credentials.api_key
        api_secret = credentials.api_secret

        from urllib.parse import urlencode
        import hmac
        import hashlib

        account_types = {}
        total_all_accounts = 0.0

        # 1. Get Spot Account Balance
        try:
            endpoint = "https://api.binance.com/api/v3/account"
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}

            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature

            headers = {"X-MBX-APIKEY": api_key}

            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()

            if data and "balances" in data:
                # Get prices for conversion
                try:
                    price_response = requests.get(
                        "https://api.binance.com/api/v3/ticker/price", timeout=10
                    )
                    price_response.raise_for_status()
                    price_data = price_response.json()

                    prices = {}
                    for item in price_data:
                        symbol = item.get("symbol", "")
                        price = safe_float_convert(item.get("price", 0))
                        if symbol and price > 0:
                            prices[symbol] = price
                except:
                    prices = {}

                spot_total = 0.0
                for balance in data.get("balances", []):
                    asset = (balance.get("asset", "") or "").upper()
                    free = safe_float_convert(balance.get("free", 0))
                    locked = safe_float_convert(balance.get("locked", 0))
                    total = free + locked

                    if total > 0.000001:
                        # Convert to USD value
                        usd_value = 0.0
                        if asset in _BINANCE_STABLE_COINS:
                            usd_value = total
                        else:
                            for quote in ["USDT", "BUSD", "USDC"]:
                                pair = f"{asset}{quote}"
                                if pair in prices:
                                    usd_value = total * prices[pair]
                                    break
                        if usd_value <= 0:
                            usd_value = _binance_convert_to_usd(asset, total)
                        spot_total += usd_value

                account_types["Spot"] = spot_total
                total_all_accounts += spot_total

        except Exception as e:
            print_warning(f"Could not fetch Binance Spot balance: {e}")
            account_types["Spot"] = None

        # 2. Get USD-M Futures Balance (using balance endpoint instead of account)
        try:
            endpoint = "https://fapi.binance.com/fapi/v2/balance"
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}

            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature

            headers = {"X-MBX-APIKEY": api_key}

            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            balance_data = response.json()

            # Calculate total USD-M futures balance from individual assets
            usdm_total = 0.0
            if balance_data and isinstance(balance_data, list):
                for asset_balance in balance_data:
                    if isinstance(asset_balance, dict):
                        balance = safe_float_convert(asset_balance.get("balance", 0))
                        if balance > 0:
                            usdm_total += balance

            account_types["USD-M Futures"] = usdm_total
            total_all_accounts += usdm_total

        except requests.exceptions.HTTPError as e:
            print_error(f"USD-M Futures HTTP error {e.response.status_code}: {e.response.text}")
            account_types["USD-M Futures"] = 0.0
        except Exception as e:
            print_error(f"USD-M Futures error: {e}")
            account_types["USD-M Futures"] = 0.0

        # 3. Get Coin-M Futures Balance
        try:
            endpoint = "https://dapi.binance.com/dapi/v1/account"
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}

            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature

            headers = {"X-MBX-APIKEY": api_key}

            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()

            if data and "totalWalletBalance" in data:
                coinm_balance = safe_float_convert(data.get("totalWalletBalance", 0))
                account_types["Coin-M Futures"] = coinm_balance
                total_all_accounts += coinm_balance
            else:
                account_types["Coin-M Futures"] = 0.0

        except Exception as e:
            # This is normal if user doesn't have coin futures enabled
            account_types["Coin-M Futures"] = 0.0

        # 4. Get Funding Account Balance
        try:
            endpoint = "https://api.binance.com/sapi/v1/asset/get-funding-asset"
            timestamp = int(time.time() * 1000)
            params = {
                "timestamp": timestamp,
            }

            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature

            headers = {"X-MBX-APIKEY": api_key}

            response = requests.post(endpoint, data=params, headers=headers, timeout=20)
            response.raise_for_status()
            funding_data = response.json()

            funding_total = 0.0
            if isinstance(funding_data, list):
                for entry in funding_data:
                    if not isinstance(entry, dict):
                        continue

                    asset_symbol = (entry.get("asset", "") or "").upper()
                    free_amt = safe_float_convert(entry.get("free", 0))
                    locked_amt = safe_float_convert(entry.get("locked", 0))
                    freeze_amt = safe_float_convert(entry.get("freeze", 0))
                    withdrawing_amt = safe_float_convert(entry.get("withdrawing", 0))

                    total_amount = free_amt + locked_amt + freeze_amt + withdrawing_amt
                    if total_amount <= 0:
                        continue

                    usd_value = safe_float_convert(entry.get("usdValuation", 0.0))
                    if usd_value <= 0:
                        btc_value = safe_float_convert(entry.get("btcValuation", 0.0))
                        if btc_value > 0:
                            usd_value = _binance_convert_to_usd("BTC", btc_value)
                        if usd_value <= 0:
                            usd_value = _binance_convert_to_usd(asset_symbol, total_amount)

                    funding_total += max(usd_value, 0.0)

            account_types["Funding"] = funding_total
            total_all_accounts += funding_total

        except requests.exceptions.HTTPError as e:
            print_warning(f"Funding account HTTP error {e.response.status_code}: {e.response.text}")
            account_types["Funding"] = 0.0
        except Exception as e:
            print_warning(f"Funding account error: {e}")
            account_types["Funding"] = 0.0

        return {
            "total_all_accounts": total_all_accounts,
            "account_types": account_types,
        }

    except Exception as e:
        print_error(f"Error fetching Binance account types breakdown: {e}")
        return None


@binance_retry
def get_binance_futures_positions() -> Optional[Dict[str, Any]]:
    """Fetch Binance USD-M and Coin-M futures position details."""
    try:
        if not api_key_manager.authenticate():
            print_warning(
                "API key manager authentication failed, skipping Binance futures positions"
            )
            return None

        credentials = api_key_manager.get_credentials("binance")
        if not credentials:
            print_warning("Binance API credentials not found, skipping futures position fetch")
            return None

        api_key = credentials.api_key
        api_secret = credentials.api_secret

        from urllib.parse import urlencode
        import hmac
        import hashlib

        def signed_get(endpoint: str) -> Optional[List[Dict[str, Any]]]:
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature
            headers = {"X-MBX-APIKEY": api_key}

            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            print_warning(f"Unexpected response type from {endpoint}: {type(payload)}")
            return None

        usd_m_positions_raw = signed_get("https://fapi.binance.com/fapi/v2/positionRisk")
        coin_m_positions_raw = signed_get("https://dapi.binance.com/dapi/v1/positionRisk")

        def normalize_positions(
            raw_positions: Optional[List[Dict[str, Any]]],
        ) -> List[Dict[str, Any]]:
            normalized: List[Dict[str, Any]] = []
            if not isinstance(raw_positions, list):
                return normalized

            for position in raw_positions:
                if not isinstance(position, dict):
                    continue

                symbol = position.get("symbol") or position.get("pair")
                position_amt = safe_float_convert(
                    position.get("positionAmt")
                    or position.get("position")
                    or position.get("positionQty")
                    or 0
                )
                if abs(position_amt) < 1e-9:
                    continue

                entry_price = safe_float_convert(position.get("entryPrice") or 0)
                mark_price = safe_float_convert(position.get("markPrice") or 0)
                liquidation_price = safe_float_convert(position.get("liquidationPrice") or 0)
                raw_notional = safe_float_convert(
                    position.get("notional") or position.get("notionalUsd") or 0
                )
                notional = abs(raw_notional)
                unrealized = safe_float_convert(position.get("unRealizedProfit") or 0)
                leverage = safe_float_convert(position.get("leverage") or 0)

                isolated_margin = safe_float_convert(
                    position.get("isolatedMargin")
                    or position.get("isolatedWallet")
                    or position.get("isolatedBalance")
                    or 0
                )
                position_initial_margin = safe_float_convert(
                    position.get("positionInitialMargin") or 0
                )
                initial_margin = isolated_margin if isolated_margin > 0 else position_initial_margin

                normalized.append(
                    {
                        "symbol": symbol,
                        "size": position_amt,
                        "entry_price": entry_price if entry_price > 0 else None,
                        "mark_price": mark_price if mark_price > 0 else None,
                        "liquidation_price": liquidation_price if liquidation_price > 0 else None,
                        "position_value": notional if abs(notional) > 0 else None,
                        "unrealized_pnl": unrealized,
                        "leverage": leverage if leverage > 0 else None,
                        "margin_type": position.get("marginType"),
                        "margin": initial_margin if initial_margin > 0 else None,
                        "initial_margin": (
                            position_initial_margin if position_initial_margin > 0 else None
                        ),
                    }
                )

            return normalized

        return {
            "usd_m": normalize_positions(usd_m_positions_raw),
            "coin_m": normalize_positions(coin_m_positions_raw),
            "timestamp": int(time.time() * 1000),
        }

    except requests.exceptions.HTTPError as e:
        print_error(
            f"HTTP Error fetching Binance futures positions: {e.response.status_code} - {e.response.text}"
        )
        return None
    except Exception as e:
        print_error(f"Error fetching Binance futures positions: {e}")
        return None


@binance_retry
def get_binance_detailed_balance() -> Optional[Dict[str, Any]]:
    """Get detailed Binance balance breakdown by individual assets."""
    try:
        from api_clients.api_manager import api_key_manager

        # Get Binance credentials from API key manager
        if not api_key_manager.authenticate():
            print_warning(
                "API key manager authentication failed, skipping Binance detailed breakdown"
            )
            return None

        credentials = api_key_manager.get_credentials("binance")
        if not credentials:
            print_warning("Binance API credentials not found, skipping detailed breakdown")
            return None

        api_key = credentials.api_key
        api_secret = credentials.api_secret

        # Use the standard account endpoint to get individual asset balances
        endpoint = "https://api.binance.com/api/v3/account"
        timestamp = int(time.time() * 1000)
        params = {"timestamp": timestamp}

        from urllib.parse import urlencode
        import hmac
        import hashlib

        query_string = urlencode(params)
        signature = hmac.new(
            api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature

        headers = {"X-MBX-APIKEY": api_key}

        response = requests.get(endpoint, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()

        if not data or "balances" not in data:
            print_warning("Binance account endpoint returned no balance data")
            return None

        aggregated_assets: Dict[str, Dict[str, float]] = {}
        total_equity = 0.0

        # We'll need prices to convert to USD - get them from a price endpoint
        try:
            price_response = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=10)
            price_response.raise_for_status()
            price_data = price_response.json()

            # Create price lookup dict
            prices = {}
            for item in price_data:
                symbol = item.get("symbol", "")
                price = safe_float_convert(item.get("price", 0))
                if symbol and price > 0:
                    prices[symbol] = price

        except Exception as e:
            print_warning(f"Could not fetch Binance prices for asset conversion: {e}")
            prices = {}

        def accumulate_asset(
            symbol: str, *, total: float, free: float, locked: float, usd_value: float
        ) -> None:
            if not symbol or total <= 0:
                return
            entry = aggregated_assets.setdefault(
                symbol,
                {"coin": symbol, "total": 0.0, "free": 0.0, "locked": 0.0, "usd_value": 0.0},
            )
            entry["total"] += total
            entry["free"] += free
            entry["locked"] += locked
            entry["usd_value"] += max(usd_value, 0.0)

        for balance in data.get("balances", []):
            asset = (balance.get("asset", "") or "").upper()
            free = safe_float_convert(balance.get("free", 0))
            locked = safe_float_convert(balance.get("locked", 0))
            total = free + locked

            if total <= 0.000001:
                continue

            usd_value = 0.0
            if asset in _BINANCE_STABLE_COINS:
                usd_value = total
            else:
                for quote in ["USDT", "BUSD", "USDC"]:
                    pair = f"{asset}{quote}"
                    if pair in prices:
                        usd_value = total * prices[pair]
                        break
            if usd_value <= 0:
                usd_value = _binance_convert_to_usd(asset, total)

            accumulate_asset(asset, total=total, free=free, locked=locked, usd_value=usd_value)

        # Fetch funding account balances and merge
        try:
            endpoint = "https://api.binance.com/sapi/v1/asset/get-funding-asset"
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}

            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            params["signature"] = signature

            headers = {"X-MBX-APIKEY": api_key}

            response = requests.post(endpoint, data=params, headers=headers, timeout=20)
            response.raise_for_status()
            funding_assets = response.json()

            if isinstance(funding_assets, list):
                for entry in funding_assets:
                    if not isinstance(entry, dict):
                        continue
                    asset_symbol = (entry.get("asset", "") or "").upper()
                    free_amt = safe_float_convert(entry.get("free", 0))
                    locked_amt = safe_float_convert(entry.get("locked", 0))
                    freeze_amt = safe_float_convert(entry.get("freeze", 0))
                    withdrawing_amt = safe_float_convert(entry.get("withdrawing", 0))
                    total_amt = free_amt + locked_amt + freeze_amt + withdrawing_amt
                    if total_amt <= 0:
                        continue

                    usd_value = safe_float_convert(entry.get("usdValuation", 0.0))
                    if usd_value <= 0:
                        btc_value = safe_float_convert(entry.get("btcValuation", 0.0))
                        if btc_value > 0:
                            usd_value = _binance_convert_to_usd("BTC", btc_value)
                        if usd_value <= 0:
                            usd_value = _binance_convert_to_usd(asset_symbol, total_amt)

                    # Treat freeze/withdrawing as locked component
                    additional_locked = locked_amt + freeze_amt + withdrawing_amt
                    accumulate_asset(
                        asset_symbol,
                        total=total_amt,
                        free=free_amt,
                        locked=additional_locked,
                        usd_value=usd_value,
                    )
        except Exception as e:
            print_warning(f"Funding asset merge failed: {e}")

        asset_breakdown = [
            asset_data
            for asset_data in (
                {
                    "coin": symbol,
                    "total": values["total"],
                    "free": values["free"],
                    "locked": values["locked"],
                    "usd_value": values["usd_value"],
                }
                for symbol, values in aggregated_assets.items()
            )
            if asset_data["usd_value"] > 0.01
        ]

        total_equity = sum(item["usd_value"] for item in asset_breakdown)

        return {
            "total_equity": total_equity,
            "assets": sorted(asset_breakdown, key=lambda x: x["usd_value"], reverse=True),
        }

    except requests.exceptions.HTTPError as e:
        print_error(
            f"HTTP Error fetching Binance account data: {e.response.status_code} - {e.response.text}"
        )
        return None
    except Exception as e:
        print_error(f"Error fetching Binance detailed balance: {e}")
        return None
