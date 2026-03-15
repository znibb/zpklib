#!/usr/bin/env bash

set -euo pipefail

# Ensures that there's a plugin setting called KICAD_FIELD_VISIBILITY_PARAMETER_GLOBAL
# exists and set the value to 'Package_RCL', ensuring that a Kicad field with that
# name will be visible on the symbol by default
docker exec inventree-db psql -U pguser -d inventree -c "
INSERT INTO plugin_pluginsetting (key, value, plugin_id)
VALUES (
    'KICAD_FIELD_VISIBILITY_PARAMETER_GLOBAL',
    'Package_RCL',
    (SELECT id FROM plugin_pluginconfig WHERE key = 'kicad-library-plugin')
)
ON CONFLICT (plugin_id, key) DO UPDATE SET value = EXCLUDED.value;
"
