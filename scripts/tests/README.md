# FNWM Test Scripts

This directory contains test and verification scripts for validating FNWM functionality.

## Available Tests

### Metric Calculators
- `test_bdi_calculator.py` - Test Baseflow Dominance Index calculations
- `test_velocity_classifier.py` - Test velocity suitability classifier
- `test_rising_limb_detector.py` - Test rising limb detection algorithm
- `test_rising_limb_simple.py` - Simplified rising limb test
- `verify_rising_limb.py` - Verify rising limb detection on real data
- `test_flow_percentile.py` - Test flow percentile calculations

### Composite Tests
- `test_all_metrics_50_reaches.py` - Run all metrics on 50 sample reaches
- `test_species_scoring.py` - Test species habitat scoring

## Usage

All test scripts can be run directly from the project root:

```bash
# Activate environment
conda activate fnwm

# Run a specific test
python scripts/tests/test_flow_percentile.py

# Run all metrics test
python scripts/tests/test_all_metrics_50_reaches.py
```

## When to Use These Scripts

- **During development**: Validate changes to metric calculations
- **After database updates**: Ensure data integrity
- **Before deployment**: Run comprehensive tests
- **Debugging**: Isolate and diagnose calculation issues

## Note

These are development/validation scripts, not production code. They are not required for normal FNWM operation.
