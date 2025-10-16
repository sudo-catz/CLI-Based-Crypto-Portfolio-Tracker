#!/usr/bin/env python3
"""
API Key Management System for Port2
-----------------------------------
Handles secure storage and management of API credentials for various exchanges
and services. Uses encryption for secure storage.
"""

import base64
import getpass
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from colorama import Fore, Style
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from utils.helpers import (
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)


@dataclass
class APICredentials:
    """Data class for API credentials"""

    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    testnet: bool = False
    note: Optional[str] = None
    created_at: Optional[str] = None


class APIKeyManager:
    """Manages API keys with encryption and secure storage"""

    def __init__(self, config_file: str = "data/api_config.enc"):
        """Initialize the API Key Manager with encryption capabilities"""
        self.config_file = config_file
        self.salt_file = "data/.api_salt"
        self.fernet = None
        self._master_password = None
        self._auth_locked = False

        # Ensure data directory exists
        data_dir = os.path.dirname(config_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

        self.supported_exchanges = {
            "binance": "Binance",
            "okx": "OKX",
            "bybit": "Bybit",
            "backpack": "Backpack",
        }

        # Debug mode initialization
        from config.constants import DEBUG_MODE

        if DEBUG_MODE:
            print_info("API Manager: Debug mode detected - using simplified authentication")

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def _get_or_create_salt(self) -> bytes:
        """Get existing salt or create new one"""
        if os.path.exists(self.salt_file):
            with open(self.salt_file, "rb") as f:
                return f.read()
        else:
            salt = os.urandom(16)
            with open(self.salt_file, "wb") as f:
                f.write(salt)
            # Hide the salt file on Unix systems
            if os.name != "nt":
                os.chmod(self.salt_file, 0o600)
            return salt

    def _initialize_encryption(self, password: str):
        """Initialize encryption with master password"""
        salt = self._get_or_create_salt()
        key = self._derive_key(password, salt)
        self.fernet = Fernet(key)
        self._master_password = password

    def authenticate(self) -> bool:
        """Authenticate user with master password"""
        if self._master_password:
            return True
        if self._auth_locked:
            print_error("Authentication is locked for this session after too many failed attempts.")
            sys.exit(1)

        # Check for debug mode
        from config.constants import DEBUG_MODE, DEBUG_MASTER_PASSWORD, DEBUG_WARNING_MESSAGE

        if DEBUG_MODE:
            print(f"{Fore.YELLOW}{DEBUG_WARNING_MESSAGE}{Style.RESET_ALL}")
            self._initialize_encryption(DEBUG_MASTER_PASSWORD)
            print_success("Debug mode: Authentication bypassed")
            return True

        print_header("API Key Management Authentication")
        print_info("Enter your master password to access encrypted API keys")

        if not os.path.exists(self.config_file):
            return self._handle_first_time_setup()

        max_attempts = 3
        for attempt in range(max_attempts):
            password = getpass.getpass(f"{Fore.CYAN}Master password: {Style.RESET_ALL}")

            if self._verify_password(password):
                self._initialize_encryption(password)
                print_success("Authentication successful")
                self._auth_locked = False
                return True
            else:
                remaining = max_attempts - attempt - 1
                if remaining > 0:
                    print_error(f"Invalid password. {remaining} attempts remaining.")
                else:
                    print_error("Authentication failed. Access locked for this session.")
                    self._auth_locked = True

        if self._auth_locked:
            print_error("Too many failed master password attempts. Exiting for security.")
            sys.exit(1)
        return False

    def _verify_password(self, password: str) -> bool:
        """Verify the master password"""
        try:
            salt = self._get_or_create_salt()
            key = self._derive_key(password, salt)
            test_fernet = Fernet(key)

            # Try to decrypt the config file
            with open(self.config_file, "rb") as f:
                encrypted_data = f.read()
                test_fernet.decrypt(encrypted_data)
            return True

        except Exception:
            return False

    def _handle_first_time_setup(self) -> bool:
        """Interactive flow for creating the initial master password."""
        from config.constants import DEBUG_MODE, DEBUG_MASTER_PASSWORD

        if DEBUG_MODE:
            password = DEBUG_MASTER_PASSWORD
            if not self._store_master_password(password):
                print_error("Debug mode: Failed to initialize master password storage.")
                return False
            self._initialize_encryption(password)
            print_success("Debug mode: Master password set successfully")
            print_success("Authentication successful")
            self._auth_locked = False
            return True

        print_info("No existing API vault found. Let's set up a master password (min 8 characters).")

        while True:
            password = getpass.getpass(
                f"{Fore.CYAN}Create master password (min 8 chars): {Style.RESET_ALL}"
            )
            if len(password) < 8:
                print_error("Password must be at least 8 characters long")
                continue

            confirm_password = getpass.getpass(
                f"{Fore.CYAN}Confirm master password: {Style.RESET_ALL}"
            )
            if password != confirm_password:
                print_error("Passwords don't match")
                continue

            if not self._store_master_password(password):
                print_error("Failed to initialize encrypted store. Please try again.")
                continue

            self._initialize_encryption(password)
            print_success("Master password set successfully")
            print_success("Authentication successful")
            self._auth_locked = False
            return True

    def _store_master_password(self, password: str) -> bool:
        """Persist an empty encrypted config using the provided master password."""
        if len(password) < 8:
            return False
        # Create empty encrypted config
        salt = self._get_or_create_salt()
        key = self._derive_key(password, salt)
        fernet = Fernet(key)

        empty_config = {}
        encrypted_data = fernet.encrypt(json.dumps(empty_config).encode())

        with open(self.config_file, "wb") as f:
            f.write(encrypted_data)

        # Set file permissions
        if os.name != "nt":
            os.chmod(self.config_file, 0o600)

        return True

    def store_credentials(self, exchange: str, credentials: APICredentials):
        """Store encrypted API credentials"""
        if not self.fernet:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Load existing config
        config = self._load_config()

        # Add timestamp if not present
        if not credentials.created_at:
            from datetime import datetime

            credentials.created_at = datetime.now().isoformat()

        # Store credentials
        config[exchange] = asdict(credentials)

        # Encrypt and save
        self._save_config(config)
        print_success(f"API credentials stored for {exchange}")

    def get_credentials(self, exchange: str) -> Optional[APICredentials]:
        """Retrieve decrypted API credentials"""
        if not self.fernet:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        config = self._load_config()

        if exchange not in config:
            return None

        cred_data = config[exchange]
        return APICredentials(**cred_data)

    def list_stored_credentials(self) -> Dict[str, Dict[str, Any]]:
        """List all stored credentials with metadata (but not the actual keys)"""
        if not self.fernet:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        config = self._load_config()
        result = {}

        for exchange, cred_data in config.items():
            result[exchange] = {
                "exchange_name": self.supported_exchanges.get(exchange, exchange.title()),
                "has_passphrase": bool(cred_data.get("passphrase")),
                "testnet": cred_data.get("testnet", False),
                "note": cred_data.get("note"),
                "created_at": cred_data.get("created_at"),
                "api_key_preview": (
                    cred_data.get("api_key", "")[:8] + "..." if cred_data.get("api_key") else "None"
                ),
            }

        return result

    def remove_credentials(self, exchange: str) -> bool:
        """Remove credentials for an exchange"""
        if not self.fernet:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        config = self._load_config()

        if exchange in config:
            del config[exchange]
            self._save_config(config)
            print_success(f"API credentials removed for {exchange}")
            return True
        else:
            print_warning(f"No credentials found for {exchange}")
            return False

    def _load_config(self) -> Dict[str, Any]:
        """Load and decrypt configuration"""
        if not os.path.exists(self.config_file):
            from config.constants import DEBUG_MODE

            if DEBUG_MODE:
                # In debug mode, return empty config without error
                return {}
            return {}

        try:
            with open(self.config_file, "rb") as f:
                encrypted_data = f.read()
                decrypted_data = self.fernet.decrypt(encrypted_data)
                return json.loads(decrypted_data.decode())
        except Exception as e:
            from config.constants import DEBUG_MODE

            if DEBUG_MODE:
                # In debug mode, don't show error - just return empty config
                return {}
            print_error(f"Failed to load API configuration: {e}")
            return {}

    def _save_config(self, config: Dict[str, Any]):
        """Encrypt and save configuration"""
        try:
            encrypted_data = self.fernet.encrypt(json.dumps(config).encode())
            with open(self.config_file, "wb") as f:
                f.write(encrypted_data)

            # Set file permissions
            if os.name != "nt":
                os.chmod(self.config_file, 0o600)

        except Exception as e:
            print_error(f"Failed to save API configuration: {e}")
            raise


# Global instance
api_key_manager = APIKeyManager()
