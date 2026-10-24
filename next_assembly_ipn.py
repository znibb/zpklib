#!/usr/bin/env python3
"""
Reserve the next available assembly IPN in InvenTree.

Finds the next free EA-NNNNN IPN, creates an (empty) assembly part with that
IPN under the electronic-assemblies category, and prints the IPN and a link to
the new part. Set the IPN as the PART_NUMBER text variable in the KiCad
project, then use update_assembly.py to upload the assembly information.

Usage:
  next_assembly_ipn.py

This script is stand-alone and can be run from any directory.
Connection details are read automatically from zpklib.kicad_httplib.
"""

import json
import re
import sys
from pathlib import Path

import requests

HTTPLIB_FILE = Path(__file__).parent / "zpklib.kicad_httplib"
CATEGORY_NAME = "electronic-assemblies"


def _read_httplib(path):
    with open(path) as f:
        data = json.load(f)
    source = data["source"]
    root_url = source["root_url"].rstrip("/")
    base = root_url.split("/plugin/")[0]
    return base, source["token"]


BASE_URL = None
AUTH_HEADERS = {}
HEADERS = {}


def api_get(path):
    r = requests.get(f"{BASE_URL}/{path}", headers=AUTH_HEADERS)
    r.raise_for_status()
    return r.json()


def api_post(path, data):
    r = requests.post(f"{BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def as_list(data):
    return data if isinstance(data, list) else data.get("results", [])


def find_category(name):
    cats = as_list(api_get("part/category/?limit=9999"))
    for cat in cats:
        if cat["name"] == name:
            return cat
    return None


def find_assembly_by_name(name, category_pk):
    parts = as_list(api_get(f"part/?category={category_pk}&assembly=true&limit=9999"))
    for part in parts:
        if part.get("name") == name:
            return part
    return None


def next_assembly_ipn():
    """Return the next available EA-NNNNN IPN."""
    pattern = re.compile(r"^EA-(\d{5})$")
    parts = as_list(api_get("part/?limit=9999"))
    max_serial = 0
    for part in parts:
        m = pattern.match(part.get("IPN") or "")
        if m:
            max_serial = max(max_serial, int(m.group(1)))
    return f"EA-{max_serial + 1:05d}"


def main():
    global BASE_URL, AUTH_HEADERS, HEADERS

    if len(sys.argv) > 1:
        print(f"Usage: {sys.argv[0]}", file=sys.stderr)
        sys.exit(1)

    base, token = _read_httplib(HTTPLIB_FILE)
    BASE_URL = f"{base}/api"
    AUTH_HEADERS = {"Authorization": f"Token {token}", "Accept": "application/json"}
    HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

    print(f"Looking up '{CATEGORY_NAME}' category...")
    category = find_category(CATEGORY_NAME)
    if not category:
        print(f"ERROR: Category '{CATEGORY_NAME}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"  Found: pk={category['pk']}")

    print("Resolving next IPN...")
    ipn = next_assembly_ipn()
    print(f"  Next IPN: {ipn}")

    name = ""
    while not name:
        name = input("\nAssembly name: ").strip()
    description = input("Description: ").strip()

    existing = find_assembly_by_name(name, category["pk"])
    if existing:
        print(
            f"\nWarning: an assembly named '{name}' already exists "
            f"(IPN={existing.get('IPN') or '(none)'}, pk={existing['pk']})."
        )

    print("\n--- Summary ---")
    print(f"  IPN:         {ipn}")
    print(f"  Name:        {name}")
    print(f"  Description: {description}")
    print(f"  Category:    {category['name']} (pk={category['pk']})")
    print()
    confirm = input("Create assembly? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    assembly = api_post("part/", {
        "name": name,
        "description": description,
        "category": category["pk"],
        "assembly": True,
        "active": True,
        "IPN": ipn,
    })

    print(f"\nCreated assembly pk={assembly['pk']}: {name}")
    print(f"IPN: {ipn}")
    print(f"URL: {base}/web/part/{assembly['pk']}")
    print(
        "\nSet PART_NUMBER to this IPN in the KiCad project "
        "(Project Setup -> Text Variables), then run update_assembly.py."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
