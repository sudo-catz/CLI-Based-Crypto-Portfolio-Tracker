# CLI-Based Crypto Portfolio Tracker

A terminal-first cryptocurrency portfolio tracker that consolidates balances across centralized exchanges (CEXs) and on-chain wallets, plus selected DeFi platforms.  

## 📦 Repository
- GitHub: https://github.com/sudo-catz/CLI-Based-Crypto-Portfolio-Tracker

## 🚀 Features

### Supported Exchanges
- **Binance** (Spot, Funding, USDM accounts)
- **OKX** (Trading & Funding accounts)
- **Bybit** (Unified + Funding accounts)
- **Backpack** (Collateral balances)

### Supported Blockchains
- **Ethereum** (ETH + ERC-20 tokens via DeBank)
- **Bitcoin** (native balances via public APIs)
- **Solana** (SOL + SPL tokens via RPC + Jupiter)

### DeFi Platforms
- **Hyperliquid** (Perpetual trading positions)
- **Lighter** (Perp DEX account balances + open positions)

### Key Capabilities
- 📊 Exposure analysis with asset concentration breakdown
- 📊 Real-time portfolio valuation in USD
- 🎯 Asset distribution analysis
- 💰 Balance offset management (for loans/debts)
- 📈 Historical analysis storage with an interactive viewer and cleanup tools
- 🎨 Beautiful terminal UI with colors
- 🔐 Encrypted API key storage
- 🌐 Multi-chain wallet management
- 📱 Interactive menu system
- 🧾 Combined wallet exports with automatic portfolio summary statistics
- 🪙 Custom coin tracking with multi-source price fetching
- ⚡ Performance-optimized async data fetching with pooling, batching, and backoff
- 🧮 Futures and perp position coverage with refreshable exposure metrics
- ⚙️ Quick analysis mode for fast snapshots without deep wallet scraping

## 📋 Requirements

### System Requirements
- **Python 3.8+**
- **Linux/macOS/Windows** (Linux recommended)
- **Internet connection** for API access

### Dependencies
See `requirements.txt` for complete list. Key dependencies:
- `ccxt` - Exchange API integration
- `playwright` - Web scraping for DeBank
- `pynacl` - Cryptographic signing for Backpack
- `colorama` - Terminal colors
- `tabulate` - Beautiful table formatting
- `httpx` - Async HTTP client

## 🛠️ Installation

### 1. Clone and Setup Environment
```bash
git clone <repository-url>
cd Port2
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install  # Install browser engines
```
Prefer `make install-dev` if you already have the Makefile prerequisites (`python`, `pip`, `playwright`) available—it wraps the same steps and keeps the toolkit up to date.

### 3. Launch & Configure API Keys
```bash
python port2.py
```

On first launch, open **Manage API Keys**, set a master password, and add your exchange credentials through the built-in encrypted storage. No manual file edits required.

### 4. Wallet Configuration
On first run, use the "Manage Wallets" menu to add your wallet addresses for each supported blockchain.

> **Debug Mode Shortcut:**  
> During development you can skip authentication prompts and load demo data with:
> ```bash
> python port2.py --debug
> ```
> Never run this mode in production—it bypasses security checks.

## 🚀 Usage

### Launch Modes
- `python port2.py` – start the interactive menu (recommended)
- `python port2.py --debug` – development shortcut that bypasses authentication and seeds demo data (never use with real keys)

Once the app loads, the main menu offers:
1. **🚀 Run FULL Portfolio Analysis** – full wallet scraping (DeBank, RPC, Hyperliquid, Lighter) with exposure refresh
2. **⚡ Run QUICK Portfolio Analysis** – skip heavier wallet scraping for a rapid snapshot
3. **📊 View Past Analysis** – list, open, refresh, combine, or delete saved analyses (`d<number>` deletes, `cleanup` trims to newest 10)
4. **🏦 Manage Wallets** – add/remove wallets and toggle Hyperliquid/Lighter per Ethereum address
5. **🔑 Manage API Keys** – encrypted credential storage guarded by your master password
6. **🪙 Manage Custom Coins** – register additional tickers, inspect tracked coins, prune entries, and test live pricing
7. **⚖️ Adjust Balance Offset** – set a portfolio offset for loans, liabilities, or off-ledger funds
8. **👋 Exit** – close the application

Inside any portfolio analysis view, type:
- `refresh` – recompute exposure insights and portfolio summary statistics
- `combine` – generate a combined wallet breakdown plus `portfolio_summary_stats.json`

### Data Storage & Outputs
- `data/api_config.enc` / `data/.api_salt` – encrypted API credential vault and salt file (created after you set a master password)
- `data/wallets.json` – wallets, Hyperliquid and Lighter toggles, and balance offset (auto-managed)
- `data/custom_coins.json` – custom coin registry with metadata and balances
- `exported_data/analysis_<timestamp>/` – every analysis run gets a dedicated folder containing:
  - `portfolio_analysis.json` – canonical snapshot driving the UI
  - `wallet_breakdown_<chain>_<address>.json` – per-wallet exports captured during the run
  - `combined_wallet_breakdown.json` – generated on demand via `combine`
  - `portfolio_summary_stats.json` – consolidated metrics powering exposure refreshes
  - Supporting screenshots, logs, or error artifacts when scraping fails
- `data/analysis/` – legacy flat storage kept for backward compatibility (new runs prefer `exported_data/*`)
- `data/screenshots/` – optional DeBank failure screenshots (controlled by `DEBANK_SCREENSHOT_ON_ERROR`)
- `logs/` – reserved for verbose output when extended logging is enabled

## 📁 Project Structure

```
Port2/
├── port2.py              # Main application entry point
├── requirements.txt      # Python dependencies
├── combined_wallet_integration.py  # Combined wallet + summary helpers
├── combine_wallet_data.py          # Utility used by the combined export flow
├── api_clients/          # Exchange & blockchain client helpers
├── config/               # Application constants
├── core/                 # Portfolio aggregation & exposure logic
├── data/                 # Local app data (empty templates checked in)
├── docs/                 # Additional documentation
├── eth_exposure_enhancement/  # Optional ETH deep-dive module (plug-in style)
├── exported_data/        # Time-stamped analysis exports
├── models/               # Data models (wallet tracker, etc.)
├── tests/                # Test suite (requires optional env vars)
├── ui/                   # Terminal UI components
├── utils/                # Shared utilities (pricing, performance, summaries)
└── wallets/              # On-chain wallet fetchers
```

> **Public-Repo Note:** Before first run you may safely delete any `.example` files and allow the application to regenerate fresh encrypted stores. All directories that typically contain personal data are present but empty.

## 🔧 Configuration & Verification

### Analysis Modes
- **Full** – recommended for daily monitoring; runs enhanced wallet scraping (DeBank + RPC), Hyperliquid/Lighter API calls, and saves detailed breakdown files.
- **Quick** – skips the heavier scraping and exposure refresh to provide a near-instant view based on cached wallet metadata and exchange balances.

### Rate Limits & Resilience
- Built-in throttles match exchange guidance (Binance ~1200 req/min, OKX ~20 req/s, Bybit ~120 req/min, Backpack customized).
- The performance optimizer batches requests, shares HTTP connection pools, and automatically applies exponential backoff on `429`/`5xx` errors.
- Wallet fetchers include retries and polite delays to avoid triggering anti-bot checks (especially with DeBank + Playwright).

### Failover Endpoints
- Solana RPC calls rotate through a prioritized list (`solana-rpc.publicnode.com`, `api.mainnet-beta.solana.com`, `rpc.ankr.com`, etc.).
- Bitcoin balances fall back to BlockCypher, Blockchain.info, and other public APIs when the primary endpoint fails.
- Exposure analysis can optionally import supplemental ETH breakdowns from `eth_exposure_enhancement/` if you drop the module into the repo.

### Environment Flags & Settings
- `DEBUG_MODE` (set via `--debug`) bypasses auth flows and seeds demo values—only enable on a development machine.
- `DEBANK_SCREENSHOT_ON_ERROR` controls whether Playwright captures HTML screenshots after failed scrapes.
- `COINMARKETCAP_API_KEY` is bundled for experiments; swap in your own if you intend to hit CoinMarketCap directly.
- All paths can be relocated by editing `config/constants.py` (wallet store, analysis folder pattern, failover endpoints).

### Verification Workflow
- `make quality` runs Black, flake8, and mypy; `make test` executes pytest (Hyperliquid/Lighter tests auto-skip unless env vars are provided).
- `make check-structure` and `make organize` help keep ad-hoc artifacts inside the expected directories.
- `make stats` provides quick LOC + directory breakdowns when auditing changes.

## 🔐 Security

### API Key Vault
- The **Manage API Keys** menu prompts for a master password on first use (minimum 8 characters, confirmed twice).
- Credentials are encrypted with PBKDF2-HMAC (100k iterations) + Fernet and written to `data/api_config.enc`; the salt lives in `data/.api_salt`.
- Three failed login attempts lock the session until restart; debug mode swaps in a well-known password for local development only.
- To reset access, delete both vault files (`rm data/api_config.enc data/.api_salt`). You will lose all stored credentials and must re-enter them.

#### Resetting the Master Password
Deleting `data/api_config.enc` together with `data/.api_salt` wipes the vault and its encryption salt. The next time you launch `python port2.py`, the app treats it as a first-run experience: it asks for a new master password, creates a fresh vault, and leaves all exchange slots blank. Re-enter your API keys through **🔑 Manage API Keys** to repopulate the secure store.

### Operational Hygiene
- Treat generated exports (`exported_data/analysis_*`) as sensitive—they contain balances, wallet addresses, and sometimes screenshots.
- `data/custom_coins.json` stores coin metadata and balances in plain JSON. Omit the file before sharing the repo publicly.
- No API secrets are printed to the console or logs; debug traces redact credential fields.
- HTTPS is used for all API traffic; HTTP clients apply custom headers to avoid being flagged as bots during scraping.

### Quality Checks & Tests

Use the Makefile helpers for a consistent workflow:
- `make install-dev` – upgrade `pip`, install dependencies, and download Playwright browsers
- `make format | make lint | make type-check` – run Black, flake8, and mypy individually
- `make quality` – run the full lint + type-check pipeline
- `make test` – execute pytest (`LIGHTER_TEST_ADDRESS=<eth_address>` enables the Lighter integration tests)
- `make all` – clean caches, run quality gates, and execute tests in one go

Screenshots are only written when DeBank scraping fails (`data/screenshots/`). Delete them before pushing to a public fork if they contain sensitive balances.

## 🐛 Troubleshooting

### Common Issues

#### "Failed to initialize Binance connection"
- Re-enter credentials via **Manage API Keys** (master password may have changed)
- Confirm the key has read-only permissions for spot, funding, and futures where applicable
- Binance testnet keys are not supported—disable the `testnet` toggle before saving

#### "DeBank scraping failed"
- DeBank regularly rate limits and blocks bots; retry later or switch to **Quick** mode for a partial snapshot
- Check `data/screenshots/` for captured HTML screenshots (enable via `DEBANK_SCREENSHOT_ON_ERROR`)
- Verify Playwright browsers are installed (`playwright install`) and system dependencies (fonts, libatk) are present

#### "Quick analysis is missing wallet data"
- Quick mode intentionally skips enhanced scraping; rerun **Full** analysis or open the latest saved folder for reference
- Ensure `exported_data/analysis_<timestamp>/wallet_breakdown_*.json` exists—if not, the previous run did not complete wallet fetching

#### "Module not found" errors
- Activate the virtual environment before launching (`source .venv/bin/activate`)
- Reinstall dependencies (`pip install -r requirements.txt`) and ensure Python ≥ 3.8
- If optional modules (ETH exposure enhancement) are removed, delete stale `.pyc` files or run `make clean`

#### Repeated HTTP 429/5xx Responses
- The performance optimizer retries automatically, but excessive rate limits may still bubble up; pause between runs or enable **Quick** mode
- Check your IP reputation—consider an exchange-provided IP whitelist or VPN if limits persist

### Debug Mode Notes
- `python port2.py --debug` bypasses master-password prompts and seeds demo data; never load production API keys in this mode.
- The debug banner warns when the bypass is active; reset the vault afterwards to ensure no demo secrets linger.
- For deeper tracebacks, temporarily catch fewer exceptions or run under `python -m pdb port2.py --debug`.

## 📊 Understanding the Output

### Analysis Workspace
- Every run lands in an analysis sub-menu with context-aware options: wallets, perp DEX positions, CEX breakdown, asset distributions, and exposure analysis (full mode only).
- `refresh` reprocesses exposure analytics and regenerates `portfolio_summary_stats.json`; `combine` builds a unified wallet export for cross-wallet reporting.
- A `Quick Mode` banner appears in the overview whenever the run skipped enhanced wallet scraping.

### Portfolio Overview Panel
- **Total Portfolio Value** – gross USD value before offsets
- **Balance Offset** – manual adjustment applied via `⚖️ Adjust Balance Offset`
- **Net Portfolio Value** – total minus offset
- **Platform Breakdown** – weighted allocation by exchange, wallet, and DeFi source
- **Asset Distribution** – top cryptocurrencies with USD values and percentages
- **Custom Coin Contribution** – highlights balances sourced from `data/custom_coins.json` when present

### Exposure Analysis Panel
- Calculates stable vs non-stable percentages, concentration alerts, and largest directional positions.
- Consolidates symbols across sources (e.g., `WETH` + `ETH`) and nets borrowed vs supplied balances.
- Pulls extended stats from `portfolio_summary_stats.json` when available to avoid reprocessing heavy wallet data.

### Other Panels
- **Wallet Balances** – deep dive per wallet, including protocol and token breakdowns with Hyperliquid/Lighter flags.
- **Perp DEX Positions** – grouped by exchange with entry price, PnL, margin usage, and leverage context.
- **CEX Account Breakdown** – aggregated spot, funding, and futures balances, plus top holdings per account type.
- **Asset Distribution Chart** – tabular view suitable for screenshots or CSV conversion.

### Color Coding
- 🟢 **Green**: successful operations, positive balances
- 🔴 **Red**: errors or unresponsive sources
- 🟡 **Yellow**: warnings, partial data, retry notices
- 🔵 **Blue**: informational headers and prompts
- ⚪ **White**: neutral text, totals, formatting dividers

## 🛠️ Developer Shortcuts

- `make help` prints a categorized summary of every automation target.
- `make check-structure` validates the expected directory layout and reports missing placeholders.
- `make organize` sweeps loose analysis JSON files or screenshots back into their folders.
- `make stats` surfaces line-count and file-distribution summaries for quick PR reviews.
- `python port2.py --debug` opens the UI with demo data—perfect for iterating on styling or UX, but never run with real credentials.
- `pytest tests/test_*.py -k lighter` combined with `LIGHTER_TEST_ADDRESS` lets you explicitly run the on-chain DEX integration tests.

## 📄 License

This project is released under the **MIT License**.  
When publishing your own fork, feel free to replace the copyright line with
your individual or organization name.

## ⚠️ Disclaimer

This software is for personal portfolio tracking only. The authors are not responsible for:
- API rate limit violations
- Exchange account restrictions  
- Financial losses due to data inaccuracies
- Third-party service availability

Always verify critical information independently and comply with exchange terms of service. 
