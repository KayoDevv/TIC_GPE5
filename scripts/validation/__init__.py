"""Pipeline de validation sandbox à grande échelle.

Trois tests :
  A. Déterminisme  — même input, même score à epsilon près
  B. Distribution  — histogramme stable des scores entre runs
  C. Justesse      — F1/precision/recall si labels présents (benign/malicious)

Idempotent : l'état est split en deux fichiers DuckDB (cf. db.py) —
validation/feeder_state.duckdb (corpus + jobs envoyés, écrit par le feeder) et
validation/results.duckdb (résultats reçus, écrit par le validator). Re-run =
reprend où on s'est arrêté.
"""
