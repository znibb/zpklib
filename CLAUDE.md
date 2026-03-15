# zpklib — API instructions

## Project Overview

KiCad HTTP library backed by an InvenTree parts database. Parts are organized
under `kicad-parts/` and served to KiCad via the InvenTree KiCad Library Plugin as an httplib library.

## InvenTree API

Base URL: `http://localhost:8000/api/`
Auth header: `Authorization: Token <token>`
Token is stored in `zpklib.kicad_httplib`.

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

**Add entries:** the API endpoint (`/api/selection/<list_id>/entry/`) does not
correctly assign `list_id` via the URL — entries are created with `list_id=null`.
Fix with a direct SQL update after creating entries:
```
POST /api/selection/<list_id>/entry/
{ "value": "X5R", "label": "X5R" }
→ returns { "id": <entry_id>, "list": null }   ← list is null, must be fixed

docker exec inventree-db psql -U pguser -d inventree -c \
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

### KiCad Plugin Category Mapping

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

### KiCad Footprint Parameter Mappings

The plugin resolves footprints via the `FootprintParameterMapping` model, which maps
a raw parameter value (e.g. `0402`) to a fully-qualified KiCad footprint string
(e.g. `capacitor:C_0402_1005Metric`). This is separate from selection list labels —
labels are only used for display in InvenTree's UI.

The mapping is **not exposed via the plugin REST API** — entries must be inserted
directly into the database:

```sql
INSERT INTO inventree_kicad_footprintparametermapping
  (parameter_value, kicad_footprint, kicad_category_id)
VALUES
  ('0201', 'capacitor:C_0201_0603Metric', <kicad_category_pk>),
  ('0402', 'capacitor:C_0402_1005Metric', <kicad_category_pk>),
  ...;
```

`kicad_category_id` is the `pk` of the `inventree_kicad_selectedcategory` row
(returned when creating the KiCad plugin category mapping), NOT the InvenTree
part category id.

**Current mappings:**

| KiCad category pk | InvenTree category   | parameter_value | kicad_footprint            |
|-------------------|----------------------|-----------------|----------------------------|
| 3                 | kicad-parts/Resistor | 0201            | resistor:R_0201_0603Metric |
| 3                 | kicad-parts/Resistor | 0402            | resistor:R_0402_1005Metric |
| 3                 | kicad-parts/Resistor | 0603            | resistor:R_0603_1608Metric |
| 3                 | kicad-parts/Resistor | 0805            | resistor:R_0805_2012Metric |
| 3                 | kicad-parts/Resistor | 1206            | resistor:R_1206_3216Metric |
| 3                 | kicad-parts/Resistor | 1210            | resistor:R_1210_3225Metric |
| 4                 | kicad-parts/Capacitor| 0201            | capacitor:C_0201_0603Metric|
| 4                 | kicad-parts/Capacitor| 0402            | capacitor:C_0402_1005Metric|
| 4                 | kicad-parts/Capacitor| 0603            | capacitor:C_0603_1608Metric|
| 4                 | kicad-parts/Capacitor| 0805            | capacitor:C_0805_2012Metric|
| 4                 | kicad-parts/Capacitor| 1206            | capacitor:C_1206_3216Metric|
| 4                 | kicad-parts/Capacitor| 1210            | capacitor:C_1210_3225Metric|

