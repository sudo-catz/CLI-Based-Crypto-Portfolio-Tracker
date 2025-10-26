# -*- coding: utf-8 -*-
"""
Configuration constants for Multi-Chain Portfolio Tracker
Enhanced with failover endpoints for maximum reliability
"""

# OKX API Constants
OKX_GET = "GET"
OKX_POST = "POST"
OKX_API_URL = "https://www.okx.com"
OKX_SERVER_TIMESTAMP_URL = "/api/v5/public/time"
OKX_GET_BALANCES = "/api/v5/asset/balances"
OKX_GET_ACCOUNT_BALANCE = "/api/v5/account/balance"
OKX_GET_POSITIONS = "/api/v5/account/positions"

# Solana API Constants with Enhanced Failover
SOLANA_RPC_ENDPOINTS = [
    "https://solana-rpc.publicnode.com",  # PublicNode (tested working)
    "https://api.mainnet-beta.solana.com",  # Official Solana
    "https://rpc.ankr.com/solana",  # Ankr
    "https://solana.drpc.org",  # DRPC
    "https://endpoints.omniatech.io/v1/sol/mainnet/public",  # Omniatech
]
SOLANA_RPC_URL = SOLANA_RPC_ENDPOINTS[0]  # Default (backwards compatibility)
SOLANA_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SOLANA_NATIVE_MINT = "So11111111111111111111111111111111111111112"
SOLANA_TOKENS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "sSOL": "sSo14endRuUbvQaJS3dq36Q829a3A6BEfoeeRGJywEh",  # Example wrapped SOL
    # Add other relevant SPL tokens here
}
JUPITER_PRICE_API = "https://price.jup.ag/v4/price"

# Bitcoin API Constants with Failover
BITCOIN_API_ENDPOINTS = [
    "https://blockstream.info/api",  # Blockstream (reliable)
    "https://api.blockcypher.com/v1/btc/main",  # BlockCypher
    "https://api.blockchain.info",  # Blockchain.info (often has DNS issues)
    "https://btc.getblock.io/rest",  # GetBlock (may require auth)
]
BITCOIN_API_URL = BITCOIN_API_ENDPOINTS[0]  # Default

# Hyperliquid API Constants
HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"

# Lighter Perp DEX API Constants
LIGHTER_API_BASE_URL = "https://mainnet.zklighter.elliot.ai/api/v1"
LIGHTER_ACCOUNT_ENDPOINT = f"{LIGHTER_API_BASE_URL}/account"

# Polymarket API / RPC Constants
POLYMARKET_DATA_API_URL = "https://data-api.polymarket.com"
POLYMARKET_POSITIONS_ENDPOINT = f"{POLYMARKET_DATA_API_URL}/positions"
POLYGON_RPC_URL = "https://polygon-rpc.com"
POLYMARKET_USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Binance API Constants
BINANCE_BASE_URL = "https://api.binance.com"
BINANCE_WALLET_BALANCE_ENDPOINT = "/sapi/v1/asset/wallet/balance"

# Backpack API Constants
BACKPACK_API_URL = "https://api.backpack.exchange/api/v1/capital/collateral"
BACKPACK_WINDOW = 5000  # ms

# File and Directory Constants
DATA_DIR = "data"
ANALYSIS_DIR = "data/analysis"
SCREENSHOTS_DIR = "data/screenshots"
LOGS_DIR = "logs"

# File Patterns
WALLET_STORAGE_FILE = "data/wallets.json"
ANALYSIS_FILE_PATTERN = "data/analysis/portfolio_analysis_*.json"
DEBANK_SCREENSHOT_PATTERN = "data/screenshots/debank_error_{}_*_attempt*.png"
DEBANK_URL_TEMPLATE = "https://debank.com/profile/{}"

# Other Constants
DEBANK_LOAD_WAIT_SECONDS = 15  # Legacy constant - now using intelligent waiting strategies
DEBANK_SCREENSHOT_ON_ERROR = True  # Set to True to save screenshots on DeBank errors
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_COIN_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
SUPPORTED_CHAINS = ["ethereum", "bitcoin", "solana"]
SATOSHIS_PER_BTC = 100_000_000
LAMPOSTS_PER_SOL = 1_000_000_000
TABLE_FORMAT = "fancy_grid"  # Consistent table style

# Blockchain endpoint failover mapping (for network utilities)
BLOCKCHAIN_FAILOVERS = {
    "solana": SOLANA_RPC_ENDPOINTS,
    "bitcoin": BITCOIN_API_ENDPOINTS,
}

# For price fetching, especially for custom coins or name resolution
SUPPORTED_EXCHANGES_FOR_PRICES = [
    "binance",
    "okx",
    "bybit",
]  # Order of preference for price fetching

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_PRICE_URL = f"{COINGECKO_BASE_URL}/simple/price"
COINGECKO_COIN_LIST_URL = f"{COINGECKO_BASE_URL}/coins/list?include_platform=false"

# CoinMarketCap API Key - Replace with your actual key
COINMARKETCAP_API_KEY = "773b36aa-6e9b-4a2c-878a-28f423c39a3a"

# General application settings
APP_VERSION = "1.2.0"

# List of major cryptocurrencies for display in market snapshots, etc.
SUPPORTED_CRYPTO_CURRENCIES_FOR_DISPLAY = ["BTC", "ETH", "SOL"]

# Debug Mode Configuration
DEBUG_MODE = False  # Will be set via command line argument
DEBUG_MASTER_PASSWORD = "debug123"  # Default password for debug mode
DEBUG_SKIP_AUTHENTICATION = True  # Skip all authentication in debug mode

# Debug mode warning message
DEBUG_WARNING_MESSAGE = """
⚠️  DEBUG MODE ACTIVE ⚠️
• Authentication is bypassed
• Using default master password
• This mode is for development only
• Do not use in production!
"""
