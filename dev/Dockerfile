ARG INVENTREE_TAG=stable
FROM inventree/inventree:${INVENTREE_TAG}

# Install KiCad plugin
RUN pip install --quiet inventree-kicad-plugin==2.0.3

# Patch serializer (KiCad Description field issue)
COPY files/patch_serializer.py /tmp/patch_serializer.py
RUN python3 /tmp/patch_serializer.py && rm /tmp/patch_serializer.py

# Patch plugin settings (fix KiCad parameter default visibility)
COPY files/apply_plugin_settings.py /home/inventree/apply_plugin_settings.py
COPY files/docker-cmd.sh /home/inventree/docker-cmd.sh
RUN chmod +x /home/inventree/docker-cmd.sh

CMD ["/bin/bash", "/home/inventree/docker-cmd.sh"]
