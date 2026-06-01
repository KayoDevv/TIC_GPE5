"""Pure functional core of the analysis pipeline.

Logic with no I/O and no subprocess, shared between the ELF and PDF paths:
    - core/scoring.py → weighted sum → anomaly_score, verdict bands
    - core/report.py  → narrative / behavioural summary (Layer 4)

Pure = testable in CI without a sandbox or a sample (see tests/test_golden_core.py).
The imperative shell (acquire, execution under strace, snapshot, publish) lives
elsewhere (run_*.py, snapshot.py, executors). The config (weight sets, thresholds)
stays with the run_*.py orchestrators.
"""
