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

python3 local/create-genesis-json.py "$1" "$2"

echo "Setup complete! Genesis file created in the 'generated' directory."

fly launch

local/test.sh
