#!/usr/bin/env python3
"""
Set up the InvenTree structure for zpklib.
Idempotent: creates missing items and updates existing ones to match the
structure defined in inventree_structure.yaml.

Usage:
  setup_inventree.py            Apply all changes.
  setup_inventree.py --dry-run  Show what would change without modifying anything.
  setup_inventree.py -d         Same as --dry-run.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests
import yaml

REPO_ROOT = Path(__file__).parent
STRUCTURE_FILE = REPO_ROOT / "inventree_structure.yaml"
HTTPLIB_FILE = REPO_ROOT / "zpklib.kicad_httplib"


def _read_httplib(path):
    """Read base URL and token from a .kicad_httplib file.
    Returns (base_url, token) where base_url has no trailing slash."""
    with open(path) as f:
        data = json.load(f)
    source = data["source"]
    root_url = source["root_url"].rstrip("/")
    base = root_url.split("/plugin/")[0]
    return base, source["token"]


BASE_URL = None    # set in main()
PLUGIN_URL = None  # set in main()
TOKEN = None       # set in main()
AUTH_HEADERS = {}  # set in main()
HEADERS = {}       # set in main()

DRY_RUN = False  # set by parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(path, base=None):
    r = requests.get(f"{base or BASE_URL}/{path}", headers=AUTH_HEADERS)
    r.raise_for_status()
    return r.json()


def api_post(path, data, base=None):
    if DRY_RUN:
        return {"pk": None, "id": None}
    r = requests.post(f"{base or BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def api_patch(path, data, base=None):
    if DRY_RUN:
        return {}
    r = requests.patch(f"{base or BASE_URL}/{path}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()


def api_delete(path, base=None):
    if DRY_RUN:
        return
    r = requests.delete(f"{base or BASE_URL}/{path}", headers=AUTH_HEADERS)
    if not r.ok:
        print(f"  ERROR {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()

def as_list(data):
    return data if isinstance(data, list) else data.get("results", [])


def footprint_names(pretty_dir):
    lib_name = Path(pretty_dir).stem
    return sorted(
        f"{lib_name}:{p.stem}"
        for p in (REPO_ROOT / "footprint" / pretty_dir).glob("*.kicad_mod")
    )


def symbol_names(symbol_file):
    """Return sorted list of top-level symbol names from a .kicad_sym file, as library:name."""
    lib_name = Path(symbol_file).stem
    text = (REPO_ROOT / "symbol" / symbol_file).read_text()
    # Top-level symbols are at exactly one tab of indentation inside kicad_symbol_lib
    names = sorted(re.findall(r'^\t\(symbol "([^"]+)"', text, re.MULTILINE))
    return [f"{lib_name}:{name}" for name in names]


def w(past, infinitive):
    """Return past tense or 'would <infinitive>' depending on DRY_RUN."""
    return f"would {infinitive}" if DRY_RUN else past


# ---------------------------------------------------------------------------
# Step 1: Top-level category
# ---------------------------------------------------------------------------

def ensure_top_category(top_category):
    name = top_category["name"]
    print(f"Step 1: Ensuring top-level category '{name}'...")
    cats = as_list(api_get(f"part/category/?search={name}"))
    for cat in cats:
        if cat["name"] == name:
            pk = cat["pk"]
            desired = {
                "description": top_category["description"],
                "structural": top_category.get("structural", False),
            }
            current = {"description": cat["description"], "structural": cat["structural"]}
            if desired != current:
                api_patch(f"part/category/{pk}/", desired)
                print(f"  {w('Updated', 'update')} pk={pk}")
            else:
                print(f"  No changes pk={pk}")
            return pk
    api_post("part/category/", top_category)
    print(f"  {w('Created', 'create')}")
    return None  # pk unknown in dry-run; real run exits above via return pk


# ---------------------------------------------------------------------------
# Step 2: Selection lists
# ---------------------------------------------------------------------------

def sync_selection_list(name, description, desired_entries):
    existing_lists = {item["name"]: item["pk"] for item in as_list(api_get("selection/"))}
    desired_set = set(desired_entries)

    if name in existing_lists:
        list_pk = existing_lists[name]
        print(f"  Syncing '{name}' (pk={list_pk})...")
        existing_entries = {e["value"]: e["id"] for e in as_list(api_get(f"selection/{list_pk}/entry/"))}
    else:
        lst = api_post("selection/", {"name": name, "description": description, "locked": False})
        list_pk = lst["pk"]
        existing_entries = {}
        if list_pk is None:
            # dry-run: can't query entries for a list that doesn't exist yet
            print(f"  {w('Created', 'create')} '{name}' (would add {len(desired_entries)} entries)")
            return None
        print(f"  Created '{name}' pk={list_pk}")

    to_add = [v for v in desired_entries if v not in existing_entries]
    to_remove = [(v, eid) for v, eid in existing_entries.items() if v not in desired_set]

    null_ids = []
    for value in to_add:
        # Include "list" explicitly in the body as a workaround for versions that
        # don't assign list_id from the URL.
        entry = api_post(f"selection/{list_pk}/entry/", {"value": value, "label": value, "list": list_pk})
        # If list is still null, fall back to a direct SQL fix (local docker only).
        if entry.get("id") is not None and entry.get("list") is None:
            null_ids.append(entry["id"])

    if null_ids:
        ids_csv = ", ".join(str(i) for i in null_ids)
        sql(f"UPDATE common_selectionlistentry SET list_id = {list_pk} WHERE id IN ({ids_csv});")

    for _, entry_id in to_remove:
        api_delete(f"selection/{list_pk}/entry/{entry_id}/")

    if to_add:
        print(f"    {w('Added', 'add')} {len(to_add)} entries")
    if to_remove:
        print(f"    {w('Removed', 'remove')} {len(to_remove)} entries")

    return list_pk


def setup_selection_lists(structure):
    print("Step 2: Syncing selection lists...")
    lists = {}
    for sl in structure.get("selection_lists", []):
        lists[sl["name"]] = sync_selection_list(sl["name"], sl["description"], sl["entries"])
    for psl in structure.get("package_selection_lists", []):
        lists[psl["name"]] = sync_selection_list(
            psl["name"], psl["description"], footprint_names(psl["pretty_dir"])
        )
    for ssl in structure.get("symbol_selection_lists", []):
        lists[ssl["name"]] = sync_selection_list(
            ssl["name"], ssl["description"], symbol_names(ssl["symbol_file"])
        )
    return lists


# ---------------------------------------------------------------------------
# Step 3: Parameter templates
# ---------------------------------------------------------------------------

def setup_parameter_templates(structure, selection_lists):
    print("Step 3: Syncing parameter templates...")
    existing = {t["name"]: t for t in as_list(api_get("parameter/template/?limit=9999"))}
    templates = {}
    for tmpl in structure.get("parameter_templates", []):
        name = tmpl["name"]
        sl_key = tmpl.get("selectionlist")
        desired = {
            "description": tmpl["description"],
            "checkbox": tmpl.get("checkbox", False),
            "units": tmpl.get("unit", ""),
            "selectionlist": selection_lists.get(sl_key) if sl_key else None,
        }
        if name in existing:
            pk = existing[name]["pk"]
            current = {
                "description": existing[name]["description"],
                "checkbox": existing[name]["checkbox"],
                "units": existing[name]["units"],
                "selectionlist": existing[name]["selectionlist"],
            }
            if desired != current:
                api_patch(f"parameter/template/{pk}/", desired)
                print(f"  '{name}': {w('updated', 'update')} pk={pk}")
            else:
                print(f"  '{name}': no changes pk={pk}")
            templates[name] = pk
        else:
            result = api_post("parameter/template/", {"name": name, **desired})
            templates[name] = result["pk"]  # None in dry-run
            print(f"  '{name}': {w('created', 'create')}" + (f" pk={result['pk']}" if result["pk"] else ""))
    return templates


# ---------------------------------------------------------------------------
# Step 4: Sub-categories + parameter assignments
# ---------------------------------------------------------------------------

def sync_category_params(category_pk, desired_template_pks):
    """Add missing and remove extra directly-assigned params for a category."""
    if category_pk is None:
        return
    # Filter out None pks that result from dry-run template creation
    desired_set = {pk for pk in desired_template_pks if pk is not None}

    all_existing = as_list(api_get(f"part/category/parameters/?category={category_pk}&limit=9999"))
    direct = {e["template"]: e["pk"] for e in all_existing if e["category"] == category_pk}

    added = [pk for pk in desired_set if pk not in direct]
    for tmpl_pk in added:
        api_post("part/category/parameters/", {
            "category": category_pk, "template": tmpl_pk, "default_value": "",
        })

    removed = [asgn_pk for tmpl_pk, asgn_pk in direct.items() if tmpl_pk not in desired_set]
    for asgn_pk in removed:
        api_delete(f"part/category/parameters/{asgn_pk}/")

    if added or removed:
        print(f"    params: {w('added', 'add')} {len(added)}, {w('removed', 'remove')} {len(removed)}")


def setup_subcategories(structure, top_pk, templates):
    print("Step 4: Syncing sub-categories and parameters...")

    top_name = structure["top_category"]["name"]
    print(f"  '{top_name}' (pk={top_pk}): syncing top-level params...")
    top_tmpl_pks = [templates.get(n) for n in structure.get("top_level_params", [])]
    sync_category_params(top_pk, top_tmpl_pks)

    existing_cats = {}
    if top_pk is not None:
        existing_cats = {c["name"]: c for c in as_list(api_get(f"part/category/?parent={top_pk}"))}

    subcategory_pks = {}
    for subcat in structure.get("subcategories", []):
        name = subcat["name"]
        if name in existing_cats:
            cat = existing_cats[name]
            cat_pk = cat["pk"]
            desired = {"description": subcat["description"], "icon": subcat.get("icon", "")}
            current = {"description": cat["description"], "icon": cat.get("icon", "")}
            if desired != current:
                api_patch(f"part/category/{cat_pk}/", desired)
                print(f"  '{name}': {w('updated', 'update')} pk={cat_pk}")
            else:
                print(f"  '{name}': no changes pk={cat_pk}")
        else:
            result = api_post("part/category/", {
                "name": name,
                "description": subcat["description"],
                "icon": subcat.get("icon", ""),
                "parent": top_pk,
            })
            cat_pk = result["pk"]  # None in dry-run
            print(f"  '{name}': {w('created', 'create')}" + (f" pk={cat_pk}" if cat_pk else ""))

        subcategory_pks[name] = cat_pk
        tmpl_pks = [templates.get(n) for n in subcat.get("params", [])]
        sync_category_params(cat_pk, tmpl_pks)

    return subcategory_pks


# ---------------------------------------------------------------------------
# Step 5: KiCad plugin category mappings
# ---------------------------------------------------------------------------

def setup_kicad_mappings(structure, subcategory_pks, templates):
    print("Step 5: Syncing KiCad plugin category mappings...")
    value_tmpl_pk = templates.get("ValueStandard")
    existing_by_cat = {
        e["category"]["id"]: e
        for e in as_list(api_get("category/", base=PLUGIN_URL))
    }

    for subcat in structure.get("subcategories", []):
        name = subcat["name"]
        kicad = subcat.get("kicad")
        if not kicad:
            continue
        cat_pk = subcategory_pks.get(name)
        if cat_pk is None:
            print(f"  '{name}': {w('created', 'create')} kicad mapping (category pk unknown)")
            continue
        value_param_name = kicad.get("value_param", "ValueStandard")
        desired = {
            "default_symbol": kicad["default_symbol"],
            "default_reference": kicad["default_reference"],
            "default_value_parameter_template": templates.get(value_param_name),
            "footprint_parameter_template": templates.get(kicad.get("footprint_param")),
        }
        if cat_pk in existing_by_cat:
            existing = existing_by_cat[cat_pk]
            kicad_pk = existing["pk"]
            val_tmpl = existing["default_value_parameter_template"]
            fp_tmpl = existing["footprint_parameter_template"]
            current = {
                "default_symbol": existing["default_symbol"],
                "default_reference": existing["default_reference"],
                "default_value_parameter_template": val_tmpl["id"] if val_tmpl else None,
                "footprint_parameter_template": fp_tmpl["id"] if fp_tmpl else None,
            }
            if desired != current:
                api_patch(f"category/{kicad_pk}/", desired, base=PLUGIN_URL)
                print(f"  '{name}': {w('updated', 'update')} kicad_category pk={kicad_pk}")
            else:
                print(f"  '{name}': no changes kicad_category pk={kicad_pk}")
        else:
            if not desired["default_symbol"]:
                print(f"  '{name}': skipped kicad_category creation (no default_symbol)")
                continue
            result = api_post("category/", {"category": cat_pk, **desired}, base=PLUGIN_URL)
            pk_str = f" pk={result['pk']}" if result["pk"] else ""
            print(f"  '{name}': {w('created', 'create')} kicad_category{pk_str}")



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(description="Set up InvenTree structure from inventree_structure.yaml")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Show what would change without making any modifications")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    global BASE_URL, PLUGIN_URL, TOKEN, AUTH_HEADERS, HEADERS

    base, TOKEN = _read_httplib(HTTPLIB_FILE)
    BASE_URL = f"{base}/api"
    PLUGIN_URL = f"{base}/plugin/kicad-library-plugin/api"
    AUTH_HEADERS = {"Authorization": f"Token {TOKEN}", "Accept": "application/json"}
    HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

    if DRY_RUN:
        print("Dry-run mode — all endpoints will be queried but no changes will be made.\n")

    with open(STRUCTURE_FILE) as f:
        structure = yaml.safe_load(f)

    top_pk = ensure_top_category(structure["top_category"])
    selection_lists = setup_selection_lists(structure)
    templates = setup_parameter_templates(structure, selection_lists)
    subcategory_pks = setup_subcategories(structure, top_pk, templates)
    setup_kicad_mappings(structure, subcategory_pks, templates)
    print("\nDone.")


if __name__ == "__main__":
    main()
