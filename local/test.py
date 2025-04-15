#!/usr/bin/env python3

import unittest
import json
import os
import time
import requests
import subprocess
import re
import socket
import sys
from api_client import AlgorandAPIClient


def determine_api_host():
    """Determine the API host using fly CLI and config."""
    # Get app name from fly.toml
    try:
        with open("fly.toml", "r") as f:
            for line in f:
                if line.startswith("app = "):
                    app_name = line.split("=")[1].strip().strip("'\"")
                    break
    except:
        app_name = "algorand-node"  # Default fallback

    print(f"Using app name: {app_name}")

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


def load_genesis_secrets():
    """Load genesis account information from generated file."""
    genesis_secrets_file = "generated/genesis_secrets.json"

    if not os.path.exists(genesis_secrets_file):
        print(f"ERROR: Genesis information file not found: {genesis_secrets_file}")
        print("Please run setup.sh first to generate the genesis file.")
        sys.exit(1)

    try:
        with open(genesis_secrets_file, "r") as f:
            genesis_data = json.load(f)

        # Get main genesis account info
        genesis_info = genesis_data.get("genesis", {})
        address = genesis_info.get("address")
        mnemo = genesis_info.get("mnemonic")

        if not address or not mnemo:
            print(f"ERROR: Missing address or mnemonic in {genesis_secrets_file}")
            sys.exit(1)

        return address, mnemo

    except Exception as e:
        print(f"ERROR loading genesis information: {e}")
        sys.exit(1)


class AlgorandAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test environment - connect to the API and ensure it's healthy."""
        # Get required values from configuration files
        cls.genesis_address, cls.genesis_mnemonic = load_genesis_secrets()

        cls.api_host = determine_api_host()

        # Test parameters
        cls.test_transfer_amount = 1000000  # 1 picoXDR = 1 microAlgo

        # Create API client
        cls.api_client = AlgorandAPIClient(cls.api_host)

        print(f"Using API at: {cls.api_client.api_url}")
        print(f"Using Genesis address: {cls.genesis_address}")

        # Wait for API to be healthy before running tests
        cls.wait_for_api_health()

    @classmethod
    def wait_for_api_health(cls):
        """Wait for the API to become healthy with retries."""
        MAX_RETRY_ATTEMPTS = 15  # More retries for initial setup
        RETRY_DELAY = 5  # seconds

        print(f"Waiting for API to be healthy (max {MAX_RETRY_ATTEMPTS} attempts)...")

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                if cls.api_client.health_check():
                    print(
                        f"✅ API is healthy! (attempt {attempt+1}/{MAX_RETRY_ATTEMPTS})"
                    )
                    return
                else:
                    print(
                        f"❌ API unhealthy on attempt {attempt+1}/{MAX_RETRY_ATTEMPTS}"
                    )
            except Exception as e:
                print(
                    f"❌ Connection error on attempt {attempt+1}/{MAX_RETRY_ATTEMPTS}: {e}"
                )

            # Last attempt - don't sleep
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                print(f"Waiting {RETRY_DELAY} seconds before next health check...")
                time.sleep(RETRY_DELAY)

        # If we get here, we couldn't connect after all retries
        print("\n⚠️  WARNING: Could not verify API health after multiple attempts")
        print("Tests will proceed anyway, but may fail if the API is not ready.")
        print("\nTROUBLESHOOTING STEPS:")
        print("1. Check if the Fly.io app is running with 'fly status'")
        print("2. Check server logs with 'fly logs'")
        print("3. Make sure the server is properly configured")

    def create_test_account(self):
        """Helper to create a test account for any test that needs one."""
        # Create a new account
        account_info = self.api_client.create_account()

        # Validate the response
        self.assertIn("address", account_info)
        self.assertIn("mnemonic", account_info)
        self.assertTrue(len(account_info["address"]) > 30)
        self.assertTrue(len(account_info["mnemonic"].split()) == 25)

        return account_info

    def test_01_health_check(self):
        """Test the health check endpoint."""
        healthy = self.api_client.health_check()
        self.assertTrue(healthy, "API health check failed")

    def test_02_create_account(self):
        """Test account creation."""
        try:
            # Create a test account and verify it
            account_info = self.create_test_account()
            self.assertIsNotNone(account_info, "Should create a valid account")
        except Exception as e:
            self.fail(f"Failed to create account: {e}")

    def test_03_check_genesis_balance(self):
        """Test if genesis account has funds."""
        try:
            account_info = self.api_client.get_balance(
                self.genesis_address, self.genesis_mnemonic
            )

            self.assertIn("balance", account_info)
            balance = account_info["balance"]
            self.assertGreater(balance, 0, "Genesis account has no funds")

            print(f"Genesis account balance: {balance} picoXDRs")
        except Exception as e:
            self.fail(f"Failed to check genesis account balance: {e}")

    def test_04_transfer_funds(self):
        """Test transferring funds from genesis to a new test account."""
        try:
            # Create a test account to transfer funds to
            test_account = self.create_test_account()

            # Transfer funds from genesis to test account
            result = self.api_client.transfer(
                self.genesis_address,
                self.genesis_mnemonic,
                test_account["address"],
                self.test_transfer_amount,
                "Test transfer",
            )

            # Check result
            self.assertIn("tx_id", result)
            self.assertIn("status", result)
            tx_id = result["tx_id"]

            print(f"Transfer initiated with transaction ID: {tx_id}")

            # If status is pending, wait briefly for confirmation
            if result["status"] == "pending":
                print("Transaction pending, waiting 5 seconds for confirmation...")
                time.sleep(5)

            # Verify the balance was received by checking the test account
            account_info = self.api_client.get_balance(
                test_account["address"], test_account["mnemonic"]
            )

            self.assertIn("balance", account_info)
            balance = account_info["balance"]

            # The test account should have the transferred amount (or potentially more)
            self.assertGreaterEqual(
                balance,
                self.test_transfer_amount,
                f"Test account balance {balance} is less than transfer amount {self.test_transfer_amount}",
            )

            print(f"Test account received {balance} picoXDRs")

        except Exception as e:
            self.fail(f"Failed to transfer funds and verify: {e}")

    def test_05_multiple_accounts(self):
        """Test creating multiple accounts and transferring between them."""
        try:
            # Create two test accounts
            account1 = self.create_test_account()
            account2 = self.create_test_account()

            # Fund account1 from genesis
            fund_result = self.api_client.transfer(
                self.genesis_address,
                self.genesis_mnemonic,
                account1["address"],
                self.test_transfer_amount * 2,  # Double for transfer between accounts
                "Fund for multi-account test",
            )

            # Wait for confirmation
            if fund_result["status"] == "pending":
                print("Funding transaction pending, waiting for confirmation...")
                time.sleep(5)

            # Transfer from account1 to account2
            transfer_amount = self.test_transfer_amount
            transfer_result = self.api_client.transfer(
                account1["address"],
                account1["mnemonic"],
                account2["address"],
                transfer_amount,
                "Transfer between test accounts",
            )

            # Wait for confirmation
            if transfer_result["status"] == "pending":
                print("Transfer transaction pending, waiting for confirmation...")
                time.sleep(5)

            # Verify account2 received the funds
            account2_info = self.api_client.get_balance(
                account2["address"], account2["mnemonic"]
            )

            self.assertGreaterEqual(
                account2_info["balance"],
                transfer_amount,
                "Account2 should have received the transferred funds",
            )

            print(f"Account2 received {account2_info['balance']} picoXDRs")

        except Exception as e:
            self.fail(f"Failed in multiple account test: {e}")


if __name__ == "__main__":
    unittest.main()
