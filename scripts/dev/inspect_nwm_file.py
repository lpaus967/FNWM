"""
Inspect NWM NetCDF file to understand feature_id structure
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

import xarray as xr
from ingest.nwm_client import NWMClient
from datetime import datetime, timezone

print("=" * 80)
print("INSPECTING NWM NETCDF FILE")
print("=" * 80)

# Download a file
client = NWMClient()
filepath = client.download_product(
    product="analysis_assim",
    reference_time=datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc),
    forecast_hour=0,
    domain="conus"
)

print(f"\nFile: {filepath}")
print(f"\nOpening with xarray...")

# Open with xarray
ds = xr.open_dataset(filepath)

print(f"\n{'='*80}")
print("DIMENSIONS")
print("=" * 80)
for dim in ds.dims:
    print(f"  {dim}: {ds.dims[dim]}")

print(f"\n{'='*80}")
print("VARIABLES")
print("=" * 80)
for var in ds.variables:
    print(f"  {var}:")
    print(f"    Type: {ds[var].dtype}")
    print(f"    Dims: {ds[var].dims}")
    print(f"    Shape: {ds[var].shape}")
    if ds[var].size < 20:  # If small, show all values
        print(f"    Values: {ds[var].values}")
    else:  # Otherwise show first 10
        print(f"    First 10 values: {ds[var].values.flat[:10]}")
    print()

print(f"{'='*80}")
print("GLOBAL ATTRIBUTES")
print("=" * 80)
for attr in ds.attrs:
    print(f"  {attr}: {ds.attrs[attr]}")

print(f"\n{'='*80}")
print("FEATURE_ID ANALYSIS")
print("=" * 80)
feature_ids = ds['feature_id'].values
print(f"Total feature IDs: {len(feature_ids):,}")
print(f"Min feature_id: {feature_ids.min()}")
print(f"Max feature_id: {feature_ids.max()}")
print(f"Data type: {feature_ids.dtype}")
print(f"\nFirst 20 feature IDs:")
for i in range(min(20, len(feature_ids))):
    print(f"  [{i}] {feature_ids[i]}")

ds.close()
