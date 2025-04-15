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


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Create a genesis.json file with a specified currency amount."
    )
    parser.add_argument(
        "amount", type=float, help="The amount in the specified currency"
    )
    parser.add_argument("currency", type=str, help="Three-letter ISO currency code")

    args = parser.parse_args()
    amount = args.amount
    currency_code = args.currency.upper()

    # Download and parse IMF data
    exchange_rates = download_and_parse_imf_data()

    # Convert amount to SDRs
    sdrs = convert_to_sdrs(amount, currency_code, exchange_rates)

    # Calculate microalgos (SDRs * 1,000,000,000,000) as an integer
    # Use Decimal arithmetic for precision
    microalgos = int(sdrs * Decimal("1000000000000"))

    # Generate Algorand account
    private_key, address = account.generate_account()
    mnemo = mnemonic.from_private_key(private_key)
    print("Genesis address:", address)
    print("Genesis mnemonic:", mnemo)

    # Show conversion information
    print(f"Converting {amount} {currency_code} to {sdrs:.6f} SDRs")
    print(f"Setting initial balance to {microalgos} microAlgos")

    # Genesis file template
    genesis_template = {
        "alloc": [
            {
                "addr": address,  # Use the generated address
                "state": {"algo": microalgos, "onl": 0},
            }
        ],
        "network": "solarfunk",
        "proto": "future",
        "rwd": address,
        "fees": address,
        "timestamp": int(time.time()),  # Use current timestamp
    }

    # Create the generated directory if it doesn't exist
    generated_dir = "generated"
    os.makedirs(generated_dir, exist_ok=True)

    # Write the genesis file
    with open("generated/genesis.json", "w") as f:
        json.dump(genesis_template, f, indent=2)

    # Store genesis account info in a separate file
    genesis_info = {"address": address, "mnemonic": mnemo}

    with open("generated/genesis_info.json", "w") as f:
        json.dump(genesis_info, f, indent=2)

    print(f"Genesis file created with account {address} in generated/genesis.json")
    print(f"Genesis account information stored in generated/genesis_info.json")


if __name__ == "__main__":
    main()
