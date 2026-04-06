#!/usr/bin/env python3
"""
Interactively create a new component in InvenTree.

Fetches available categories and their parameters (including inherited ones
from parent categories), prompts for values respecting selection lists, then
creates the part and sets all parameter values.

Usage:
  create_component.py

Connection details are read automatically from zpklib.kicad_httplib.
"""

import io
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

HTTPLIB_FILE = Path(__file__).parent / "zpklib.kicad_httplib"


def _read_httplib(path):
    """Read base URL and token from a .kicad_httplib file.
    Returns (base_url, token) where base_url has no trailing slash."""
    with open(path) as f:
        data = json.load(f)
    source = data["source"]
    root_url = source["root_url"].rstrip("/")
    base = root_url.split("/plugin/")[0]
    return base, source["token"]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

BASE_URL = None
PLUGIN_URL = None
AUTH_HEADERS = {}
HEADERS = {}


def api_get(path, base=None):
    r = requests.get(f"{base or BASE_URL}/{path}", headers=AUTH_HEADERS)
    r.raise_for_status()
    return r.json()


def api_post(path, data):
    r = requests.post(f"{BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


_MIME_TO_EXT = {
    "application/pdf":          ".pdf",
    "image/png":                ".png",
    "image/jpeg":               ".jpg",
    "image/gif":                ".gif",
    "image/webp":               ".webp",
    "application/zip":          ".zip",
    "application/x-zip-compressed": ".zip",
}


def api_upload(path, fields, file_bytes, filename, mime_type="application/octet-stream"):
    """POST multipart form data with a single file attachment."""
    r = requests.post(
        f"{BASE_URL}/{path}",
        headers=AUTH_HEADERS,  # no Content-Type — requests sets it with boundary
        data=fields,
        files={"attachment": (filename, io.BytesIO(file_bytes), mime_type)},
    )
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def download_datasheet(url):
    """Download a file from url and return (bytes, extension, mime_type), or (None, None, None)."""
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  Warning: could not download datasheet: {e}", file=sys.stderr)
        return None, None, None

    mime_type = r.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()

    # 1. Try Content-Disposition filename
    ext = None
    content_disp = r.headers.get("Content-Disposition", "")
    if "filename=" in content_disp:
        fname = content_disp.split("filename=")[-1].strip().strip("\"'")
        _, ext = os.path.splitext(fname)

    # 2. Map MIME type to extension
    if not ext:
        ext = _MIME_TO_EXT.get(mime_type)

    # 3. Fall back to URL path extension
    if not ext:
        _, ext = os.path.splitext(urlparse(url).path)

    # 4. Last resort
    if not ext:
        ext = ".bin"

    return r.content, ext.lower(), mime_type


def as_list(data):
    return data if isinstance(data, list) else data.get("results", [])


# ---------------------------------------------------------------------------
# Category helpers
# ---------------------------------------------------------------------------

def build_category_tree(categories):
    """Return [(depth, category), ...] in display order (DFS by name)."""
    by_parent = {}
    for cat in categories:
        by_parent.setdefault(cat.get("parent"), []).append(cat)

    result = []

    def walk(parent_pk, depth):
        for cat in sorted(by_parent.get(parent_pk, []), key=lambda c: c["name"]):
            result.append((depth, cat))
            walk(cat["pk"], depth + 1)

    walk(None, 0)
    return result


def ancestor_pks(category, cats_by_pk):
    """Return [category_pk, parent_pk, grandparent_pk, ...] up to the root."""
    pks = []
    cat = category
    while cat:
        pks.append(cat["pk"])
        cat = cats_by_pk.get(cat.get("parent"))
    return pks


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------

def fetch_templates_for_category(category, cats_by_pk):
    """
    Return (templates, defaults) where:
    - templates: list of parameter template dicts that apply to the given
      category, including those inherited from ancestor categories. Order:
      ancestors first (broadest scope first), then the selected category's
      own params. Deduplicates by template pk.
    - defaults: dict mapping template pk → default_value string from the
      closest (most specific) ancestor category assignment.
    """
    cat_pks = list(reversed(ancestor_pks(category, cats_by_pk)))  # root → leaf
    templates_by_pk = {}
    ordered_pks = []
    defaults = {}  # tmpl_pk → default_value; later (more specific) assignments win

    for cat_pk in cat_pks:
        assignments = as_list(
            api_get(f"part/category/parameters/?category={cat_pk}&limit=9999")
        )
        for a in assignments:
            # Only take directly assigned params for each category to avoid
            # double-counting when the endpoint also returns inherited entries.
            if a["category"] != cat_pk:
                continue
            tmpl_pk = a["template"]
            if tmpl_pk not in templates_by_pk:
                tmpl = api_get(f"parameter/template/{tmpl_pk}/")
                templates_by_pk[tmpl_pk] = tmpl
                ordered_pks.append(tmpl_pk)
            defaults[tmpl_pk] = a.get("default_value", "")

    return [templates_by_pk[pk] for pk in ordered_pks], defaults


def fetch_selection_entries(templates):
    """Return {selection_list_id: [entry, ...]} for all templates that have one."""
    entries_by_list = {}
    for tmpl in templates:
        sl_id = tmpl.get("selectionlist")
        if sl_id and sl_id not in entries_by_list:
            entries_by_list[sl_id] = as_list(api_get(f"selection/{sl_id}/entry/"))
    return entries_by_list


# ---------------------------------------------------------------------------
# IPN helpers
# ---------------------------------------------------------------------------

def fetch_kicad_reference(category_pk):
    """
    Return the KiCad default_reference string for the given category pk, or
    None if the category has no KiCad plugin mapping.
    """
    mappings = as_list(api_get("category/", base=PLUGIN_URL))
    for m in mappings:
        cat = m.get("category") or {}
        cat_id = cat.get("id") if isinstance(cat, dict) else cat
        if cat_id == category_pk:
            return m.get("default_reference")
    return None


_IPN_RE = re.compile(r"^(.+)-(\d{5})$")


def next_ipn(reference):
    """
    Scan all parts globally for IPNs matching '<reference>-NNNNN' and return
    the next serial as a formatted IPN string, e.g. 'C-00042'.
    Global search ensures IPN uniqueness across categories sharing a prefix.
    """
    parts = as_list(api_get(f"part/?limit=9999"))
    max_serial = 0
    prefix = f"{reference}-"
    for part in parts:
        ipn = part.get("IPN") or ""
        m = _IPN_RE.match(ipn)
        if m and m.group(1) == reference:
            max_serial = max(max_serial, int(m.group(2)))
    return f"{prefix}{max_serial + 1:05d}"


# ---------------------------------------------------------------------------
# Value compact-notation conversion
# ---------------------------------------------------------------------------

_SI_PREFIXES = set('TGMkmuμnpf')



def to_compact(value_str, is_resistor=False):
    """
    Convert standard decimal notation to compact notation:
      '4.7k'  → '4k7'
      '10.2u' → '10u2'
      '6.7'   → '6R7'  (resistor, no SI prefix → use 'R')
    Returns empty string if the value has no decimal point (no conversion possible).
    """
    s = value_str.strip()
    if '.' not in s:
        return ''

    # Split off a trailing SI prefix
    if s and s[-1] in _SI_PREFIXES:
        prefix = s[-1]
        number = s[:-1]
    else:
        prefix = ''
        number = s

    if '.' not in number:
        return ''

    integer_part, fractional_part = number.split('.', 1)

    if prefix:
        return f"{integer_part}{prefix}{fractional_part}"
    if is_resistor:
        return f"{integer_part}R{fractional_part}"
    return ''


_COMPACT_SI_RE = re.compile(r'^(\d+)([TGMkmuμnpf])(\d+)$')
_COMPACT_R_RE = re.compile(r'^(\d+)R(\d+)$')


def from_compact(value_str, is_resistor=False):
    """
    Convert compact notation back to standard decimal notation:
      '4k7'  → '4.7k'
      '10u2' → '10.2u'
      '6R7'  → '6.7'   (resistor: R means decimal point, no SI prefix)
    Returns empty string if the value is not in compact format.
    """
    s = value_str.strip()
    m = _COMPACT_SI_RE.match(s)
    if m:
        return f"{m.group(1)}.{m.group(3)}{m.group(2)}"
    if is_resistor:
        m = _COMPACT_R_RE.match(s)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
    return ''


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def prompt_pick(label, options):
    """
    Display a numbered list of options and return the chosen one.
    options: list of {"label": str, "value": any}
    """
    for i, opt in enumerate(options, 1):
        print(f"    {i:2}. {opt['label']}")
    while True:
        raw = input(f"  {label} [1-{len(options)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]["value"]
        except ValueError:
            pass
        print("  Invalid choice, try again.")


def prompt_parameter(tmpl, entries_by_list):
    """Prompt for a single parameter value and return it (string or empty)."""
    name = tmpl["name"]
    description = tmpl.get("description", "")
    units = tmpl.get("units", "")
    is_checkbox = tmpl.get("checkbox", False)
    sl_id = tmpl.get("selectionlist")

    label_parts = [name]
    if description:
        label_parts.append(f"({description})")
    if units:
        label_parts.append(f"[{units}]")
    label = " ".join(label_parts)

    if is_checkbox:
        while True:
            raw = input(f"  {label} [y/n/blank]: ").strip().lower()
            if raw in ("y", "yes"):
                return "True"
            if raw in ("n", "no"):
                return "False"
            if raw == "":
                return ""
            print("  Enter y, n, or leave blank to skip.")

    if sl_id and sl_id in entries_by_list:
        entries = entries_by_list[sl_id]
        options = [{"label": "(skip)", "value": ""}] + [
            {"label": e["value"], "value": e["value"]} for e in entries
        ]
        print(f"  {label}:")
        return prompt_pick("Choose", options)

    return input(f"  {label} (blank to skip): ").strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global BASE_URL, PLUGIN_URL, AUTH_HEADERS, HEADERS

    base, token = _read_httplib(HTTPLIB_FILE)
    BASE_URL = f"{base}/api"
    PLUGIN_URL = f"{base}/plugin/kicad-library-plugin/api"
    AUTH_HEADERS = {"Authorization": f"Token {token}", "Accept": "application/json"}
    HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Step 1: Choose a category
    # ------------------------------------------------------------------
    print("Fetching categories...")
    all_cats = as_list(api_get("part/category/?limit=9999"))
    cats_by_pk = {c["pk"]: c for c in all_cats}
    tree = build_category_tree(all_cats)

    selectable = []
    print("\nAvailable categories:")
    for depth, cat in tree:
        indent = "  " * depth
        if cat.get("structural"):
            print(f"  {indent}{cat['name']}  [structural]")
        else:
            selectable.append(cat)
            n = len(selectable)
            desc = f" — {cat['description']}" if cat.get("description") else ""
            print(f"  {indent}{n:2}. {cat['name']}{desc}")

    if not selectable:
        print("No non-structural categories available.", file=sys.stderr)
        sys.exit(1)

    print()
    while True:
        raw = input(f"Select category [1-{len(selectable)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(selectable):
                category = selectable[idx - 1]
                break
        except ValueError:
            pass
        print("  Invalid choice, try again.")

    print(f"\nCategory: {category['name']} (pk={category['pk']})")

    # ------------------------------------------------------------------
    # Step 2: Resolve IPN
    # ------------------------------------------------------------------
    print("Resolving IPN...")
    reference = fetch_kicad_reference(category["pk"])
    if reference:
        ipn = next_ipn(reference)
        print(f"  Next IPN: {ipn}")
    else:
        ipn = None
        print("  Warning: no KiCad mapping found for this category — IPN will not be assigned.")

    # ------------------------------------------------------------------
    # Step 3: Fetch applicable parameters
    # ------------------------------------------------------------------
    print("Fetching parameters...")
    templates, param_defaults = fetch_templates_for_category(category, cats_by_pk)

    if not templates:
        print("  (no parameters defined)")
    else:
        print(f"  Found {len(templates)} parameter(s): "
              + ", ".join(t["name"] for t in templates))

    entries_by_list = fetch_selection_entries(templates)

    hide_fields_pk = next((t["pk"] for t in templates if t["name"] == "KicadHideFields"), None)
    hide_fields_val = param_defaults.get(hide_fields_pk, "") if hide_fields_pk else None
    extra_fields_pk = next((t["pk"] for t in templates if t["name"] == "KicadExtraFields"), None)
    extra_fields_val = param_defaults.get(extra_fields_pk, "") if extra_fields_pk else None

    # ------------------------------------------------------------------
    # Step 4: Collect part info
    # ------------------------------------------------------------------
    # Generic symbol pk — used by KiCad plugin; written alongside the category-specific Symbol_* param.
    symbol_pk = next((t["pk"] for t in templates if t["name"] == "Symbol"), None)
    # Category-specific symbol selector (e.g. Symbol_ConnectorPower, Symbol_PowerModule).
    symbol_specific_pk = next((t["pk"] for t in templates if t["name"].startswith("Symbol_")), None)

    print(f"\n--- New part in '{category['name']}' ---")

    mpn_tmpl_pk    = next((t["pk"] for t in templates if t["name"] == "MPN"), None)
    value_std_pk   = next((t["pk"] for t in templates if t["name"] == "ValueStandard"), None)
    value_alt_pk   = next((t["pk"] for t in templates if t["name"] == "ValueAlternate"), None)
    power_pk       = next((t["pk"] for t in templates if t["name"] == "Power"), None)
    case_pk        = next((t["pk"] for t in templates if t["name"] == "Case"), None)

    # Determine which package template drives the auto-Case derivation
    if reference == "C":
        package_for_case_pk = next((t["pk"] for t in templates if t["name"] == "Package_Capacitor"), None)
    elif reference == "R":
        package_for_case_pk = next((t["pk"] for t in templates if t["name"] == "Package_Resistor"), None)
    else:
        package_for_case_pk = None

    # If both Package and Case exist for this category, handle them together
    auto_case = package_for_case_pk is not None and case_pk is not None

    pre_filled_pks = {
        pk for pk in (
            mpn_tmpl_pk, value_std_pk, value_alt_pk,
            power_pk,
            *(( package_for_case_pk, case_pk) if auto_case else ()),
        )
        if pk is not None
    }

    manufacturer_pk = next((t["pk"] for t in templates if t["name"] == "Manufacturer"), None)
    if manufacturer_pk is not None:
        pre_filled_pks.add(manufacturer_pk)

    if symbol_pk is not None:
        pre_filled_pks.add(symbol_pk)
    if symbol_specific_pk is not None:
        pre_filled_pks.add(symbol_specific_pk)
    if hide_fields_pk is not None:
        pre_filled_pks.add(hide_fields_pk)
    if extra_fields_pk is not None:
        pre_filled_pks.add(extra_fields_pk)

    mpn = input("MPN (required): ").strip().replace("/", "-")
    if not mpn:
        print("MPN is required.", file=sys.stderr)
        sys.exit(1)
    name = mpn
    manufacturer = input("Manufacturer (required): ").strip()
    if not manufacturer:
        print("Manufacturer is required.", file=sys.stderr)
        sys.exit(1)
    description = input("Description: ").strip()
    datasheet_url = input("Datasheet URL (blank to skip): ").strip()

    is_resistor = reference in ("R", "RV") if reference else False
    component_value = input(f"Value (blank to use MPN '{mpn}'): ").strip() or mpn
    if '.' in component_value:
        # Standard format entered — derive alternate (fall back to identical copy)
        value_std = component_value
        value_alt = to_compact(component_value, is_resistor) or component_value
    else:
        # Try to parse as compact/alternate format — derive standard
        value_std = from_compact(component_value, is_resistor)
        if value_std:
            value_alt = component_value
        else:
            # No decimal, no embedded separator — same for both
            value_std = component_value
            value_alt = component_value

    power_val = ''
    if power_pk is not None:
        raw_power = input("Power [W] (decimal or fraction, e.g. 0.25 or 1/8, blank to skip): ").strip()
        if raw_power and '/' in raw_power:
            try:
                num_s, den_s = raw_power.split('/', 1)
                decimal = float(num_s) / float(den_s)
                power_val = f"{decimal:.2f}".rstrip('0').rstrip('.')
            except (ValueError, ZeroDivisionError):
                power_val = raw_power
        else:
            power_val = raw_power

    # ------------------------------------------------------------------
    # Step 5: Collect parameter values
    # ------------------------------------------------------------------
    param_values = {}
    if hide_fields_pk is not None and hide_fields_val:
        param_values[hide_fields_pk] = hide_fields_val
    if extra_fields_pk is not None and extra_fields_val:
        param_values[extra_fields_pk] = extra_fields_val
    if mpn_tmpl_pk is not None:
        param_values[mpn_tmpl_pk] = mpn
    if manufacturer_pk is not None:
        param_values[manufacturer_pk] = manufacturer
    if value_std_pk is not None:
        param_values[value_std_pk] = value_std
    if value_alt_pk is not None:
        param_values[value_alt_pk] = value_alt
    if power_pk is not None:
        param_values[power_pk] = power_val

    if auto_case:
        pkg_tmpl = next(t for t in templates if t["pk"] == package_for_case_pk)
        package_val = prompt_parameter(pkg_tmpl, entries_by_list)
        param_values[package_for_case_pk] = package_val
        footprint_name = package_val.split(':', 1)[-1]
        m = re.match(r'^[A-Za-z]+_(\d{4})_\d{4}Metric$', footprint_name)
        if m:
            param_values[case_pk] = m.group(1)
            print(f"  Case auto-set to: {m.group(1)}")

    if symbol_specific_pk is not None:
        sym_tmpl = next(t for t in templates if t["pk"] == symbol_specific_pk)
        symbol_val = prompt_parameter(sym_tmpl, entries_by_list)
        param_values[symbol_specific_pk] = symbol_val
        if symbol_pk is not None:
            param_values[symbol_pk] = symbol_val  # feed generic Symbol used by KiCad plugin
        # Symbols ending in "Held" (e.g. FuseHeld) represent a part with no
        # physical footprint — skip all Package_* prompts.
        sym_name = symbol_val.split(":")[-1] if ":" in symbol_val else symbol_val
        if sym_name.endswith("Held"):
            for t in templates:
                if t["name"].startswith("Package_"):
                    pre_filled_pks.add(t["pk"])

    remaining = [t for t in templates if t["pk"] not in pre_filled_pks]
    if remaining:
        print("\nParameter values:")
        for tmpl in remaining:
            param_values[tmpl["pk"]] = prompt_parameter(tmpl, entries_by_list)

    # ------------------------------------------------------------------
    # Step 6: Confirm
    # ------------------------------------------------------------------
    print("\n--- Summary ---")
    print(f"  IPN:         {ipn or '(none)'}")
    print(f"  MPN / Name:  {name}")
    print(f"  Manufacturer:{manufacturer}")
    print(f"  Description: {description}")
    if datasheet_url:
        print(f"  Datasheet:   {datasheet_url}")
    print(f"  Value:       {value_std or '(empty)'}" + (f"  →  {value_alt}" if value_alt else ""))
    if power_pk is not None:
        print(f"  Power:       {power_val or '(empty)'}")
    print(f"  Category:    {category['name']} (pk={category['pk']})")
    if param_values:
        print("  Parameters:")
        for tmpl in templates:
            val = param_values.get(tmpl["pk"], "")
            if val:
                print(f"    {tmpl['name']}: {val}")
    print()
    confirm = input("Create part? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Step 7: Create the part
    # ------------------------------------------------------------------
    part_data = {
        "name": name,
        "description": description,
        "category": category["pk"],
        "active": True,
        "copy_category_parameters": True,
    }
    if ipn:
        part_data["IPN"] = ipn
    part = api_post("part/", part_data)
    part_pk = part["pk"]
    print(f"\nCreated part pk={part_pk}: {name}" + (f" ({ipn})" if ipn else ""))

    # ------------------------------------------------------------------
    # Step 8: Set parameter values
    # ------------------------------------------------------------------
    # copy_category_parameters may have pre-created some parameters; look them
    # up so we can PATCH instead of POST to avoid unique-constraint errors.
    existing_params = as_list(api_get(f"parameter/?model_type=part&model_id={part_pk}&limit=9999"))
    existing_pk_by_template = {p["template"]: p["pk"] for p in existing_params}

    for tmpl in templates:
        val = param_values.get(tmpl["pk"], "")
        if not val:
            print(f"  Skipped {tmpl['name']} (empty)")
            continue
        existing_pk = existing_pk_by_template.get(tmpl["pk"])
        if existing_pk:
            r = requests.patch(
                f"{BASE_URL}/parameter/{existing_pk}/",
                headers=HEADERS,
                json={"data": val},
            )
            if not r.ok:
                print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
                r.raise_for_status()
        else:
            api_post("parameter/", {
                "model_type": "part",
                "model_id": part_pk,
                "template": tmpl["pk"],
                "data": val,
            })
        print(f"  Set {tmpl['name']} = {val}")

    # ------------------------------------------------------------------
    # Step 9: Upload datasheet attachment
    # ------------------------------------------------------------------
    if datasheet_url:
        print(f"\nDownloading datasheet from {datasheet_url} ...")
        file_bytes, file_ext, mime_type = download_datasheet(datasheet_url)
        if file_bytes:
            ds_filename = f"{manufacturer}-{mpn}-datasheet{file_ext}"
            api_upload(
                "attachment/",
                {"model_type": "part", "model_id": part_pk, "comment": "datasheet"},
                file_bytes,
                ds_filename,
                mime_type,
            )
            print(f"  Uploaded attachment: {ds_filename}")
        else:
            print("  Skipped attachment upload (download failed).")

    print(f"\nDone. Part '{name}' created (pk={part_pk})" + (f" IPN={ipn}" if ipn else "") + ".")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
