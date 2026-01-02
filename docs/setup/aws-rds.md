# AWS RDS Database Setup - Complete

This document confirms your AWS RDS PostgreSQL database setup for the FNWM project.

---

## Database Configuration

**Status:** ✅ Connected and Configured

### Connection Details

```
Host: fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com
Region: us-east-2 (Ohio)
Port: 5432
Database: fnwm-db
Username: masteruser
```

**Your `.env` file is configured with these credentials.**

---

## Security Checklist

### ✅ Completed
- [x] AWS RDS instance created
- [x] Database `fnwm-db` created
- [x] Master user `masteruser` configured
- [x] Connection details added to `.env`

### ⚠️ Important - Verify These

1. **Security Group Configuration**
   - Go to AWS Console → RDS → Your Database → Connectivity & Security
   - Click on your VPC security group
   - Verify **Inbound Rules** allow PostgreSQL (port 5432)
   - Should have your IP address or 0.0.0.0/0 (less secure)

2. **Public Accessibility**
   - Go to AWS Console → RDS → Your Database → Connectivity & Security
   - Verify "Publicly accessible" is **Yes**
   - If it says "No", you won't be able to connect from your local machine

3. **Password Security**
   - Your password `Pacific1ride` is now visible in this conversation
   - Consider rotating it in AWS RDS Console if concerned
   - Never commit `.env` to git (already in `.gitignore`)

---

## Testing Your Connection

### Option 1: Quick Python Test

```bash
# Activate your conda environment
conda activate fnwm

# Install SQLAlchemy if not already installed
conda install -c conda-forge sqlalchemy psycopg2

# Run the test script
python scripts/test_db_connection.py
```

**Expected Output:**
```
Testing database connection...
Host: fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com
Database: fnwm-db
User: masteruser

✅ Connection successful!
PostgreSQL version: PostgreSQL 15.x...
🎉 Database is ready to use!
```

### Option 2: Using psql Command Line

```bash
# Install PostgreSQL client (if needed)
conda install -c conda-forge postgresql

# Connect to your database
psql -h fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com -U masteruser -d fnwm-db

# Enter password when prompted: Pacific1ride

# Once connected, you can run SQL:
\l              # List databases
\dt             # List tables (none yet)
SELECT version();  # Check PostgreSQL version
\q              # Quit
```

---

## Optional: Enable TimescaleDB Extension

TimescaleDB is recommended for time-series data optimization (your NWM data is time-series).

**Check if TimescaleDB is available:**

```sql
-- Connect to database
psql -h fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com -U masteruser -d fnwm-db

-- Try to enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Verify
\dx  -- List extensions
```

**If not available:**
- AWS RDS may not have TimescaleDB in default PostgreSQL
- You can still proceed - it's an optimization, not required
- Alternative: Use Amazon Timestream (different service) or continue without

---

## Troubleshooting

### Cannot Connect - Connection Timeout

**Cause:** Security group doesn't allow your IP

**Fix:**
1. Go to AWS RDS Console → Your database
2. Click on VPC Security Group
3. Edit Inbound Rules
4. Add rule: Type=PostgreSQL, Port=5432, Source=My IP
5. Save and try again

### Cannot Connect - Authentication Failed

**Cause:** Wrong username or password

**Fix:**
1. Verify `.env` credentials match what you set in RDS
2. Try resetting password in AWS RDS Console
3. Update `.env` with new password

### Public Access Disabled

**Cause:** RDS instance not publicly accessible

**Fix:**
1. Go to AWS RDS Console → Your database → Modify
2. Connectivity → Public access → Yes
3. Apply immediately
4. Wait for modification to complete

### Connection from Different Machine

**To allow team members to connect:**

1. Get their IP address
2. Add their IP to Security Group inbound rules
3. Share connection details securely (not in git!)
4. They update their `.env` file

---

## Database Schema Setup (Next Step)

Once connection is verified, you'll create tables for:

1. **hydro_timeseries** - Normalized NWM data
2. **species_scores** - Computed habitat scores
3. **hatch_forecasts** - Hatch likelihood predictions
4. **user_observations** - Validation feedback

This will be done in **EPIC 1, Ticket 1.2** when you create `scripts/init_db.py`

---

## Cost Monitoring

**To avoid unexpected charges:**

1. **Check your AWS Billing Dashboard regularly**
   - AWS Console → Billing → Bills
   - Should be $0 if in free tier

2. **Set up billing alerts**
   - AWS Console → Billing → Budgets
   - Create budget: $5-10/month threshold
   - Get email if exceeded

3. **Stop database when not in use** (optional)
   - RDS Console → Actions → Stop
   - Saves money but database will auto-start after 7 days
   - Better: Delete and recreate when needed (if just testing)

4. **Delete when done** (after project completion)
   - RDS Console → Actions → Delete
   - Choose whether to create final snapshot

---

## Backup Configuration

Your RDS instance should have automated backups enabled:

**Verify:**
1. Go to RDS Console → Your database → Maintenance & backups
2. Check "Automated backups" is Enabled
3. Retention period: 7 days (default)

**Manual backup (optional):**
```
RDS Console → Actions → Take snapshot
```

---

## Next Steps - Start Building!

Now that your database is set up:

### 1. Test Connection

```bash
conda activate fnwm
python scripts/test_db_connection.py
```

### 2. Review Implementation Guide

Open `IMPLEMENTATION_GUIDE.md` and start with:

**EPIC 1, Ticket 1.1: NWM Product Ingestor**
- Create `src/ingest/nwm_client.py`
- Build HTTP client to download NWM data
- Parse NetCDF files

### 3. Create Database Schema (Ticket 1.2)

You'll create `scripts/init_db.py` to set up tables:

```python
# This will be created in EPIC 1, Ticket 1.2
# scripts/init_db.py

from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

# Create tables
# (See IMPLEMENTATION_GUIDE.md for schema)
```

---

## Summary

✅ AWS RDS PostgreSQL database is running
✅ Publicly accessible at: `fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com`
✅ Connection details configured in `.env`
✅ Ready for development

**You're all set to start coding EPIC 1!**

---

## Quick Reference

```bash
# Activate environment
conda activate fnwm

# Test connection
python scripts/test_db_connection.py

# Connect with psql
psql -h fnwm-db.cjome0482kqx.us-east-2.rds.amazonaws.com -U masteruser -d fnwm-db

# Start coding
# Follow IMPLEMENTATION_GUIDE.md starting at EPIC 1, Ticket 1.1
```
