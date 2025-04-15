#!/usr/bin/env python3

import os
import secrets
import string
import json


def generate_api_key(length=64):
    """Generate a secure API key of specified length."""
    alphabet = string.ascii_letters + string.digits
    api_key = "".join(secrets.choice(alphabet) for _ in range(length))
    return api_key


def main():
    # Create the generated directory if it doesn't exist
    generated_dir = "generated"
    os.makedirs(generated_dir, exist_ok=True)

    # Generate a secure API key
    api_key = generate_api_key()

    # Write the API key to the token file
    token_file = os.path.join(generated_dir, "algod.token")
    with open(token_file, "w") as f:
        f.write(api_key)

    # Set appropriate permissions (readable only by owner)
    os.chmod(token_file, 0o600)

    print(f"API token generated and saved to {token_file}")
    print(f"Token: {api_key}")
    print("Keep this token secure - it provides access to your Algorand node API.")


if __name__ == "__main__":
    main()
