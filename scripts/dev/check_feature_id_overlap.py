"""
Check if NWM feature_ids overlap with NHD COMIDs
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import xarray as xr

load_dotenv()

print("=" * 80)
print("CHECKING NWM vs NHD FEATURE ID OVERLAP")
print("=" * 80)

# Get NHD feature IDs
print("\n1. Getting NHD feature IDs from database...")
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text("SELECT nhdplusid FROM nhd_flowlines"))
    nhd_ids = set(row[0] for row in result)

print(f"   NHD COMIDs in database: {len(nhd_ids):,}")
print(f"   Min: {min(nhd_ids)}")
print(f"   Max: {max(nhd_ids)}")
print(f"   Sample: {list(sorted(nhd_ids))[:5]}")

# Get NWM feature IDs
print("\n2. Getting NWM feature IDs from NetCDF...")
nc_file = Path("data/raw/nwm/analysis_assim_20260105_t00z_f000_conus.nc")
ds = xr.open_dataset(nc_file)
nwm_ids = set(ds['feature_id'].values.tolist())

print(f"   NWM feature_ids in file: {len(nwm_ids):,}")
print(f"   Min: {min(nwm_ids)}")
print(f"   Max: {max(nwm_ids)}")
print(f"   Sample: {list(sorted(nwm_ids))[:5]}")

# Check overlap
print("\n3. Checking overlap...")
overlap = nhd_ids.intersection(nwm_ids)

print(f"   Overlapping IDs: {len(overlap):,}")

if len(overlap) > 0:
    print(f"\n   ✅ SUCCESS! Found {len(overlap)} matching IDs")
    print(f"   Sample overlapping IDs:")
    for fid in list(sorted(overlap))[:10]:
        print(f"      {fid}")
else:
    print(f"\n   ❌ NO OVERLAP FOUND")

    # Check if any NHD IDs are in the NWM range
    print(f"\n4. Checking if NHD IDs fall within NWM range...")
    nwm_min = min(nwm_ids)
    nwm_max = max(nwm_ids)

    nhd_in_range = [fid for fid in nhd_ids if nwm_min <= fid <= nwm_max]
    print(f"   NHD IDs within NWM range ({nwm_min:,} to {nwm_max:,}): {len(nhd_in_range)}")

    if nhd_in_range:
        print(f"   These NHD IDs are in range but not in NWM file:")
        for fid in sorted(nhd_in_range)[:10]:
            print(f"      {fid}")

    # Check if NWM has any IDs starting with 2300...
    print(f"\n5. Checking for NWM IDs starting with 2300...")
    nwm_2300 = [fid for fid in nwm_ids if 23000000000000 <= fid < 24000000000000]
    print(f"   NWM IDs in 2300... range: {len(nwm_2300)}")

    if nwm_2300:
        print(f"   Sample:")
        for fid in sorted(nwm_2300)[:10]:
            print(f"      {fid}")

ds.close()
