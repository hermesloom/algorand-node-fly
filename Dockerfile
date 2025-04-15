FROM algorand/algod:latest

# Install system dependencies
RUN apt-get update && \
    apt-get install -y python3-pip python3-venv

# Set up Python environment
RUN python3 -m venv /algod/venv && \
    . /algod/venv/bin/activate && \
    pip install flask gunicorn algosdk flask-swagger-ui

# Create required directories
RUN mkdir -p /algod/data && \
    chmod 700 /algod/data

# The run.sh script will be executed when the container starts via fly.toml's cmd setting 
