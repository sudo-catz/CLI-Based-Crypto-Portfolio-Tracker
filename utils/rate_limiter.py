"""
Rate Limiting and Retry Utilities
Handles 429 errors gracefully with exponential backoff and user feedback.
"""

import time
import asyncio
import random
from typing import Callable, Any, Optional, Dict
from functools import wraps
import requests
from utils.helpers import print_warning, print_info, print_error
from colorama import Fore, Style
import functools


class RateLimiter:
    """Smart rate limiter with exponential backoff and user feedback"""

    def __init__(self):
        self.last_requests = {}  # Track last request time per domain
        self.request_counts = {}  # Track request counts per domain
        self.base_delays = {
            "api.coingecko.com": 1.5,  # CoinGecko rate limit: 30/min = 2 seconds
            "api.mainnet-beta.solana.com": 0.5,  # Solana RPC: be more conservative
            "blockchain.info": 1.0,  # Bitcoin API
            "rpc.mainnet.near.org": 0.3,  # NEAR RPC
        }

    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        if "://" in url:
            url = url.split("://")[1]
        return url.split("/")[0]

    async def wait_if_needed(self, url: str):
        """Wait if we need to respect rate limits"""
        domain = self.get_domain(url)
        base_delay = self.base_delays.get(domain, 0.1)

        if domain in self.last_requests:
            time_since_last = time.time() - self.last_requests[domain]
            if time_since_last < base_delay:
                wait_time = base_delay - time_since_last
                print_info(f"⏳ Rate limiting {domain} - waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        self.last_requests[domain] = time.time()


# Domain-specific retry delays (in seconds)
DOMAIN_DELAYS = {
    "api.coingecko.com": 1.5,  # CoinGecko rate limit: 30/min = 2 seconds
    "api.bybit.com": 1.0,  # Bybit rate limit: more lenient but add delay for stability
    "api.binance.com": 0.5,  # Binance has good rate limits
    "api.okx.com": 0.8,  # OKX moderate rate limits
}


# Enhanced progress display for rate limiting
class EnhancedProgressDisplay:
    """Enhanced progress display with better formatting and status tracking."""

    def __init__(self, service_name: str, max_retries: int):
        self.service_name = service_name
        self.max_retries = max_retries
        self.attempt = 0

    def show_retry_attempt(self, attempt: int, delay: float, error_msg: str = ""):
        """Show retry attempt with progress information."""
        self.attempt = attempt
        progress = f"[{attempt}/{self.max_retries}]"
        error_preview = f": {error_msg[:50]}..." if error_msg else ""
        print_warning(f"⚠ Error in {self.service_name} (attempt {progress}){error_preview}")
        print_info(f"🔄 Retrying in {delay:.1f}s...")

    def show_final_failure(self):
        """Show final failure message."""
        print_error(f"❌ {self.service_name} failed after {self.max_retries} attempts")

    def show_success_after_retry(self, attempt: int):
        """Show success message after retry."""
        print_info(f"✅ {self.service_name} succeeded on attempt {attempt}/{self.max_retries}")


def smart_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    domain_delay: Optional[str] = None,
    service_name: str = "API call",
):
    """
    Enhanced retry decorator with exponential backoff, jitter, and domain-specific delays.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        domain_delay: Domain key for domain-specific delay lookup
        service_name: Human-readable service name for progress display
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            progress = EnhancedProgressDisplay(service_name, max_retries)
            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    result = func(*args, **kwargs)

                    # Show success message if this was a retry
                    if attempt > 0:
                        progress.show_success_after_retry(attempt + 1)

                    return result

                except requests.exceptions.HTTPError as e:
                    if e.response and e.response.status_code == 429:
                        if attempt < max_retries:
                            delay = calculate_retry_delay(
                                attempt,
                                base_delay,
                                max_delay,
                                exponential_base,
                                jitter,
                                domain_delay,
                            )
                            progress.show_retry_attempt(attempt + 1, delay, "Rate limited")
                            time.sleep(delay)
                            continue
                        else:
                            progress.show_final_failure()
                            raise
                    else:
                        # For non-429 HTTP errors, don't retry by default
                        raise

                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError,
                    Exception,
                ) as e:
                    error_msg = str(e)

                    if attempt < max_retries:
                        delay = calculate_retry_delay(
                            attempt, base_delay, max_delay, exponential_base, jitter, domain_delay
                        )
                        error_type = type(e).__name__
                        progress.show_retry_attempt(attempt + 1, delay, f"{error_type}")
                        time.sleep(delay)
                        continue
                    else:
                        progress.show_final_failure()
                        raise

            # This should never be reached due to the raise above
            progress.show_final_failure()
            raise Exception(f"{service_name} failed after {max_retries} attempts")

        return wrapper

    return decorator


def calculate_retry_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential_base: float,
    jitter: bool,
    domain_delay: Optional[str],
) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    # Apply domain-specific delay if specified
    if domain_delay and domain_delay in DOMAIN_DELAYS:
        base_delay = max(base_delay, DOMAIN_DELAYS[domain_delay])

    # Calculate exponential backoff
    delay = min(base_delay * (exponential_base**attempt), max_delay)

    # Add jitter to prevent thundering herd
    if jitter:
        jitter_amount = delay * 0.1  # 10% jitter
        delay += random.uniform(-jitter_amount, jitter_amount)

    return max(delay, 0.1)  # Minimum 0.1 second delay


# Pre-configured retry decorators for common services
coingecko_retry = smart_retry(
    max_retries=4,
    base_delay=2.0,
    max_delay=30.0,
    domain_delay="api.coingecko.com",
    service_name="CoinGecko API",
)

solana_retry = smart_retry(
    max_retries=3,
    base_delay=1.0,
    max_delay=15.0,
    service_name="Solana RPC",
)

bybit_retry = smart_retry(
    max_retries=3,
    base_delay=1.0,
    max_delay=10.0,
    domain_delay="api.bybit.com",
    service_name="Bybit API",
)

# Enhanced retry decorators for exchanges
binance_retry = smart_retry(
    max_retries=4,  # Increased retries due to frequent DNS issues
    base_delay=0.5,
    max_delay=8.0,
    domain_delay="api.binance.com",
    service_name="Binance API",
)

okx_retry = smart_retry(
    max_retries=4,  # Increased retries due to DNS issues
    base_delay=0.8,
    max_delay=12.0,
    domain_delay="api.okx.com",
    service_name="OKX API",
)

backpack_retry = smart_retry(
    max_retries=5,  # Backpack has the most DNS issues
    base_delay=1.5,
    max_delay=15.0,
    service_name="Backpack API",
)

blockchain_retry = smart_retry(
    max_retries=2,
    base_delay=1.0,
    max_delay=8.0,
    service_name="Blockchain API",
)

# Network-specific retry for DNS and connectivity issues
network_retry = smart_retry(
    max_retries=6,  # Increased for network issues
    base_delay=2.0,
    max_delay=20.0,
    service_name="Network Request",
)
