#!/usr/bin/env python3
"""
GRIB File Processor

Extracts wind component bands (u and v) from HRRR GRIB2 files using gdal_translate.
Default bands are 77 (u-component) and 78 (v-component) at 10m height.
"""

import subprocess
from pathlib import Path

import config
import utils


def process_grib_file(input_file, output_dir, bands=None):
    """
    Process a single GRIB file using gdal_translate to extract specific bands.

    Args:
        input_file: Path to input GRIB2 file
        output_dir: Directory to save processed files
        bands: List of band numbers to extract (default from config)

    Returns:
        bool: True if successful, False otherwise
    """
    bands = bands or config.WIND_BANDS

    input_path = Path(input_file)
    output_path = utils.ensure_directory(output_dir)

    # Generate output filename
    output_filename = input_path.stem + config.PROCESSED_SUFFIX
    output_file = output_path / output_filename

    # Check if output file already exists
    if output_file.exists():
        print(f"Skipping {input_path.name} (already processed)")
        return True

    # Build gdal_translate command
    cmd = ["gdal_translate", "-of", "GRIB"]
    for band in bands:
        cmd.extend(["-b", str(band)])
    cmd.extend([str(input_file), str(output_file)])

    try:
        print(f"Processing {input_path.name}...")
        print(f"  Extracting bands: {', '.join(str(b) for b in bands)}")

        # Run gdal_translate
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        print(f"✓ Processed: {input_path.name} -> {output_filename}")

        # Print GDAL warnings if any
        if result.stderr:
            stderr_lines = result.stderr.strip()
            # Filter out common GDAL progress messages
            if stderr_lines and not all(line.startswith('Input file size') for line in stderr_lines.split('\n')):
                print(f"  GDAL output: {stderr_lines}")

        return True

    except subprocess.CalledProcessError as e:
        print(f"✗ Error processing {input_path.name}:")
        print(f"  {e.stderr}")
        # Clean up partial output file
        output_file.unlink(missing_ok=True)
        return False

    except FileNotFoundError:
        print("✗ Error: gdal_translate not found. Please ensure GDAL is installed.")
        print("  Install with:")
        print("    - macOS: brew install gdal")
        print("    - Linux: apt-get install gdal-bin")
        print("    - Conda: conda install -c conda-forge gdal")
        return False


def process_all_grib_files(input_dir, output_dir, bands=None, pattern=None):
    """
    Process all GRIB files in a directory.

    Args:
        input_dir: Directory containing GRIB2 files
        output_dir: Directory to save processed files
        bands: List of band numbers to extract (default from config)
        pattern: File pattern to match (default from config)

    Returns:
        dict: Summary of processing results
    """
    bands = bands or config.WIND_BANDS
    pattern = pattern or config.GRIB_FILE_PATTERN

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Find all GRIB files
    grib_files = sorted(input_path.glob(pattern))

    if not grib_files:
        print(f"No GRIB files found in {input_dir}")
        return {**utils.init_results_dict(), 'total': 0}

    print(f"Found {len(grib_files)} GRIB files to process")
    print(f"Output directory: {output_dir}\n")

    # Process each file
    results = utils.init_results_dict()

    for grib_file in grib_files:
        # Check if already processed
        output_filename = grib_file.stem + config.PROCESSED_SUFFIX
        output_file = output_path / output_filename

        if output_file.exists():
            print(f"Skipping {grib_file.name} (already processed)")
            results['skipped'] += 1
        else:
            success = process_grib_file(grib_file, output_dir, bands)
            results['success' if success else 'failed'] += 1

        print()  # Blank line between files

    # Add total and print summary
    results['total'] = len(grib_files)
    utils.print_summary("Processing Summary", results)

    return results


if __name__ == "__main__":
    print("GRIB File Processor")
    print("=" * 60)

    # Process all GRIB files using config defaults
    results = process_all_grib_files(
        input_dir=str(config.RAW_GRIB_DIR.resolve()),
        output_dir=str(config.PROCESSED_DIR.resolve())
    )
