"""
Patches the InvenTree KiCad plugin serializer:

Root cause: KiCad's sch_io_http_lib.cpp reads the part description from a
top-level 'description' string key in the JSON response (aPart.desc). After
the field loop runs, it calls symbol->SetDescription(aPart.desc) which
OVERWRITES whatever the field loop wrote to the Description field. Since
KicadDetailedPartSerializer never emits a top-level 'description' key,
aPart.desc is always empty, clearing the Description field on every placed part.

Fix:
  1. Add 'description' to KicadDetailedPartSerializer.Meta.fields.
  2. Add an explicit description SerializerMethodField + get_description method,
     since DRF's auto-generated field for Part.description returns None.
"""

path = '/usr/local/lib/python3.11/site-packages/inventree_kicad/serializers.py'

with open(path) as f:
    content = f.read()

# ── Patch 1: Meta.fields — add top-level 'description' ──────────────────────

meta_state_a = (
    "        fields = [\n"
    "            'id',\n"
    "            'name',\n"
    "            'symbolIdStr',\n"
    "            'exclude_from_bom',\n"
    "            'exclude_from_board',\n"
    "            'exclude_from_sim',\n"
    "            'fields',\n"
    "        ]\n"
)
meta_target = (
    "        fields = [\n"
    "            'id',\n"
    "            'name',\n"
    "            'symbolIdStr',\n"
    "            'exclude_from_bom',\n"
    "            'exclude_from_board',\n"
    "            'exclude_from_sim',\n"
    "            'fields',\n"
    "            'description',\n"
    "        ]\n"
)

if meta_target in content:
    print("Meta.fields patch: already applied, skipping")
elif meta_state_a in content:
    content = content.replace(meta_state_a, meta_target, 1)
    print("Meta.fields patch: applied")
else:
    raise AssertionError("Meta.fields patch: unexpected serializer format")

# ── Patch 2: add description SerializerMethodField + get_description method ──

field_state_a = (
    "    fields = serializers.SerializerMethodField('get_kicad_fields')\n"
    "\n"
    "    def get_name(self, part):\n"
)
field_target = (
    "    fields = serializers.SerializerMethodField('get_kicad_fields')\n"
    "    description = serializers.SerializerMethodField('get_description')\n"
    "\n"
    "    def get_description(self, part):\n"
    "        return str(part.description) if part.description else ''\n"
    "\n"
    "    def get_name(self, part):\n"
)

if field_target in content:
    print("description field patch: already applied, skipping")
elif field_state_a in content:
    content = content.replace(field_state_a, field_target, 1)
    print("description field patch: applied")
else:
    raise AssertionError("description field patch: unexpected serializer format")

with open(path, 'w') as f:
    f.write(content)
