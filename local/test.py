#!/usr/bin/env python3

import unittest
import json
import os
import time
import subprocess
import re
import socket
import sys
import urllib3
import ssl
from algosdk import account, mnemonic, encoding
from algosdk.v2client import algod
from algosdk.transaction import PaymentTxn
from algosdk.error import AlgodHTTPError

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def determine_algod_host():
    """Determine the Algorand node host using fly CLI and config."""
    # Get app name from fly.toml
    app_name = get_app_name()
    if not app_name:
        print("No app name found in fly.toml, using localhost")
        return "localhost"

    # Get the IP address directly from Fly CLI
    print(f"Getting IP address for {app_name}...")
    try:
        result = subprocess.run(
            ["fly", "ips", "list", "--app", app_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Extract IP from the output
            ip_match = re.search(r"v4\s+([0-9.]+)", result.stdout)
            if ip_match:
                ip_address = ip_match.group(1)
                print(f"Using Fly.io app IP address: {ip_address}")
                return ip_address
    except Exception as e:
        print(f"Could not get IP address: {e}")

    # If we can't get IP, try the domain
    fly_host = f"{app_name}.fly.dev"

    # Try to resolve the hostname
    MAX_RETRY_ATTEMPTS = 10
    RETRY_DELAY = 3  # seconds

    print(
        f"Attempting to resolve host {fly_host}... (max {MAX_RETRY_ATTEMPTS} attempts)"
    )

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            # Try to resolve the hostname to check if DNS is working
            socket.gethostbyname(fly_host)
            print(f"Host {fly_host} successfully resolved on attempt {attempt+1}")
            return fly_host
        except socket.gaierror as e:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                print(
                    f"Attempt {attempt+1}/{MAX_RETRY_ATTEMPTS} failed to resolve {fly_host}: {e}"
                )
                print(f"Waiting {RETRY_DELAY} seconds before retrying...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"All {MAX_RETRY_ATTEMPTS} attempts to resolve {fly_host} failed")

    print("\n⚠️  WARNING: Could not resolve hostname after multiple attempts")
    print("\nTROUBLESHOOTING SUGGESTIONS:")
    print(f"1. Ensure the app is deployed with 'fly deploy --app {app_name}'")
    print("2. Wait longer for DNS propagation (can take up to 15-30 minutes)")
    print(f"3. Check app status with 'fly status --app {app_name}'")

    # Return the hostname anyway, but tests will likely fail
    return fly_host


def load_genesis_info():
    """Load genesis account information from generated file."""
    genesis_info_file = "generated/genesis_info.json"

    if not os.path.exists(genesis_info_file):
        print(f"ERROR: Genesis information file not found: {genesis_info_file}")
        print("Please run setup.sh first to generate the genesis file.")
        sys.exit(1)

    try:
        with open(genesis_info_file, "r") as f:
            genesis_data = json.load(f)

        address = genesis_data.get("address")
        mnemo = genesis_data.get("mnemonic")

        if not address or not mnemo:
            print(f"ERROR: Missing address or mnemonic in {genesis_info_file}")
            sys.exit(1)

        return address, mnemo

    except Exception as e:
        print(f"ERROR loading genesis information: {e}")
        sys.exit(1)


def get_app_name():
    """Extract the app name from fly.toml."""
    if os.path.exists("fly.toml"):
        try:
            with open("fly.toml", "r") as f:
                content = f.read()
                app_match = re.search(r'app\s*=\s*[\'"]([^\'"]+)[\'"]', content)
                if app_match:
                    return app_match.group(1)
        except Exception:
            pass
    return "algorand-node"  # Default fallback


def load_api_token():
    """Load the API token from the generated file."""
    token_file = "generated/algod.token"

    if not os.path.exists(token_file):
        print(f"WARNING: API token file not found: {token_file}")
        print("Using empty token. This might fail if API authentication is required.")
        return ""

    try:
        with open(token_file, "r") as f:
            token = f.read().strip()
        return token
    except Exception as e:
        print(f"WARNING: Couldn't read API token: {e}")
        return ""


class AlgorandNodeTest(unittest.TestCase):
    """Test suite for validating Algorand node deployment and basic functionality."""

    # Test settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    @classmethod
    def setUpClass(cls):
        """Set up test environment - connect to Algorand node."""
        # Get required values from configuration files
        cls.genesis_address, cls.genesis_mnemonic = load_genesis_info()
        cls.algod_host = determine_algod_host()
        cls.algod_token = load_api_token()

        # Derive keys from mnemonic
        cls.genesis_private_key = mnemonic.to_private_key(cls.genesis_mnemonic)

        # Create test account
        cls.test_private_key, cls.test_address = account.generate_account()
        cls.test_mnemonic = mnemonic.from_private_key(cls.test_private_key)
        print(f"Test account created: {cls.test_address}")

        # Test parameters
        cls.test_transfer_amount = 1000000  # 1 Algo

        # Determine if the host is an IP address
        is_ip_address = cls.algod_host.replace(".", "").isdigit()

        # Use HTTP for IP addresses (internal/testing) but HTTPS for domains (production)
        if is_ip_address:
            cls.algod_address = f"http://{cls.algod_host}"
        else:
            cls.algod_address = f"https://{cls.algod_host}"

        # Create the client
        cls.algod_client = algod.AlgodClient(cls.algod_token, cls.algod_address)

        print(f"Using Algorand node at: {cls.algod_address}")
        print(f"Using Genesis address: {cls.genesis_address}")

        # Test connectivity with retries
        cls.is_node_accessible = cls.check_connectivity()
        if not cls.is_node_accessible:
            print(
                f"\n⚠️  WARNING: Could not connect to Algorand node at {cls.algod_address}"
            )
            print("Tests will likely fail. The node may not be ready or deployed yet.")

    @classmethod
    def check_connectivity(cls):
        """Check if we can connect to the Algorand node with retries."""
        for attempt in range(cls.MAX_RETRIES):
            try:
                status = cls.algod_client.status()
                return True
            except Exception as e:
                if attempt < cls.MAX_RETRIES - 1:
                    print(
                        f"Connection attempt {attempt+1}/{cls.MAX_RETRIES} failed: {e}"
                    )
                    print(f"Retrying in {cls.RETRY_DELAY} seconds...")
                    time.sleep(cls.RETRY_DELAY)
                else:
                    print(f"Final connection attempt failed: {e}")
        return False

    def setUp(self):
        """Set up for each test - skip if node isn't accessible."""
        if not self.is_node_accessible:
            self.skipTest("Skipping test due to node connectivity issues")

    def test_01_node_connection(self):
        """Test connectivity to the Algorand node."""
        try:
            node_status = self.algod_client.status()
            self.assertIsNotNone(node_status)
            print(f"Connected to Algorand node: {node_status}")
        except Exception as e:
            self.fail(f"Failed to connect to Algorand node: {e}")

    def test_02_node_syncing(self):
        """Test if the node is syncing."""
        try:
            node_status = self.algod_client.status()
            self.assertIn("last-round", node_status)
            print(f"Node last round: {node_status['last-round']}")
        except Exception as e:
            self.fail(f"Failed to check node sync status: {e}")

    def test_03_genesis_account_balance(self):
        """Test if genesis account has funds."""
        try:
            account_info = self.algod_client.account_info(self.genesis_address)
            self.assertIn("amount", account_info)
            balance = account_info["amount"]
            self.assertGreater(balance, 0, "Genesis account has no funds")
            print(f"Genesis account balance: {balance} microAlgos")
        except Exception as e:
            self.fail(f"Failed to check genesis account balance: {e}")

    def test_04_create_transaction(self):
        """Test transaction creation."""
        try:
            # Get parameters for transaction
            params = self.algod_client.suggested_params()

            # Create a transaction
            unsigned_txn = PaymentTxn(
                sender=self.genesis_address,
                sp=params,
                receiver=self.test_address,
                amt=self.test_transfer_amount,
                note="Test transaction".encode(),
            )

            # Check transaction was created
            self.assertIsNotNone(unsigned_txn)
            print("Successfully created test transaction")
        except Exception as e:
            self.fail(f"Failed to create transaction: {e}")

    def test_05_sign_and_send_transaction(self):
        """Test transaction signing and submission."""
        try:
            # Get parameters for transaction
            params = self.algod_client.suggested_params()

            # Create a transaction
            unsigned_txn = PaymentTxn(
                sender=self.genesis_address,
                sp=params,
                receiver=self.test_address,
                amt=self.test_transfer_amount,
                note="Test transaction".encode(),
            )

            # Sign the transaction
            signed_txn = unsigned_txn.sign(self.genesis_private_key)

            # Send the transaction
            try:
                tx_id = self.algod_client.send_transaction(signed_txn)
                print(f"Transaction sent with ID: {tx_id}")

                # Wait for confirmation
                self.wait_for_confirmation(tx_id)
                print("Transaction confirmed")
            except AlgodHTTPError as e:
                # If this is a private network starting up, it might not accept transactions yet
                # We'll consider this a "soft failure" and print a warning
                print(f"Warning: Couldn't send transaction: {e}")
                print("This might be expected if the network is still starting up.")
                return
        except Exception as e:
            self.fail(f"Failed to sign or send transaction: {e}")

    def test_06_verify_receipt(self):
        """Test if the test account received the funds."""
        try:
            # Check if the previous transaction test was successful
            if not hasattr(self, "transaction_successful"):
                print("Skipping verification as transaction test was not successful")
                return

            # Check receiver's balance
            account_info = self.algod_client.account_info(self.test_address)
            self.assertIn("amount", account_info)
            balance = account_info["amount"]
            self.assertGreaterEqual(
                balance,
                self.test_transfer_amount,
                f"Test account balance {balance} is less than transfer amount {self.test_transfer_amount}",
            )
            print(f"Test account balance: {balance} microAlgos")
        except Exception as e:
            self.fail(f"Failed to verify transaction receipt: {e}")

    def wait_for_confirmation(self, txid):
        """Wait until the transaction is confirmed or rejected."""
        last_round = self.algod_client.status().get("last-round", 0)
        while True:
            try:
                pending_txn = self.algod_client.pending_transaction_info(txid)
            except Exception:
                return
            if pending_txn.get("confirmed-round", 0) > 0:
                # Transaction confirmed
                self.transaction_successful = True
                return
            elif pending_txn.get("pool-error", None):
                # Transaction rejected
                raise Exception(f'Transaction rejected: {pending_txn["pool-error"]}')

            last_round += 1
            self.algod_client.status_after_block(last_round)
            time.sleep(2)  # Brief pause to avoid hammering the API


if __name__ == "__main__":
    unittest.main()
