# Znibb's Personal Kicad LIBrary

## Table of Contents <!-- omit from toc -->
- [1. Description](#1-description)
- [2. Setup](#2-setup)
  - [2.1. Inventree](#21-inventree)
  - [2.2. Kicad](#22-kicad)
- [3. Usage](#3-usage)
  - [3.1. Helper scripts](#31-helper-scripts)
  - [3.2. Bulk update Inventree](#32-bulk-update-inventree)
  - [3.3. Adding components to categories](#33-adding-components-to-categories)
  - [3.4. Assemblies](#34-assemblies)
  - [3.5. Releasing a project](#35-releasing-a-project)
  - [3.6. Customizing category symbols](#36-customizing-category-symbols)
- [4. KiCad layer specific usage](#4-kicad-layer-specific-usage)
- [5. EMS Capabilities](#5-ems-capabilities)

## 1. Description
The name of your KiCad symbol libraries will be `LIBRARY_FILE_NAME - TOP_LEVEL_CATEGORY/SUBCATEGORY`, meaning that if your setup is using:

    - Library file name: zpklib.kicad_httplib
    - Inventree top level category name: kicad-parts
    - Subcategory: Resistor

your resistors will show up under a symbol library named `zpklib - kicad-parts/Resistor`

## 2. Setup
### 2.1. Inventree
1. Log into the Inventree web UI and access the Django admin panel by appending `/admin/` to the URL (NOTE the trailing forward slash)
1. Scroll down to `USERS->API Tokens`, click it and then click `ADD API TOKEN +`
1. Take nto of the `Key`, select which `User` the key is for and click `SAVE`

### 2.2. Kicad
1. Create a python venv and install the required packages: `./setup-venv.sh`
1. Create the httplib file: `setup-inventree-httplib.sh`
1. Check that the Inventree server is reachable: `./check_inventree_connection.py`
1. Open the KiCad main window, go to `Preferences->Configure Paths...`
1. Add an `Environment Variable` called `ZPKLIB_DIR` that points to your local library path and click `OK`
1. Go to `Preferences->Manage Symbol Libraries...` and click `Add existing->HTTP (.kicad_httplib)`
1. Select `zpklib.kicad_httplib` and click `Open`

## 3. Usage
### 3.1. Helper scripts
| Name | Usage |
| :--- | :---- |
| check_inventree_connection.py | Verify if httplib is setup correctly |
| create_part.py | Create new Part based on existing component structure |
| next_assembly_ipn.py | Create new EA Part with next IPN in series |
| patch_inventree_structure.py | Compares current `kicad-parts` category state with inventree_structure.yaml and patches the difference in Inventree |
| release_project.py | Handles creation of git tag, github release and upload of relevant assets to said release |
| setup-inventree-httplib.sh | Creates the httplib file used by Kicad to access Inventree |
| setup-venv.sh | Creates a python venv and installs the modules specified in `requirements.txt` |
| update_assembly.py | Update the Inventree Part for the Electronic Assembly |

### 3.2. Bulk update Inventree
1. Source the venv: `. .venv/bin/activate`
1. Analyze the contents of `inventree_structure.yaml` 
1. Applying the structure by running: `./inventree_structure_patch.py`  

### 3.3. Adding components to categories
1. Source the venv: `. .venv/bin/activate`
1. Run `./create_component.py`

### 3.4. Assemblies
1. Source the venv: `. .venv/bin/activate`
1. Reserve an assembly IPN (can be run from any directory): `./next_assembly_ipn.py`. It prompts for the assembly name, creates the part under `electronic-assemblies` and prints the IPN and a link to it
1. In KiCad, go to `Schematic Setup->Project->Text Variables` and add `PART_NUMBER` with the printed IPN
1. Generate the production files, then upload the assembly information (BOM, revision, description and image) to that IPN: `./update_assembly.py PROJECT_DIR`

### 3.5. Releasing a project
1. In the Kicad project, set the `VERSION` and `RELEASE_DATE` text variables, add a `## vX.Y.Z` section to `CHANGELOG.md`, run the production jobset, then commit and push
1. Create the git tag and GitHub release and upload the production files: `./release_project.py PROJECT_DIR`

The script needs `git` and an authenticated `gh`. It aborts if the working tree is dirty, HEAD isn't pushed, or any file name's `_vX.Y.Z_` doesn't match `VERSION`. If the tag or release already exists you are asked before it is overwritten. The uploaded files are set by `FILE_PATTERNS` at the top of the script, and the release notes are the matching `CHANGELOG.md` section.

### 3.6. Customizing category symbols
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

## 4. KiCad layer specific usage
| Layer | Usage |
| :---- | :---- |
| User.Drawings | Footprint-specific notes, connector protrusion etc. |
| User.Comments | PCB/feature dimensions |
| User.1 / PCB.Comments | PCB comments, stackup details, impedances etc. |

## 5. EMS Capabilities
EMS:
- [JLCPCB](docs/capabilities_JLCPCB.md)