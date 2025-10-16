# API Integrations Reference

This document captures how the portfolio tracker talks to exchanges, blockchains, and DeFi platforms. Use it as a reference when auditing network calls, rotating credentials, or swapping in custom endpoints.

## Centralised Exchange Connectors

All CEX integrations rely on ccxt or signed REST requests and respect per-exchange rate limits via the performance optimiser (`utils/performance_optimizer.py`) and retry decorators in `utils/rate_limiter.py`.

### Binance

- **Base URLs**
  - REST: `https://api.binance.com` (spot & funding)
  - USDM futures: `https://fapi.binance.com`
  - Coin-M futures: `https://dapi.binance.com`
- **Key Endpoints**
  - `/api/v3/account` – master account balances
  - `/fapi/v2/balance`, `/dapi/v1/account` – futures equity snapshots
  - `/sapi/v1/asset/get-funding-asset` – funding wallet balances
  - `/sapi/v1/asset/wallet/balance` – detailed wallet balances (fallback)
  - `/api/v3/ticker/price` – price lookups for USD conversion
- **Authentication** – HMAC-SHA256 signature of query/body using the API secret (`X-MBX-APIKEY` header).
- **Rate Limiting** – throttled to ~1200 req/min, with automatic retries on HTTP 429 and error logging when the API throttles.
- **Output** – spot, funding, and futures balances plus futures position risk for exposure analysis.

### OKX

- **Base URL** – `https://www.okx.com`
- **Endpoints**
  - `/api/v5/asset/balances` – funding balances
  - `/api/v5/account/balance` – trading balances & positions
  - `/api/v5/account/positions` – futures/derivatives positions
  - `/api/v5/public/time` – server timestamp sync
- **Authentication** – HMAC-SHA256 with base64 encoding of the prehash (`timestamp + method + path + body`). Requires API key, secret, and passphrase (`OK-ACCESS-*` headers).
- **Rate Limiting** – default limit ~20 req/s. The custom retry decorator backs off on HTTP 429 and 5xx responses.
- **Output** – USD-equivalent balances, per-account breakdowns, and derivatives exposure.

### Bybit

- **Base URL** – `https://api.bybit.com`
- **Endpoints**
  - `/v5/asset/transfer/query-account-coins-balance` – unified account balances (per account type)
  - Additional requests via ccxt for market data used in USD conversion.
- **Authentication** – Bybit V5 signature (`timestamp + apiKey + recv_window + query + body`) hashed with HMAC-SHA256 (`X-BAPI-*` headers).
- **Rate Limiting** – handled by `bybit_retry` decorator; automatically backs off on transient errors.
- **Output** – unified trading & funding balances, converted to USD via live market data.

### Backpack

- **Base URL** – `https://api.backpack.exchange`
- **Endpoints**
  - `/api/v1/capital/collateral` – collateral balances
- **Authentication** – ED25519 signatures using PyNaCl:
  - Headers: `X-API-Key`, `X-Timestamp`, `X-Window`, `X-Signature`
  - Body signed with the base64-encoded private key.
- **Rate Limiting** – custom retry (`backpack_retry`) enforces polite spacing between calls.
- **Output** – collateral balances in USD across supported assets.

## On-Chain & DeFi Sources

### Ethereum Wallets (via DeBank)

- **Primary Method** – Playwright-driven browser session hitting `https://debank.com/profile/{address}` to collect ERC‑20 balances and DeFi positions.
- **Behaviour**
  - Full analysis launches Playwright headless Chromium, stores cookies in the session, and captures screenshots on failure (`data/screenshots/`).
  - The tracker suppresses duplicate Hyperliquid data when both DeBank and direct Hyperliquid APIs are used.
- **Fallbacks** – Basic ETH balances may be fetched via direct RPC calls when DeBank blocks scraping, but ERC‑20 data requires DeBank or the optional ETH exposure enhancement module.

### Bitcoin Wallets

- **Primary Endpoint** – `https://blockstream.info/api/address/{address}`
- **Fallbacks** – BlockCypher (`https://api.blockcypher.com/v1/btc/main/addrs/...`) and Blockchain.info (`https://blockchain.info/address/{address}?format=json`)
- **Output** – UTXO sums converted to BTC then USD using live prices.

### Solana Wallets

- **RPC Rotation** – `wallets/fetchers.py` cycles through:
  - `https://solana-rpc.publicnode.com`
  - `https://api.mainnet-beta.solana.com`
  - `https://rpc.ankr.com/solana`
  - `https://solana-mainnet.g.alchemy.com/v2/demo`
  - `https://rpc.helius.xyz/?api-key=`
- **Methods**
  - `getBalance` – native SOL balance
  - `getTokenAccountsByOwner` – SPL token accounts (JSON parsed)
- **Pricing**
  - SOL price from CoinGecko
  - SPL token vs SOL price from Jupiter (`https://price.jup.ag/v4/price`), converted to USD using the SOL price.
- **Resilience** – automatic rotation on HTTP 429/403, timeouts, or JSON errors with cooldown tracking.

### Hyperliquid Perp DEX

- **Endpoint** – `POST https://api.hyperliquid.xyz/info`
- **Payload** – `{"type": "clearinghouseState", "user": "<wallet>"}` (address in lowercase hex)
- **Output** – margin summary, account value, open positions with size, entry price, PnL, leverage, and liquidation price.
- **Caching** – Responses cached briefly via `cached_wallet_data` to avoid flooding the API during a single run.

### Lighter Perp DEX

- **Endpoint** – `GET https://mainnet.zklighter.elliot.ai/api/v1/account`
- **Query Params** – `by=l1_address`, `value=<Ethereum address>` (checksum preferred)
- **Output** – collateral, available balance, total asset value, and open positions (with sign-aware sizing).
- **Testing** – Integration tests require `LIGHTER_TEST_ADDRESS` to exercise the live API.

### Custom Coin Pricing

- **Primary Source** – CoinGecko Simple Price API (`https://api.coingecko.com/api/v3/simple/price`)
- **Fallback** – Exchange tickers via ccxt (Binance/OKX/Bybit) for pairs like `SYMBOL/USDT`, `SYMBOL/USD`.
- **Workflow** – `utils/enhanced_price_service.py` orchestrates lookups and exposes async helpers for batch fetching, used by `PortfolioAnalyzer`.

## Performance & Error Handling

- **Connection Pooling** – `utils/performance_optimizer.ConnectionPoolManager` reuses HTTP sessions and aiohttp connectors to minimise TLS handshakes.
- **Batching** – `BatchRequestProcessor` queues calls that can be run together, reducing API chatter.
- **Retry Strategy** – Decorators in `utils/rate_limiter.py` add exponential backoff for Binance, Bybit, OKX, Backpack, Solana, CoinGecko, and others. Repeated failures surface in the terminal with guidance on next steps.
- **Caching** – Wallet fetchers use short-lived caches (`CACHE_TTL_FAST`) to avoid duplicate Hyperliquid/Lighter calls within a single analysis while preserving fresh data on subsequent runs.

## Security & Compliance Notes

- The API key manager never stores secrets in plain text; all credentials are read from the encrypted vault before signing requests.
- Every REST call uses HTTPS; headers and payloads avoid logging sensitive fields.
- Rate limits and polite backoff are enforced to minimise the risk of account throttling or bans.

Refer back to the source modules (`api_clients/`, `wallets/fetchers.py`, and `utils/enhanced_price_service.py`) for concrete implementations or when extending the integration surface.
