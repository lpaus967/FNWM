"""
Setup script to initialize the FNWM project structure
Run this script after cloning the repository to set up directories and initial files
"""

import os
from pathlib import Path


def create_directory_structure():
    """Create the project directory structure"""

    directories = [
        # Source code directories (EPIC-aligned)
        "src/ingest",
        "src/normalize",
        "src/metrics",
        "src/temperature",
        "src/species",
        "src/hatches",
        "src/confidence",
        "src/api",
        "src/validation",
        "src/common",  # Shared utilities

        # Configuration directories
        "config/species",
        "config/hatches",
        "config/thresholds",

        # Data directories
        "data/raw/nwm",
        "data/processed",
        "data/cache",

        # Test directories
        "tests/unit",
        "tests/integration",
        "tests/fixtures",
        "tests/property",

        # Scripts directory
        "scripts",

        # Notebooks for exploration
        "notebooks",

        # Logs
        "logs",

        # Documentation
        "docs/api",
        "docs/architecture",
    ]

    for directory in directories:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        # Create __init__.py for Python packages
        if directory.startswith("src/") or directory.startswith("tests/"):
            init_file = path / "__init__.py"
            if not init_file.exists():
                init_file.touch()

        print(f"[OK] Created {directory}")


def create_initial_config_files():
    """Create initial configuration files"""

    # Example species config
    trout_config = """name: "Coldwater Trout"

scoring_weights:
  flow_suitability: 0.30
  velocity_suitability: 0.25
  thermal_suitability: 0.25
  stability: 0.20

flow_percentile_optimal:
  min: 40
  max: 70

velocity_ranges:
  min_optimal: 0.3  # m/s
  max_optimal: 0.8
  min_tolerable: 0.1
  max_tolerable: 1.5

bdi_threshold: 0.6

temperature:
  optimal_min: 10  # Celsius
  optimal_max: 16
  stress_threshold: 18
  critical_threshold: 20
"""

    # Example hatch config
    green_drake_config = """name: "Green Drake"
species: "Ephemera guttulata"

hydrologic_signature:
  flow_percentile:
    min: 55
    max: 80
  rising_limb:
    allowed: ["false", "weak"]
  velocity:
    min: 0.4
    max: 0.9
  bdi_threshold: 0.65

temporal_window:
  start_day_of_year: 135  # Mid-May
  end_day_of_year: 180    # Late June

geographic_range:
  - "eastern_us"
  - "midwest"
"""

    # Rising limb thresholds
    rising_limb_config = """default:
  min_slope: 0.5  # m³/s per hour
  min_duration: 3  # consecutive hours
  intensity_thresholds:
    weak: 0.5
    moderate: 2.0
    strong: 5.0

species_overrides:
  anadromous_salmonid:
    min_slope: 2.0
    min_duration: 6
    intensity_thresholds:
      weak: 2.0
      moderate: 5.0
      strong: 10.0
"""

    configs = {
        "config/species/trout.yaml": trout_config,
        "config/hatches/green_drake.yaml": green_drake_config,
        "config/thresholds/rising_limb.yaml": rising_limb_config,
    }

    for filepath, content in configs.items():
        path = Path(filepath)
        if not path.exists():
            path.write_text(content)
            print(f"[OK] Created {filepath}")


def create_readme_in_dirs():
    """Create README files in key directories"""

    readmes = {
        "src/ingest/README.md": "# NWM Data Ingestion\n\nEPIC 1: Handles downloading and initial parsing of NWM products.\n",
        "src/metrics/README.md": "# Derived Metrics\n\nEPIC 2: Computes derived hydrologic metrics (BDI, rising limb, etc.).\n",
        "src/species/README.md": "# Species Scoring\n\nEPIC 4: Species-specific habitat suitability scoring.\n",
        "config/README.md": "# Configuration Files\n\nAll species, hatch, and threshold configurations. YAML files owned by science team.\n",
        "tests/README.md": "# Tests\n\nUnit, integration, and property-based tests.\n",
        "data/README.md": "# Data Directory\n\nLocal data storage. **Not committed to Git.**\n",
    }

    for filepath, content in readmes.items():
        path = Path(filepath)
        if not path.exists():
            path.write_text(content)
            print(f"[OK] Created {filepath}")


def main():
    """Run all setup tasks"""
    print("Setting up FNWM project structure...\n")

    create_directory_structure()
    print()

    create_initial_config_files()
    print()

    create_readme_in_dirs()
    print()

    print("Project structure initialized successfully!")
    print("\nNext steps:")
    print("1. Copy .env.example to .env and fill in your configuration")
    print("2. Create a virtual environment: python -m venv venv")
    print("3. Activate it: venv\\Scripts\\activate (Windows) or source venv/bin/activate (Unix)")
    print("4. Install dependencies: pip install -r requirements.txt")
    print("5. Install dev dependencies: pip install -r requirements-dev.txt")
    print("6. Set up pre-commit hooks: pre-commit install")
    print("7. Start with EPIC 1 in the IMPLEMENTATION_GUIDE.md")


if __name__ == "__main__":
    main()
