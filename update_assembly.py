#!/usr/bin/env python3
"""
Upload assembly information from a KiCad project to an existing InvenTree
assembly part.

The assembly IPN is read from the PART_NUMBER text variable in the project's
.kicad_pro file. The IPN must already exist in InvenTree; reserve one with
next_assembly_ipn.py first.

The VERSION text variable sets the part's revision (as vX.Y.Z) and the
RELEASE_DATE text variable (YYYY-MM-DD) is added or updated as the part's
RELEASE_DATE parameter. The parameter template is created if it doesn't exist.

Reads the BOM from output/PCBA/*_BOM_Generic.csv, looks up each component by
IPN, updates the assembly's name, revision and description, and syncs its Bill
of Materials. DNP rows are excluded.

If img/PCB_Render_Top.png exists it is uploaded as the part image.

Usage:
  update_assembly.py [PROJECT_DIR]

PROJECT_DIR defaults to the current working directory if omitted.

Connection details are read automatically from zpklib.kicad_httplib.
"""

import json
import re
import sys
from pathlib import Path

HTTPLIB_FILE = Path(__file__).parent / "zpklib.kicad_httplib"


def check_venv():
    """Warn if no virtual environment is active and ask whether to continue.

    Runs before the third-party imports below, since those are the packages
    that are missing when the venv isn't active.
    """
    if sys.prefix != sys.base_prefix:
        return

    activate = Path(__file__).resolve().parent / ".venv" / "bin" / "activate"
    print("WARNING: No active Python virtual environment detected.", file=sys.stderr)
    print("This script needs the packages in requirements.txt (pandas, requests).", file=sys.stderr)
    print(f"Activate the venv first:  . {activate}", file=sys.stderr)
    print("(or create it with ./setup-venv.sh)\n", file=sys.stderr)
    try:
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
    except EOFError:
        confirm = ""
    if confirm not in ("y", "yes"):
        print("Aborted.")
        sys.exit(1)


check_venv()

try:
    import pandas as pd
    import requests
except ModuleNotFoundError as e:
    print(
        f"ERROR: Missing Python package '{e.name}'. "
        "Activate the venv (or run ./setup-venv.sh) and try again.",
        file=sys.stderr,
    )
    sys.exit(1)


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


def api_patch(path, data):
    r = requests.patch(f"{BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def as_list(data):
    return data if isinstance(data, list) else data.get("results", [])


def parse_semver(revision):
    """Parse a vMAJOR.MINOR.PATCH string. Returns (major, minor, patch) or None."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", revision.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def find_part_by_ipn(ipn):
    parts = as_list(api_get(f"part/?IPN={ipn}&limit=10"))
    for part in parts:
        if part.get("IPN") == ipn:
            return part
    return None


def read_text_variables(kicad_pro_path):
    """Return the text_variables dict from a .kicad_pro file, or exit with an error."""
    try:
        with open(kicad_pro_path) as f:
            project = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: Could not read {kicad_pro_path.name}: {e}", file=sys.stderr)
        sys.exit(1)
    return project.get("text_variables") or {}


def read_part_number(kicad_pro_path, text_vars):
    """Return the PART_NUMBER text variable, or exit with an error."""
    part_number = text_vars.get("PART_NUMBER", "").strip()
    if not part_number:
        print(
            f"ERROR: No PART_NUMBER text variable set in {kicad_pro_path.name}.\n"
            "\n"
            "Reserve an IPN with next_assembly_ipn.py, then set it as PART_NUMBER\n"
            "in KiCad under Project Setup -> Text Variables.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not re.match(r"^EA-\d{5}$", part_number):
        print(
            f"ERROR: PART_NUMBER '{part_number}' is not a valid assembly IPN "
            "(expected EA-NNNNN).",
            file=sys.stderr,
        )
        sys.exit(1)
    return part_number


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


def get_or_create_template(name, description):
    """Return the pk of the parameter template called name, creating it if missing."""
    for tmpl in as_list(api_get("parameter/template/?limit=9999")):
        if tmpl["name"] == name:
            return tmpl["pk"]
    tmpl = api_post("parameter/template/", {
        "name": name,
        "description": description,
        "units": "",
        "checkbox": False,
    })
    print(f"  Created parameter template '{name}' (pk={tmpl['pk']})")
    return tmpl["pk"]


def set_part_parameter(part_pk, template_pk, value):
    """Add or update a part parameter. Returns "added", "updated" or "unchanged"."""
    params = as_list(api_get(f"parameter/?model_type=part&model_id={part_pk}&limit=9999"))
    for param in params:
        if param["template"] == template_pk:
            if param["data"] == value:
                return "unchanged"
            api_patch(f"parameter/{param['pk']}/", {"data": value})
            return "updated"
    api_post("parameter/", {
        "model_type": "part",
        "model_id": part_pk,
        "template": template_pk,
        "data": value,
    })
    return "added"


def upload_part_image(assembly_pk, image_path, filename):
    """Upload image_path as the part image via PATCH /api/part/<pk>/."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    r = requests.patch(
        f"{BASE_URL}/part/{assembly_pk}/",
        headers=AUTH_HEADERS,  # no Content-Type — requests sets multipart boundary
        files={"image": (filename, image_bytes, "image/png")},
    )
    if not r.ok:
        print(f"ERROR uploading image {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()


def main():
    global BASE_URL, AUTH_HEADERS, HEADERS

    if len(sys.argv) > 2:
        print(f"Usage: {sys.argv[0]} [PROJECT_DIR]", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Verify we are in a KiCad project directory
    # ------------------------------------------------------------------
    cwd = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path.cwd()
    kicad_pro_files = list(cwd.glob("*.kicad_pro"))
    if not kicad_pro_files:
        print(
            f"ERROR: No .kicad_pro file found in {cwd}.\n"
            "\n"
            "Pass the KiCad project directory as an argument, or run this script\n"
            "from it. It reads PART_NUMBER from the .kicad_pro file, looks for the\n"
            "BOM in output/PCBA/ and optionally uploads img/PCB_Render_Top.png\n"
            "as the part image.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(kicad_pro_files) > 1:
        print(f"ERROR: Multiple .kicad_pro files found in {cwd}:", file=sys.stderr)
        for f in kicad_pro_files:
            print(f"  {f.name}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Read the assembly IPN from the project
    # ------------------------------------------------------------------
    text_vars = read_text_variables(kicad_pro_files[0])
    ipn = read_part_number(kicad_pro_files[0], text_vars)
    print(f"PART_NUMBER: {ipn}")

    version = text_vars.get("VERSION", "").strip()
    release_date = text_vars.get("RELEASE_DATE", "").strip()
    if version:
        print(f"VERSION: {version}")
    else:
        print("VERSION: not set in the project — revision falls back to the BOM filename")
    if not release_date:
        print("RELEASE_DATE: not set in the project — skipping release date parameter")
    elif not re.match(r"^\d{4}-\d{2}-\d{2}$", release_date):
        print(f"RELEASE_DATE: '{release_date}' is not YYYY-MM-DD — skipping release date parameter")
        release_date = ""
    else:
        print(f"RELEASE_DATE: {release_date}")

    # ------------------------------------------------------------------
    # Find BOM file
    # ------------------------------------------------------------------
    pcba_dir = cwd / "output" / "PCBA"
    bom_files = list(pcba_dir.glob("*_BOM_Generic.csv"))
    if not bom_files:
        print(f"ERROR: No *_BOM_Generic.csv found in {pcba_dir}", file=sys.stderr)
        sys.exit(1)
    if len(bom_files) > 1:
        print(f"ERROR: Multiple BOM files found in {pcba_dir}:", file=sys.stderr)
        for f in bom_files:
            print(f"  {f.name}", file=sys.stderr)
        sys.exit(1)
    bom_path = bom_files[0]
    print(f"BOM: {bom_path}")

    # ------------------------------------------------------------------
    # Check for render image
    # ------------------------------------------------------------------
    render_path = cwd / "img" / "PCB_Render_Top.png"
    if render_path.exists():
        print(f"Image: {render_path}")
    else:
        print(f"Image: not found ({render_path}) — skipping")
        render_path = None

    base, token = _read_httplib(HTTPLIB_FILE)
    BASE_URL = f"{base}/api"
    AUTH_HEADERS = {"Authorization": f"Token {token}", "Accept": "application/json"}
    HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Find the assembly part
    # ------------------------------------------------------------------
    print(f"\nLooking up assembly {ipn}...")
    existing = find_part_by_ipn(ipn)
    if existing is None:
        print(
            f"ERROR: No part with IPN {ipn} found in InvenTree.\n"
            "Reserve the IPN with next_assembly_ipn.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not existing.get("assembly"):
        print(f"ERROR: Part {ipn} (pk={existing['pk']}) is not an assembly.", file=sys.stderr)
        sys.exit(1)
    assembly_pk = existing["pk"]
    current_name = existing.get("name") or ""
    current_revision = existing.get("revision") or ""
    current_description = existing.get("description") or ""
    print(f"  Found: pk={assembly_pk}, name={current_name}, revision={current_revision or '(none)'}")

    # ------------------------------------------------------------------
    # Read BOM
    # ------------------------------------------------------------------
    df = pd.read_csv(bom_path, sep=",", skipinitialspace=True)
    df_populated = df[df["DNP"].isna() | (df["DNP"] == "")]
    print(f"{len(df_populated)} populated rows ({len(df) - len(df_populated)} DNP excluded)")

    # ------------------------------------------------------------------
    # Collect assembly metadata
    # ------------------------------------------------------------------
    stem = bom_path.name.removesuffix("_BOM_Generic.csv")
    m = re.match(r"^(.+?)_(v\d+\.\d+\.\d+)$", stem)
    if version:
        default_revision = version if version.startswith("v") else f"v{version}"
    else:
        default_revision = m.group(2) if m else ""

    name = input(f"Assembly name [{current_name}]: ").strip() or current_name
    revision = input(f"Revision [{default_revision}]: ").strip() or default_revision
    description = input(f"Description [{current_description}]: ").strip() or current_description

    current_ver = parse_semver(current_revision)
    new_ver = parse_semver(revision)

    if current_ver is None:
        if current_revision:
            print(f"  Warning: current revision '{current_revision}' is not valid semver — skipping version check.")
    elif new_ver is None:
        print(f"ERROR: new revision '{revision}' is not valid semver (expected vMAJOR.MINOR.PATCH).", file=sys.stderr)
        sys.exit(1)
    elif new_ver < current_ver:
        print(f"ERROR: cannot downgrade from {current_revision} to {revision}.", file=sys.stderr)
        sys.exit(1)

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
    print("\n--- Summary ---")
    print(f"  Assembly:    {ipn} (pk={assembly_pk}, current revision: {current_revision or '(none)'})")
    print(f"  Name:        {name}")
    print(f"  Revision:    {revision or '(none)'}")
    print(f"  Description: {description}")
    print(f"  Release date: {release_date or '(none)'}")
    print(f"  BOM items:   {len(rows)}")
    print(f"  Image:       {render_path.name if render_path else '(none)'}")
    print()
    confirm = input("Update assembly? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Update assembly part
    # ------------------------------------------------------------------
    patch_data = {}
    if name and name != current_name:
        patch_data["name"] = name
    if description and description != current_description:
        patch_data["description"] = description
    if revision and revision != current_revision:
        patch_data["revision"] = revision
    if patch_data:
        api_patch(f"part/{assembly_pk}/", patch_data)
    print(f"\nUpdated assembly pk={assembly_pk}: {name}")

    if release_date:
        print("\nSetting release date parameter...")
        template_pk = get_or_create_template("RELEASE_DATE", "Release date (YYYY-MM-DD)")
        result = set_part_parameter(assembly_pk, template_pk, release_date)
        print(f"  RELEASE_DATE {release_date}: {result}")

    print("\nSyncing BOM items...")
    added, removed, updated = sync_bom_items(assembly_pk, rows)
    print(f"  {added} added, {removed} removed, {updated} updated")

    # ------------------------------------------------------------------
    # Upload part image
    # ------------------------------------------------------------------
    if render_path:
        print("\nUploading part image...")
        image_filename = f"{name}_{revision}.png"
        upload_part_image(assembly_pk, render_path, image_filename)
        print(f"  Uploaded as {image_filename}")

    print(f"\nDone. Assembly '{name}' ({ipn}) updated (pk={assembly_pk}).")
    print(f"  URL: {base}/web/part/{assembly_pk}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
