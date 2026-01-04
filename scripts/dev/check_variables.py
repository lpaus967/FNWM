from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.begin() as conn:
    result = conn.execute(text('''
        SELECT variable, COUNT(*) as count
        FROM hydro_timeseries
        GROUP BY variable
        ORDER BY variable
    '''))

    print('Variables currently in database:')
    for row in result:
        print(f'  {row[0]}: {row[1]:,} records')
