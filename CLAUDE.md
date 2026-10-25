# zpklib — API instructions

## Project Overview

KiCad HTTP library backed by an InvenTree parts database. Parts are organized
under `kicad-parts/` and served to KiCad via the InvenTree KiCad Library Plugin as an httplib library.

The point is an atomic-parts workflow in stock KiCad: one InvenTree part (one IPN)
carries the symbol, footprint, parameters, datasheet and supplier data, instead
of loose symbol fields copied between projects. Geometry (symbols, footprints,
design blocks) lives in this git repo; data lives in InvenTree.

Production InvenTree is a remote instance (the `root_url` in `zpklib.kicad_httplib`,
behind Traefik/Authentik and a Caddy proxy for `/media`). The Docker setup in
the next sections is for local development only. All scripts below talk to
whatever instance `zpklib.kicad_httplib` points at, i.e. normally production,
so they write to live data.

## Repository layout

| Path | Purpose |
| :--- | :--- |
| `symbol/*.kicad_sym`, `footprint/*.pretty` | KiCad symbol and footprint libraries, one per category family. A symbol file can hold several symbols, derived ones use `extends` (e.g. `mounting_hole` sizes) |
| `inventree_structure.yaml` | Declarative InvenTree structure (categories, parameter templates, selection lists, KiCad mappings), applied by `patch_inventree_structure.py` |
| `design_block/` | KiCad design blocks (reusable schematic+layout snippets), e.g. `TC2030_ISP_DualSide`, `TC2030_ISP_DualSide_NoLegs`, `TPS54331DDA` (empty placeholder) |
| `template/` | `template_project` (starting KiCad project) and `Zkylark_DrawingSheet.kicad_wks` (drawing sheet, see text variables below) |
| `jobset/GenerateProductionFiles.kicad_jobset` | KiCad jobset that produces everything the release script uploads |
| `script/` | Helpers run by the jobset: `convert-bom.py` (KiCad BOM to JLC/Digikey/PCBWay formats), `convert-pnp.py` (pick and place to JLC/PCBWay), own `requirements.txt` |
| `logo/` | Zkylark logo in several forms (SVG, PNG, worksheet images, 5x5mm silkscreen footprint); `imageConversionHelp.txt` has the ImageMagick command |
| `docs/` | EMS (assembly house) capabilities, e.g. JLCPCB |

## Scripts

All Python scripts use `requests` and read the URL and token from
`zpklib.kicad_httplib` (the part of `root_url` before `/plugin/` is the base
URL). They do not use environment variables. Each script carries its own copy
of the small API helpers (`_read_httplib`, `api_get`, `api_post`, `as_list`);
this is deliberate, keep the scripts stand-alone. Run them inside the venv
(`./setup-venv.sh` creates `.venv`, `. .venv/bin/activate`).

| Script | Purpose |
| :--- | :--- |
| `setup-venv.sh` | Creates `.venv` and installs `requirements.txt` |
| `setup-inventree-httplib.sh` | Writes `zpklib.kicad_httplib` (asks for domain and token). `root_url` is `https://<domain>/plugin/kicad-library-plugin`, no `/v1/` (adding it hides all categories in KiCad) |
| `check_inventree_connection.py` | Calls `/api/` with the token to verify reachability and auth |
| `patch_inventree_structure.py` | Idempotently syncs `inventree_structure.yaml` to InvenTree. `--dry-run`/`-d` shows changes without writing |
| `create_part.py` | Interactive creation of a component |
| `next_assembly_ipn.py` | Reserves the next assembly IPN by creating an empty assembly part |
| `update_assembly.py PROJECT_DIR` | Uploads revision, release date, BOM and image of a KiCad project to its reserved assembly part |
| `release_project.py PROJECT_DIR` | Git tag + GitHub release + file upload for a KiCad project |

(The usage lines in the docstrings of `create_part.py` and
`patch_inventree_structure.py` still show their old names `create_component.py`
and `setup_inventree.py`.)

### patch_inventree_structure.py

Five steps, each prints `N unchanged` plus the list of changes (with `would`
wording in dry-run):
1. Top-level category (`top_category`)
2. Selection lists: those in `selection_lists`, plus lists derived at runtime from the
   repo files: package lists from `pretty_dirs` (footprint names in the `.pretty` dirs)
   and symbol lists from `symbol_file` (symbol names in the `.kicad_sym`)
3. Parameter templates (`parameter_templates`)
4. Sub-categories under the top category with their parameter assignments
   (`top_level_params` are added to every category), via `/api/part/category/parameters/`
5. KiCad plugin category mappings from each subcategory's `kicad:` block

A subcategory is only exposed to KiCad if it has a `kicad:` block. Keys:
`default_symbol` (`lib:Symbol`), `default_reference` (also the IPN prefix, see below),
`footprint_param` (parameter template whose value is the footprint name),
`value_param` (defaults to `ValueAlternate`), `hide_fields`, `show_extra_fields`.
The block must be a mapping; with leading dashes YAML makes it a list and step 5 crashes
with `'list' object has no attribute 'get'`.

Changes made in InvenTree reach KiCad only after its cache expires (see KiCad client notes).

### IPNs

Format `<prefix>-NNNNN`. Component prefix = the category's KiCad `default_reference`
(C, R, D, J, U, Q, SW, ...). Assemblies use `EA-NNNNN` under the
`electronic-assemblies` category (not under `kicad-parts`). The next number is the
global maximum + 1 across all parts with that prefix, so prefixes shared by several
categories stay unique. `create_part.py` and `next_assembly_ipn.py` both do this
(`next_ipn`, `next_assembly_ipn`).

### create_part.py

Lists categories under `kicad-parts`, collects the category's parameters (including
inherited ones) and prompts for each, honouring selection lists, checkboxes and
compact value notation (`4R7`, `4u7`). Asks MPN, manufacturer, description, optional
datasheet URL and value. IPN comes from the plugin's `default_reference` for the
category (no mapping = no IPN, with a warning). Creates the part, sets parameters, and
if a datasheet URL was given downloads it and uploads it as an attachment named
`<Manufacturer>-<MPN>-datasheet.<ext>` with comment `datasheet`.

### Assembly workflow (next_assembly_ipn.py + update_assembly.py)

Two steps so the IPN exists before the design is released.

`next_assembly_ipn.py` (no arguments, run from anywhere): finds category
`electronic-assemblies`, computes the next `EA-NNNNN`, prompts for name and description,
warns if the name already exists, confirms, creates an empty assembly part, prints
`IPN:` and the part URL. It does not touch any KiCad project; the user sets the
`PART_NUMBER` text variable in KiCad (Schematic Setup, Project, Text Variables).

`update_assembly.py PROJECT_DIR` (defaults to cwd), checks before any write:
- Venv check first (before importing pandas/requests): if no venv is active it warns,
  prints the activate command and asks to continue.
- Reads the project's single `.kicad_pro` and its `text_variables`:
  `PART_NUMBER` (required, must match `EA-\d{5}`), `VERSION`, `RELEASE_DATE`
  (must be `YYYY-MM-DD`, otherwise skipped with a warning).
- Finds the part by IPN; errors if it doesn't exist (run `next_assembly_ipn.py` first)
  or isn't an assembly.
- Finds the BOM `output/PCBA/*_BOM_Generic.csv` (exactly one) and optional
  `img/PCB_Render_Top.png`; DNP rows are excluded.
- Prompts for name, revision, description with the existing values as defaults. The
  revision default is `v` + `VERSION` (falls back to the BOM filename `_vX.Y.Z` if
  `VERSION` is unset). Semver is enforced, downgrades are refused.
- Resolves every BOM IPN to a part. Unresolved IPNs (including a BOM row with an empty
  IPN, shown as `nan`) require explicit confirmation, and since the BOM sync removes
  items not in the new list, missing parts stay missing.
- After confirmation: patches changed name/description/revision, adds or updates the
  `RELEASE_DATE` parameter (template created on first use, free text), syncs BOM items
  with a diff (add/remove/update quantity and reference designators), and uploads the
  image as the part image.

### Release workflow (release_project.py)

`release_project.py PROJECT_DIR` (stdlib only, needs `git` and an authenticated `gh`).
Everything is validated before anything is written:
- `VERSION` from the project's `.kicad_pro` (MAJOR.MINOR.PATCH); tag and release are
  both `v<VERSION>`.
- Files come from the `FILE_PATTERNS` list at the top of the script (globs relative to
  the project dir: the 3D model, PCB/PCBA zips, PCB-Layers and Schematic PDFs, and
  everything in `output/PCBA/`). A pattern with no match aborts (jobset not run).
- Each file name's `_vX.Y.Z_` must equal `VERSION` (only that part is compared, because
  name prefixes differ). Files without a version get a warning.
- Project working tree must be clean and HEAD pushed to its upstream.
- Existing local/remote tag and existing release are detected and each needs an explicit
  yes to overwrite. Overwriting a tag moves it (`git tag -f`, force push) and never
  deletes it; an existing release is updated in place: `gh release edit` for the notes,
  `gh release upload --clobber` for same-named assets, `gh release delete-asset` for
  assets no longer in the file set. A published release follows its tag by name, so
  moving the tag keeps the release (deleting the tag would orphan it). Release notes
  are the `## vX.Y.Z` section of the project's `CHANGELOG.md`. (If the repo had
  immutable releases enabled the force push would be rejected, before the release is
  touched.)

## KiCad project conventions

Text variables used by the templates, jobset and scripts (Project Setup, Text Variables):
`PROJECT_NAME`, `VERSION` (`2.0.1`, no `v`), `RELEASE_DATE` (`YYYY-MM-DD`),
`PART_NUMBER` (the assembly IPN), `AUTHOR`, `AUTHOR_SHORT`, `COMPANY`, `EMAIL`.
`Zkylark_DrawingSheet.kicad_wks` shows `${PROJECT_NAME}`, `${VERSION}`,
`${RELEASE_DATE}`, `${PART_NUMBER}`, `${AUTHOR}`, `${EMAIL}` plus KiCad built-ins.
Use `PROJECT_NAME`, not the built-in `PROJECTNAME` (which comes from the file name,
e.g. `ThreeMan_HW`). The jobset's PCB Comments PDF still uses `${PROJECTNAME}`, so
that one file is named `<ProjectFile>_vX.Y.Z_PCB-Comments.pdf`.

The jobset (`GenerateProductionFiles.kicad_jobset`) clears `output/` (creating it if
missing), sets up a project venv from `script/requirements.txt`, then exports gerbers,
drill, BOM (`output/PCBA/<PROJECT_NAME>_v<VERSION>_BOM_Generic.csv`), the Digikey BOM
conversion, pick and place, assembly drawing, PCB comments, 3D STEP, schematic and
layer PDFs, zips `output/PCB` and `output/PCBA` into `output/<name>_v<VERSION>_PCB.zip`
and `_PCBA.zip`, and renders `img/PCB_Render_Top.png` and `_Bottom.png`. Projects
gitignore `output/`. Projects keep a `CHANGELOG.md` with one `## vX.Y.Z` section per
release (`Released:` date, Added/Changed/Fixed/Removed).

Release procedure: set `VERSION`/`RELEASE_DATE`, update `CHANGELOG.md`, run the jobset,
commit and push, `update_assembly.py PROJECT_DIR`, then `release_project.py PROJECT_DIR`.

## KiCad client notes

- Libraries of the HTTP source only provide symbols. The symbol and footprint libraries
  they name (`lib:Symbol`, `lib:Footprint`) must also be registered in KiCad's global
  `sym-lib-table` and `fp-lib-table` (type `KiCad`, uri `${ZPKLIB_DIR}/symbol/<lib>.kicad_sym`
  and `${ZPKLIB_DIR}/footprint/<lib>.pretty`), otherwise previews are blank.
  `ZPKLIB_DIR` is set in Preferences, Configure Paths. KiCad 10 config is under
  `~/.config/kicad/10.0/`.
- KiCad caches HTTP library content: category contents for `timeout_categories_seconds`
  (6000 s in the generated httplib), parts for `timeout_parts_seconds` (60 s). Restart
  KiCad to see new categories or parts immediately.
- On Wayland (Plasma 6.8) KiCad 10 from Arch crashes on any keyboard shortcut (wx asserts
  in `wxGetKeyState`). Start it with `GDK_BACKEND=x11` (user desktop files in
  `~/.local/share/applications/` do this).

## External references

Local checkouts of source code is available at:
Inventree: ../inventree
Inventree python plugin: ../inventree_python
Kicad: ../kicad-source-mirror
Kicad plugin: ../inventree_kicad

## Docker / database (local development)

- Container names: `inventree-server`, `inventree-worker`, `inventree-db`, `inventree-cache`, `inventree-proxy`
- DB credentials: user=`inventree`, db=`inventree` (see `dev/.env`)
- Run migrations after installing a new plugin:
  ```
  docker exec inventree-server invoke migrate
  ```
- After activating a plugin, restart the server so its URLs are registered
  (Django URL patterns are built at startup; activating a plugin at runtime does not reload them):
  ```
  docker restart inventree-server inventree-worker
  ```

## InvenTree API (local development)

Base URL (local Docker): `http://localhost:8000/api/`. Production uses the host from
`zpklib.kicad_httplib`.
Auth header: `Authorization: Token <token>`
Token is stored in `zpklib.kicad_httplib` (gitignored).

The scripts read the URL and token from `zpklib.kicad_httplib`; to point them at the
local instance, regenerate that file with `setup-inventree-httplib.sh`.

**HTTP client notes:**
- Always send `Accept: application/json` on GET requests
- Do NOT send `Content-Type: application/json` on GET requests — the plugin
  endpoints will redirect (302) or return HTML if this header is present on GETs
- List endpoints return a bare JSON array (not a paginated `{"results": [...]}` object)

### Part Categories

**Create subcategory:**
```
POST /api/part/category/
{ "name": "...", "description": "...", "parent": <parent_id> }
```

- Do NOT insert directly into `part_partcategory` — it uses MPTT tree fields

### Selection Lists (for parameter templates with a fixed set of choices)

**Create list:**
```
POST /api/selection/
{ "name": "...", "description": "...", "locked": false }
→ returns { "pk": <list_id>, ... }
```

**Add entries:** older InvenTree versions have a bug where the API endpoint
(`/api/selection/<list_id>/entry/`) does not correctly assign `list_id` via the
URL — entries are created with `list_id=null`. Fixed in InvenTree 1.2.6+.
The patch script checks `entry["list"]` in the response and only runs the SQL
fix when it is null:
```
POST /api/selection/<list_id>/entry/
{ "value": "X5R", "label": "X5R" }
→ older: { "id": <entry_id>, "list": null }   ← SQL fix needed
→ newer: { "id": <entry_id>, "list": <list_id> } ← no fix needed

docker exec inventree-db psql -U inventree -d inventree -c \
  "UPDATE common_selectionlistentry SET list_id = <list_id> WHERE id IN (...);"
```

### Parameter Templates

**Create template:**
```
POST /api/parameter/template/
{
  "name": "...",
  "description": "...",
  "units": "V",           // empty string for dimensionless
  "selectionlist": <id>   // omit or null for free-text parameters
}
→ returns { "pk": <template_id>, ... }
```

**Assign template to category:**
```
POST /api/part/category/parameters/
{ "category": <category_id>, "template": <template_id>, "default_value": "" }
```
Note: the endpoint is the global list `/api/part/category/parameters/`, NOT
a per-category sub-path.

### Part Parameters

InvenTree uses a generic parameter system shared across model types. Part
parameters are NOT at `/api/part/parameter/` — that endpoint does not exist.

**Set a parameter value on a part:**
```
POST /api/parameter/
{
  "model_type": "part",
  "model_id": <part_id>,
  "template": <template_id>,
  "data": "<value>"
}
```

### KiCad Plugin Category Mapping

The plugin must be installed and its migrations run before the API is available.
To expose a category to KiCad (maps InvenTree category → KiCad symbol/footprint):
```
POST /plugin/kicad-library-plugin/api/category/
{
  "category": <category_id>,
  "default_symbol": "libname:SymbolName",
  "default_reference": "C",
  "default_value_parameter_template": <template_id>,   // parameter used as KiCad Value field
  "footprint_parameter_template": <template_id>         // parameter used as KiCad Footprint suffix
}
```

**List existing mappings:**
```
GET /plugin/kicad-library-plugin/api/category/
```
Note: send only `Authorization` and `Accept: application/json` — no `Content-Type` header.

