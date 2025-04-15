#!/usr/bin/env python3

import os
import json
import time
from flask import Flask, request, jsonify
from algosdk import account, mnemonic, encoding
from algosdk.v2client import algod
from algosdk.transaction import PaymentTxn

app = Flask(__name__)

# Rate limiting settings
REQUEST_LIMIT = 100
RATE_WINDOW = 3600  # 1 hour in seconds
request_counts = {}

# Algorand client setup
ALGOD_TOKEN = ""
try:
    with open("/algod/data/algod.token", "r") as f:
        ALGOD_TOKEN = f.read().strip()
except:
    # Fall back to empty token if file not found
    pass

ALGOD_ADDRESS = "http://localhost:8080"
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


def rate_limit(client_ip):
    """Basic rate limiting to prevent abuse."""
    current_time = int(time.time())

    # Clean up old entries
    for ip in list(request_counts.keys()):
        if current_time - request_counts[ip]["timestamp"] > RATE_WINDOW:
            del request_counts[ip]

    # Check/update the count for this IP
    if client_ip in request_counts:
        if current_time - request_counts[client_ip]["timestamp"] > RATE_WINDOW:
            # Reset if window has passed
            request_counts[client_ip] = {"count": 1, "timestamp": current_time}
        else:
            # Increment count
            request_counts[client_ip]["count"] += 1
    else:
        # First request from this IP
        request_counts[client_ip] = {"count": 1, "timestamp": current_time}

    # Return True if rate limit exceeded
    return request_counts[client_ip]["count"] > REQUEST_LIMIT


from algosdk import mnemonic, account


def validate_mnemonic(mnemonic_phrase, address=None):
    """Validate that the mnemonic is valid and corresponds to the address if provided."""
    try:
        # Try to convert mnemonic to private key (will raise if invalid)
        private_key = mnemonic.to_private_key(mnemonic_phrase)

        # If address is provided, check if mnemonic resolves to it
        if address:
            derived_address = account.address_from_private_key(private_key)
            if derived_address != address:
                print(f"Invalid mnemonic for address: {derived_address} != {address}")
            return derived_address == address

        return True
    except Exception as e:
        print(f"Error validating mnemonic: {e}")
        return False


@app.route("/api/account/new", methods=["POST"])
def create_account():
    """Create a new Algorand account."""
    # Basic rate limiting
    client_ip = request.remote_addr
    if rate_limit(client_ip):
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        # Generate a new account
        private_key, address = account.generate_account()
        mnemo = mnemonic.from_private_key(private_key)

        return jsonify({"address": address, "mnemonic": mnemo})
    except Exception as e:
        app.logger.error(f"Error creating account: {e}")
        return jsonify({"error": "Failed to create account"}), 500


@app.route("/api/account/balance", methods=["POST"])
def get_balance():
    """Get the balance of an account with mnemonic authentication."""
    # Basic rate limiting
    client_ip = request.remote_addr
    if rate_limit(client_ip):
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        data = request.get_json()
        address = data.get("address")
        mnemo = data.get("mnemonic")

        # Validate inputs
        if not address or not mnemo:
            return jsonify({"error": "Missing address or mnemonic"}), 400

        # Validate mnemonic corresponds to address
        if not validate_mnemonic(mnemo, address):
            return jsonify({"error": "Invalid mnemonic for address"}), 403

        # Get account info
        account_info = algod_client.account_info(address)

        return jsonify(
            {
                "address": address,
                "balance": account_info.get("amount", 0),
                "status": (
                    "active" if account_info.get("status") == "Online" else "offline"
                ),
            }
        )
    except Exception as e:
        app.logger.error(f"Error getting balance: {e}")
        return jsonify({"error": "Failed to retrieve balance"}), 500


@app.route("/api/transfer", methods=["POST"])
def transfer_funds():
    """Transfer funds from one account to another with mnemonic authentication."""
    # Basic rate limiting
    client_ip = request.remote_addr
    if rate_limit(client_ip):
        return jsonify({"error": "Rate limit exceeded"}), 429

    try:
        data = request.get_json()
        sender_address = data.get("from")
        sender_mnemonic = data.get("mnemonic")
        receiver_address = data.get("to")
        amount = data.get("amount")
        note = data.get("note", "")

        # Validate inputs
        if not all([sender_address, sender_mnemonic, receiver_address, amount]):
            return jsonify({"error": "Missing required fields"}), 400

        try:
            amount = int(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError:
            return jsonify({"error": "Invalid amount"}), 400

        # Validate mnemonic corresponds to sender address
        if not validate_mnemonic(sender_mnemonic, sender_address):
            return jsonify({"error": "Invalid mnemonic for sender address"}), 403

        # Convert mnemonic to private key
        sender_private_key = mnemonic.to_private_key(sender_mnemonic)

        # Get transaction parameters
        params = algod_client.suggested_params()

        # Create and sign transaction
        unsigned_txn = PaymentTxn(
            sender=sender_address,
            sp=params,
            receiver=receiver_address,
            amt=amount,
            note=note.encode() if note else None,
        )

        signed_txn = unsigned_txn.sign(sender_private_key)

        # Submit transaction
        tx_id = algod_client.send_transaction(signed_txn)

        # Wait for confirmation
        try:
            wait_for_confirmation(algod_client, tx_id)
            return jsonify({"tx_id": tx_id, "status": "confirmed"})
        except Exception as e:
            return jsonify({"tx_id": tx_id, "status": "pending", "error": str(e)}), 202

    except Exception as e:
        app.logger.error(f"Error transferring funds: {e}")
        return jsonify({"error": f"Failed to transfer funds: {str(e)}"}), 500


def wait_for_confirmation(client, txid, timeout=10):
    """Wait until the transaction is confirmed or rejected, or until timeout."""
    start_round = client.status()["last-round"] + 1
    current_round = start_round

    while current_round < start_round + timeout:
        try:
            pending_txn = client.pending_transaction_info(txid)
        except Exception:
            return

        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        elif pending_txn.get("pool-error"):
            raise Exception(f"Transaction failed: {pending_txn['pool-error']}")

        client.status_after_block(current_round)
        current_round += 1

    raise Exception(f"Transaction not confirmed after {timeout} rounds")


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for the API."""
    try:
        # Check if we can connect to the Algorand node
        status = algod_client.status()
        return jsonify(
            {
                "status": "healthy",
                "node_status": {
                    "last_round": status.get("last-round"),
                    "time_since_last_round": status.get("time-since-last-round"),
                },
            }
        )
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503


# Log when API is initialized
app.logger.info("Algorand minimal REST API initialized")

if __name__ == "__main__":
    # Run the API server on all interfaces, port 3000
    print("Starting Algorand minimal REST API server on port 3000...")
    app.run(host="0.0.0.0", port=3000)
