#!/usr/bin/env python3
"""
HRRR Wind Data Pipeline

Complete pipeline for downloading, processing, and uploading HRRR wind data to S3.
Automatically fetches the HRRR file closest to the current time, processes it,
and uploads to AWS S3.
"""

import sys
from datetime import datetime

import config
import utils
import dataFetcher
import processGrib
import uploadToS3


def print_pipeline_header():
    """Print pipeline header with current time information."""
    current_time = utils.get_current_time_est()
    utc_time = datetime.utcnow()

    print("=" * 70)
    print("HRRR Wind Data Pipeline")
    print(f"Date (EST): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Date (UTC): {utc_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()


def print_step_header(step_num, title):
    """Print formatted step header."""
    print("\n" + "=" * 70)
    print(f"STEP {step_num}: {title}")
    print("=" * 70)


def check_step_results(results, step_name):
    """
    Check step results and return appropriate status.

    Args:
        results: Results dictionary from step
        step_name: Name of the step for error messages

    Returns:
        bool: True if step succeeded, False if should abort
    """
    if results.get('failed', 0) > 0:
        print(f"\n⚠ Warning: {results['failed']} files failed in {step_name}")

    if results.get('success', 0) == 0 and results.get('skipped', 0) == 0:
        print(f"\n✗ Error: No data was processed in {step_name}. Aborting pipeline.")
        return False

    return True


def main():
    """Run the complete wind data pipeline."""
    print_pipeline_header()

    current_time = utils.get_current_time_est()

    # Step 1: Fetch HRRR data
    print_step_header(1, "Fetching HRRR Data (closest to current time)")

    try:
        fetch_results = dataFetcher.fetch_current_time_hrrr(
            output_dir=str(config.RAW_GRIB_DIR.resolve()),
            date=current_time
        )

        if not check_step_results(fetch_results, "data fetching"):
            return 1

    except Exception as e:
        print(f"\n✗ Error in data fetching step: {e}")
        return 1

    # Step 2: Process GRIB files
    print_step_header(2, "Processing GRIB Files")

    try:
        process_results = processGrib.process_all_grib_files(
            input_dir=str(config.RAW_GRIB_DIR.resolve()),
            output_dir=str(config.PROCESSED_DIR.resolve())
        )

        if not check_step_results(process_results, "GRIB processing"):
            return 1

    except Exception as e:
        print(f"\n✗ Error in processing step: {e}")
        return 1

    # Step 3: Upload to S3
    print_step_header(3, "Uploading to S3")

    try:
        uploadToS3.main()
    except Exception as e:
        print(f"\n✗ Error in upload step: {e}")
        return 1

    # Print final summary
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"Data Fetching:   {fetch_results['success']} successful, "
          f"{fetch_results['failed']} failed, {fetch_results['skipped']} skipped")
    print(f"GRIB Processing: {process_results['success']} successful, "
          f"{process_results['failed']} failed, {process_results['skipped']} skipped")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
