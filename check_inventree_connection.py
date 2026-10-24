#!/usr/bin/env python3
"""
Verify connectivity to the InvenTree API.

Reads connection details from zpklib.kicad_httplib and performs a simple
API call to confirm the server is reachable and the token is valid.
"""

import json
import sys
from pathlib import Path

import requests

HTTPLIB_FILE = Path(__file__).parent / "zpklib.kicad_httplib"


def main():
    with open(HTTPLIB_FILE) as f:
        data = json.load(f)
    source = data["source"]
    root_url = source["root_url"].rstrip("/")
    base = root_url.split("/plugin/")[0]
    token = source["token"]

    url = f"{base}/api/"
    print(f"Connecting to {base} ...")

    try:
        r = requests.get(url, headers={"Authorization": f"Token {token}", "Accept": "application/json"}, timeout=10)
    except requests.ConnectionError as e:
        print(f"ERROR: could not reach server: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print("ERROR: request timed out", file=sys.stderr)
        sys.exit(1)

    if r.status_code == 401:
        print("ERROR: authentication failed — token is invalid or expired", file=sys.stderr)
        sys.exit(1)

    if not r.ok:
        print(f"ERROR: unexpected response {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)

    info = r.json()
    version = info.get("version", "unknown")
    print(f"OK — connected, InvenTree version {version}.")


if __name__ == "__main__":
    main()
