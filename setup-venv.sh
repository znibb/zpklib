#!/usr/bin/env bash

# Creates a virtualenv if none exists and installs the required python modules

set -euo pipefail

VENV_DIR="$(dirname "$0")/.venv"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$(dirname "$0")/requirements.txt"

echo "Venv ready. Activate with: source $VENV_DIR/bin/activate"
