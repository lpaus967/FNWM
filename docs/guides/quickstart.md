# FNWM Quick Start Guide

Get up and running with the Fisheries National Water Model project in minutes.

---

## Prerequisites

- **Python 3.10 or higher**
- **Git**
- **Docker** (optional, for local database)
- **PostgreSQL 15+** (if not using Docker)

---

## Initial Setup

### 1. Clone and Navigate

```bash
git clone <your-repo-url>
cd FNWM
```

### 2. Run Setup Script

This creates the full directory structure and initial config files:

```bash
python setup_project.py
```

### 3. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

```bash
# Production dependencies
pip install -r requirements.txt

# Development dependencies (includes testing, linting, etc.)
pip install -r requirements-dev.txt
```

### 5. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your settings
# At minimum, configure database connection
```

**Windows:**
```bash
copy .env.example .env
notepad .env
```

### 6. Set Up Database (Docker Option)

```bash
# Start PostgreSQL with TimescaleDB
docker run -d \
  --name fnwm-db \
  -e POSTGRES_PASSWORD=dev_password \
  -e POSTGRES_DB=fnwm \
  -p 5432:5432 \
  timescale/timescaledb-ha:pg15
```

**Or use the Makefile:**
```bash
make db-up
```

### 7. Initialize Database Schema

```bash
# TODO: Will be created in EPIC 1
# python scripts/init_db.py
```

### 8. Install Pre-commit Hooks (Optional but Recommended)

```bash
pre-commit install
```

This will automatically format and lint your code before each commit.

---

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Or use Makefile
make test
make test-cov
```

### Code Formatting

```bash
# Format code with black and isort
black src/ tests/
isort src/ tests/

# Or use Makefile
make format
```

### Linting

```bash
# Run linters
flake8 src/ tests/
mypy src/

# Or use Makefile
make lint
```

### Running the API (Once Implemented)

```bash
# Start FastAPI development server
uvicorn src.api.main:app --reload

# Or use Makefile
make run-api
```

---

## Project Structure Overview

```text
FNWM/
├── src/                    # Source code (organized by EPIC)
│   ├── ingest/            # EPIC 1: NWM data ingestion
│   ├── normalize/         # EPIC 1: Time normalization
│   ├── metrics/           # EPIC 2: Derived metrics
│   ├── temperature/       # EPIC 3: Temperature integration
│   ├── species/           # EPIC 4: Species scoring
│   ├── hatches/           # EPIC 4: Hatch likelihood
│   ├── confidence/        # EPIC 5: Uncertainty
│   ├── api/               # EPIC 6: API endpoints
│   └── validation/        # EPIC 7: Feedback loop
├── config/                # YAML configs (science-owned)
│   ├── species/           # Species thresholds
│   ├── hatches/           # Hatch signatures
│   └── thresholds/        # Metric thresholds
├── tests/                 # Test suite
├── scripts/               # Utility scripts
├── notebooks/             # Jupyter notebooks for exploration
├── data/                  # Local data (not in git)
└── docs/                  # Documentation
```

---

## Common Commands (Makefile)

If you have `make` installed:

```bash
make help          # Show all available commands
make setup         # Initialize project structure
make install       # Install production dependencies
make install-dev   # Install dev dependencies
make test          # Run tests
make test-cov      # Run tests with coverage
make format        # Format code
make lint          # Run linters
make run-api       # Start API server
make db-up         # Start database (Docker)
make db-down       # Stop database
make clean         # Remove cache files
```

---

## Implementation Order

Follow the **IMPLEMENTATION_GUIDE.md** for detailed steps. Recommended order:

1. **EPIC 1** - Data Ingestion (Tickets 1.1, 1.2)
   - Get NWM data flowing into your database
   - Normalize time semantics

2. **EPIC 2** - Derived Metrics (Tickets 2.1, 2.2, 2.3)
   - Implement BDI, rising limb, velocity classification

3. **EPIC 4** - Species Scoring (Tickets 4.1, 4.2)
   - Build scoring engine (can parallelize with EPIC 3)

4. **EPIC 3** - Temperature (Tickets 3.1, 3.2)
   - Add thermal suitability

5. **EPIC 5** - Confidence (Tickets 5.1, 5.2)
   - Quantify uncertainty

6. **EPIC 6** - API (Tickets 6.1, 6.2)
   - Expose everything via clean APIs

7. **EPIC 7** - Validation (Tickets 7.1, 7.2, 7.3)
   - Close the feedback loop

---

## Verifying Your Setup

After setup, verify everything is working:

```bash
# Check Python version
python --version  # Should be 3.10+

# Check packages installed
pip list | grep pandas
pip list | grep fastapi

# Run initial tests (once you write them)
pytest tests/

# Check database connection
# python -c "from sqlalchemy import create_engine; import os; from dotenv import load_dotenv; load_dotenv(); engine = create_engine(os.getenv('DATABASE_URL')); print('DB Connected!' if engine else 'Failed')"
```

---

## Getting Help

- **Implementation Guide**: See `IMPLEMENTATION_GUIDE.md` for detailed coding steps
- **PRD**: See `Claude-Context/prd.txt` for product requirements and design principles
- **Issues**: Check the GitHub Issues for known problems

---

## Next Steps

1. ✅ Complete initial setup (you're here!)
2. 📖 Read `IMPLEMENTATION_GUIDE.md` in detail
3. 🎯 Start with EPIC 1, Ticket 1.1 (NWM Product Ingestor)
4. 🧪 Write tests as you go
5. 📊 Validate metrics against known data

---

**Remember**: Shipping raw hydrology is easy. Shipping trusted fisheries intelligence is the work.
