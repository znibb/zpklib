#!/usr/bin/env bash

set -euo pipefail

# Patch the KiCad plugin serializer - see patch_serializer.py for details
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker cp "$SCRIPT_DIR/patch_serializer.py" inventree-server:/tmp/patch_serializer.py
docker exec inventree-server python3 /tmp/patch_serializer.py