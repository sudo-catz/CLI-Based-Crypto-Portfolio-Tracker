#!/usr/bin/env python3
"""
Enhanced DeBankc Scraper - ETH Exposure Enhancement Sub-Project

This scraper extracts detailed token breakdowns from DeBankc instead of just total balance.
Uses CSS selectors discovered in Phase 1 to get individual token amounts and categorize them properly.

Usage:
    python enhanced_debank_scraper.py <ethereum_address>
    python enhanced_debank_scraper.py --test  # Uses demo addresses
"""

import os
import sys
import asyncio
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("⚠️ BeautifulSoup4 not available. Install with: pip install beautifulsoup4")


@dataclass
class TokenBalance:
    """Represents a single token balance."""

    symbol: str
    amount: float
    usd_value: float
    category: str  # 'stable', 'eth_exposure', 'eth_staking', 'other'
    chain: str = "ethereum"  # Add chain field with default
    source: str = "debank_enhanced"


@dataclass
class EnhancedWalletData:
    """Enhanced wallet data with detailed token breakdown."""

    address: str
    total_usd_value: float
    tokens: List[TokenBalance]
    protocols: List[Dict[str, Any]]
    timestamp: str
    source: str = "debank_enhanced"

    def categorize_exposure(self) -> Dict[str, float]:
        """Categorize tokens into exposure types."""
        categories = {"stable": 0.0, "eth_exposure": 0.0, "eth_staking": 0.0, "other_crypto": 0.0}

        for token in self.tokens:
            if token.category in categories:
                categories[token.category] += token.usd_value
            else:
                categories["other_crypto"] += token.usd_value

        return categories


class EnhancedDeBankScraper:
    """Enhanced DeBankc scraper that extracts detailed token information."""

    def __init__(self):
        # CSS selectors discovered in Phase 1
        self.selectors = {
            "token_values": ".AssetsOnChain_usdValue__I1B7X",
            "header_value": ".HeaderInfo_value__7Nj3p",  # This was wrong - follower TVL
            "portfolio_balance": [  # Use the same selectors as the working implementation
                ".HeaderInfo_totalAssetInner__HyrdC",
                '[data-testid="total-asset"]',
                ".total-asset",
                ".HeaderInfo_totalAsset__",
                ".total-balance",
                '[class*="totalAsset"]',
                '[class*="TotalAsset"]',
                '[class*="headerInfo"]',
                ".asset-value",
                ".portfolio-value",
                ".HeaderInfo_totalAsset__WcFLB",
                ".HeaderInfo_totalAssetInner__4Gdgw",
            ],
            "token_info": ".AssetsOnChain_chainInfo__fKA2k",
            "protocol_items": ".Portfolio_defiItem__cVQM-",
            "token_containers": ".AssetsOnChain_item__GBfMt",
            "chain_sections": ".AssetsOnChain_chainName__jAJuC",
            "wallet_token_rows": ".db-table-wrappedRow",  # Token rows in wallet table
            "wallet_token_symbol": ".TokenWallet_detailLink__goYJR",  # Token symbol links
            "wallet_token_price": ".db-table-cell",  # Table cells containing price/amount/value
            # NEW: Panels that sometimes hold extra protocol cards not caught by previous selectors
            "panel_container": '[class*="Panel_container"]',
            "panel_row": '[class*="table_contentRow"]',
            # Table header row inside panel card
            "table_header": '[class*="table_header"]',
        }

        # Token categorization rules
        self.token_categories = {
            "stable": {
                "USDT",
                "USDC",
                "DAI",
                "BUSD",
                "TUSD",
                "USDP",
                "FRAX",
                "FDUSD",
                "USDD",
                "LUSD",
                "sUSD",
                "MIM",
                "HUSD",
            },
            "eth_exposure": {"ETH", "WETH"},
            "eth_staking": {"stETH", "rETH", "cbETH", "sETH2", "ankrETH", "swETH"},
        }

    def categorize_token(self, symbol: str) -> str:
        """Categorize a token based on its symbol."""
        symbol_upper = symbol.upper()

        for category, tokens in self.token_categories.items():
            if symbol_upper in tokens:
                return category

        # Special handling for LP tokens and wrapped tokens
        if "LP" in symbol_upper or "UNI-V" in symbol_upper:
            return "lp_token"  # Needs special handling
        elif symbol_upper.startswith("W") and len(symbol_upper) <= 5:
            # Wrapped tokens (WBTC, WMATIC, etc.)
            base_token = symbol_upper[1:]
            if base_token in ["BTC", "MATIC", "AVAX", "FTM"]:
                return "other_crypto"

        return "other_crypto"

    def _detect_chain_from_symbol(self, symbol: str) -> str:
        """Detect chain from token symbol when chain sections aren't available."""
        symbol_upper = symbol.upper()

        # Chain-specific tokens
        chain_tokens = {
            "OP": "optimism",
            "ARB": "arbitrum",
            "MATIC": "polygon",
            "AVAX": "avalanche",
            "FTM": "fantom",
            "BNB": "bsc",
            "SOL": "solana",
            "ATOM": "cosmos",
        }

        if symbol_upper in chain_tokens:
            return chain_tokens[symbol_upper]

        # Default to ethereum for most tokens
        return "ethereum"

    async def scrape_wallet_enhanced(
        self, address: str, debug_rows: bool = False
    ) -> Optional[EnhancedWalletData]:
        """Scrape wallet with enhanced token breakdown."""
        print(f"🔍 Enhanced scraping for {address[:8]}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
            )

            page = await context.new_page()

            try:
                url = f"https://debank.com/profile/{address}"

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector("body", timeout=30000)

                # Wait for dynamic content to load
                await asyncio.sleep(10)

                # Click show all buttons to reveal hidden tokens and protocols
                await self._click_show_all_buttons(page)

                # Extract total portfolio value
                total_value = await self._extract_total_value(page)
                print(f"💰 Portfolio value: ${total_value:,.2f}")

                # Extract individual token balances
                tokens = await self._extract_token_balances(page)
                print(f"🪙 Found {len(tokens)} tokens")

                # Extract protocol positions
                protocols = await self._extract_protocol_positions(page)
                print(f"🏛️ Found {len(protocols)} protocols")

                # Create enhanced wallet data
                wallet_data = EnhancedWalletData(
                    address=address,
                    total_usd_value=total_value,
                    tokens=tokens,
                    protocols=protocols,
                    timestamp=datetime.now().isoformat(),
                )

                # VALIDATION: Check if extracted values match total portfolio
                await self._validate_extraction(wallet_data, total_value)

                # 4. Supplementary extraction from Panel_container elements (may include additional protocols)
                try:
                    panel_selector = self.selectors.get(
                        "panel_container", '[class*="Panel_container"]'
                    )
                    panel_elements = await page.query_selector_all(panel_selector)
                    if panel_elements:
                        print(
                            f"  🔍 Found {len(panel_elements)} panel container elements (additional protocols). Parsing..."
                        )
                        for j, panel_el in enumerate(panel_elements):
                            try:
                                protocol_data = await self._parse_protocol_element(
                                    panel_el, j + len(protocols)
                                )
                                if protocol_data and not any(
                                    p["name"] == protocol_data["name"]
                                    and abs(p["total_value"] - protocol_data["total_value"]) < 0.01
                                    for p in protocols
                                ):
                                    protocols.append(protocol_data)
                            except Exception:
                                continue
                except Exception as e:
                    print(f"  ⚠️ Error while parsing panel containers: {e}")

                if debug_rows:
                    await self._dump_first_rows(page)

                return wallet_data

            except Exception as e:
                print(f"❌ Error scraping {address[:8]}: {e}")
                return None
            finally:
                await browser.close()

    async def _click_show_all_buttons(self, page):
        """Click 'Show all' buttons to reveal tokens with small balances."""
        print("\n🔍 Attempting to click 'Show all' for tokens...")
        # --- Click "Show all" for tokens ---
        try:
            token_button = page.locator(".TokenWallet_showAll__PecCN").first
            if await token_button.is_visible(timeout=3000):
                print("  ✅ Found 'Show all' for tokens. Clicking...")
                await token_button.click(timeout=5000)
                await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  ⚠️  Could not click 'Show all' for tokens: {e}")

        print("🔍 Finished 'Show all' for tokens attempt.")

    async def _extract_total_value(self, page) -> float:
        """Extract total portfolio value using the same approach as the working implementation."""
        try:
            # Try the correct portfolio balance selectors
            total_balance_element = None
            used_selector = None

            for selector in self.selectors["portfolio_balance"]:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        if element:
                            text = await element.inner_text()
                            # Check if this element contains a dollar amount
                            if re.search(r"\$[\d,]+", text):
                                total_balance_element = element
                                used_selector = selector
                                break
                    if total_balance_element:
                        break
                except Exception:
                    continue

            if total_balance_element:
                text = await total_balance_element.inner_text()
                print(f"🔍 Portfolio balance text found: '{text}' (selector: {used_selector})")

                # Enhanced balance parsing with multiple regex patterns (same as working implementation)
                balance_patterns = [
                    r"\$?([\d,]+\.?\d*)\s*([-+]?\d+\.?\d*%)?",  # Standard pattern
                    r"Total\s*:?\s*\$?([\d,]+\.?\d*)",  # "Total: $123.45"
                    r"Portfolio\s*:?\s*\$?([\d,]+\.?\d*)",  # "Portfolio: $123.45"
                    r"Assets?\s*:?\s*\$?([\d,]+\.?\d*)",  # "Assets: $123.45"
                    r"Net\s*Worth\s*:?\s*\$?([\d,]+\.?\d*)",  # "Net Worth: $123.45"
                    r"Balance\s*:?\s*\$?([\d,]+\.?\d*)",  # "Balance: $123.45"
                    r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",  # Just numbers with commas
                ]

                for pattern in balance_patterns:
                    balance_match = re.search(pattern, text, re.IGNORECASE)
                    if balance_match:
                        try:
                            value = float(balance_match.group(1).replace(",", ""))
                            print(
                                f"✅ Portfolio balance extracted: ${value:,.2f} (pattern: {pattern})"
                            )
                            return value
                        except (ValueError, IndexError):
                            continue

            # Fallback: comprehensive search for dollar amounts
            print("🔍 No portfolio balance found, searching for largest dollar amount...")
            elements = await page.query_selector_all("*")
            largest_value = 0.0

            dollar_amounts = []
            for element in elements[:200]:  # Check more elements
                try:
                    text = await element.inner_text()
                    if "$" in text:
                        match = re.search(r"\$?([\d,]+\.?\d*)", text)
                        if match:
                            value = float(match.group(1).replace(",", ""))
                            if value > 1 and value < 100000000:  # Reasonable bounds
                                dollar_amounts.append(value)
                                if value > largest_value:
                                    largest_value = value
                except:
                    continue

            print(f"🔍 Found {len(dollar_amounts)} dollar amounts, largest: ${largest_value:,.2f}")
            if len(dollar_amounts) > 0:
                print(
                    f"🔍 Top 5 values: {[f'${v:,.0f}' for v in sorted(dollar_amounts, reverse=True)[:5]]}"
                )

            return largest_value

        except Exception as e:
            print(f"⚠️ Error extracting total value: {e}")
            return 0.0

    async def _extract_token_balances(self, page) -> List[TokenBalance]:
        """Extract individual token balances."""
        tokens = []

        try:
            # First try to extract from wallet token table (most reliable)
            wallet_tokens = await self._extract_wallet_tokens(page)
            tokens.extend(wallet_tokens)

            # If we didn't get many tokens from wallet, try other approaches
            if len(tokens) < 3:
                # Look for token containers
                token_elements = await page.query_selector_all(self.selectors["token_containers"])

                for element in token_elements[:20]:  # Limit to first 20 to avoid spam
                    try:
                        token_data = await self._parse_token_element(element)
                        if token_data:
                            tokens.append(token_data)
                    except Exception:
                        continue

                # Alternative: look for value elements directly
                if len(tokens) < 3:
                    value_elements = await page.query_selector_all(self.selectors["token_values"])

                    for element in value_elements[:10]:
                        try:
                            token_data = await self._parse_value_element(element, page)
                            if token_data:
                                tokens.append(token_data)
                        except Exception:
                            continue

        except Exception:
            pass

        return tokens

    async def _extract_wallet_tokens(self, page) -> List[TokenBalance]:
        """Extract tokens from the wallet token table with direct chain information from URLs."""
        tokens = []

        try:
            # Look for wallet token rows
            token_rows = await page.query_selector_all(self.selectors["wallet_token_rows"])

            for row in token_rows:
                try:
                    # Extract token info from the TokenWallet_detailLink
                    link_element = await row.query_selector("a.TokenWallet_detailLink__goYJR")
                    if not link_element:
                        continue

                    # Get token symbol from the link text
                    symbol = await link_element.inner_text()
                    symbol = symbol.strip()

                    # Extract chain from the href URL
                    href = await link_element.get_attribute("href")
                    chain = self._extract_chain_from_url(href) if href else "ethereum"

                    # Extract all table cells
                    cells = await row.query_selector_all(self.selectors["wallet_token_price"])
                    if len(cells) < 4:  # Need at least 4 cells: token, price, amount, value
                        continue

                    # Parse price (2nd cell)
                    price_text = await cells[1].inner_text()
                    price_match = re.search(r"\$?([\d,]+\.?\d*)", price_text.replace("$", ""))
                    price = float(price_match.group(1).replace(",", "")) if price_match else 0.0

                    # Parse amount (3rd cell)
                    amount_text = await cells[2].inner_text()
                    amount_match = re.search(r"([\d,]+\.?\d*)", amount_text.replace(",", ""))
                    amount = float(amount_match.group(1).replace(",", "")) if amount_match else 0.0

                    # Parse USD value (4th cell)
                    value_text = await cells[3].inner_text()
                    value_match = re.search(r"\$?([\d,]+\.?\d*)", value_text.replace("$", ""))
                    usd_value = float(value_match.group(1).replace(",", "")) if value_match else 0.0

                    # Only add if we have valid data
                    if symbol and usd_value > 0:
                        category = self.categorize_token(symbol)

                        token = TokenBalance(
                            symbol=symbol,
                            amount=amount,
                            usd_value=usd_value,
                            category=category,
                            chain=chain,
                        )
                        tokens.append(token)
                        print(f"🪙 Found token: {symbol} on {chain} - ${usd_value:.2f}")

                except Exception as e:
                    print(f"⚠️ Error parsing token row: {e}")
                    continue

        except Exception as e:
            print(f"❌ Error extracting wallet tokens: {e}")
            pass

        return tokens

    def _extract_chain_from_url(self, href: str) -> str:
        """Extract chain information from TokenWallet_detailLink href URL.

        Examples:
        - /token/arb/0xaf88d065e77c8cc2239327c5edb3a432268e5831 -> arbitrum
        - /token/soneium/soneium -> soneium
        - /token/op/op -> optimism
        - /token/eth/eth -> ethereum
        """
        if not href:
            return "ethereum"

        # Parse URL pattern: /token/{chain}/{token_address_or_symbol}
        parts = href.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "token":
            chain_code = parts[1]
            return self._normalize_chain_name(chain_code)

        return "ethereum"

    async def _parse_token_element(self, element) -> Optional[TokenBalance]:
        """Parse a token container element."""
        try:
            # Get all text from the element
            full_text = await element.inner_text()

            # Look for token symbol (3-5 uppercase letters)
            symbol_match = re.search(r"\b([A-Z]{2,6})\b", full_text)
            if not symbol_match:
                return None

            symbol = symbol_match.group(1)

            # Look for USD value
            value_match = re.search(r"\$?([\d,]+\.?\d*)", full_text)
            if not value_match:
                return None

            usd_value = float(value_match.group(1).replace(",", ""))

            # Estimate amount (simplified - in real implementation would need token prices)
            amount = usd_value  # Placeholder

            # Categorize token
            category = self.categorize_token(symbol)

            # Add simple chain detection
            chain = self._detect_chain_from_symbol(symbol)

            return TokenBalance(
                symbol=symbol, amount=amount, usd_value=usd_value, category=category, chain=chain
            )

        except Exception as e:
            return None

    async def _parse_value_element(self, element, page) -> Optional[TokenBalance]:
        """Parse a value element to extract token info."""
        try:
            # Get the USD value
            value_text = await element.inner_text()
            value_match = re.search(r"\$?([\d,]+\.?\d*)", value_text)
            if not value_match:
                return None

            usd_value = float(value_match.group(1).replace(",", ""))

            # Look for token symbol in nearby elements
            parent = await element.evaluate("element => element.parentElement")
            if parent:
                parent_text = await page.evaluate("element => element.textContent", parent)
                symbol_match = re.search(r"\b([A-Z]{2,6})\b", parent_text)
                if symbol_match:
                    symbol = symbol_match.group(1)
                    category = self.categorize_token(symbol)

                    # Add simple chain detection
                    chain = self._detect_chain_from_symbol(symbol)

                    return TokenBalance(
                        symbol=symbol,
                        amount=usd_value,  # Simplified
                        usd_value=usd_value,
                        category=category,
                        chain=chain,
                    )

            return None

        except Exception as e:
            return None

    async def _extract_protocol_positions(self, page) -> List[Dict[str, Any]]:
        """Extract DeFi protocol positions with detailed parsing and robust 'Show All' clicking."""
        print("\n🔍 Extracting protocol positions...")

        # 1. Attempt to click the 'Show All' button for protocols first.
        show_all_selectors = [
            ".Portfolio_projectsShowAll__Huhry",
            ".Portfolio_toggleCentiBtn__hBQ+k",
            '[class*="ProjectsShowAll"]',
        ]
        clicked_show_all = False
        for selector in show_all_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=2000):
                    print(f"  ✅ Found 'Show All' button with selector: '{selector}'. Clicking...")
                    await button.scroll_into_view_if_needed()
                    await button.click(timeout=5000, force=True)
                    await page.wait_for_timeout(3000)  # Wait for new protocols to load
                    clicked_show_all = True
                    print("  ✅ Successfully clicked 'Show All'.")
                    break
            except Exception:
                # This is expected if a selector doesn't match
                continue

        if not clicked_show_all:
            print(
                "  ⚠️ Could not find or click the 'Show All' button for protocols. Results may be incomplete."
            )

        # 2. Extract all protocol elements.
        protocols = []
        protocol_elements = []
        try:
            # This is the most reliable selector for the container of each protocol
            protocol_selector = ".Project_project__GCrhx"
            print(f"  🔍 Querying for protocol elements with selector: '{protocol_selector}'")
            protocol_elements = await page.query_selector_all(protocol_selector)
            print(f"  ✅ Found {len(protocol_elements)} potential protocol elements.")

            if not protocol_elements:
                # Fallback if the primary selector fails
                fallback_selector = ".Portfolio_defiItem__cVQM-"
                print(
                    f"  🟡 Primary selector found nothing. Trying fallback: '{fallback_selector}'"
                )
                protocol_elements = await page.query_selector_all(fallback_selector)
                print(f"  ✅ Found {len(protocol_elements)} elements with fallback selector.")

            # 3. Parse each element found (primary selectors)
            for i, element in enumerate(protocol_elements):
                try:
                    protocol_data = await self._parse_protocol_element(element, i)
                    if protocol_data and not any(
                        p["name"] == protocol_data["name"]
                        and abs(p["total_value"] - protocol_data["total_value"]) < 0.01
                        for p in protocols
                    ):
                        protocols.append(protocol_data)
                except Exception:
                    # Suppress parsing errors for individual elements
                    pass

        except Exception as e:
            print(f"  ❌ Major error during protocol extraction: {e}")

        # 4. Filter out any 'Wallet' protocols to prevent double counting.
        real_protocols = [
            p
            for p in protocols
            if not (p.get("name") == "Wallet" and p.get("source") == "reverted_simple_parsing")
        ]

        print(f"  ✅ Extracted {len(real_protocols)} unique protocols.")
        return real_protocols

    async def _parse_protocol_element(self, element, index: int) -> Optional[Dict[str, Any]]:
        """Parse a single protocol element to extract detailed information."""
        try:
            # Get all text from the element
            full_text = await element.inner_text()

            # Look for the protocol title div
            title_element = await element.query_selector(".ProjectTitle_projectTitle__yC5VD")
            if not title_element:
                return None

            # Extract protocol name from the protocol link
            name_element = await title_element.query_selector(".ProjectTitle_protocolLink__4Yqn3")
            if name_element:
                protocol_name = await name_element.inner_text()
                protocol_name = protocol_name.strip()
            else:
                # Fallback: try to extract from title element
                title_text = await title_element.inner_text()
                lines = [line.strip() for line in title_text.split("\n") if line.strip()]
                protocol_name = lines[0] if lines else f"Unknown Protocol {index}"

            # Look for the project title number
            balance_element = await title_element.query_selector(".projectTitle-number")
            if not balance_element:
                return None

            # Extract the balance value
            balance_text = await balance_element.inner_text()
            balance_text = balance_text.strip()

            # Parse the dollar amount
            balance_match = re.search(r"\$?([\d,]+\.?\d*)", balance_text)
            if not balance_match:
                return None

            total_value = float(balance_match.group(1).replace(",", ""))

            # Look for chain information
            chain = "unknown"
            chain_img = await title_element.query_selector(".ProjectTitle_projectChain__w-QNR")
            if chain_img:
                # Primary Method: Parse the chain from the image source URL
                chain_src = await chain_img.get_attribute("src")
                if chain_src:
                    chain_text = ""
                    try:
                        if "/logo_url/" in chain_src:
                            # Handles URLs like: .../logo_url/arb/HASH.png
                            parts = chain_src.split("/")
                            if "logo_url" in parts and len(parts) > parts.index("logo_url") + 1:
                                chain_text = parts[parts.index("logo_url") + 1]
                        elif "/media/" in chain_src:
                            # Handles URLs like: .../media/eth.HASH.svg
                            filename = Path(chain_src).stem
                            chain_text = filename.split(".")[0]
                    except Exception:
                        # In case of parsing errors, we can proceed to the fallback below
                        pass

                    if chain_text:
                        chain = self._normalize_chain_name(chain_text)
                    else:
                        # Fallback for legacy or unhandled URL formats
                        if "/eth/" in chain_src or "/ethereum/" in chain_src:
                            chain = "ethereum"
                        elif "/arb/" in chain_src or "/arbitrum/" in chain_src:
                            chain = "arbitrum"
                        elif "/matic/" in chain_src or "/polygon/" in chain_src:
                            chain = "polygon"
                        elif "/op/" in chain_src or "/optimism/" in chain_src:
                            chain = "optimism"
                        elif "/base/" in chain_src:
                            chain = "base"
                        elif "/sonic/" in chain_src:
                            chain = "sonic"
                        elif "/lisk/" in chain_src:
                            chain = "lisk"
                        elif "/ink/" in chain_src:
                            chain = "ink"
                        elif "/soneium/" in chain_src:
                            chain = "soneium"
                        elif "/uni/" in chain_src:
                            chain = "unichain"

            # HEURISTIC: If we found a valid protocol but could not determine the
            # chain from a logo, assume it is on Ethereum mainnet, as Debank often
            # omits the logo for the default chain.
            if chain == "unknown":
                chain = "ethereum"

            # Extract position type from panels
            position_type = "Unknown"
            panel_elements = await element.query_selector_all(".BookMark_bookmark__UG5a4")
            if panel_elements:
                position_types = []
                for panel in panel_elements:
                    panel_text = await panel.inner_text()
                    position_types.append(panel_text.strip())
                position_type = ", ".join(position_types)

            # Attempt to extract detailed positions inside the panel container
            positions_list, headers = [], []
            try:
                panel_sel = self.selectors.get("panel_container", '[class*="Panel_container"]')
                panel_el = await element.query_selector(panel_sel)
                if not panel_el:
                    # Expand the card to reveal panel
                    try:
                        await element.scroll_into_view_if_needed()
                        await element.click(timeout=1500, force=True)
                        try:
                            await element.wait_for_selector(panel_sel, timeout=2000)
                        except Exception:
                            await asyncio.sleep(0.6)
                        panel_el = await element.query_selector(panel_sel)
                    except Exception:
                        # Final retry
                        await asyncio.sleep(0.8)
                        panel_el = await element.query_selector(panel_sel)
                if panel_el:
                    positions_list, headers = await self._parse_positions_in_panel(
                        panel_el, position_type
                    )
            except Exception:
                positions_list, headers = [], []

            # If we failed to capture detailed positions, skip this protocol entirely
            if not positions_list:
                print(f"  ⏭️  Skipping '{protocol_name}' – no detailed panel rows detected.")
                return None

            # Success path
            print(f"  ✅ Parsed {len(positions_list)} positions for protocol '{protocol_name}'.")

            src_tag = "panel_container_parsed"

            if protocol_name and total_value > 0:
                return {
                    "name": protocol_name,
                    "chain": chain,
                    "total_value": total_value,
                    "positions": positions_list,
                    "position_type": position_type,
                    "table_headers": headers,
                    "raw_balance_text": balance_text,
                    "source": src_tag,
                    "parsing_method": "protocol_element_panel",
                    "risk_double_count": False,
                }
            else:
                return None

        except Exception:
            return None

    async def _validate_extraction(self, wallet_data: EnhancedWalletData, total_value: float):
        """Validate the extracted values against the total portfolio balance."""
        # Calculate extracted values - exclude fallback 'Wallet' protocols to avoid double counting
        total_token_value = sum(token.usd_value for token in wallet_data.tokens)
        total_protocol_value = sum(
            protocol["total_value"]
            for protocol in wallet_data.protocols
            if not (
                protocol.get("name") == "Wallet"
                and protocol.get("chain") == "unknown"
                and protocol.get("source") == "reverted_simple_parsing"
            )
        )
        total_extracted = total_token_value + total_protocol_value

        # Calculate difference
        difference = abs(total_extracted - total_value)
        percentage_diff = (difference / total_value * 100) if total_value > 0 else 0

        # Simple validation status
        if difference < 100:  # Less than $100 difference
            print("✅ Validation PASSED")
        elif percentage_diff < 5:  # Less than 5% difference
            print("⚠️ Validation WARNING (small discrepancy)")
        else:
            print("❌ Validation FAILED (significant discrepancy)")
            print(f"   Difference: ${difference:,.2f} ({percentage_diff:.1f}%)")

    async def scrape_offline(
        self, html_file_path: str, address: Optional[str] = None
    ) -> Optional[EnhancedWalletData]:
        """Scrape wallet data from a saved HTML file for offline analysis."""
        if not BS4_AVAILABLE:
            print(
                "❌ BeautifulSoup4 required for offline scraping. Install with: pip install beautifulsoup4"
            )
            return None

        if not os.path.exists(html_file_path):
            print(f"❌ HTML file not found: {html_file_path}")
            return None

        print(f"🔍 Offline scraping from: {html_file_path}")

        # Extract address from filename if not provided - ensure it's always a string
        if not address:
            filename = os.path.basename(html_file_path)
            if filename.startswith("0x"):
                address = filename[:10]  # Extract first 10 chars (0x + 8 hex chars)
            else:
                address = "unknown"

        # At this point address is guaranteed to be a string
        assert address is not None, "Address should not be None at this point"

        try:
            # Read HTML file
            with open(html_file_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Parse with BeautifulSoup for offline analysis
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract total portfolio value using similar logic
            total_value = self._extract_total_value_offline(soup)
            print(f"💰 Total portfolio value: ${total_value:,.2f}")

            # Extract tokens using BeautifulSoup
            tokens = self._extract_tokens_offline(soup)
            print(f"🪙 Found {len(tokens)} tokens")

            # Extract protocols using BeautifulSoup
            protocols = self._extract_protocols_offline(soup)
            print(f"🏛️ Found {len(protocols)} protocols")

            # Create enhanced wallet data - address is guaranteed to be str now
            wallet_data = EnhancedWalletData(
                address=address,  # This is now guaranteed to be a string
                total_usd_value=total_value,
                tokens=tokens,
                protocols=protocols,
                timestamp=datetime.now().isoformat(),
            )

            # Show categorized exposure
            exposure = wallet_data.categorize_exposure()
            print(f"📊 Exposure breakdown:")
            for category, value in exposure.items():
                percentage = (value / total_value * 100) if total_value > 0 else 0
                print(f"  • {category}: ${value:,.2f} ({percentage:.1f}%)")

            # VALIDATION: Check if extracted values match total portfolio
            await self._validate_extraction_offline(wallet_data, total_value)

            return wallet_data

        except Exception as e:
            print(f"❌ Error in offline scraping: {e}")
            return None

    def _extract_total_value_offline(self, soup) -> float:
        """Extract total portfolio value from BeautifulSoup object."""
        try:
            # Try the same selectors we use in live scraping
            selectors = [
                ".HeaderInfo_totalAssetInner__HyrdC",
                '[data-testid="total-asset"]',
                ".total-asset",
                ".HeaderInfo_totalAsset__",
                ".total-balance",
                '[class*="totalAsset"]',
                '[class*="TotalAsset"]',
                '[class*="headerInfo"]',
                ".asset-value",
                ".portfolio-value",
            ]

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    if text and "$" in text:
                        balance_match = re.search(r"\$?([\d,]+\.?\d*)", text)
                        if balance_match:
                            value = float(balance_match.group(1).replace(",", ""))
                            print(f"✅ Portfolio balance extracted offline: ${value:,.2f}")
                            return value

            # Fallback: search for largest dollar amount
            all_text = soup.get_text()
            amounts = re.findall(r"\$?([\d,]+\.?\d*)", all_text)
            largest_value = 0.0
            for amount_str in amounts:
                try:
                    value = float(amount_str.replace(",", ""))
                    if value > largest_value and value < 100000000:
                        largest_value = value
                except:
                    continue

            return largest_value

        except Exception as e:
            print(f"⚠️ Error extracting total value offline: {e}")
            return 0.0

    def _extract_tokens_offline(self, soup) -> List[TokenBalance]:
        """Extract token balances from BeautifulSoup object with chain information."""
        tokens = []

        try:
            # Look for token table rows
            token_rows = soup.select(".db-table-wrappedRow")
            print(f"🔍 Found {len(token_rows)} token rows in HTML")

            for i, row in enumerate(token_rows):
                try:
                    # Extract token info from the TokenWallet_detailLink
                    link_elements = row.select("a.TokenWallet_detailLink__goYJR")
                    if not link_elements:
                        continue

                    link_element = link_elements[0]
                    symbol = link_element.get_text(strip=True)

                    # Extract chain from the href URL
                    href = link_element.get("href", "")
                    chain = self._extract_chain_from_url(href) if href else "ethereum"

                    # Extract all table cells
                    cells = row.select(".db-table-cell")
                    if len(cells) < 4:
                        continue

                    # Parse USD value (4th cell)
                    value_text = cells[3].get_text(strip=True)
                    value_match = re.search(r"\$?([\d,]+\.?\d*)", value_text.replace("$", ""))
                    usd_value = float(value_match.group(1).replace(",", "")) if value_match else 0.0

                    # Parse amount (3rd cell)
                    amount_text = cells[2].get_text(strip=True)
                    amount_match = re.search(r"([\d,]+\.?\d*)", amount_text.replace(",", ""))
                    amount = float(amount_match.group(1).replace(",", "")) if amount_match else 0.0

                    if symbol and usd_value > 0:
                        category = self.categorize_token(symbol)
                        token = TokenBalance(
                            symbol=symbol,
                            amount=amount,
                            usd_value=usd_value,
                            category=category,
                            chain=chain,
                        )
                        tokens.append(token)

                        if i < 10:  # Show first 10 for debugging
                            print(
                                f"✅ Offline Token {i+1}: {symbol} on {chain} = ${usd_value:,.2f} ({category})"
                            )

                except Exception as e:
                    continue

        except Exception as e:
            print(f"⚠️ Error extracting tokens offline: {e}")

        return tokens

    def _extract_protocols_offline(self, soup) -> List[Dict[str, Any]]:
        """Extract protocol positions from BeautifulSoup object."""
        protocols = []

        try:
            # Look for protocol elements
            protocol_elements = soup.select(".Project_project__GCrhx")
            print(f"🔍 Found {len(protocol_elements)} protocol elements in HTML")

            for i, element in enumerate(protocol_elements):
                try:
                    # Find title element
                    title_elements = element.select(".ProjectTitle_projectTitle__yC5VD")
                    if not title_elements:
                        continue

                    title_element = title_elements[0]

                    # Extract protocol name
                    name_elements = title_element.select(".ProjectTitle_protocolLink__4Yqn3")
                    if name_elements:
                        protocol_name = name_elements[0].get_text(strip=True)
                    else:
                        # Fallback
                        lines = [
                            line.strip()
                            for line in title_element.get_text().split("\n")
                            if line.strip()
                        ]
                        protocol_name = lines[0] if lines else f"Unknown Protocol {i}"

                    # Extract balance
                    balance_elements = title_element.select(".projectTitle-number")
                    if not balance_elements:
                        continue

                    balance_text = balance_elements[0].get_text(strip=True)
                    balance_match = re.search(r"\$?([\d,]+\.?\d*)", balance_text)
                    if not balance_match:
                        continue

                    total_value = float(balance_match.group(1).replace(",", ""))

                    # Extract chain (simplified for offline)
                    chain = "unknown"
                    chain_imgs = title_element.select(".ProjectTitle_projectChain__w-QNR")
                    if chain_imgs:
                        src = chain_imgs[0].get("src", "")
                        if "/eth/" in src or "/ethereum/" in src:
                            chain = "Ethereum"
                        elif "/arb/" in src:
                            chain = "Arbitrum"
                        elif "/base/" in src:
                            chain = "Base"
                        # Add more chain detection as needed

                    if protocol_name and total_value > 0:
                        protocols.append(
                            {
                                "name": protocol_name,
                                "chain": chain,
                                "total_value": total_value,
                                "position_type": "Unknown",
                                "raw_balance_text": balance_text,
                                "source": "offline_parsing",
                            }
                        )

                        if i < 10:  # Show first 10 for debugging
                            print(
                                f"✅ Offline Protocol {i+1}: {protocol_name} = ${total_value:,.2f} on {chain}"
                            )

                except Exception as e:
                    continue

        except Exception as e:
            print(f"⚠️ Error extracting protocols offline: {e}")

        return protocols

    async def _validate_extraction_offline(
        self, wallet_data: EnhancedWalletData, total_value: float
    ):
        """Validate the extracted values against the total portfolio balance for offline scraping."""
        # Calculate extracted values - exclude fallback 'Wallet' protocols to avoid double counting
        total_token_value = sum(token.usd_value for token in wallet_data.tokens)
        total_protocol_value = sum(
            protocol["total_value"]
            for protocol in wallet_data.protocols
            if not (
                protocol.get("name") == "Wallet"
                and protocol.get("chain") == "unknown"
                and protocol.get("source") == "reverted_simple_parsing"
            )
        )
        total_extracted = total_token_value + total_protocol_value

        # Calculate difference
        difference = abs(total_extracted - total_value)
        percentage_diff = (difference / total_value * 100) if total_value > 0 else 0

        # Simple validation status
        if difference < 100:  # Less than $100 difference
            print("✅ Offline Validation PASSED")
        elif percentage_diff < 5:  # Less than 5% difference
            print("⚠️ Offline Validation WARNING (small discrepancy)")
        else:
            print("❌ Offline Validation FAILED (significant discrepancy)")
            print(f"   Difference: ${difference:,.2f} ({percentage_diff:.1f}%)")

    def scrape_from_structured_data(self, address, data_dir="saved_pages"):
        """Scrape from captured structured data files (BYPASS METHOD)."""
        print(f"🚀 BYPASS: Scraping from structured data for address: {address}")

        # Check for structured data files
        data_path = os.path.join(data_dir, address)
        structured_file = os.path.join(data_path, "structured_data.json")
        expanded_file = os.path.join(data_path, "expanded_data.json")

        tokens = []
        protocols = []

        # Try structured data first
        if os.path.exists(structured_file):
            tokens, protocols = self._parse_structured_json(structured_file)
        # Fallback to expanded data
        elif os.path.exists(expanded_file):
            tokens, protocols = self._parse_expanded_json(expanded_file)
        else:
            print(f"❌ No structured data files found in {data_path}")
            return [], [], {}

        # Calculate summary stats
        total_value = sum(token.get("value_usd", 0) for token in tokens)
        summary_stats = {
            "total_value_usd": total_value,
            "total_tokens": len(tokens),
            "total_protocols": len(protocols),
            "data_source": "structured_data",
        }

        print(
            f"✅ Structured data scraping complete - Found {len(tokens)} tokens and {len(protocols)} protocols"
        )
        return tokens, protocols, summary_stats

    def _parse_structured_json(self, file_path):
        """Parse structured JSON data."""
        print(f"📊 Parsing structured data from: {file_path}")

        with open(file_path, "r") as f:
            data = json.load(f)

        tokens = []
        protocols = []

        # Parse token list
        if "token_list" in data:
            for token_data in data["token_list"]:
                token = self._parse_token_from_json(token_data)
                if token:
                    tokens.append(token)

        # Parse protocol list
        if "protocol_list" in data:
            for protocol_data in data["protocol_list"]:
                protocol = self._parse_protocol_from_json(protocol_data)
                if protocol:
                    protocols.append(protocol)

        return tokens, protocols

    def _parse_expanded_json(self, file_path):
        """Parse expanded JSON data."""
        print(f"📊 Parsing expanded data from: {file_path}")

        with open(file_path, "r") as f:
            data = json.load(f)

        tokens = []
        protocols = []

        # Parse token list
        if "token_list" in data:
            for token_data in data["token_list"]:
                token = self._parse_token_from_json(token_data)
                if token:
                    tokens.append(token)

        # Parse protocol list
        if "protocol_list" in data:
            for protocol_data in data["protocol_list"]:
                protocol = self._parse_protocol_from_json(protocol_data)
                if protocol:
                    protocols.append(protocol)

        return tokens, protocols

    def _parse_token_from_json(self, token_data):
        """Parse token data from JSON format."""
        try:
            symbol = token_data.get("symbol", "UNKNOWN")
            amount = token_data.get("amount", 0)
            usd_value = token_data.get("usd_value", 0)
            category = token_data.get("category", "other_crypto")
            chain = token_data.get("chain", "ethereum")  # Add chain field with default

            if symbol and usd_value > 0:
                return TokenBalance(
                    symbol=symbol,
                    amount=amount,
                    usd_value=usd_value,
                    category=category,
                    chain=chain,
                )
        except Exception as e:
            print(f"⚠️ Error parsing token from JSON: {e}")
        return None

    def _parse_protocol_from_json(self, protocol_data):
        """Parse protocol from JSON data."""
        try:
            name = protocol_data.get("protocol_name", "").strip()
            deposit_str = protocol_data.get("protocol_deposit", "").strip()

            if not name:
                return None

            # Parse deposit amount
            deposit_usd = 0
            if deposit_str and deposit_str.startswith("$"):
                deposit_clean = re.sub(r"[,$]", "", deposit_str[1:])  # Remove $ and commas
                try:
                    deposit_usd = float(deposit_clean)
                except (ValueError, TypeError):
                    deposit_usd = 0

            return {"name": name, "total_usd": deposit_usd, "source": "structured_data"}
        except Exception as e:
            print(f"⚠️ Error parsing protocol data: {e}")
            return None

    def _normalize_chain_name(self, chain_text: str) -> str:
        """Normalize chain name from DeBanks text to standardized format."""
        chain_lower = chain_text.lower().strip()

        # Direct chain mappings from the DeBanks URLs
        chain_mappings = {
            "eth": "ethereum",
            "ethereum": "ethereum",
            "arb": "arbitrum",
            "arbitrum": "arbitrum",
            "matic": "polygon",
            "polygon": "polygon",
            "base": "base",
            "op": "optimism",
            "optimism": "optimism",
            "bsc": "bsc",
            "binance": "bsc",
            "avax": "avalanche",
            "avalanche": "avalanche",
            "sonic": "sonic",
            "lisk": "lisk",
            "ink": "ink",
            "soneium": "soneium",
            "uni": "unichain",
            "unichain": "unichain",
            "xlayer": "xlayer",
            "gravity": "gravity",
            "itze": "itze",
            "rsk": "rsk",
            "abs": "abstract",
            "abstract": "abstract",
            "linea": "linea",
            "mnt": "mantle",
            "mantle": "mantle",
            "ftm": "fantom",
            "fantom": "fantom",
            "celo": "celo",
            "near": "near",
            "sol": "solana",
            "solana": "solana",
        }

        # Check for direct mapping first
        if chain_lower in chain_mappings:
            return chain_mappings[chain_lower]

        # Check for partial matches (legacy logic)
        if "ethereum" in chain_lower or "eth" in chain_lower:
            return "ethereum"
        elif "arbitrum" in chain_lower or "arb" in chain_lower:
            return "arbitrum"
        elif "polygon" in chain_lower or "matic" in chain_lower:
            return "polygon"
        elif "base" in chain_lower:
            return "base"
        elif "optimism" in chain_lower or "op" in chain_lower:
            return "optimism"
        elif "bsc" in chain_lower or "binance" in chain_lower:
            return "bsc"
        elif "avalanche" in chain_lower or "avax" in chain_lower:
            return "avalanche"
        elif "sonic" in chain_lower:
            return "sonic"
        elif "lisk" in chain_lower:
            return "lisk"
        elif "ink" in chain_lower:
            return "ink"
        elif "soneium" in chain_lower:
            return "soneium"
        elif "unichain" in chain_lower:
            return "unichain"
        elif "abstract" in chain_lower:
            return "abstract"
        elif "linea" in chain_lower:
            return "linea"
        elif "mantle" in chain_lower:
            return "mantle"
        elif "fantom" in chain_lower:
            return "fantom"
        else:
            # For unknown chains, return the original chain code to avoid losing information
            return chain_lower if chain_lower else "ethereum"

    # ---------------------------------------------------------------------
    # Helper: Save results to disk (used by CLI test flow)
    # ---------------------------------------------------------------------
    def save_results(self, wallet_data: EnhancedWalletData, output_dir: str = "results") -> None:
        """Persist scraped wallet data as JSON for later inspection/tests."""
        try:
            from dataclasses import asdict

            os.makedirs(output_dir, exist_ok=True)

            # File name: wallet_breakdown_<address>.json
            file_path = os.path.join(output_dir, f"wallet_breakdown_{wallet_data.address}.json")

            # Convert dataclass objects to serializable dicts
            data_dict = asdict(wallet_data)
            # asdict converts nested dataclasses too, so TokenBalance objects become dicts automatically

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=2)

            print(f"💾 Results saved to {file_path}")
        except Exception as e:
            print(f"⚠️ Error saving results: {e}")

    # ------------------------------------------------------------------
    # Panel / position parsing helpers
    # ------------------------------------------------------------------
    async def _parse_positions_in_panel(self, panel_element, panel_type: str):
        """Parse rows in DOM order, updating header_type when a new header row appears."""
        positions = []
        headers_global = []
        try:
            header_sel = self.selectors.get("table_header", '[class*="table_header"]')
            row_sel = self.selectors.get("panel_row", '[class*="table_contentRow"]')

            alt_row_sel = '[class*="More_line"]'
            combined_query = f"{header_sel}, {row_sel}, {alt_row_sel}"

            # Gather both header & row nodes in DOM order inside table content container
            nodes = await panel_element.query_selector_all(combined_query)

            current_header = ""
            for node in nodes:
                # Determine if node is header or row
                class_attr = await node.get_attribute("class")
                if class_attr and "table_header" in class_attr:
                    # New header row
                    span_nodes = await node.query_selector_all("span")
                    local_texts = []
                    for span in span_nodes:
                        txt = (await span.inner_text()).strip()
                        if txt and txt != "\u00a0":
                            local_texts.append(txt)
                    if local_texts:
                        current_header = local_texts[0]
                        headers_global.append(current_header)
                    continue

                # Must be a content row
                try:
                    row_text = (await node.inner_text()).strip()
                    if not row_text:
                        continue
                    lines = [l.strip() for l in row_text.split("\n") if l.strip()]
                    if not lines:
                        continue
                    position_label = lines[0]
                    asset_line = lines[1] if len(lines) >= 2 else position_label
                    asset = asset_line

                    # USD value
                    usd_matches = re.findall(r"\$([\d,]+\.?\d*)", row_text)
                    if usd_matches:
                        usd_value = float(usd_matches[-1].replace(",", ""))
                    else:
                        usd_value = 0.0

                    # amount
                    amount = 0.0
                    for p in lines[1:]:
                        if "$" not in p:
                            m = re.search(r"([\d,]+\.?\d*)", p)
                            if m:
                                amount = float(m.group(1).replace(",", ""))
                                break

                    if usd_value == 0.0 and amount == 0.0:
                        continue

                    positions.append(
                        {
                            "label": position_label,
                            "asset": asset,
                            "amount": amount,
                            "usd_value": usd_value,
                            "header_type": current_header,
                            "panel_type": panel_type,
                            "raw_row_text": row_text,
                        }
                    )
                except Exception:
                    continue
        except Exception:
            pass

        return positions, headers_global

    def _infer_position_kind(self, text: str) -> str:
        """Infer the product / position kind from a panel row's text."""
        t = text.lower()
        # Borrowed / debt first so we don't mark collateral as supply when both appear
        borrow_keywords = ["borrow", "debt", "owed", "liability"]
        supply_keywords = ["supply", "supplied", "deposit", "lent", "collateral", "provide"]
        reward_keywords = ["reward", "rewards", "pending", "earned", "claim"]
        stake_keywords = ["stake", "staked", "staking", "locked", "bond"]
        perp_keywords = ["perp", "perpetual"]
        spot_keywords = ["spot balance", "spot"]
        lp_keywords = ["liquidity pool", "lp "]

        if any(k in t for k in borrow_keywords):
            return "borrowed"
        if any(k in t for k in supply_keywords):
            return "supplied"
        if any(k in t for k in reward_keywords):
            return "reward"
        if any(k in t for k in stake_keywords):
            return "staked"
        if any(k in t for k in perp_keywords):
            return "perp"
        if any(k in t for k in spot_keywords):
            return "spot"
        # LP detection: row starting with '#' (NFT style position id) & '+', or explicit keywords
        if text.strip().startswith("#") and "+" in text[:60]:
            return "liquidity_pool"
        if any(k in t for k in lp_keywords):
            return "liquidity_pool"
        return "unknown"

    async def _dump_first_rows(self, page):
        """Dump innerHTML for first 5 position rows for debugging."""
        try:
            # Look for panel elements
            panel_selector = self.selectors.get("panel_container", '[class*="Panel_container"]')
            panel_elements = await page.query_selector_all(panel_selector)
            if not panel_elements:
                print("  🟡 No panel elements found")
                return

            for i, panel_el in enumerate(panel_elements[:5]):
                try:
                    snippet = (await panel_el.inner_html())[:1500]
                    print(
                        f"      🐞 Panel {i+1} HTML snippet (first 1.5k chars):\n"
                        + snippet.replace("\n", " ")[:1500]
                    )
                except Exception as e:
                    print(f"      ⚠️ Could not dump panel HTML: {e}")
        except Exception as e:
            print(f"⚠️ Error dumping first rows: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Enhanced DeBankc scraper")
    parser.add_argument("address", nargs="?", help="Ethereum address to scrape")
    parser.add_argument("--test", action="store_true", help="Use demo addresses")
    parser.add_argument("--output", default="results", help="Output directory")
    parser.add_argument(
        "--debug-rows",
        action="store_true",
        help="Dump innerHTML for first 5 position rows for debugging",
    )

    args = parser.parse_args()

    scraper = EnhancedDeBankScraper()

    # Demo addresses
    demo_addresses = [
        "0x60c6c28e10ee895037260d653ef8a22a9cae6f3c",  # Simpler wallet for testing
    ]

    if args.test:
        print("🧪 Testing enhanced scraper with demo address...")
        for address in demo_addresses:
            wallet_data = await scraper.scrape_wallet_enhanced(address, debug_rows=args.debug_rows)
            if wallet_data:
                scraper.save_results(wallet_data, args.output)
                print(f"✅ Successfully processed {address[:8]}...")

    elif args.address:
        wallet_data = await scraper.scrape_wallet_enhanced(args.address, debug_rows=args.debug_rows)
        if wallet_data:
            scraper.save_results(wallet_data, args.output)
            print(f"✅ Successfully processed {args.address[:8]}...")
    else:
        print("Please provide an address or use --test flag")
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
