# Phase 12 stretch experiments

## Synthetic Kolkata portability fixture

`make simulate-kolkata` creates a Git-ignored, explicitly synthetic delivery-like dataset under `data/simulated/`. It is deterministic from a seed and exercises a generic origin/destination/time/distance contract. It is not real Kolkata trip data, must not be used for business findings, and must not be merged with TLC results.

## Local replay

`make replay` emits the first 100 completed January trip starts as JSON Lines at 3,600× replay speed. It reads the local warehouse and writes only stdout. It is a deterministic demo source, not streaming infrastructure and not a live data feed.

## Congestion-fee comparison

Run `python -m stretch.congestion_pricing --pre-month YYYY-MM --post-month YYYY-MM` once two suitable completed months are loaded. It reports descriptive differences in trip volume, duration, distance, and recorded congestion surcharge. It does not identify a causal policy effect; a credible analysis would need an agreed comparison design and a richer time window.

## Cloud deployment

No cloud resources are created by this project. A deployment requires an explicit provider, region, budget, credential-management approach, and approval. The current Docker API image is the portable handoff point for a future deployment.
