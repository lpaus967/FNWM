"""
Cleanup orphaned ingestion jobs

Finds jobs that have been "running" for too long and marks them as failed.
This happens when a process is killed before it can update the ingestion_log.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))

print("Checking for orphaned ingestion jobs...")
print("=" * 60)

with engine.begin() as conn:
    # Find jobs that have been "running" for more than 1 hour
    result = conn.execute(text("""
        SELECT id, product, started_at,
               EXTRACT(EPOCH FROM (NOW() - started_at)) as duration_sec
        FROM nwm.ingestion_log
        WHERE status = 'running'
        AND EXTRACT(EPOCH FROM (NOW() - started_at)) > 3600
        ORDER BY started_at DESC
    """))

    orphaned_jobs = list(result)

    if not orphaned_jobs:
        print("No orphaned jobs found.")
    else:
        print(f"Found {len(orphaned_jobs)} orphaned job(s):\n")
        for job in orphaned_jobs:
            hours = job.duration_sec / 3600
            print(f"  Job #{job.id}: {job.product}")
            print(f"    Started: {job.started_at}")
            print(f"    Duration: {hours:.1f} hours")
            print()

        # Mark them as failed
        print("Marking orphaned jobs as failed...")
        conn.execute(text("""
            UPDATE nwm.ingestion_log
            SET
                status = 'failed',
                error_message = 'Process killed/orphaned - marked as failed during cleanup',
                completed_at = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))
            WHERE status = 'running'
            AND EXTRACT(EPOCH FROM (NOW() - started_at)) > 3600
        """))

        print(f"✓ Cleaned up {len(orphaned_jobs)} orphaned job(s)")

print()
print("=" * 60)
print("Cleanup complete!")
print()

# Show current status
with engine.begin() as conn:
    result = conn.execute(text("""
        SELECT status, COUNT(*) as count
        FROM nwm.ingestion_log
        GROUP BY status
        ORDER BY status
    """))

    print("Current ingestion job status:")
    for row in result:
        print(f"  {row.status}: {row.count}")
