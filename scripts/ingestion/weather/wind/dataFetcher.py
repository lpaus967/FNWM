#!/usr/bin/env python3
"""
HRRR Wind Data Fetcher

Downloads HRRR wrfsfcf00.grib2 files from NOAA NOMADS server.
Supports fetching data for specific hours or the file closest to current time.
"""

import requests
from datetime import datetime
import re
import os
from pathlib import Path
from urllib.parse import urljoin

import config
import utils


def get_hrrr_url(date=None):
    """
    Generate the HRRR data URL for a given date.

    Args:
        date: datetime object or None (uses today's date if None)

    Returns:
        str: URL to HRRR data directory
    """
    if date is None:
        date = datetime.now()

    date_str = date.strftime('%Y%m%d')
    return f"{config.HRRR_BASE_URL}hrrr.{date_str}/conus/"


def parse_directory_listing(url):
    """
    Parse NOAA directory listing to extract GRIB file information.

    Args:
        url: URL to the directory listing

    Returns:
        list: List of dictionaries containing file information
    """
    try:
        response = requests.get(url, timeout=config.DIRECTORY_LISTING_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching directory listing: {e}")
        return []

    # Parse HTML to find file links (filename, date, time, size)
    pattern = r'<a href="([^"]+)">.*?(\d{2}-\w{3}-\d{4})\s+(\d{2}:\d{2})\s+(\S+)'
    matches = re.findall(pattern, response.text)

    files = []
    for filename, date, time, size in matches:
        if filename.endswith('.grib2') and not filename.endswith('.idx'):
            files.append({
                'filename': filename,
                'date': date,
                'time': time,
                'size': size,
                'url': urljoin(url, filename)
            })

    return files


def extract_hour_from_filename(filename):
    """
    Extract hour from HRRR filename.

    Args:
        filename: HRRR filename

    Returns:
        int: Hour (0-23), or None if not found
    """
    pattern = r'hrrr\.t(\d{2})z\.wrfsfcf00\.grib2'
    match = re.match(pattern, filename)
    return int(match.group(1)) if match else None


def download_file(url, destination_path, filename):
    """
    Download a file from URL to destination with progress tracking.

    Args:
        url: URL to download from
        destination_path: Directory to save file
        filename: Name of the file

    Returns:
        bool: True if successful, False otherwise
    """
    filepath = os.path.join(destination_path, filename)

    # Check if file already exists
    if os.path.exists(filepath):
        print(f"File already exists: {filename}")
        return True

    try:
        print(f"Downloading {filename}...")
        response = requests.get(url, stream=True, timeout=config.DOWNLOAD_TIMEOUT)
        response.raise_for_status()

        # Get file size for progress tracking
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=config.DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Print progress
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        downloaded_str = utils.format_file_size(downloaded)
                        total_str = utils.format_file_size(total_size)
                        print(f"\rProgress: {percent:.1f}% ({downloaded_str} / {total_str})", end='')

        print(f"\n✓ Downloaded: {filename}")
        return True

    except requests.RequestException as e:
        print(f"\n✗ Error downloading {filename}: {e}")
        # Clean up partial download
        if os.path.exists(filepath):
            os.remove(filepath)
        return False


def find_files_for_hours(files, hours):
    """
    Find GRIB files for specified hours, with fallback to nearest available.

    Args:
        files: List of available files from directory listing
        hours: List of target hours

    Returns:
        list: List of file info dictionaries for matched files
    """
    # Create a lookup of available hours
    available_files = {}
    for file_info in files:
        hour = extract_hour_from_filename(file_info['filename'])
        if hour is not None:
            available_files[hour] = file_info

    available_hours = list(available_files.keys())
    target_files = []

    for hour in hours:
        if hour in available_files:
            target_files.append(available_files[hour])
        else:
            # Find nearest available hour
            nearest = utils.find_nearest_hour(hour, available_hours, prefer_future=True)
            if nearest is not None:
                print(f"Warning: Hour {hour:02d} not available, using hour {nearest:02d} instead")
                target_files.append(available_files[nearest])
            else:
                print(f"Warning: No suitable alternative found for hour {hour:02d}")

    return target_files


def download_files(files, output_dir):
    """
    Download a list of files to output directory.

    Args:
        files: List of file info dictionaries
        output_dir: Destination directory

    Returns:
        dict: Summary of download results
    """
    results = utils.init_results_dict()

    for file_info in files:
        filepath = os.path.join(output_dir, file_info['filename'])

        if os.path.exists(filepath):
            print(f"\nSkipping {file_info['filename']} (already exists)")
            results['skipped'] += 1
        else:
            print()  # New line for better formatting
            success = download_file(file_info['url'], output_dir, file_info['filename'])
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1

    return results


def fetch_hrrr_data(hours=None, output_dir=None, date=None):
    """
    Fetch HRRR wrfsfcf00.grib2 files for specified hours.

    Args:
        hours: List of hours (0-23) to download data for (default from config)
        output_dir: Directory to save downloaded files (default from config)
        date: datetime object or None (uses today's date if None)

    Returns:
        dict: Summary of download results
    """
    hours = hours or config.DEFAULT_FORECAST_HOURS
    output_dir = output_dir or str(config.RAW_GRIB_DIR.resolve())

    # Ensure output directory exists
    utils.ensure_directory(output_dir)

    # Get and parse directory listing
    url = get_hrrr_url(date)
    print(f"Fetching data from: {url}")

    files = parse_directory_listing(url)
    if not files:
        print("No files found in directory listing.")
        return utils.init_results_dict()

    # Find files for specified hours
    target_files = find_files_for_hours(files, hours)

    if not target_files:
        print("No matching files found.")
        return utils.init_results_dict()

    print(f"\nFound {len(target_files)} files to download:")
    for f in target_files:
        print(f"  - {f['filename']} ({f['size']})")

    # Download files
    results = download_files(target_files, output_dir)
    results['total'] = len(target_files)

    # Print summary
    utils.print_summary("Download Summary", results)

    return results


def fetch_current_time_hrrr(output_dir=None, date=None):
    """
    Fetch the HRRR wrfsfcf00.grib2 file closest to the current time.

    Args:
        output_dir: Directory to save downloaded file (default from config)
        date: datetime object or None (uses current time in EST if None)

    Returns:
        dict: Summary of download results
    """
    output_dir = output_dir or str(config.RAW_GRIB_DIR.resolve())
    date = date or utils.get_current_time_est()

    # Ensure output directory exists
    utils.ensure_directory(output_dir)

    # Get and parse directory listing
    url = get_hrrr_url(date)
    print(f"Fetching data from: {url}")
    print(f"Current time: {date.strftime('%Y-%m-%d %H:%M:%S')}")

    files = parse_directory_listing(url)
    if not files:
        print("No files found in directory listing.")
        return utils.init_results_dict()

    # Extract available hours
    available_files = {}
    for file_info in files:
        hour = extract_hour_from_filename(file_info['filename'])
        if hour is not None:
            file_info['hour'] = hour
            available_files[hour] = file_info

    if not available_files:
        print("No wrfsfcf00.grib2 files found in directory listing.")
        return utils.init_results_dict()

    # Find closest hour
    current_hour = date.hour
    available_hours = list(available_files.keys())
    closest_hour = utils.find_nearest_hour(current_hour, available_hours, prefer_future=True)

    if closest_hour is None:
        print("Could not determine closest file.")
        return utils.init_results_dict()

    closest_file = available_files[closest_hour]

    print(f"\nSelected file closest to current time:")
    print(f"  - {closest_file['filename']} (hour {closest_hour:02d}, {closest_file['size']})")
    print(f"  - Current hour: {current_hour:02d}, difference: {abs(closest_hour - current_hour)} hours")

    # Download file
    results = download_files([closest_file], output_dir)
    results['total'] = 1

    # Print summary
    utils.print_summary("Download Summary", results)

    return results


if __name__ == "__main__":
    print("HRRR Data Fetcher")
    print("=" * 60)

    # Default: Fetch closest file to current time
    results = fetch_current_time_hrrr()
