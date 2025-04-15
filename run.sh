#!/bin/bash
# Strict error handling
set -euo pipefail

# Log with timestamp
log() {
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"
}

# Exit with error
error_exit() {
  log "ERROR: $*"
  exit 1
}

log "Starting Algorand node initialization..."

# Create the data directory with secure permissions
mkdir -p /algod/data
chmod 700 /algod/data

# Verify genesis file exists
if [ ! -f "/app/genesis.json" ]; then
  error_exit "Genesis file not found at /app/genesis.json"
fi

# Copy genesis file
log "Copying genesis file..."
cp /app/genesis.json /algod/data/genesis.json
chmod 600 /algod/data/genesis.json

# Create config file with correct network settings
CONFIG_FILE="/algod/data/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
  log "Creating config.json with correct network settings..."
  
  # Check if we have a token file
  if [ -f "/algod/data/algod.token" ]; then
    log "Using provided API token for authentication"
  else
    # If no token file found, create one with the same content as in admin.token
    log "No API token file found, creating one..."
    echo "$(cat /algod/data/admin.token)" > /algod/data/algod.token
    chmod 600 /algod/data/algod.token
  fi

  cat > "$CONFIG_FILE" << EOF
{
  "Version": 12,
  "EndpointAddress": "0.0.0.0:8080",
  "DNSBootstrapID": "",
  "EnableDeveloperAPI": true,
  "EnableProfiler": false,
  "EnableLedgerService": false,
  "EnableBlockService": false,
  "EnableGossipBlockService": true,
  "EnableAccountService": false,
  "CatchpointInterval": 1000,
  "CatchpointFileHistoryLength": 365,
  "NetAddress": "0.0.0.0:4160",
  "APIEndpoint": "0.0.0.0:8080",
  "UseRelayAddrFromForwardedForHeader": true,
  "AdminAPIToken": "",
  "DisableTelemetry": true,
  "EnableAPIAuth": true
}
EOF
  chmod 600 "$CONFIG_FILE"
fi

# Initialize the node if not already initialized
if [ ! -d /algod/data/ledger ]; then
  log "Initializing Algorand node..."
  
  # Initialize from the genesis file
  # The fee sink is already included in the genesis file
  algod -d /algod/data -g /algod/data/genesis.json || error_exit "Failed to initialize Algorand node"
fi

# Log environment information for debugging
log "Network configuration:"
echo "---------------------"
ip addr show
echo "---------------------"
netstat -tulpn 2>/dev/null | grep LISTEN || echo "netstat command not available"
echo "---------------------"

# Check if algod is already running and kill it if needed
if pgrep -x "algod" > /dev/null; then
  log "Algorand node is already running. Stopping it..."
  pkill -x "algod" || error_exit "Failed to stop existing Algorand node"
  sleep 2
fi

# Start the node with proper parameters
log "Starting Algorand node..."
exec algod -d /algod/data
