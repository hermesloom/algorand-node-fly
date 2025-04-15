#!/usr/bin/env python3

import json
import os
import sys
import argparse
import requests
import time
from io import StringIO
import csv
from decimal import Decimal, getcontext
from algosdk import account, mnemonic
import datetime

# Set decimal precision
getcontext().prec = 28

# Currency name to ISO code mapping (for SDRs per Currency unit section)
CURRENCY_TO_ISO = {
    "Chinese yuan": "CNY",
    "Euro": "EUR",
    "Japanese yen": "JPY",
    "U.K. pound": "GBP",
    "U.S. dollar": "USD",
    "Algerian dinar": "DZD",
    "Australian dollar": "AUD",
    "Botswana pula": "BWP",
    "Brazilian real": "BRL",
    "Brunei dollar": "BND",
    "Canadian dollar": "CAD",
    "Chilean peso": "CLP",
    "Czech koruna": "CZK",
    "Danish krone": "DKK",
    "Indian rupee": "INR",
    "Israeli New Shekel": "ILS",
    "Korean won": "KRW",
    "Kuwaiti dinar": "KWD",
    "Malaysian ringgit": "MYR",
    "Mauritian rupee": "MUR",
    "Mexican peso": "MXN",
    "New Zealand dollar": "NZD",
    "Norwegian krone": "NOK",
    "Omani rial": "OMR",
    "Peruvian sol": "PEN",
    "Philippine peso": "PHP",
    "Polish zloty": "PLN",
    "Qatari riyal": "QAR",
    "Russian ruble": "RUB",
    "Saudi Arabian riyal": "SAR",
    "Singapore dollar": "SGD",
    "South African rand": "ZAR",
    "Swedish krona": "SEK",
    "Swiss franc": "CHF",
    "Thai baht": "THB",
    "Trinidadian dollar": "TTD",
    "U.A.E. dirham": "AED",
    "Uruguayan peso": "UYU",
}

# Reverse mapping for looking up currency names from ISO codes
ISO_TO_CURRENCY = {v: k for k, v in CURRENCY_TO_ISO.items()}


def download_and_parse_imf_data():
    """Download IMF exchange rate data and parse it."""
    url = "https://www.imf.org/external/np/fin/data/rms_five.aspx?tsvflag=Y"

    try:
        response = requests.get(url)
        response.raise_for_status()

        # Parse the TSV data
        data = StringIO(response.text)
        reader = csv.reader(data, delimiter="\t")

        # Skip headers until we reach the currency rates section
        in_sdrs_per_currency_unit = False
        exchange_rates = {}

        for row in reader:
            if not row:
                continue

            if row[0] == "SDRs per Currency unit (2)":
                in_sdrs_per_currency_unit = True
                continue

            if in_sdrs_per_currency_unit:
                if row[0] == "Currency units per SDR(3)":
                    break

                if row[0] == "Currency":
                    continue

                # Extract the most recent exchange rate (first date column with data)
                currency_name = row[0]
                rate = None

                for cell in row[1:]:
                    if cell.strip() and cell != "n.a.":
                        try:
                            rate = Decimal(cell)
                            break
                        except:
                            continue

                if rate is not None and currency_name in CURRENCY_TO_ISO:
                    exchange_rates[CURRENCY_TO_ISO[currency_name]] = rate

        return exchange_rates
    except requests.RequestException as e:
        print(f"Error downloading IMF data: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing IMF data: {e}")
        sys.exit(1)


def convert_to_sdrs(amount, currency_code, exchange_rates):
    """Convert a given amount in a specific currency to SDRs."""
    if currency_code not in exchange_rates:
        valid_currencies = ", ".join(sorted(exchange_rates.keys()))
        print(f"Error: Currency code '{currency_code}' not found in IMF data.")
        print(f"Valid currency codes: {valid_currencies}")
        sys.exit(1)

    # Convert the amount to Decimal
    amount_decimal = Decimal(str(amount))

    # SDRs = Amount in currency * SDRs per unit of currency
    sdrs = amount_decimal * exchange_rates[currency_code]
    return sdrs


def create_genesis_json(amount_xdr, currency):
    """Create a genesis.json file for a new Algorand network with dedicated accounts."""

    # Generate accounts
    genesis_private_key, genesis_address = account.generate_account()
    genesis_mnemo = mnemonic.from_private_key(genesis_private_key)

    rewards_private_key, rewards_address = account.generate_account()
    rewards_mnemo = mnemonic.from_private_key(rewards_private_key)

    fee_sink_private_key, fee_sink_address = account.generate_account()
    fee_sink_mnemo = mnemonic.from_private_key(fee_sink_private_key)

    # Store accounts in genesis_secrets.json
    genesis_info = {
        "genesis": {"address": genesis_address, "mnemonic": genesis_mnemo},
        "rewards": {"address": rewards_address, "mnemonic": rewards_mnemo},
        "fee_sink": {"address": fee_sink_address, "mnemonic": fee_sink_mnemo},
    }

    # Convert XDR amount to picoXDRs (1 XDR = 1,000,000,000,000 picoXDRs)
    amount_picoxdr = int(float(amount_xdr) * 1_000_000_000_000)
    print(
        f"Initializing genesis account with {amount_xdr} XDR = {amount_picoxdr} picoXDRs"
    )

    # Create genesis file structure with an integer timestamp
    genesis_time = int(time.time())

    genesis_json = {
        "alloc": [
            {
                "addr": genesis_address,
                "state": {
                    "algo": amount_picoxdr,
                    "onl": 1,
                },
            }
        ],
        "fees": fee_sink_address,
        "network": "solarfunk",
        "proto": "future",
        "rwd": rewards_address,
        "timestamp": genesis_time,
    }

    # Ensure output directory exists
    os.makedirs("generated", exist_ok=True)

    # Write genesis.json
    with open("generated/genesis.json", "w") as f:
        json.dump(genesis_json, f, indent=2)

    # Write genesis_secrets.json with all account details
    with open("generated/genesis_secrets.json", "w") as f:
        json.dump(genesis_info, f, indent=2)

    print(f"Genesis files created:")
    print(f"  - generated/genesis.json")
    print(f"  - generated/genesis_secrets.json")
    print(f"\nGenesis account: {genesis_address}")
    print(f"Rewards account: {rewards_address}")
    print(f"Fee sink account: {fee_sink_address}")


def main():
    parser = argparse.ArgumentParser(
        description="Create a genesis.json file for a new Algorand network"
    )
    parser.add_argument(
        "amount", help="Amount of XDR to initialize in the genesis account"
    )
    parser.add_argument("currency", help="Currency code for reference (e.g., EUR, USD)")

    args = parser.parse_args()

    create_genesis_json(args.amount, args.currency)


if __name__ == "__main__":
    main()
