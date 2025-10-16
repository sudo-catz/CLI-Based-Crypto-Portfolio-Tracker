# Custom Coin Tracking Guide

The tracker can monitor tokens beyond the built-in majors (BTC, ETH, SOL). This guide explains how custom coins are stored, how to manage them from the UI, and how their prices feed into portfolio analytics.

## What Gets Tracked

Every custom coin entry in `data/custom_coins.json` includes:

- `symbol` – uppercase identifier (e.g., `PEPE`)
- `name` – friendly display name (auto-fetched when possible)
- `balance` – quantity you hold (defaults to `0.0`)
- `price_only` – `True` when the coin is tracked for price awareness only
- `coingecko_id` – optional override for CoinGecko lookups
- `exchange_pairs` – optional comma-separated trading pairs for exchange-based pricing
- `last_price` / `price_source` – cached values from the most recent analysis

Example snippet:

```json
{
  "custom_coins": {
    "PEPE": {
      "symbol": "PEPE",
      "name": "Pepe",
      "balance": 0.0,
      "price_only": true,
      "coingecko_id": "pepe",
      "exchange_pairs": ["PEPE/USDT", "PEPE/USD"],
      "last_price": 0.0000012,
      "price_source": "coingecko"
    }
  }
}
```

The file is created automatically when you first add a coin from the UI. Treat it as sensitive data—balances and price history are stored in plain JSON.

## Managing Coins in the UI

From the main menu choose **🪙 Manage Custom Coins**. The submenu provides:

1. **Add Custom Coin**  
   - Enter a symbol (e.g., `PEPE`).  
   - The tracker creates a record with `balance = 0.0` and attempts to fetch the full name via the enhanced price service.  
   - Prices are resolved automatically during analysis (CoinGecko first, then exchange pairs).
2. **View All Coins**  
   - Displays tracked coins, showing whether they are price-only or have balances, along with the last price source.
3. **Remove Custom Coin**  
   - Deletes the selected symbol from `data/custom_coins.json`.
4. **Test All Custom Coin Prices**  
   - Runs the price service without executing a full portfolio analysis.  
   - Handy for confirming new tokens can be priced before an official run.

> Tip: After adding or removing coins, the tracker reloads the JSON automatically—no manual refresh required.

## Updating Balances

The current UI does not prompt for balances when you add a coin. Use one of the following approaches to record holdings:

### Option A – Quick Python Snippet

```python
from models.custom_coins import CustomCoinTracker

tracker = CustomCoinTracker()
tracker.update_balance("PEPE", 1_500_000)
```

Run the snippet inside your virtual environment (`python` from the project root). The tracker writes the new balance to `data/custom_coins.json`.

### Option B – Manual JSON Edit

1. Open `data/custom_coins.json`.
2. Locate the coin entry and update the `balance` field.
3. Save the file and re-run the analysis.

When `balance > 0`, the coin moves from the “price-only watchlist” into held positions during analysis, contributing to total portfolio value.

## How Prices Are Fetched

The enhanced price service (`utils/enhanced_price_service.py`) follows a fallback chain:

1. **CoinGecko** – default source using the symbol or `coingecko_id`.
2. **Exchange Pairs** – if you supply pairs, the service tries Binance, OKX, and Bybit via ccxt.
3. **Auto-Generated Pairs** – common combinations like `SYMBOL/USDT`, `SYMBOL/USD`, `SYMBOL/USDC`.

Prices are cached in memory during a single analysis run; no persistent cache is kept, ensuring fresh data the next time you execute the tracker.

## Portfolio Impact

- Price-only coins appear in market snapshots and exposure analysis but contribute `0` value until a balance is recorded.
- Coins with balances feed into:
  - Total and net portfolio value
  - Asset distribution charts
  - Exposure metrics (stable vs non-stable allocation)
- Combined wallet exports (`combined_wallet_breakdown.json`) include custom coins under the “Custom Coin Contribution” section, making it easy to compare on-chain and manual holdings.

## Troubleshooting

| Issue | Suggested Fix |
|-------|---------------|
| `⚠️ Could not fetch price for SYMBOL` | Verify the CoinGecko ID, add more exchange pairs, or wait for rate limits to reset. |
| Coin still shows `0.00` after setting a balance | Ensure the symbol in `update_balance` or JSON edit matches exactly (uppercase). Run a fresh analysis afterwards. |
| Prices seem stale | Run **Test All Custom Coin Prices** to refresh `last_price`, then re-run the full analysis. |
| Want to reset everything | Delete `data/custom_coins.json`; the tracker recreates an empty file on next run. |

With these workflows you can extend the tracker to cover niche tokens, community projects, or even off-exchange IOUs while preserving the automated pricing pipeline.
