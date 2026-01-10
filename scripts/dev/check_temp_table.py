"""Check temperature table structure"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    result = conn.execute(text('SELECT * FROM observations.temperature_timeseries LIMIT 3'))
    print('Columns:', [col for col in result.keys()])
    print('\nSample data:')
    for row in result:
        print(dict(row._mapping))
