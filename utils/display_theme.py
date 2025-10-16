# -*- coding: utf-8 -*-
"""
Simple Display Theme System
"""

from colorama import Fore, Style


class SimpleTheme:
    """Basic theme with consistent colors."""

    def __init__(self):
        # Primary colors
        self.PRIMARY = Fore.WHITE + Style.BRIGHT
        self.ACCENT = Fore.CYAN + Style.BRIGHT
        self.SUCCESS = Fore.GREEN + Style.BRIGHT
        self.ERROR = Fore.RED + Style.BRIGHT
        self.WARNING = Fore.YELLOW + Style.BRIGHT
        self.INFO = Fore.BLUE + Style.BRIGHT
        self.SUBTLE = Style.DIM
        self.RESET = Style.RESET_ALL

        # Simple symbols
        self.CHECKMARK = "✓"
        self.CROSS = "✗"
        self.WARNING_SYMBOL = "⚠"
        self.INFO_SYMBOL = "ℹ"


# Global theme instance
theme = SimpleTheme()
