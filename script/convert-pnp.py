#!/usr/bin/python3

import argparse
import pandas as pd

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="Convert raw KiCad Pick and Place file to EMS format")
    parser.add_argument("input_file", help="Path to the input CSV file")
    parser.add_argument("ems", help="EMS format to output (jlc/all)")
    args = parser.parse_args()

    input_file = args.input_file
    print(f"Input: {input_file}")
    ems = args.ems

    # Read KiCad pick and place CSV
    df_in = pd.read_csv(input_file, sep=",", skipinitialspace=True)

    # Extract output file name base
    base_name = input_file.removesuffix("_PNP_Generic-all-pos.csv")

    # Check with EMS format to output
    match ems.lower():
        case "jlc":
            convert_jlc(df_in, base_name)
        case "all":
            convert_jlc(df_in, base_name)
        case _:
            print(f"Unknown EMS format: {args.ems}")


def convert_jlc(df_in, base_name):
    # Create output DataFrame
    df_out = pd.DataFrame()

    # Convert and populate fileds
    df_out["Designator"] = df_in["Ref"]
    df_out["Mid X"] = df_in["PosX"].astype(str) + "mm"
    df_out["Mid Y"] = df_in["PosY"].astype(str) + "mm"
    df_out["Layer"] = df_in["Side"].map({"top": "T", "bottom": "B"})
    df_out["Rotation"] = df_in["Rot"]

    # Construct output filename
    output_file = f"{base_name}_PNP_JLC.csv"

    # Save to file
    df_out.to_csv(output_file, sep=",", index=False)
    print(f"Success: Converted PNP file written to {output_file}")

if __name__ == "__main__":
    main()
