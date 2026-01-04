from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.begin() as conn:
    # Check reach_metadata table
    result = conn.execute(text('''
        SELECT COUNT(*) as total,
               COUNT(latitude) as has_lat,
               COUNT(longitude) as has_lon
        FROM reach_metadata
    '''))

    row = result.fetchone()
    print(f"Reach metadata:")
    print(f"  Total records: {row[0]}")
    print(f"  Records with latitude: {row[1]}")
    print(f"  Records with longitude: {row[2]}")

    # Check sample
    result = conn.execute(text('''
        SELECT feature_id, latitude, longitude
        FROM reach_metadata
        WHERE latitude IS NOT NULL
        LIMIT 5
    '''))

    print(f"\nSample records:")
    for row in result:
        print(f"  Reach {row[0]}: {row[1]}, {row[2]}")
