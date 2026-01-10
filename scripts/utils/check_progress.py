"""Quick check of database progress"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.begin() as conn:
    # Check total records
    result = conn.execute(text("SELECT COUNT(*) FROM nwm.hydro_timeseries"))
    total = result.fetchone()[0]
    print(f"Total records in database: {total:,}")

    # Check by source
    result = conn.execute(text("""
        SELECT source, COUNT(*) as count
        FROM nwm.hydro_timeseries
        GROUP BY source
    """))
    print("\nRecords by source:")
    for row in result:
        print(f"  {row.source}: {row.count:,}")

    # Check ingestion log
    result = conn.execute(text("""
        SELECT id, product, status, records_ingested,
               EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - started_at)) as duration_sec
        FROM nwm.ingestion_log
        ORDER BY started_at DESC
        LIMIT 3
    """))
    print("\nRecent ingestion jobs:")
    for row in result:
        status_icon = "[OK]" if row.status == "success" else "[X]" if row.status == "failed" else "[...]"
        print(f"  {status_icon} #{row.id} {row.product}: {row.status} ({row.duration_sec:.1f}s)")
