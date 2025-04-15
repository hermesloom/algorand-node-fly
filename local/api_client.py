#!/usr/bin/env python3

import requests
import json
import argparse
import os


class AlgorandAPIClient:
    def __init__(self, api_url):
        # If api_url is just a hostname or IP address (no scheme)
        if not api_url.startswith(("http://", "https://")):
            # Check if it's an IP address
            is_ip_address = all(c.isdigit() or c == "." for c in api_url)
            protocol = "http" if is_ip_address else "https"
            api_url = f"{protocol}://{api_url}"

        self.api_url = api_url

    def health_check(self):
        """Check if the API is healthy."""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            if response.status_code != 200:
                print(f"Health check failed with status code: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error checking health: {e}")
            return False

    def create_account(self):
        """Create a new Algorand account."""
        endpoint = "/api/account/new"

        response = requests.post(f"{self.api_url}{endpoint}", json={})

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error creating account: {response.text}")

    def get_balance(self, address, mnemonic):
        """Get the balance of an account."""
        endpoint = "/api/account/balance"
        data = {"address": address, "mnemonic": mnemonic}

        response = requests.post(f"{self.api_url}{endpoint}", json=data)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error getting balance: {response.text}")

    def transfer(self, from_address, from_mnemonic, to_address, amount, note=""):
        """Transfer funds between accounts."""
        endpoint = "/api/transfer"
        data = {
            "from": from_address,
            "mnemonic": from_mnemonic,
            "to": to_address,
            "amount": amount,
            "note": note,
        }

        response = requests.post(f"{self.api_url}{endpoint}", json=data)

        if response.status_code in (200, 202):
            return response.json()
        else:
            raise Exception(f"Error transferring funds: {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Interact with the Algorand API")

    # API connection parameters
    parser.add_argument("--api-url", default=None, help="API server URL")

    # Commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Create account command
    create_parser = subparsers.add_parser("create-account", help="Create a new account")

    # Get balance command
    balance_parser = subparsers.add_parser("balance", help="Check account balance")
    balance_parser.add_argument("--address", required=True, help="Account address")
    balance_parser.add_argument("--mnemonic", required=True, help="Account mnemonic")

    # Transfer command
    transfer_parser = subparsers.add_parser("transfer", help="Transfer funds")
    transfer_parser.add_argument(
        "--from", dest="from_address", required=True, help="Sender address"
    )
    transfer_parser.add_argument(
        "--from-mnemonic", required=True, help="Sender mnemonic"
    )
    transfer_parser.add_argument("--to", required=True, help="Receiver address")
    transfer_parser.add_argument(
        "--amount", type=int, required=True, help="Amount in picoXDRs"
    )
    transfer_parser.add_argument("--note", default="", help="Optional transaction note")

    args = parser.parse_args()

    # Determine API URL
    if not args.api_url:
        # Try to determine the host
        try:
            from local.test import determine_api_host

            host = determine_api_host()
            args.api_url = host  # Just use the host, the class will add protocol
        except:
            args.api_url = "localhost:3000"

    # Create client
    client = AlgorandAPIClient(args.api_url)

    # Execute command
    if args.command == "create-account":
        result = client.create_account()
        print(json.dumps(result, indent=2))

    elif args.command == "balance":
        result = client.get_balance(args.address, args.mnemonic)
        print(json.dumps(result, indent=2))

    elif args.command == "transfer":
        result = client.transfer(
            args.from_address, args.from_mnemonic, args.to, args.amount, args.note
        )
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
