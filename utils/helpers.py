# -*- coding: utf-8 -*-
"""
Utility functions for Multi-Chain Portfolio Tracker
"""
import os
import time
import getpass
import hmac
import base64
from typing import Any, Optional, Dict
from datetime import datetime, timezone
from colorama import Fore, Style

# Import the simple theme system
from utils.display_theme import theme


def clear_screen():
    """Clears the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_loading_animation(message: str, duration: float = 3):
    """Displays an enhanced loading animation with progress feedback."""
    # Multiple animation styles to cycle through
    spinners = [
        ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],  # Modern spinner
        ["◐", "◓", "◑", "◒"],  # Circle spinner
        ["▖", "▘", "▝", "▗"],  # Box spinner
        ["●", "○", "◉", "○"],  # Dot spinner
    ]

    current_spinner = spinners[0]  # Use modern spinner by default
    idx = 0
    start_time = time.time()

    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        progress = min(100, int((elapsed / duration) * 100))

        # Create progress bar
        bar_width = 20
        filled_width = int((progress / 100) * bar_width)
        bar = "█" * filled_width + "░" * (bar_width - filled_width)

        # Format display with enhanced styling
        spinner_char = current_spinner[idx % len(current_spinner)]
        display_text = (
            f"\r{theme.INFO}{spinner_char} {message}{theme.RESET} "
            f"{theme.ACCENT}[{bar}]{theme.RESET} "
            f"{theme.SUCCESS}{progress:3d}%{theme.RESET}"
        )

        print(display_text, end="", flush=True)
        idx += 1
        time.sleep(0.1)

    # Final completion message
    checkmark = theme.CHECKMARK
    print(
        f"\r{theme.SUCCESS}{checkmark} {message}{theme.RESET} "
        f"{theme.ACCENT}[{'█' * bar_width}]{theme.RESET} "
        f"{theme.SUCCESS}100%{theme.RESET}"
    )
    time.sleep(0.3)  # Brief pause to show completion

    # Clear the animation line after brief display
    print("\r" + " " * (len(message) + 35) + "\r", end="", flush=True)


def print_progress_step(step: str, current: int, total: int):
    """Displays a progress step with counter."""
    percentage = int((current / total) * 100) if total > 0 else 0
    print(
        f"{theme.INFO}{theme.INFO_SYMBOL} Step {current}/{total}: {step} ({percentage}%){theme.RESET}"
    )


def print_loading_dots(message: str, count: int = 3):
    """Displays animated loading dots (quick feedback)."""
    for i in range(count):
        print(f"\r{theme.INFO}{message}{'.' * (i + 1)}{theme.RESET}", end="", flush=True)
        time.sleep(0.5)
    print(f"\r{theme.SUCCESS}{theme.CHECKMARK} {message}{theme.RESET}")


def print_fetch_status(source: str, status: str):
    """Displays fetch status for individual sources."""
    if status.lower() in ["success", "completed", "ok"]:
        icon = theme.CHECKMARK
        color = theme.SUCCESS
    elif status.lower() in ["error", "failed", "timeout"]:
        icon = theme.CROSS
        color = theme.ERROR
    else:
        icon = theme.INFO_SYMBOL
        color = theme.WARNING

    print(f"{color}{icon} {source}: {status}{theme.RESET}")


def print_connection_status(service: str, is_connected: bool):
    """Displays connection status for services."""
    if is_connected:
        print(f"{theme.SUCCESS}{theme.CHECKMARK} Connected to {service}{theme.RESET}")
    else:
        print(f"{theme.ERROR}{theme.CROSS} Failed to connect to {service}{theme.RESET}")


def print_header(text: str, width: int = 70):
    """Prints a formatted, professional header."""
    clear_screen()

    print(f"\n{theme.PRIMARY}{'━' * width}{theme.RESET}")
    print(
        f"{theme.PRIMARY}┃{theme.RESET} {theme.ACCENT}{text.center(width-4)}{theme.RESET} {theme.PRIMARY}┃{theme.RESET}"
    )
    print(f"{theme.PRIMARY}{'━' * width}{theme.RESET}\n")


def print_subheader(text: str, width: int = 60):
    """Prints a formatted subheader."""
    print(f"\n{theme.ACCENT}{text}{theme.RESET}")
    print(f"{theme.SUBTLE}{'─' * len(text)}{theme.RESET}")


def print_success(text: str):
    """Prints a success message."""
    print(f"{theme.SUCCESS}{theme.CHECKMARK} {text}{theme.RESET}")


def print_error(text: str, is_network_issue: bool = False):
    """Prints an error message."""
    message = f"{theme.ERROR}{theme.CROSS} Error: {text}{theme.RESET}"
    if is_network_issue:
        message += f"\n{theme.SUBTLE}   Network troubleshooting: Check connection and DNS settings{theme.RESET}"
    print(message)


def print_warning(text: str):
    """Prints a warning message."""
    print(f"{theme.WARNING}{theme.WARNING_SYMBOL} Warning: {text}{theme.RESET}")


def print_info(text: str):
    """Prints an informational message."""
    print(f"{theme.INFO}{theme.INFO_SYMBOL} {text}{theme.RESET}")


def print_divider(width: int = 60, style: str = "light"):
    """Prints a divider line."""
    if style == "heavy":
        print(f"{theme.PRIMARY}{'═' * width}{theme.RESET}")
    else:
        print(f"{theme.SUBTLE}{'─' * width}{theme.RESET}")


def print_key_value(key: str, value: str, key_width: int = 20):
    """Prints a key-value pair with consistent formatting."""
    formatted_key = f"{theme.PRIMARY}{key}:".ljust(
        key_width + len(theme.PRIMARY) + len(theme.RESET)
    )
    formatted_value = f"{theme.ACCENT}{value}{theme.RESET}"
    print(f"{formatted_key}{theme.RESET} {formatted_value}")


def print_menu_header(title: str, description: str = ""):
    """Prints a professional menu header."""
    print_header(title)
    if description:
        print(f"{theme.SUBTLE}{description}{theme.RESET}\n")


def print_menu_option(number: int, text: str, description: str = ""):
    """Prints a menu option with consistent formatting."""
    print(f"{theme.ACCENT}{number:2d}.{theme.RESET} {theme.PRIMARY}{text}{theme.RESET}")
    if description:
        print(f"     {theme.SUBTLE}{description}{theme.RESET}")


def print_loading_status(message: str):
    """Prints a loading status message."""
    print(f"{theme.INFO}► {message}...{theme.RESET}")


def format_large_number(value: float, precision: int = 2) -> str:
    """Formats large numbers with appropriate suffixes (K, M, B)."""
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.{precision}f}B"
    elif abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.{precision}f}M"
    elif abs(value) >= 1_000:
        return f"{value / 1_000:.{precision}f}K"
    else:
        return f"{value:.{precision}f}"


def get_secure_input(prompt: str) -> str:
    """Gets password input securely."""
    return getpass.getpass(prompt)


def get_current_timestamp_iso() -> str:
    """Returns the current UTC time in ISO format for OKX."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def get_current_timestamp_ms() -> int:
    """Returns the current UTC time in milliseconds since epoch."""
    return int(time.time() * 1000)


def safe_float_convert(value: Any, default: float = 0.0) -> float:
    """Safely converts a value to float, returning default if conversion fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def format_currency(value: Optional[float], color: str = "", max_precision: bool = False) -> str:
    """Formats a float as USD currency, handling None, optionally adding color and allowing max precision."""
    if value is None:
        return f"{theme.ERROR}N/A{theme.RESET}"

    if max_precision:
        return f"{color or theme.SUCCESS}${value:,.8f}{theme.RESET}"
    else:
        return f"{color or theme.SUCCESS}${value:,.2f}{theme.RESET}"


def format_currency_compact(value: Optional[float]) -> str:
    """Formats currency in compact form (K, M, B)."""
    if value is None:
        return f"{theme.ERROR}N/A{theme.RESET}"

    formatted_number = format_large_number(value)
    return f"{theme.SUCCESS}${formatted_number}{theme.RESET}"


def format_percentage(value: Optional[float], color: str = "") -> str:
    """Formats a float as a percentage, handling None, optionally adding color."""
    if value is None:
        return f"{theme.ERROR}N/A{theme.RESET}"

    if value > 0:
        return f"{color or theme.SUCCESS}+{value:.2f}%{theme.RESET}"
    elif value < 0:
        return f"{color or theme.ERROR}{value:.2f}%{theme.RESET}"
    else:
        return f"{color or theme.WARNING}{value:.2f}%{theme.RESET}"


def format_btc(value: Optional[float], color: str = "") -> str:
    """Formats a float as BTC, handling None, optionally adding color."""
    if value is None:
        return f"{theme.ERROR}N/A{theme.RESET}"
    return f"{color or theme.ACCENT}{value:.8f} BTC{theme.RESET}"


def format_native_balance(
    value: Optional[float], symbol: str, decimals: int = 4, color: str = ""
) -> str:
    """Formats a native token balance, handling None, optionally adding color."""
    if value is None:
        return f"{theme.ERROR}N/A{theme.RESET}"
    return f"{color or theme.ACCENT}{value:.{decimals}f} {symbol}{theme.RESET}"


def format_timestamp(timestamp_str: str) -> str:
    """Formats timestamp with consistent styling."""
    try:
        dt_obj = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        formatted = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"{theme.ACCENT}{formatted}{theme.RESET}"
    except ValueError:
        return f"{theme.WARNING}{timestamp_str}{theme.RESET}"


def create_summary_box(title: str, content: Dict[str, str], width: int = 60) -> str:
    """Creates a formatted summary box."""
    content_lines = []
    for key, value in content.items():
        content_lines.append(
            f"{theme.PRIMARY}{key}{theme.RESET}: {theme.ACCENT}{value}{theme.RESET}"
        )

    content_str = "\n".join(content_lines)
    border = "─" * width
    return f"\n{theme.PRIMARY}┌{border}┐{theme.RESET}\n{theme.PRIMARY}│{theme.RESET} {title.center(width-2)} {theme.PRIMARY}│{theme.RESET}\n{theme.PRIMARY}├{border}┤{theme.RESET}\n{content_str}\n{theme.PRIMARY}└{border}┘{theme.RESET}"


def print_table_separator(width: int = 60):
    """Prints a table separator line."""
    print(f"{theme.SUBTLE}{'─' * width}{theme.RESET}")


# OKX Specific Functions
def generate_okx_sign(prehash: str, secret_key: str) -> str:
    """Generates the signature for OKX API requests."""
    mac = hmac.new(
        bytes(secret_key, encoding="utf8"), bytes(prehash, encoding="utf-8"), digestmod="sha256"
    )
    return base64.b64encode(mac.digest()).decode()


def okx_pre_hash(timestamp: str, method: str, request_path: str, body: str) -> str:
    """Creates the pre-hash string for OKX API signature."""
    return str(timestamp) + str(method) + str(request_path) + str(body)


def get_okx_header(
    api_key: str, sign: str, timestamp: str, passphrase: str, flag: str = "0"
) -> Dict[str, str]:
    """Constructs the header for OKX API requests."""
    return {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": flag,  # '1' for demo trading, '0' for live
        "Content-Type": "application/json",
    }


# Enhanced Input Validation Functions


def get_validated_choice(prompt: str, valid_choices: list, case_sensitive: bool = False) -> str:
    """Gets and validates user choice with helpful error messages."""
    # Clean prompt format instead of ugly (1/2/3/4/5/6/7)
    if len(valid_choices) <= 7:
        range_str = f"1-{len(valid_choices)}"
    else:
        range_str = f"1-{len(valid_choices)}"

    full_prompt = f"{theme.PRIMARY}{prompt} ({range_str}): {theme.RESET}"

    while True:
        user_input = input(full_prompt).strip()

        if not case_sensitive:
            user_input = user_input.lower()
            valid_choices_check = [str(choice).lower() for choice in valid_choices]
        else:
            valid_choices_check = [str(choice) for choice in valid_choices]

        if user_input in valid_choices_check:
            return user_input

        # Smart suggestions for similar inputs
        suggestions = []
        for choice in valid_choices:
            choice_str = str(choice).lower() if not case_sensitive else str(choice)
            if user_input in choice_str or choice_str.startswith(user_input):
                suggestions.append(str(choice))

        # Show available options in a clean format
        choices_str = ", ".join(str(choice) for choice in valid_choices)

        if suggestions:
            print_error(
                f"Invalid choice '{user_input}'. Did you mean: {', '.join(suggestions[:3])}?"
            )
        else:
            print_error(f"Invalid choice '{user_input}'. Valid options: {choices_str}")

        print_info(f"Please enter a number from {range_str}.")


def get_validated_number(
    prompt: str,
    min_val: float = None,
    max_val: float = None,
    allow_float: bool = True,
    allow_negative: bool = False,
) -> float:
    """Gets and validates numeric input with range checking."""
    while True:
        try:
            user_input = input(f"{theme.PRIMARY}{prompt}: {theme.RESET}").strip()

            if not user_input:
                print_error("Please enter a value.")
                continue

            # Remove common formatting characters
            cleaned_input = user_input.replace(",", "").replace("$", "")

            if allow_float:
                value = float(cleaned_input)
            else:
                value = int(cleaned_input)

            # Validate range
            if not allow_negative and value < 0:
                print_error("Negative values are not allowed.")
                continue

            if min_val is not None and value < min_val:
                print_error(f"Value must be at least {min_val}")
                continue

            if max_val is not None and value > max_val:
                print_error(f"Value must be at most {max_val}")
                continue

            return value

        except ValueError:
            print_error(
                f"Invalid number format. Please enter a valid {'number' if allow_float else 'integer'}."
            )


def get_validated_address(prompt: str, chain: str) -> str:
    """Gets and validates wallet addresses with chain-specific validation."""
    # Address validation patterns
    address_patterns = {
        "ethereum": {"length": 42, "prefix": "0x", "chars": "0123456789abcdefABCDEF"},
        "bitcoin": {
            "min_length": 26,
            "max_length": 35,
            "prefixes": ["1", "3", "bc1"],
            "chars": None,
        },
        "solana": {
            "length": 44,
            "prefix": None,
            "chars": "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz",
        },
    }

    pattern = address_patterns.get(chain.lower())
    if not pattern:
        # Generic validation for unknown chains
        while True:
            address = input(f"{theme.PRIMARY}{prompt}: {theme.RESET}").strip()
            if len(address) > 10:  # Basic length check
                return address
            print_error("Address seems too short. Please verify and try again.")

    while True:
        address = input(f"{theme.PRIMARY}{prompt}: {theme.RESET}").strip()

        if not address:
            print_error("Please enter an address.")
            continue

        # Chain-specific validation
        if chain.lower() == "ethereum":
            if len(address) != pattern["length"]:
                print_error(
                    f"Ethereum addresses must be exactly {pattern['length']} characters long."
                )
                continue
            if not address.startswith(pattern["prefix"]):
                print_error(f"Ethereum addresses must start with '{pattern['prefix']}'.")
                continue
            if not all(c in pattern["chars"] for c in address[2:]):
                print_error("Ethereum address contains invalid characters.")
                continue

        elif chain.lower() == "bitcoin":
            if len(address) < pattern["min_length"] or len(address) > pattern["max_length"]:
                print_error(
                    f"Bitcoin addresses must be {pattern['min_length']}-{pattern['max_length']} characters long."
                )
                continue
            if not any(address.startswith(prefix) for prefix in pattern["prefixes"]):
                print_error(
                    f"Bitcoin addresses must start with one of: {', '.join(pattern['prefixes'])}"
                )
                continue

        elif chain.lower() == "solana":
            if len(address) != pattern["length"]:
                print_error(
                    f"Solana addresses must be exactly {pattern['length']} characters long."
                )
                continue
            if not all(c in pattern["chars"] for c in address):
                print_error("Solana address contains invalid characters.")
                continue

        print_success(f"✓ Valid {chain.capitalize()} address format")
        return address


def get_confirmed_input(prompt: str, confirmation_prompt: str = None) -> str:
    """Gets input with confirmation for critical operations."""
    if confirmation_prompt is None:
        confirmation_prompt = "Please confirm this action"

    value = input(f"{theme.PRIMARY}{prompt}: {theme.RESET}").strip()

    if value:
        print(f"\n{theme.WARNING}⚠️  {confirmation_prompt}: {theme.ACCENT}{value}{theme.RESET}")
        confirm = input(f"{theme.WARNING}Type 'YES' to confirm: {theme.RESET}")

        if confirm == "YES":
            return value
        else:
            print_info("Operation cancelled.")
            return None
    return value


def get_menu_choice(options_count: int, prompt: str = "Select option") -> str:
    """Gets validated menu choice with enhanced error handling."""
    valid_choices = [str(i) for i in range(1, options_count + 1)]
    return get_validated_choice(prompt, valid_choices)


def get_yes_no(prompt: str, default: bool = None) -> bool:
    """Gets yes/no input with smart defaults."""
    if default is True:
        suffix = " (Y/n)"
        default_str = "yes"
    elif default is False:
        suffix = " (y/N)"
        default_str = "no"
    else:
        suffix = " (y/n)"
        default_str = None

    while True:
        response = input(f"{theme.PRIMARY}{prompt}{suffix}: {theme.RESET}").strip().lower()

        if not response and default_str:
            return default

        if response in ["y", "yes", "true", "1"]:
            return True
        elif response in ["n", "no", "false", "0"]:
            return False
        else:
            print_error("Please enter 'y' for yes or 'n' for no.")


def smart_input_suggestions(user_input: str, valid_options: list) -> list:
    """Provides smart suggestions for user input."""
    suggestions = []
    user_lower = user_input.lower()

    for option in valid_options:
        option_lower = str(option).lower()

        # Exact match
        if user_lower == option_lower:
            return [str(option)]

        # Starts with
        if option_lower.startswith(user_lower):
            suggestions.append(str(option))

        # Contains
        elif user_lower in option_lower:
            suggestions.append(str(option))

    return suggestions[:5]  # Limit to 5 suggestions
