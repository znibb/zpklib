"""
Apply KiCad plugin settings to the InvenTree database.
Executed via manage.py shell so Django is already configured.
"""

import sys
import time

from django.db import OperationalError, connection

SQL = """
INSERT INTO plugin_pluginsetting (key, value, plugin_id)
SELECT
    'KICAD_FIELD_VISIBILITY_PARAMETER_GLOBAL',
    'Case',
    id
FROM plugin_pluginconfig
WHERE key = 'kicad-library-plugin'
ON CONFLICT (plugin_id, key) DO UPDATE SET value = EXCLUDED.value;
"""

for attempt in range(10):
    try:
        with connection.cursor() as cursor:
            cursor.execute(SQL)
            if cursor.rowcount > 0:
                print('KiCad plugin settings applied.', flush=True)
                sys.exit(0)
            else:
                print('KiCad plugin not yet registered, retrying...', flush=True)
    except OperationalError as e:
        print(f'DB not ready: {e}', flush=True)
    time.sleep(2)

print('Warning: could not apply KiCad plugin settings after retries.', flush=True)
