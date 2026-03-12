# zpklib — API instructions

## Project Overview

KiCad HTTP library backed by an InvenTree parts database. Parts are organized
under `kicad-parts/` and served to KiCad via the InvenTree KiCad Library Plugin as an httplib library.

## External references

Local checkouts of source code is available at:
Inventree: ../inventree
Inventree python plugin: ../inventree_python
Kicad: ../kicad-source-mirror
Kicad plugin: ../inventree_kicad

## Docker / database

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

## InvenTree API

Base URL: `http://localhost:8000/api/`
Auth header: `Authorization: Token <token>`
Token is stored in `zpklib.kicad_httplib`.

`setup_inventree.py` reads connection details from environment variables:
- `INVENTREE_BASE_URL` — e.g. `http://localhost:8000`
- `INVENTREE_TOKEN` — API token

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

