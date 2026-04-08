# Znibb's Personal Kicad LIBrary

## Table of Contents

## Description
The name of your KiCad symbol libraries will be `LIBRARY_FILE_NAME - TOP_LEVEL_CATEGORY/SUBCATEGORY`, meaning that if your setup is using:

    - Library file name: zpklib.kicad_httplib
    - Inventree top level category name: kicad-parts
    - Subcategory: Resistor

your resistors will show up under a symbol library named `zpklib - kicad-parts/Resistor`

## Usage
### Getting started
1. Create a python venv and install the required packages: `./setup-venv.sh`
1. Create the httplib file: `setup-inventree-httplib.sh`
1. Check that the Inventree server is reachable: `./check_connection.py`
1. Open the KiCad main window, go to `Preferences->Configure Paths...`
1. Add an `Environment Variable` called `ZPKLIB_DIR` that points to your local library path
1. Add the `zpklib.kicad_httplib` file to KiCad as a Symbol Library

### Bulk update Inventree
1. Source the venv: `. .venv/bin/activate`
1. Analyze the contents of `inventree_structure.yaml` 
1. Applying the structure by running: `./inventree_structure_patch.py`  

### Adding components to categories
1. Source the venv: `. .venv/bin/activate`
1. Run `./create_component.py`

### Customizing category symbols
Kicad handles the default symbol fields `reference, value, footprint, datasheet, description, keywords` in it's own batch, showing `reference` and `value` while hiding the rest by default.  

To hide any of the default fields add:  
```
kicad:
    hide_fields: "FIELD_NAME"
```
to that category in `inventree_structure.yaml`.

The rest of the symbol fields are considered "extra" fields. To make an extra field visible on the symbol add:
```
kivad:
    show_extra_fields: "FIELD_NAME"
```
to that category in `inventree_structure.yaml`.

## EMS Capabilities
EMS:
- [JLCPCB](docs/capabilities_JLCPCB.md)