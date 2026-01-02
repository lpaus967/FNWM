<div align="center">
  <img src="assets/logo.jpg" alt="FNWM Logo" width="600"/>
</div>

# Fisheries Hydrology Intelligence Engine

This repository contains the core engineering code that transforms NOAA’s **National Water Model (NWM)** into **explainable, fisheries-focused intelligence** for onWater products.

This is **not** a generic hydrology ingestion repo. Its purpose is to ingest a *minimal, opinionated subset* of NWM products and convert them into **species-, hatch-, and reach-specific metrics** that can be confidently surfaced to users.

---

## 🚀 What This Product Does

At a high level, this system:

1. Ingests selected NWM channel routing products
2. Normalizes all data into a single time abstraction ("Now", "Today", "Outlook")
3. Computes derived hydrologic and ecological metrics (e.g. rising limbs, baseflow dominance)
4. Produces **auditable, explainable scores** for fisheries use cases
5. Exposes clean APIs that never leak raw NWM complexity

The result is **trusted decision support**, not raw model output.

---

## 🎯 Design Principles (Read First)

These rules govern every line of code in this repo:

- **NWM is infrastructure, not a product**  
  Raw files, folders, and f### semantics are never exposed downstream.

- **Selectivity beats completeness**  
  ~80–90% of fisheries value comes from ~4 NWM products. We ingest only what we use.

- **Truth, prediction, and uncertainty are distinct**  
  “Now”, “Today”, and “Outlook” are separate concepts in data, APIs, and UX.

- **Ecology ≠ hydrology**  
  Gauge-corrected flows are best for display; non-assimilated flows are often better for ecological inference.

If a feature depends directly on a raw NWM variable, the work is not finished.

---

## 📦 Canonical NWM Products Used

This repo ingests **only** the following channel routing products:

| Purpose | NWM Product | Notes |
|------|-----------|------|
| Current conditions ("Now") | `analysis_assim/channel_rt` | Only valid source of truth for current flow |
| Near-term forecast (0–18h) | `short_range/channel_rt` | High temporal resolution |
| Multi-day outlook (3–10d) | `medium_range_blend/channel_rt` | Ensemble mean only |
| Ecological baseflow analysis | `analysis_assim_no_da/channel_rt` | No gauge nudging |

**Rules**
- Short-range `f001` is **never** used as “current”
- Individual ensemble members are never user-facing
- No-DA products are internal-only

---

## 🕒 Internal Time Abstractions

All NWM time semantics are collapsed into four internal concepts:

| Internal Term | Backing Data |
|-------------|-------------|
| `now` | `analysis_assim` |
| `today` | `short_range` (f001–f018) |
| `outlook` | `medium_range_blend` |
| `uncertainty` | `medium_range` ensemble members |

No downstream service should reason about filenames or `f###` values directly.

---

## 🌊 Core Derived Metrics

Raw NWM variables are never exposed. All intelligence is derived.

Examples include:

- **Rising Limb Detection** – sustained positive flow derivatives
- **Flow Percentile vs Baseline** – normalizes rivers of different sizes
- **Velocity Suitability** – species-specific energetic windows
- **Baseflow Dominance Index (BDI)** – groundwater vs stormflow signal
- **Thermal Suitability Index (TSI)** – temperature + hydrology proxy

All metrics are:
- Deterministic
- Unit-testable
- Configurable
- Explainable

---

## 🐟 Species & Hatch Intelligence

This system supports **species-specific** and **hatch-specific** interpretation layers, including:

- Coldwater trout
- Warmwater bass
- Anadromous salmonids
- Key hatches (Green Drake, PMD, Caddis)

Scores are computed using transparent equations (0–1 normalized) with configurable weights owned by science/product—not hardcoded logic.

---

## 🔍 Confidence & Uncertainty

We explicitly communicate trust.

Confidence is derived from:
- Forecast lead time
- Ensemble spread
- Gauge influence (`nudge_m3s`)

Outputs are classified as **High / Medium / Low** and included alongside all recommendations.

---

## 🧪 Validation Framework

Predictions are continuously evaluated against observations:

- User trip reports
- Hatch observations (where available)
- USGS gauges (sanity checks)

Key metrics:
- Precision
- Recall
- Lead time

This feedback loop is mandatory for all new features.

---

## 🏗️ Repository Structure (Conceptual)

```text
/
├── ingest/            # NWM ingestion & scheduling
├── normalize/         # Time & schema normalization
├── metrics/           # Derived hydrology metrics
├── species/           # Species scoring logic
├── hatches/           # Hatch-specific rules
├── temperature/       # Thermal ingestion & TSI
├── confidence/        # Uncertainty & confidence scoring
├── api/               # Internal service interfaces
├── config/            # Species & hatch thresholds (YAML/JSON)
└── validation/        # Model performance & feedback loop
```

Exact structure may evolve, but separation of concerns is enforced.

---

## 🔌 API Philosophy

APIs exposed by this repo:

- Are **reach-centric** (`feature_id`)
- Support `now`, `today`, and `outlook`
- Never expose raw NWM variables
- Always include explanation and confidence metadata

If an API response cannot explain *why* a recommendation was made, it should not ship.

---

## 📜 Product Integrity Rule

> If a feature cannot explain its recommendation in terms of flow, velocity, temperature, and stability, it does not ship.

This repository is the contract between **science, engineering, and product**.

---

## 🚀 Getting Started

### Quick Setup (Conda - Recommended)

```bash
# Create conda environment
conda env create -f environment.yml

# Activate environment
conda activate fnwm

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start developing!
```

See [docs/setup/conda.md](docs/setup/conda.md) for detailed conda instructions, or [docs/guides/quickstart.md](docs/guides/quickstart.md) for venv setup.

---

## 📚 References

- NOAA National Water Model: https://water.noaa.gov/about/nwm
- NWM Data Access: https://nomads.ncep.noaa.gov/pub/data/nccf/com/nwm/
- Implementation Guide: [docs/guides/implementation.md](docs/guides/implementation.md)
- Conda Setup: [docs/setup/conda.md](docs/setup/conda.md)

---

## 🧭 Final Note

Shipping raw hydrology is easy.

Shipping **trusted fisheries intelligence**—that users can understand, trust, and act on—is the work.

