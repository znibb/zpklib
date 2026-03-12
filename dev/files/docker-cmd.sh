#!/bin/bash

set -e

# Run database migrations.
# This also initialises Django, which activates plugins and registers
# them in the database — required before apply_plugin_settings.py runs.
invoke migrate

# Apply KiCad plugin settings.
python3 /home/inventree/src/backend/InvenTree/manage.py shell \
    --command="$(cat /home/inventree/apply_plugin_settings.py)"

# Start the web server (replace this process).
exec gunicorn \
    -c ./gunicorn.conf.py \
    InvenTree.wsgi \
    -b "${INVENTREE_WEB_ADDR}:${INVENTREE_WEB_PORT}" \
    --chdir "${INVENTREE_BACKEND_DIR}/InvenTree"
