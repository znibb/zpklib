#!/usr/bin/env bash

LIB_FILE_NAME=zpklib

set -euo pipefail

read -r -p "Enter the domain where your Inventree instance is hosted: " url
read -r -p "Enter your Inventree API token: " token

cat > $LIB_FILE_NAME.kicad_httplib <<EOF
{
    "meta": {
        "version": 1.0
    },
    "name": "KiCad HTTP Library",
    "description": "Inventree KiCad library",
    "source": {
        "type": "REST_API",
        "api_version": "v1",
        "root_url": "https://${url}/plugin/kicad-library-plugin",
        "token": "${token}",
        "timeout_parts_seconds": 60,
        "timeout_categories_seconds": 6000
    }
}
EOF

echo "Written to $LIB_FILE_NAME.kicad_httplib
