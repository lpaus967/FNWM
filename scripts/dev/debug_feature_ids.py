"""
Debug script to compare NHD feature IDs with NWM feature IDs
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from ingest.nwm_client import NWMClient
from datetime import datetime, timezone

load_dotenv()

# Get NHD feature IDs from database
print("=" * 80)
print("GETTING NHD FEATURE IDS FROM DATABASE")
print("=" * 80)

engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT nhdplusid
        FROM nhd_flowlines
        ORDER BY nhdplusid
        LIMIT 10
    """))
    nhd_ids = [row[0] for row in result]

print(f"First 10 NHD feature IDs:")
for fid in nhd_ids:
    print(f"  {fid} (type: {type(fid).__name__})")

# Convert to set
nhd_id_set = set(nhd_ids)
print(f"\nTotal NHD IDs in set: {len(nhd_id_set)}")

# Get NWM feature IDs from a downloaded file
print("\n" + "=" * 80)
print("GETTING NWM FEATURE IDS FROM NETCDF FILE")
print("=" * 80)

client = NWMClient()
filepath = client.download_product(
    product="analysis_assim",
    reference_time=datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc),
    forecast_hour=0,
    domain="conus"
)

# Parse the file
df = client.parse_channel_rt(filepath)

print(f"\nTotal NWM feature IDs in file: {len(df):,}")
print(f"\nFirst 10 NWM feature IDs:")
for fid in df['feature_id'].head(10):
    print(f"  {fid} (type: {type(fid).__name__})")

print(f"\nDataFrame column types:")
print(df.dtypes)

# Check for overlap
nwm_ids_set = set(df['feature_id'].tolist())
overlap = nhd_id_set.intersection(nwm_ids_set)

print("\n" + "=" * 80)
print("COMPARISON")
print("=" * 80)
print(f"NHD IDs: {len(nhd_id_set):,}")
print(f"NWM IDs: {len(nwm_ids_set):,}")
print(f"Overlap: {len(overlap):,}")

if len(overlap) > 0:
    print(f"\nSample overlapping IDs:")
    for fid in list(overlap)[:10]:
        print(f"  {fid}")
else:
    print("\n⚠️  NO OVERLAP FOUND!")
    print("\nChecking if NHD IDs exist anywhere in NWM data...")

    # Check first NHD ID
    first_nhd_id = nhd_ids[0]
    exists = first_nhd_id in nwm_ids_set
    print(f"  Does {first_nhd_id} exist in NWM? {exists}")

    # Check data type compatibility
    print(f"\n  NHD ID type: {type(list(nhd_id_set)[0])}")
    print(f"  NWM ID type: {type(list(nwm_ids_set)[0])}")

    # Try type conversion
    nhd_id_set_int = {int(x) for x in nhd_id_set}
    nwm_ids_set_int = {int(x) for x in nwm_ids_set}
    overlap_converted = nhd_id_set_int.intersection(nwm_ids_set_int)
    print(f"\n  After int() conversion, overlap: {len(overlap_converted)}")
