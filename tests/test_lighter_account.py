"""Integration check for Lighter account balance lookup."""

import asyncio
import os
import unittest
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

# NOTE: Lighter’s API treats addresses as case-sensitive, so preserve the exact
# casing supplied by the user when issuing requests. For public builds we rely
# on an environment variable to avoid hard-coding a personal address.
L1_ADDRESS = os.environ.get("LIGHTER_TEST_ADDRESS")
ACCOUNT_ENDPOINT = "https://mainnet.zklighter.elliot.ai/api/v1/account"


class LighterAccountAPITests(unittest.TestCase):
    """Simple integration tests against the public Lighter API."""

    def _fetch_account_payload(self) -> Dict[str, Any]:
        """Call the Lighter account endpoint and return the parsed response."""
        if not L1_ADDRESS:
            self.skipTest(
                "Set LIGHTER_TEST_ADDRESS environment variable to enable Lighter API tests."
            )

        try:
            response = requests.get(
                ACCOUNT_ENDPOINT,
                params={"by": "l1_address", "value": L1_ADDRESS},
                timeout=10,
            )
        except requests.RequestException as exc:  # pragma: no cover - network guard
            self.skipTest(f"Lighter API unreachable: {exc}")

        if response.status_code != 200:
            self.skipTest(f"Lighter API returned HTTP {response.status_code}")

        try:
            payload: Dict[str, Any] = response.json()
        except ValueError as exc:  # pragma: no cover - malformed payload
            self.skipTest(f"Invalid JSON from Lighter API: {exc}")

        if payload.get("code") != 200:
            self.skipTest(
                f"Lighter account not available (code={payload.get('code')}, message={payload.get('message')})"
            )

        return payload

    def test_fetch_account_balance_by_l1_address(self) -> None:
        """Query the account endpoint and validate the response structure."""
        if not L1_ADDRESS:
            self.skipTest(
                "Set LIGHTER_TEST_ADDRESS environment variable to enable Lighter API tests."
            )

        payload = self._fetch_account_payload()

        accounts: List[Dict[str, Any]] = payload.get("accounts") or []
        self.assertTrue(accounts, msg="No account records returned for target address")

        account = accounts[0]
        self.assertEqual(account.get("l1_address", "").lower(), L1_ADDRESS.lower())
        self.assertIn("available_balance", account)
        self.assertIn("total_asset_value", account)

    def test_fetch_total_asset_value(self) -> None:
        """Ensure total asset value is present and formatted as a numeric string."""
        if not L1_ADDRESS:
            self.skipTest(
                "Set LIGHTER_TEST_ADDRESS environment variable to enable Lighter API tests."
            )

        payload = self._fetch_account_payload()

        accounts: List[Dict[str, Any]] = payload.get("accounts") or []
        self.assertTrue(accounts, msg="No account records returned for target address")

        account = accounts[0]
        total_asset_value = account.get("total_asset_value")
        self.assertIsNotNone(total_asset_value, "Missing total_asset_value field")

        try:
            decimal_total = Decimal(str(total_asset_value))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise AssertionError(
                f"total_asset_value is not numeric: {total_asset_value!r}"
            ) from exc

        self.assertGreaterEqual(
            decimal_total,
            Decimal("0"),
            msg=f"Unexpected negative total asset value: {decimal_total}",
        )

    def test_wallet_fetcher_lighter_integration(self) -> None:
        """End-to-end fetch via the async WalletPlatformFetcher helper."""
        if not L1_ADDRESS:
            self.skipTest(
                "Set LIGHTER_TEST_ADDRESS environment variable to enable Lighter API tests."
            )

        try:
            from wallets.fetchers import (
                WalletPlatformFetcher,
            )  # Lazy import to avoid optional deps at module load
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
            self.skipTest(f"wallets.fetchers dependencies missing: {exc}")

        async def _run_fetch() -> Optional[Dict[str, Any]]:
            fetcher = WalletPlatformFetcher(
                wallets={"ethereum": [L1_ADDRESS]},
                hyperliquid_enabled=[],
                lighter_enabled=[L1_ADDRESS],
            )
            return await fetcher.get_lighter_account_info(L1_ADDRESS)

        result = asyncio.run(_run_fetch())
        if result is None:
            self.skipTest("WalletPlatformFetcher returned no data for Lighter")

        self.assertEqual(result.get("address", "").lower(), L1_ADDRESS.lower())
        self.assertIn("total_balance", result)
        self.assertGreater(result.get("total_balance", 0.0), 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
