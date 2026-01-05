# EPIC 4 Thermal Workaround Documentation

**Created**: 2026-01-04
**Status**: TEMPORARY - Pending EPIC 3 completion
**Reason**: Proceeding with EPIC 4 (Species Scoring) before EPIC 3 (Temperature Integration)

---

## Problem Statement

EPIC 4 Ticket 4.1 (Species Scoring Engine) has a dependency on EPIC 3 (Temperature & Thermal Suitability):
- Species scoring algorithm expects `thermal_score` from TSI (Thermal Suitability Index)
- Thermal suitability accounts for **25% of overall species habitat score**
- Without temperature data, we cannot compute TSI

## Temporary Solution

To proceed with EPIC 4 implementation while waiting for air temperature API setup:

### 1. Config Changes Made

**File**: `config/species/trout.yaml`

**Original Scoring Weights** (Target when EPIC 3 is complete):
```yaml
scoring_weights:
  flow_suitability: 0.30
  velocity_suitability: 0.25
  thermal_suitability: 0.25  # <-- Will be restored
  stability: 0.20
```

**Temporary Scoring Weights** (Current):
```yaml
scoring_weights:
  flow_suitability: 0.40      # +0.10 from thermal
  velocity_suitability: 0.33  # +0.08 from thermal
  thermal_suitability: 0.00   # DISABLED temporarily
  stability: 0.27             # +0.07 from thermal
```

### 2. Code Implementation Notes

When implementing EPIC 4 Ticket 4.1 (`src/species/scoring.py`):

**Temporary approach**:
```python
def compute_species_score(feature_id: int, species: str, hydro_data: dict) -> SpeciesScore:
    config = load_species_config(species)
    weights = config['scoring_weights']

    # Compute available component scores
    flow_score = score_flow_suitability(hydro_data['flow_percentile'], config)
    velocity_score = score_velocity_suitability(hydro_data['velocity'], config)
    stability_score = score_stability(hydro_data['bdi'], hydro_data['flow_variability'])

    # TODO EPIC-3: Add thermal_score when temperature data available
    # thermal_score = hydro_data.get('tsi', 0.0)  # Will be from EPIC 3
    thermal_score = 0.0  # TEMPORARY: Default to 0 until EPIC 3

    # Weighted sum
    overall = (
        weights['flow_suitability'] * flow_score +
        weights['velocity_suitability'] * velocity_score +
        weights['thermal_suitability'] * thermal_score +  # Currently 0.0 * 0.0 = 0
        weights['stability'] * stability_score
    )

    # ... rest of implementation
```

---

## Refactoring Checklist - When EPIC 3 is Complete

Once air temperature API is configured and EPIC 3 is implemented:

### Step 1: Restore Original Weights

**File**: `config/species/trout.yaml`

```yaml
scoring_weights:
  flow_suitability: 0.30      # Reduce from 0.40
  velocity_suitability: 0.25  # Reduce from 0.33
  thermal_suitability: 0.25   # Restore from 0.00
  stability: 0.20             # Reduce from 0.27
```

### Step 2: Update Species Scoring Code

**File**: `src/species/scoring.py`

Change from:
```python
thermal_score = 0.0  # TEMPORARY
```

To:
```python
thermal_score = hydro_data['tsi']  # From EPIC 3 TSI calculation
```

### Step 3: Verify Temperature Data Flow

Ensure the following pipeline is working:
1. Temperature ingestion (EPIC 3 Ticket 3.1): Air temp from Open-Meteo API
2. TSI calculation (EPIC 3 Ticket 3.2): Combines temp + BDI for thermal score
3. Species scoring: Uses TSI in weighted calculation

### Step 4: Update Tests

**Files to update**:
- `tests/unit/test_species_scoring.py`
- `tests/integration/test_species_scoring.py`

Add test cases that:
- Mock temperature data and TSI values
- Verify thermal component contributes 25% to overall score
- Test with various temperature scenarios (optimal, stress, critical)

### Step 5: Validate Score Changes

**Important**: Restoring thermal weight will change existing species scores!

- Document baseline scores before EPIC 3 integration
- Re-compute scores after EPIC 3 integration
- Compare differences and validate they make ecological sense
- Update any cached scores in `computed_scores` table

---

## Impact Analysis

### What Works Now (Without Temperature)
- Species scoring produces valid 0-1 scores
- Scores are based on 3 components: flow, velocity, stability
- All hydrologic metrics from EPIC 2 are utilized
- Explanations are generated and auditable

### What's Missing (Until EPIC 3)
- No thermal habitat assessment
- Cannot identify thermal refugia (cool springs in hot weather)
- Cannot warn about thermal stress conditions
- Overall scores may overweight flow/velocity factors

### Ecological Implications
- Scores are **conservative** (no temperature bonus for spring creeks)
- May **under-score** thermally buffered reaches (high BDI streams)
- May **over-score** reaches with good flow/velocity but poor temperature

---

## Related Files

**Config Files**:
- `config/species/trout.yaml` - Modified weights

**Code Files** (to be created in EPIC 4):
- `src/species/scoring.py` - Species scoring engine
- `src/species/__init__.py`

**Test Files** (to be created in EPIC 4):
- `tests/unit/test_species_scoring.py`
- `tests/integration/test_species_scoring.py`

**Temperature Files** (to be created in EPIC 3):
- `src/temperature/ingest.py` - Air temp ingestion
- `src/temperature/tsi.py` - Thermal Suitability Index
- `config/species/trout.yaml` - Temperature thresholds (already present)

---

## References

- **PRD**: `Claude-Context/prd.txt` - Original species scoring design
- **Implementation Guide**: `docs/guides/implementation.md` - EPIC 3 & 4 details
- **EPIC 2 Summary**: `docs/development/epic-2-completion-summary.md` - Current state

---

## Questions for Future Work

1. **Should we re-tune weights after EPIC 3?**
   - Current distribution (0.30/0.25/0.25/0.20) is hypothetical
   - May need calibration based on validation data (EPIC 7)

2. **Regional weight variations?**
   - Western freestone vs. spring creeks may weight thermal differently
   - Consider regional overrides in config

3. **Seasonal thermal importance?**
   - Summer: thermal weight higher (heat stress critical)
   - Winter: thermal weight lower (flow stability more important)
   - Could make weights season-dependent

---

**Status**: Ready to proceed with EPIC 4 implementation using temporary weights.

**Next Action**: When starting EPIC 3, reference this document to restore full thermal integration.
