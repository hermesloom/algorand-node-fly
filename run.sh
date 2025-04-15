#!/bin/bash
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

log "Starting Algorand node and API server setup..."

# Activate Python virtual environment
source /algod/venv/bin/activate

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
  
  # Always generate a new algod token
  log "Generating new Algorand API token..."
  echo "$(cat /algod/data/admin.token 2>/dev/null || openssl rand -hex 32)" > /algod/data/algod.token
  chmod 600 /algod/data/algod.token

  cat > "$CONFIG_FILE" << EOF
{
  "Version": 12,
  "EndpointAddress": "127.0.0.1:8080",
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
  "APIEndpoint": "127.0.0.1:8080",
  "UseRelayAddrFromForwardedForHeader": true,
  "AdminAPIToken": "",
  "DisableTelemetry": true,
  "EnableAPIAuth": true,
  "BlockGeneration": true
}
EOF
  chmod 600 "$CONFIG_FILE"
fi

# Copy the server API script
log "Setting up the secure API server..."
cp /app/server_api.py /algod/server_api.py
chmod 700 /algod/server_api.py

# Start the Algorand node in the background
log "Starting Algorand node..."
algod -d /algod/data &
ALGOD_PID=$!

# Wait for the node to be ready
log "Waiting for Algorand node to start..."
sleep 5

# Start the API server in the background
log "Starting secure API server..."
gunicorn --bind 0.0.0.0:3000 --workers 4 --access-logfile - --error-logfile - "server_api:app" &
GUNICORN_PID=$!

# Wait for either process to exit
log "Both processes started. Waiting for one to exit..."
wait -n

# If either process exits, kill the other and exit
log "One process exited. Shutting down both..."
kill $ALGOD_PID $GUNICORN_PID 2>/dev/null || true
wait

log "Shutdown complete."
