# FNWM Setup Guide for Conda Users

This guide is specifically for developers using **Conda** (Anaconda/Miniconda) instead of Python's built-in venv.

---

## Why Conda for This Project?

Conda is excellent for this project because it:
- Handles complex scientific dependencies (NetCDF, xarray, geopandas) better than pip
- Manages system-level libraries automatically
- Provides better package conflict resolution
- Isolates environments more reliably for data science work

---

## Prerequisites

- **Conda** (Anaconda or Miniconda) installed
- **Git** installed
- **Docker** (optional, for database)

### Installing Miniconda (if needed)

**Windows:**
```bash
# Download from: https://docs.conda.io/en/latest/miniconda.html
# Or use winget:
winget install Anaconda.Miniconda3
```

**Mac/Linux:**
```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```

---

## Quick Start with Conda

### 1. Clone Repository

```bash
cd "C:\Users\lpaus\GitHub Connections"
cd FNWM
```

### 2. Create Conda Environment

```bash
# Create environment from environment.yml
conda env create -f environment.yml

# This creates an environment named 'fnwm'
```

**Alternative: Manual creation**
```bash
# If you want to customize the environment name:
conda env create -f environment.yml -n my-fnwm-env
```

### 3. Activate Environment

```bash
conda activate fnwm
```

**Important:** You need to activate this environment every time you work on the project.

### 4. Verify Installation

```bash
# Check Python version
python --version  # Should be 3.11.x

# Verify key packages
conda list | grep pandas
conda list | grep xarray
conda list | grep fastapi

# Check environment
conda info --envs
```

### 5. Configure Environment Variables

```bash
# Your .env file is already created, just edit it:
notepad .env  # Windows
# or
nano .env     # Mac/Linux
```

Update at minimum:
```bash
DATABASE_URL=postgresql://username:password@localhost:5432/fnwm
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=fnwm
DATABASE_USER=your_username
DATABASE_PASSWORD=your_password
```

### 6. Install Pre-commit Hooks

```bash
pre-commit install
```

### 7. Set Up Database (Optional - Docker)

```bash
# Start PostgreSQL with TimescaleDB
docker run -d \
  --name fnwm-db \
  -e POSTGRES_PASSWORD=dev_password \
  -e POSTGRES_DB=fnwm \
  -p 5432:5432 \
  timescale/timescaledb-ha:pg15
```

---

## Conda-Specific Commands

### Environment Management

```bash
# Activate environment
conda activate fnwm

# Deactivate environment
conda deactivate

# List all environments
conda env list

# Update environment from environment.yml
conda env update -f environment.yml --prune

# Export your current environment
conda env export > environment-freeze.yml

# Remove environment (if needed)
conda env remove -n fnwm
```

### Package Management

```bash
# Install additional conda package
conda install -c conda-forge package_name

# Install additional pip package
pip install package_name

# Update all packages
conda update --all

# List installed packages
conda list

# Search for a package
conda search package_name
```

### Creating Environment Snapshots

```bash
# Full environment snapshot (includes all dependencies)
conda env export > environment-lock.yml

# Minimal environment (just what you explicitly installed)
conda env export --from-history > environment-minimal.yml
```

---

## Daily Workflow with Conda

### Starting Your Work Session

```bash
# 1. Navigate to project
cd "C:\Users\lpaus\GitHub Connections\FNWM"

# 2. Activate conda environment
conda activate fnwm

# 3. Pull latest changes
git pull

# 4. Update dependencies if environment.yml changed
conda env update -f environment.yml --prune

# 5. Start coding!
```

### Running Development Tasks

All Makefile commands work the same:

```bash
make test          # Run tests
make format        # Format code
make lint          # Run linters
make run-api       # Start API server
```

### Ending Your Work Session

```bash
# Commit your work
git add .
git commit -m "Your commit message"
git push

# Deactivate environment (optional)
conda deactivate
```

---

## Using Jupyter Notebooks

Jupyter is included in the conda environment:

```bash
# Activate environment
conda activate fnwm

# Start Jupyter
jupyter notebook

# Or Jupyter Lab
jupyter lab
```

Your notebooks in the `notebooks/` directory will have access to all installed packages.

---

## Conda vs Venv Reference

| Task | venv | conda |
|------|------|-------|
| Create environment | `python -m venv venv` | `conda env create -f environment.yml` |
| Activate | `venv\Scripts\activate` | `conda activate fnwm` |
| Deactivate | `deactivate` | `conda deactivate` |
| Install package | `pip install package` | `conda install package` |
| List packages | `pip list` | `conda list` |
| Update environment | `pip install -r requirements.txt` | `conda env update -f environment.yml` |
| Export environment | `pip freeze > requirements.txt` | `conda env export > environment.yml` |

---

## Troubleshooting

### Issue: Conda takes forever to solve environment

**Solution:** Use mamba (faster conda solver)
```bash
# Install mamba
conda install -c conda-forge mamba

# Use mamba instead of conda
mamba env create -f environment.yml
mamba install package_name
```

### Issue: Package conflicts

**Solution:** Update conda and retry
```bash
conda update conda
conda env create -f environment.yml --force
```

### Issue: Jupyter can't find the conda environment

**Solution:** Install ipykernel
```bash
conda activate fnwm
conda install ipykernel
python -m ipykernel install --user --name=fnwm
```

### Issue: Pre-commit hooks fail

**Solution:** Ensure pre-commit is installed in the conda environment
```bash
conda activate fnwm
conda install -c conda-forge pre-commit
pre-commit install
```

---

## Updating Dependencies

When you need to add a new package:

### Option 1: Add to environment.yml (Recommended)

```yaml
# Edit environment.yml
dependencies:
  - new-package=1.0.*
```

Then update:
```bash
conda env update -f environment.yml --prune
```

### Option 2: Install directly (Quick testing)

```bash
conda install -c conda-forge new-package

# If not available in conda:
pip install new-package
```

**Important:** If you install directly, remember to add it to `environment.yml` so others get it too!

---

## Conda Environment Best Practices

1. **Always activate the environment** before working
   ```bash
   conda activate fnwm
   ```

2. **Update environment.yml**, not just installing packages
   - This ensures reproducibility for other developers

3. **Use `conda install` for scientific packages**, `pip` for pure Python
   - Prefer conda for: numpy, pandas, xarray, geopandas, scipy
   - Use pip for: FastAPI, pydantic, many web frameworks

4. **Commit environment.yml changes** to git
   - Don't commit environment-lock.yml (too specific)

5. **Periodically clean conda cache**
   ```bash
   conda clean --all
   ```

---

## IDE Integration

### VS Code

1. Install Python extension
2. Select interpreter:
   - Ctrl+Shift+P → "Python: Select Interpreter"
   - Choose the `fnwm` conda environment

### PyCharm

1. Settings → Project → Python Interpreter
2. Add Interpreter → Conda Environment
3. Select existing environment: `fnwm`

### Jupyter

The environment is automatically available in Jupyter:
```bash
conda activate fnwm
jupyter notebook
```

---

## Next Steps

You're all set! Now proceed with:

1. **Configure `.env`** with your database credentials
2. **Start database**: `docker run ...` or use local PostgreSQL
3. **Begin implementation**: Follow **IMPLEMENTATION_GUIDE.md** starting with EPIC 1

---

## Quick Reference Card

```bash
# Daily commands
conda activate fnwm              # Start working
make test                        # Run tests
make format                      # Format code
make lint                        # Check code quality
git add . && git commit -m "..."  # Commit work
conda deactivate                 # Done for the day

# Environment maintenance
conda env update -f environment.yml --prune  # Update packages
conda list                                   # See what's installed
conda env export > environment.yml           # Save current state
```

---

**You're ready to start coding with Conda!**

Proceed to **IMPLEMENTATION_GUIDE.md** and start with EPIC 1, Ticket 1.1.
