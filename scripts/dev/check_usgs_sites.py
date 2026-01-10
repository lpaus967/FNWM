"""Quick script to check USGS_Flowsites table data"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT "siteId", name, state, "agencyCode", network, "noaaId",
               ST_X(geom) as lon, ST_Y(geom) as lat
        FROM "USGS_Flowsites"
        ORDER BY id
        LIMIT 5;
    '''))

    print('USGS_Flowsites Sample Data:')
    print('=' * 80)
    for row in result:
        print(f'Site ID: {row[0]}')
        print(f'  Name: {row[1]}')
        print(f'  State: {row[2]}')
        print(f'  Agency: {row[3]}')
        print(f'  Network: {row[4]}')
        print(f'  NOAA ID: {row[5]}')
        print(f'  Coordinates: ({row[6]:.4f}, {row[7]:.4f})')
        print()
