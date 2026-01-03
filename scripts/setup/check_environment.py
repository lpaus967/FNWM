"""
Environment Check Script

Verifies that all required packages are available.
Run this before ingestion to ensure environment is correct.
"""

import sys

print("=" * 60)
print("FNWM Environment Check")
print("=" * 60)

print(f"\nPython executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Check critical packages
packages_to_check = [
    'netCDF4',
    'xarray',
    'pandas',
    'sqlalchemy',
    'requests',
    'pydantic',
    'dotenv'
]

print("\n" + "=" * 60)
print("Package Versions:")
print("=" * 60)

all_ok = True

for package_name in packages_to_check:
    try:
        if package_name == 'dotenv':
            import importlib
            pkg = importlib.import_module('dotenv')
            module_name = 'python-dotenv'
        else:
            import importlib
            pkg = importlib.import_module(package_name)
            module_name = package_name

        version = getattr(pkg, '__version__', 'unknown')
        print(f"✅ {module_name:20} {version}")
    except ImportError as e:
        print(f"❌ {package_name:20} NOT FOUND")
        all_ok = False

print("\n" + "=" * 60)

if all_ok:
    print("✅ Environment is ready!")
    print("\nYou can now run:")
    print("  python scripts/run_full_ingestion_subset.py")
    print("  python scripts/run_full_ingestion.py")
else:
    print("❌ Some packages are missing!")
    print("\nActivate the fnwm environment:")
    print("  conda activate fnwm")
    print("\nOr install missing packages:")
    print("  conda env create -f environment.yml")

print("=" * 60)
