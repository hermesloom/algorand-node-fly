#!/bin/bash
set -e

# Check if the app exists before trying to destroy it
if fly apps list 2>/dev/null | grep -q "algorand-node"; then
    echo "Found existing algorand-node app, destroying it..."
    fly apps destroy algorand-node --yes
else
    echo "No existing algorand-node app found, will create new one."
fi

python3 -m venv venv
source venv/bin/activate
pip install algosdk requests

# Create the generated directory
mkdir -p generated

# Generate the genesis file with example SDR value
python3 local/create-genesis-json.py 100 USD

# Generate API token
python3 local/create-api-key.py

echo "Setup complete! Genesis file and API token created in the 'generated' directory."

fly launch

local/test.sh
