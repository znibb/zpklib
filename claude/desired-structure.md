# zpklib - Desired library Inventree structure

## Top level category
Name: `kicad-parts`  
Description: `Atomic parts for use in KiCad`  
Structural: True  

Add category by name if it doesn't already exist, append to it going forwards if it already exists.

## Selection lists
All lists as well as all list content rows should be set as active.

### CapacitorDielectrics
Name: `CapacitorDielectrics`  
Description: `Capacitor dialectric types`  
Value/Label:
- X5R
- X7R
- C0G/NP0

### Packages_RCL
Name: `Packages_RCL`  
Description: `Standard R/C/L packages`  
Value/Label:
- 0201
- 0402
- 0603
- 0805
- 1206
- 1210

## Parameter templates
Treat `null` as a blank entry.

| Name | Description | Unit | SelectionList |
| :--- | :---------- | :--- | :------------ |
| Dielectric        | Capacitor dielectric type         | null  | CapacitorDielectrics |
| Package_RCL       | Standard chip packages            | null  | Packages_RCL |
| PowerDecimal      | Power rating, decimal             | W     | null |
| PowerFractional   | Power rating, fractional          | W     | null |
| TemperatureMax    | Temperature rating, max           | °C    | null |
| TemperatureMin    | Temperature rating, min           | °C    | null |
| Tolerance         | Value tolerance                   | %     | null |
| ValueAlternate    | Component value, compact notation | null  | null |
| ValueStandard     | Component value, decimal notation | null  | null |
| VoltageRating     | Voltage rating                    | V     | null |

## Sub-categories
### Capacitor
Name: `Capacitor`  
Description: `Ceramic, fixed value`  
Icon: `ti:circuit-capacitor:outline`  
Category Parameters:
- Dielectric
- Package_RCL
- TemperatureMax
- TemperatureMin
- Tolerance
- ValueAlternate
- ValueStandard
- VoltageRating

### Capacitor - Polarized
Name: `CapacitorPolarized`  
Description: `Polarized, fixed value`  
Icon: `ti:circuit-capacitor-polarized:outline`  
Category Parameters:
- Dielectric
- Package_RCL
- TemperatureMax
- TemperatureMin
- Tolerance
- ValueAlternate
- ValueStandard
- VoltageRating

### Inductor
Name: `Inductor`  
Description: `Fixed value`  
Icon: `ti:circuit-inductor:outline`  
Category Parameters:
- 

### Resistor
Name: `Resistor`  
Description: `Fixed value`  
Icon: `ti:circuit-resistor:outline`  
Category Parameters:
- Package_RCL
- PowerDecimal
- PowerFractional
- TemperatureMax
- TemperatureMin
- Tolerance
- ValueAlternate
- ValueStandard

### Resistor - Variable
Name: `ResistorVariable`  
Description: `Variable value, potentiometer`  
Icon: `ti:circuit-resistor:outline`  
Category Parameters:
- Package_RCL
- PowerDecimal
- PowerFractional
- TemperatureMax
- TemperatureMin
- Tolerance
- ValueAlternate
- ValueStandard

## KiCad Plugin Category Mapping
Refer to previously created categories to convert category name to id.  
All categories use `ValueStandard` as value parameter.
| Category | Default symbol | Default reference | Footprint parameter |
| :------- | :------------- | :---------------- | :------------------ |
| Capacitor             | capacitor:Capacitor           | C     | Package_RCL |
| CapacitorPolarized    | capacitor:CapacitorPolarized  | CP    | Package_RCL |
| Inductor              | inductor:Inductor             | L     | Package_RCL |
| Resistor              | resistor:Resistor             | R     | Package_RCL |
| ResistorVariable      | resistor:ResistorVariable     | RV    | Package_RCL |