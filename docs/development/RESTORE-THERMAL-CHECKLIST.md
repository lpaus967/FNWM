# Quick Reference: Restore Thermal Component After EPIC 3

**When to use this**: After completing EPIC 3 (Temperature & Thermal Suitability Integration)

**Full documentation**: See `docs/development/epic-4-thermal-workaround.md`

---

## Quick Checklist

### 1. Verify EPIC 3 is Complete ✅
- [ ] Temperature ingestion working (Ticket 3.1)
- [ ] TSI calculation implemented (Ticket 3.2)
- [ ] Temperature data flowing to species scoring pipeline

### 2. Restore Config Weights
**File**: `config/species/trout.yaml`

```yaml
# Change FROM:
scoring_weights:
  flow_suitability: 0.40
  velocity_suitability: 0.33
  thermal_suitability: 0.00   # <-- Currently disabled
  stability: 0.27

# Change TO:
scoring_weights:
  flow_suitability: 0.30      # Restore original
  velocity_suitability: 0.25  # Restore original
  thermal_suitability: 0.25   # Enable thermal component
  stability: 0.20             # Restore original
```

### 3. Update Species Scoring Code
**File**: `src/species/scoring.py`

Search for: `TODO EPIC-3`

```python
# Change FROM:
thermal_score = 0.0  # TEMPORARY: Default to 0 until EPIC 3

# Change TO:
thermal_score = hydro_data['tsi']  # From EPIC 3 TSI calculation
```

### 4. Update Tests
**Files**: `tests/unit/test_species_scoring.py`, `tests/integration/test_species_scoring.py`

- [ ] Add test cases with temperature data
- [ ] Verify thermal component contributes 25% to score
- [ ] Test temperature scenarios: optimal, stress, critical

### 5. Validate Changes
- [ ] Re-run all species scoring tests
- [ ] Compare new scores vs. old scores (expect changes!)
- [ ] Validate thermal scores make ecological sense
- [ ] Update `computed_scores` table if scores are cached

### 6. Clean Up Documentation
- [ ] Remove workaround notes from `project-status.md`
- [ ] Archive this file and `epic-4-thermal-workaround.md` to `docs/archive/`
- [ ] Update EPIC 3 & 4 status to COMPLETE

---

## Files to Modify

1. `config/species/trout.yaml` - Restore original weights
2. `src/species/scoring.py` - Enable thermal_score from TSI
3. `tests/unit/test_species_scoring.py` - Add thermal tests
4. `tests/integration/test_species_scoring.py` - Integration tests
5. `docs/development/project-status.md` - Remove workaround notes

---

## Expected Impact

**Scores will change!** Restoring thermal will:
- Increase scores for thermally suitable reaches (cool spring creeks)
- Decrease scores for thermally stressed reaches (warm, exposed streams)
- Improve ecological accuracy of species habitat predictions

---

**Reminder**: Search codebase for `TODO EPIC-3` to find all temporary code.

```bash
# Find all TODO EPIC-3 comments
grep -r "TODO EPIC-3" src/ config/
```
