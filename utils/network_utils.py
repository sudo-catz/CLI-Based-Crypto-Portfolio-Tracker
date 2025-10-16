"""
Enhanced Network Utilities with DNS Resilience
---------------------------------------------
Provides robust network utilities with DNS failover, connection pooling,
and intelligent retry strategies for cryptocurrency exchange APIs.
"""

import requests
import socket
import time
from typing import List, Optional, Dict, Any
from utils.helpers import print_error, print_warning, print_info, print_success

# Network errors for comprehensive handling
NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
    socket.gaierror,
    OSError,
)

# DNS servers for fallback resolution
FALLBACK_DNS_SERVERS = [
    "8.8.8.8",  # Google Primary
    "8.8.4.4",  # Google Secondary
    "1.1.1.1",  # Cloudflare Primary
    "1.0.0.1",  # Cloudflare Secondary
    "208.67.222.222",  # OpenDNS
]

# Exchange API endpoint mirrors/alternatives
EXCHANGE_MIRRORS = {
    "api.binance.com": [
        "api.binance.com",
        "api1.binance.com",
        "api2.binance.com",
        "api3.binance.com",
    ],
    "www.okx.com": ["www.okx.com", "aws.okx.com", "www.okex.com"],  # Legacy domain
    "api.backpack.exchange": ["api.backpack.exchange", "api-v2.backpack.exchange"],
}


def test_dns_resolution(hostname: str, timeout: int = 5) -> bool:
    """Test if hostname can be resolved via DNS."""
    try:
        socket.gethostbyname_ex(hostname)
        return True
    except socket.gaierror:
        return False


def get_working_endpoint(base_hostname: str, timeout: int = 5) -> Optional[str]:
    """Find a working endpoint from available mirrors."""
    mirrors = EXCHANGE_MIRRORS.get(base_hostname, [base_hostname])

    for mirror in mirrors:
        if test_dns_resolution(mirror, timeout):
            print_success(f"✅ DNS resolution successful: {mirror}")
            return mirror
        else:
            print_warning(f"⚠️  DNS resolution failed: {mirror}")

    print_error(f"❌ All mirrors failed for {base_hostname}")
    return None


def smart_request_with_fallback(
    url: str, method: str = "GET", **kwargs
) -> Optional[requests.Response]:
    """Make HTTP request with DNS fallback and retry logic."""
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    hostname = parsed_url.netloc

    # Try to find working endpoint
    working_hostname = get_working_endpoint(hostname)
    if not working_hostname:
        print_error(f"No working endpoints found for {hostname}")
        return None

    # Construct new URL with working hostname
    if working_hostname != hostname:
        new_url = url.replace(hostname, working_hostname)
        print_info(f"🔄 Using fallback endpoint: {working_hostname}")
    else:
        new_url = url

    # Make request with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if method.upper() == "GET":
                response = requests.get(new_url, timeout=15, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(new_url, timeout=15, **kwargs)
            else:
                response = requests.request(method, new_url, timeout=15, **kwargs)

                response.raise_for_status()
                return response

        except NETWORK_ERRORS as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                print_warning(
                    f"⚠️  Attempt {attempt + 1} failed, retrying in {wait_time}s: {str(e)[:100]}"
                )
                time.sleep(wait_time)
            else:
                print_error(f"❌ All {max_retries} attempts failed for {new_url}")
                return None

    return None


def handle_network_error_gracefully(error: Exception, service_name: str) -> None:
    """Handle network errors gracefully with appropriate user messaging."""
    error_str = str(error)

    if "Name or service not known" in error_str or "getaddrinfo failed" in error_str:
        print_warning(f"🌐 {service_name}: DNS resolution failed (network/connectivity issue)")
    elif "Max retries exceeded" in error_str:
        print_warning(f"🔄 {service_name}: Connection timeout (server may be down)")
    elif "timeout" in error_str.lower():
        print_warning(f"⏱️  {service_name}: Request timeout (slow network)")
    else:
        print_error(f"❌ Network Error fetching {service_name}: {error}")
        print_error(
            "  (This often indicates a network/DNS issue. Check connection and DNS settings.)"
        )


def diagnose_network_connectivity() -> Dict[str, Any]:
    """Diagnose network connectivity and DNS resolution."""
    print_info("🔍 Diagnosing network connectivity...")

    results = {"dns_working": False, "exchange_connectivity": {}, "recommendations": []}

    # Test basic DNS resolution
    test_domains = ["google.com", "cloudflare.com"]
    dns_working = False

    for domain in test_domains:
        if test_dns_resolution(domain):
            print_success(f"✅ DNS working: {domain}")
            dns_working = True
            break
    else:
        print_warning(f"⚠️  DNS failed: {domain}")

    results["dns_working"] = dns_working

    if not dns_working:
        results["recommendations"].append("Check DNS settings - try 8.8.8.8 or 1.1.1.1")
        return results

    # Test exchange connectivity
    exchanges = {
        "Binance": "api.binance.com",
        "OKX": "www.okx.com",
        "Backpack": "api.backpack.exchange",
    }

    for name, hostname in exchanges.items():
        working_endpoint = get_working_endpoint(hostname)
        results["exchange_connectivity"][name] = {
            "hostname": hostname,
            "working": working_endpoint is not None,
            "working_endpoint": working_endpoint,
        }

    # Generate recommendations
    failed_exchanges = [
        name for name, status in results["exchange_connectivity"].items() if not status["working"]
    ]

    if failed_exchanges:
        results["recommendations"].append(f"DNS issues with: {', '.join(failed_exchanges)}")
        results["recommendations"].append("Try running analysis again in 5-10 minutes")
        results["recommendations"].append("Check if your ISP is blocking exchange domains")

    return results
