# Znibb's Personal Kicad LIBrary

## Table of Contents

## Description
The name of your KiCad symbol libraries will be `LIBRARY_FILE_NAME - TOP_LEVEL_CATEGORY/SUBCATEGORY`, meaning that if your setup is using:

    - Library file name: zpklib.kicad_httplib
    - Inventree top level category name: kicad-parts
    - Subcategory: Resistor

your resistors will show up under a symbol library named `zpklib - kicad-parts/Resistor`

## Configuration
### Custom parameter visibility
Kicad symbol parameters imported from Inventree are hidden by default, select parameters can be set to show by creating a plugin setting called KICAD_FIELD_VISIBILITY_PARAMETER_GLOBAL in the database and settings it's value to any parameters you want to have shown.  

Fix by running `patch-inventree-plugin-settings.sh` against the inventree db.

### Kicad symbol description field not imported
Due to an undocumented change going from Kicad 9.0.4 to 9.0.5 the handling of the description field for HTTP-libraries is broken.  

Fix by running `patch-serializer.sh` aganst the inventree db.  

Currently the patch script needs to be fun after any container restart, more permanent fix is to create a custom build Docker image.