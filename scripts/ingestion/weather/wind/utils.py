#!/usr/bin/env python3
"""
Utility functions for HRRR Wind Data Pipeline

Common helper functions used across multiple modules.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict
from zoneinfo import ZoneInfo
import config


def ensure_directory(directory: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        directory: Path to directory

    Returns:
        Path: The directory path
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def print_summary(title: str, results: Dict[str, int], separator_width: int = 60) -> None:
    """
    Print a formatted summary of results.

    Args:
        title: Title for the summary
        results: Dictionary with 'success', 'failed', 'skipped' keys
        separator_width: Width of separator line
    """
    print(f"\n{'=' * separator_width}")
    print(f"{title}:")
    print(f"  Success: {results.get('success', 0)}")
    print(f"  Failed: {results.get('failed', 0)}")
    print(f"  Skipped: {results.get('skipped', 0)}")
    if 'total' in results:
        print(f"  Total: {results['total']}")
    print(f"{'=' * separator_width}")


def get_current_time_est() -> datetime:
    """
    Get current time in Eastern Standard Time.

    Returns:
        datetime: Current time in EST (timezone-naive)
    """
    utc_now = datetime.now(ZoneInfo("UTC"))
    est_now = utc_now.astimezone(ZoneInfo(config.TIMEZONE))
    return est_now.replace(tzinfo=None)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size (e.g., "12.3 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.1f} GB"


def find_nearest_hour(target_hour: int, available_hours: list, prefer_future: bool = True) -> int:
    """
    Find the nearest available hour to the target hour.

    Args:
        target_hour: Target hour (0-23)
        available_hours: List of available hours
        prefer_future: If True, prefer future hours over past hours

    Returns:
        int: Nearest available hour, or None if no hours available
    """
    if not available_hours:
        return None

    if target_hour in available_hours:
        return target_hour

    # Calculate distances
    distances = []
    for hour in available_hours:
        diff = abs(hour - target_hour)
        # Consider wrapping around midnight
        wrapped_diff = min(diff, 24 - diff)

        # Prefer future hours if specified
        if prefer_future and hour >= target_hour:
            priority = 0  # Higher priority
        else:
            priority = 1  # Lower priority

        distances.append((wrapped_diff, priority, hour))

    # Sort by distance, then priority
    distances.sort()
    return distances[0][2]


def init_results_dict() -> Dict[str, int]:
    """
    Initialize a results dictionary with standard keys.

    Returns:
        dict: Results dictionary with success, failed, skipped set to 0
    """
    return {'success': 0, 'failed': 0, 'skipped': 0}
