#!/usr/bin/python3

import argparse
import os
import pandas as pd
import re

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="Convert raw KiCad BOM to EMS format")
    parser.add_argument("input_file", help="Path to the input CSV file")
    parser.add_argument("ems", help="EMS format to output (jlc/all)")
    args = parser.parse_args()

    input_file = args.input_file
    print(f"Input: {input_file}")
    ems = args.ems

    # Read KiCad BOM CSV
    df_in = pd.read_csv(input_file, sep=",", skipinitialspace=True)

    # Extract output file name base
    base_name = input_file.removesuffix("_BOM_Generic.csv")

    # Check with EMS format to output
    match ems.lower():
        case "jlc":
            convert_jlc(df_in, base_name)
        case "dk":
            convert_dk(df_in, base_name)
        case "all":
            convert_jlc(df_in, base_name)
            convert_dk(df_in, base_name)
        case _:
            print(f"Unknown EMS format: {args.ems}")

# JLCPCB
def convert_jlc(df_in, base_name):
    # Create output DataFrame
    df_out = pd.DataFrame()

    # Convert and populate fields
    df_out["Designator"] = df_in["Reference"].str.replace(" ", ",")
    df_out["Comment"] = df_in["Value"]
    df_out["JLCPCB Part"] = df_in["LCSC"]
    df_out["Footprint"] = df_in["Footprint"].str.replace(r"^[^:]+:", "", regex=True) # Strip library name from footprint

    # Construct output filename
    output_file = f"{base_name}_BOM_JLC.csv"

    # Save to file
    df_out.to_csv(output_file, sep=",", index=False)
    print(f"Success: Converted BOM file written to {output_file}")

# Digikey
def convert_dk(df_in, base_name):
    # Create output DataFrame
    df_out = pd.DataFrame()

    # Remove DNP items
    df_in = df_in[df_in["DNP"].isna() | (df_in["DNP"] == "")]

    # Convert and populate fields
    df_out["Reference"] = df_in["Reference"].str.replace(" ", ",")
    df_out["Qty"] = df_in["Qty"]
    df_out["Manufacturer"] = df_in["Manufacturer"]
    df_out["MPN"] = df_in["MPN"]
    df_out["Description"] = df_in["Description"]

    # Construct output filename
    output_file = f"{base_name}_BOM_DK.csv"

    # Save to file
    df_out.to_csv(output_file, sep=",", index=False)
    print(f"Success: Converted BOM file written to {output_file}")

if __name__ == "__main__":
    main()
