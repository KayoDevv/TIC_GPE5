"""Large-scale sandbox validation pipeline.

Three tests:
  A. Determinism   — same input, same score within epsilon
  B. Distribution  — stable score histogram across runs
  C. Accuracy      — F1/precision/recall if labels present (benign/malicious)

Idempotent: state is split across two DuckDB files (see db.py) —
validation/feeder_state.duckdb (corpus + sent jobs, written by the feeder) and
validation/results.duckdb (received results, written by the validator). Re-run =
resumes where it left off.
"""
