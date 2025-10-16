# Installation Guide

Follow this guide to stand up the portfolio tracker from a fresh clone. It mirrors the workflow described in the README and adds extra tips for verifying the setup.

## 1. Prerequisites

- **OS**: Linux or macOS recommended (Windows supported via PowerShell/WSL).
- **Python**: 3.8 or later (`python --version` to confirm).
- **Disk space**: ~500 MB for dependencies and Playwright browsers.
- **Network**: Outbound HTTPS access to exchanges, DeBank, and public RPC endpoints.
- **Optional**: `make` (for the bundled automation targets).

If Python is missing:
- Ubuntu/Debian: `sudo apt update && sudo apt install python3 python3-pip python3-venv`
- macOS: `brew install python`
- Windows: download from [python.org](https://www.python.org/) and add to PATH.

## 2. Clone & Virtual Environment

```bash
git clone <repository-url> Port2
cd Port2

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

## 3. Install Dependencies

### Recommended (Makefile)
```bash
make install-dev
```
This upgrades `pip`, installs `requirements.txt`, and downloads Playwright browsers.

### Manual Equivalent
```bash
pip install --upgrade pip
pip install -r requirements.txt
playwright install
```

> If you only need Chromium for DeBank scraping: `playwright install chromium`

## 4. First Run & Credential Setup

```bash
python port2.py
```

1. Choose **🔑 Manage API Keys**.
2. Set a master password (minimum 8 characters; stored via PBKDF2-HMAC + Fernet).
3. Add exchange credentials (read-only permissions strongly recommended).
4. Return to the main menu and select **🏦 Manage Wallets** to add Ethereum, Bitcoin, and Solana addresses. Toggle Hyperliquid/Lighter tracking per Ethereum wallet as needed.

Data files created during this step:
- `data/api_config.enc` and `data/.api_salt` – encrypted API vault & salt.
- `data/wallets.json` – wallet addresses, Hyperliquid/Lighter toggles, and balance offset.
- `data/custom_coins.json` – initialised on demand when you add custom tokens.

## 5. Running Analyses

- **Full analysis**: `python port2.py` → option **1** (Fetches exchange balances, on-chain wallets, DeBank data, Hyperliquid, Lighter, and recomputes exposure metrics.)
- **Quick analysis**: option **2** (Skips heavier wallet scraping for a rapid snapshot.)
- During the analysis viewer:
  - `refresh` recomputes exposure metrics and updates `portfolio_summary_stats.json`.
  - `combine` generates a merged wallet export (`combined_wallet_breakdown.json`).

Each run stores outputs in `exported_data/analysis_<timestamp>/`.

## 6. Optional: Enable Tests

```bash
export LIGHTER_TEST_ADDRESS=0xYourEthereumAddress  # enables Lighter integration tests
pytest
```

Without the environment variable the Lighter tests skip automatically. `make test` and `make quality` wrap pytest, mypy, flake8, and formatting checks.

## 7. Troubleshooting Quick Checks

| Symptom | Quick Fix |
|---------|-----------|
| `ModuleNotFoundError` | Ensure the virtual environment is activated, then rerun `pip install -r requirements.txt`. |
| Playwright errors | Reinstall browsers: `playwright install`. On Linux, install system deps (`libnss3`, `libatk-bridge2.0-0`, `libxcomposite1`). |
| Binance auth fails | Re-enter keys via **Manage API Keys**; confirm read-only permissions and disable testnet toggles. |
| DeBank scraping fails repeatedly | Retry later, switch to **Quick** mode, or review `data/screenshots/` if screenshot capture is enabled. |

## 8. Security Checklist

- Restrict `data/` to your user (`chmod 700 data` on Unix).
- Delete `data/api_config.enc`, `data/.api_salt`, and analysis folders before publishing a public fork.
- Use read-only exchange keys and configure IP whitelists when available.
- Never run `python port2.py --debug` with production credentials; debug mode bypasses the master-password prompt for development convenience only.

## 9. Next Steps

- Add custom coins through **🪙 Manage Custom Coins** and set balances via a quick Python snippet if needed (see `docs/CUSTOM_COINS_GUIDE.md`).
- Explore `make help` for automation targets (`make organize`, `make stats`, etc.).
- Read `docs/API_DOCUMENTATION.md` and `docs/CONFIGURATION.md` for deeper insight into API usage and configurable constants.

With these steps complete, you are ready to run full or quick analyses and start collecting historical snapshots of your portfolio.
