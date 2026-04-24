#!/usr/bin/env python3
"""
Create an assembly part in InvenTree from a KiCad BOM CSV file.

Reads a _BOM_Generic.csv, looks up each component by IPN, creates a new
assembly part under the electronic-assemblies category, and populates its
Bill of Materials. DNP rows are excluded.

Usage:
  create_assembly.py <bom_csv>

Connection details are read automatically from zpklib.kicad_httplib.
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

HTTPLIB_FILE = Path(__file__).parent / "zpklib.kicad_httplib"


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


def api_patch(path, data):
    r = requests.patch(f"{BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def sync_bom_items(assembly_pk, new_rows):
    """Diff existing BOM against new_rows and apply only the necessary changes.

    new_rows: list of {"part_pk", "qty", "refs", "ipn"}
    Returns (added, removed, updated) counts.
    """
    existing = {item["sub_part"]: item for item in as_list(api_get(f"bom/?part={assembly_pk}&limit=9999"))}
    incoming = {row["part_pk"]: row for row in new_rows}

    to_remove = [item for sub_pk, item in existing.items() if sub_pk not in incoming]
    to_add    = [row for sub_pk, row in incoming.items() if sub_pk not in existing]
    to_update = [row for sub_pk, row in incoming.items()
                 if sub_pk in existing
                 and (existing[sub_pk]["quantity"] != str(row["qty"])
                      or existing[sub_pk].get("reference", "") != row["refs"])]

    for item in to_remove:
        r = requests.delete(f"{BASE_URL}/bom/{item['pk']}/", headers=HEADERS)
        if not r.ok:
            print(f"ERROR deleting BOM item {item['pk']}: {r.status_code}", file=sys.stderr)
            r.raise_for_status()
        print(f"  Removed {item['sub_part_detail']['IPN'] if 'sub_part_detail' in item else item['sub_part']}")

    for row in to_add:
        api_post("bom/", {
            "part": assembly_pk,
            "sub_part": row["part_pk"],
            "quantity": row["qty"],
            "reference": row["refs"],
        })
        print(f"  Added   {row['ipn']}  x{row['qty']}  ({row['refs']})")

    for row in to_update:
        item_pk = existing[row["part_pk"]]["pk"]
        api_patch(f"bom/{item_pk}/", {"quantity": row["qty"], "reference": row["refs"]})
        print(f"  Updated {row['ipn']}  x{row['qty']}  ({row['refs']})")

    return len(to_add), len(to_remove), len(to_update)


def find_part_by_ipn(ipn):
    parts = as_list(api_get(f"part/?IPN={ipn}&limit=10"))
    for part in parts:
        if part.get("IPN") == ipn:
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

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <bom_csv>", file=sys.stderr)
        sys.exit(1)

    bom_path = Path(sys.argv[1])
    if not bom_path.exists():
        print(f"File not found: {bom_path}", file=sys.stderr)
        sys.exit(1)

    base, token = _read_httplib(HTTPLIB_FILE)
    BASE_URL = f"{base}/api"
    AUTH_HEADERS = {"Authorization": f"Token {token}", "Accept": "application/json"}
    HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Read BOM
    # ------------------------------------------------------------------
    df = pd.read_csv(bom_path, sep=",", skipinitialspace=True)
    df_populated = df[df["DNP"].isna() | (df["DNP"] == "")]
    print(f"BOM: {len(df_populated)} populated rows ({len(df) - len(df_populated)} DNP excluded)")

    # ------------------------------------------------------------------
    # Collect assembly metadata
    # ------------------------------------------------------------------
    stem = bom_path.name.removesuffix("_BOM_Generic.csv")
    m = re.match(r"^(.+?)_(v\d+\.\d+\.\d+)$", stem)
    default_name = m.group(1) if m else stem
    default_revision = m.group(2) if m else ""

    name = input(f"Assembly name [{default_name}]: ").strip() or default_name
    revision = input(f"Revision [{default_revision}]: ").strip() or default_revision
    description = input("Description: ").strip()
    print("Resolving next IPN...")
    suggested_ipn = next_assembly_ipn()
    ipn = suggested_ipn  # may be overridden below if this is a new part

    # ------------------------------------------------------------------
    # Find category
    # ------------------------------------------------------------------
    print("\nLooking up 'electronic-assemblies' category...")
    category = find_category("electronic-assemblies")
    if not category:
        print("ERROR: Category 'electronic-assemblies' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"  Found: pk={category['pk']}")

    # ------------------------------------------------------------------
    # Check for existing assembly with the same name
    # ------------------------------------------------------------------
    existing = find_assembly_by_name(name, category["pk"])
    if existing:
        ipn = existing.get("IPN") or ipn
        print(f"\nFound existing assembly pk={existing['pk']} (IPN={ipn}, revision={existing.get('revision') or '(none)'})")
    else:
        ipn = input(f"IPN [{suggested_ipn}]: ").strip() or suggested_ipn

    # ------------------------------------------------------------------
    # Resolve component IPNs
    # ------------------------------------------------------------------
    print("\nResolving component IPNs...")
    rows = []
    errors = []
    for _, row in df_populated.iterrows():
        ipn_val = str(row["IPN"]).strip()
        refs = str(row["Reference"]).strip()
        qty = int(row["Qty"])

        part = find_part_by_ipn(ipn_val)
        if part is None:
            errors.append(f"  IPN not found: {ipn_val}  ({refs})")
            continue

        rows.append({"part_pk": part["pk"], "qty": qty, "refs": refs, "ipn": ipn_val})
        print(f"  {ipn_val:12s}  pk={part['pk']}  {refs}")

    if errors:
        print("\nUnresolved IPNs:")
        for e in errors:
            print(e)
        confirm = input("\nContinue anyway? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    print(f"\n--- Summary ---")
    if existing:
        print(f"  Mode:        UPDATE (pk={existing['pk']}, current revision: {existing.get('revision') or '(none)'})")
    else:
        print(f"  Mode:        CREATE")
    print(f"  Name:        {name}")
    print(f"  Revision:    {revision or '(none)'}")
    print(f"  IPN:         {ipn}")
    print(f"  Description: {description}")
    print(f"  Category:    {category['name']} (pk={category['pk']})")
    print(f"  BOM items:   {len(rows)}")
    print()
    action = "Update" if existing else "Create"
    confirm = input(f"{action} assembly? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Create or update assembly part
    # ------------------------------------------------------------------
    if existing:
        assembly_pk = existing["pk"]
        patch_data = {}
        if description:
            patch_data["description"] = description
        if revision:
            patch_data["revision"] = revision
        if patch_data:
            api_patch(f"part/{assembly_pk}/", patch_data)
        print(f"\nUpdated assembly pk={assembly_pk}: {name}")

        print("\nSyncing BOM items...")
        added, removed, updated = sync_bom_items(assembly_pk, rows)
        print(f"  {added} added, {removed} removed, {updated} updated")
    else:
        part_data = {
            "name": name,
            "description": description,
            "category": category["pk"],
            "assembly": True,
            "active": True,
        }
        if revision:
            part_data["revision"] = revision
        if ipn:
            part_data["IPN"] = ipn

        assembly = api_post("part/", part_data)
        assembly_pk = assembly["pk"]
        print(f"\nCreated assembly pk={assembly_pk}: {name}")

        print("\nAdding BOM items...")
        for row in rows:
            api_post("bom/", {
                "part": assembly_pk,
                "sub_part": row["part_pk"],
                "quantity": row["qty"],
                "reference": row["refs"],
            })
            print(f"  Added {row['ipn']}  x{row['qty']}  ({row['refs']})")

    web_base = BASE_URL.removesuffix("/api")
    action_past = "updated" if existing else "created"
    print(f"\nDone. Assembly '{name}' {action_past} (pk={assembly_pk}).")
    print(f"  URL: {web_base}/web/part/{assembly_pk}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
