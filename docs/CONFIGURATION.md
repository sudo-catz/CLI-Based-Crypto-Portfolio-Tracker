# Configuration Guide

Configuration for the portfolio tracker is intentionally lightweight—the UI handles most setup at runtime. This guide explains which files control behaviour, how to tweak endpoints and rate limits, and where sensitive data lives so you can customise the app safely.

## Overview

- Application defaults live in `config/constants.py`.
- Credentials, wallets, and analysis outputs are created automatically in the `data/` and `exported_data/` directories.
- CLI flags (`python port2.py --debug`) adjust runtime behaviour without editing source files.
- Only one environment variable is required, and it is used exclusively for optional Lighter integration tests.

## Core Files & Directories

- `config/constants.py` – centralises rate limits, API endpoints, debug toggles, and file paths.
- `data/` – stores encrypted API keys (`api_config.enc`), wallet definitions (`wallets.json`), custom coins (`custom_coins.json`), and Playwright artefacts when debugging.
- `exported_data/analysis_<timestamp>/` – time-stamped analysis folders containing `portfolio_analysis.json`, per-wallet breakdowns, combined exports, and optional screenshots/logs.
- `eth_exposure_enhancement/` – optional plugin folder. Drop in the enhancement module to enable richer ETH analytics; remove it to revert to the default behaviour.

## Runtime Flags & Menu Options

- `python port2.py` – launches the interactive UI.
- `python port2.py --debug` – development shortcut that bypasses the master-password prompt, seeds demo data, and marks the session as “Debug Mode”. Never combine this with production credentials.
- Inside the UI, choose **Run FULL Portfolio Analysis** for comprehensive wallet scraping or **Run QUICK Portfolio Analysis** to skip expensive DeBank/RPC lookups.
- While viewing an analysis, type `refresh` to recompute exposure metrics or `combine` to generate a combined wallet export plus `portfolio_summary_stats.json`.

## Key Constants

The following settings in `config/constants.py` are safe to tweak:

- **API Base URLs & Endpoints** – Binance, OKX, Bybit, Backpack, Solana, and Bitcoin URLs. Update these if you prefer regional endpoints or private RPCs.
- **Failover Endpoint Lists** – `SOLANA_RPC_ENDPOINTS`, `BITCOIN_API_ENDPOINTS`, and the `BLOCKCHAIN_FAILOVERS` map. Reorder or extend these lists to prioritise your preferred providers.
- **Rate Limits & Timeouts** – exchange-specific limits, default HTTP timeout (30s), and retry logic leveraged by the performance optimiser.
- **File Paths** – `DATA_DIR`, `ANALYSIS_DIR`, `SCREENSHOTS_DIR`, and related filenames (`WALLET_STORAGE_FILE`, `ANALYSIS_FILE_PATTERN`). Adjust if you want to relocate storage.
- **Debug Toggles** – `DEBUG_MODE`, `DEBUG_MASTER_PASSWORD`, and `DEBUG_SKIP_AUTHENTICATION`. These are overridden at runtime by the `--debug` flag; only change them if you are customising debug behaviour.
- **Display Configuration** – constants such as `TABLE_FORMAT` and `SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY` customise UI aesthetics and snapshot content.

After editing constants, restart the application so the new settings take effect.

## Credentials & Data Security

- API keys are stored in `data/api_config.enc`, encrypted with PBKDF2-HMAC + Fernet. The salt (`data/.api_salt`) is generated automatically the first time you configure the vault.
- Wallets, Hyperliquid/Lighter toggles, and balance offsets live in `data/wallets.json`. Manage them through **Manage Wallets** in the UI; manual edits are rarely necessary.
- Custom coin definitions (`data/custom_coins.json`) are maintained via the **Manage Custom Coins** menu. The file includes balances, CoinGecko IDs, and exchange pairs when available.
- Each full or quick analysis saves outputs to `exported_data/analysis_<timestamp>/`. Treat these folders as sensitive—they contain balances, wallet addresses, and occasionally Playwright screenshots.
- To reset the master password, delete `data/api_config.enc` and `data/.api_salt`. The application will prompt you to create a new vault and re-enter credentials.

## Environment Variables

Only the Lighter integration tests require an environment variable:

```bash
export LIGHTER_TEST_ADDRESS=0xYourEthereumAddress
pytest tests/test_lighter_account.py
```

If `LIGHTER_TEST_ADDRESS` is unset, the Lighter tests are skipped automatically. The main application does not rely on `.env` files or other environment-based configuration.

## Logging & Troubleshooting

- The performance optimiser reports rate-limit handling and retries directly in the terminal output during analysis runs.
- Set `DEBANK_SCREENSHOT_ON_ERROR = True` in `config/constants.py` (enabled by default) to capture HTML screenshots under `data/screenshots/` whenever DeBank scraping fails.
- Create a `logs/` directory if you want to persist extended logs or custom diagnostics—helper utilities already reference `LOGS_DIR`.
- Use `python port2.py --debug` when experimenting with UI changes or testing without real credentials; the banner will warn you while debug mode is active.

## Hardening Tips

- Restrict filesystem permissions on `data/` (e.g., `chmod 700 data` on Unix) to limit who can read API keys and wallet data.
- Keep Playwright browsers patched (`playwright install`) to avoid scraping regressions.
- If you fork the project publicly, remove or redact `data/api_config.enc`, `data/.api_salt`, `wallets.json`, and any analysis folders before pushing.

With these touch points, you can customise the tracker while keeping the deployment secure and maintainable.
