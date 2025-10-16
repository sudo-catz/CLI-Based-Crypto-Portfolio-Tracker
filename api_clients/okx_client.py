# -*- coding: utf-8 -*-
"""
OKX API Client for Multi-Chain Portfolio Tracker
"""
import json
import httpx
from typing import Dict, Any, Optional
from urllib.parse import urlencode

# Import constants and utilities
from config.constants import (
    OKX_API_URL,
    OKX_GET,
    OKX_POST,
    OKX_GET_ACCOUNT_BALANCE,
    OKX_GET_BALANCES,
    OKX_GET_POSITIONS,
)
from utils.helpers import (
    get_current_timestamp_iso,
    okx_pre_hash,
    generate_okx_sign,
    get_okx_header,
    print_error,
)


class OkxClient:
    """Client for interacting with the OKX API."""

    def __init__(self, api_key: str, api_secret_key: str, passphrase: str, flag: str = "0"):
        self.api_key = api_key
        self.api_secret_key = api_secret_key
        self.passphrase = passphrase
        self.flag = flag
        # Use httpx.AsyncClient for async operations
        self.client = httpx.AsyncClient(
            base_url=OKX_API_URL, http2=True, timeout=30.0
        )  # Increased timeout

    async def _request(
        self, method: str, request_path: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Makes a generic asynchronous request to the OKX API. Returns None on failure."""
        body_str = ""
        query_params = ""
        full_request_path = request_path

        if method == OKX_GET and params:
            query_params = urlencode(params)
            full_request_path = f"{request_path}?{query_params}"
        elif method == OKX_POST and params:
            body_str = json.dumps(params)

        timestamp = get_current_timestamp_iso()
        prehash_str = okx_pre_hash(timestamp, method, full_request_path, body_str)
        signature = generate_okx_sign(prehash_str, self.api_secret_key)
        headers = get_okx_header(self.api_key, signature, timestamp, self.passphrase, self.flag)

        try:
            if method == OKX_GET:
                response = await self.client.get(full_request_path, headers=headers)
            elif method == OKX_POST:
                response = await self.client.post(request_path, content=body_str, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()  # Raise exception for bad status codes (4xx or 5xx)
            return response.json()

        except httpx.HTTPStatusError as e:
            print_error(
                f"OKX API HTTP Error ({e.response.status_code}) for {method} {request_path}: {e.response.text}"
            )
        except httpx.RequestError as e:
            # Check if it's likely a network issue
            is_network = isinstance(
                e, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)
            )
            print_error(
                f"OKX API Request Error for {method} {request_path}: {e}",
                is_network_issue=is_network,
            )
        except json.JSONDecodeError as e:
            print_error(
                f"OKX API JSON Decode Error for {method} {request_path}: {e} - Response: {response.text if 'response' in locals() else 'N/A'}"
            )
        except Exception as e:
            print_error(f"Unexpected error during OKX API request ({method} {request_path}): {e}")

        return None  # Explicitly return None on any error

    async def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """Fetches the total account balance from OKX asynchronously. Returns None on failure."""
        return await self._request(OKX_GET, OKX_GET_ACCOUNT_BALANCE)

    async def get_asset_balances(self) -> Optional[Dict[str, Any]]:
        """Fetches funding (asset) account balances."""
        return await self._request(OKX_GET, OKX_GET_BALANCES)

    async def get_positions(self, inst_type: str = "SWAP") -> Optional[Dict[str, Any]]:
        """Fetches account positions from OKX."""
        params = {"instType": inst_type}
        return await self._request(OKX_GET, OKX_GET_POSITIONS, params)

    async def close(self):
        """Closes the underlying HTTP client."""
        await self.client.aclose()
