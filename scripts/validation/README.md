# Sandbox validation pipeline

Measures three properties of the sandbox layer over a corpus:

- **A. Determinism** — the same file replayed twice yields the same `anomaly_score` (tolerance Δ < 0.05)
- **B. Distribution** — stable score histogram between two distinct runs (drift test)
- **C. Correctness** — `precision` / `recall` / `F1` on the `benign` / `malicious` labelled samples

All state lives in `validation/feeder_state.duckdb` + `validation/results.duckdb`. Runs are idempotent: re-running resumes exactly where it stopped, with no double send.

---

## Corpus layout

```
<corpus_root>/
├── benign/      ← non-malicious files
├── malicious/   ← malicious files
└── unknown/     ← unlabelled (tests A + B only, excluded from F1)
```

The label is derived from the **first-level subfolder name** — no metadata file to maintain.

**Label provenance (anti-circularity, M2).** Pass `LABEL_SOURCE=` (or `--label-source`
on the feeder) to record where the labels came from:
`academic_groundtruth` / `synthetic` (independent of any AV → kept in the headline),
`av_consensus` (e.g. MalwareBazaar — **excluded** from the accuracy figure, since
scoring against the same AV the sandbox imitates is circular), `unspecified` (legacy
default, kept). Run each dataset as its own campaign:

```bash
make sandbox-validate CORPUS=~/datasets/cic-evasive-pdf  RUN_ID=cic  LABEL_SOURCE=academic_groundtruth
make sandbox-validate CORPUS=~/datasets/malwarebazaar_pdf RUN_ID=mbz LABEL_SOURCE=av_consensus
```

> **Single canonical root: `scripts/validation/real_corpus/`.** It is the default of the Makefile and of `prepare_corpus.py`. The samples are **real malware** → the folder is **gitignored** (never committed). Do not recreate a parallel `corpus/` or `tmp/corpus/`: one source of truth only.

---

## Prerequisites

```bash
# Kafka + MinIO are in-cluster (Bitnami + MinIO StatefulSet):
make bootstrap-in-cluster   # deploys Kafka + MinIO if not already done
make deploy-dev             # consumer + watcher workers
make install                # Python dependencies (aiokafka, minio, duckdb)
```

---

## Main command

```bash
make sandbox-validate CORPUS=<dir> RUN_ID=<id> REPS=<n> MAX_INFLIGHT=<n>
```

Chains automatically:

```
=== [1/3] Feed  ===   → upload corpus to MinIO + publish file.requested
=== [2/3] Collect === → stops automatically when all results are received
=== [3/3] Report === → prints sections A / B / C
```

The validator stops **automatically** as soon as `matched = total jobs sent`.
(`matched` counts every result persisted to the DB, **errors included** — errors
are a subset of `matched`, not a separate term to add.)

### Examples

```bash
# Quick test, 5 files, 1 repetition
make sandbox-validate CORPUS=/tmp/mini RUN_ID=test1 REPS=1 MAX_INFLIGHT=2

# Determinism test, 100 files × 2 repetitions = 200 jobs
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runV1 REPS=2 MAX_INFLIGHT=7

# Save the report to a file
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runV1 REPS=2 > validation/report_v1.md
```

---

## Preparing a corpus from external datasets (`prepare_corpus.py`)

Randomly picks N files from a source folder and copies them into the corpus, under the right label subfolder. The **multi-source** pattern works natively: call it several times with different `--source` but the **same `--output`**, each call appends to the matching subfolder (collision-safe).

### Options

| Argument | Default | Usage |
|---|---|---|
| `--source` | — (required) | Source folder containing the samples |
| `--count` | 1000 | Number of files to pick |
| `--label` | `malicious` | Label subfolder: `malicious` / `benign` / `unknown` |
| `--output` | `scripts/validation/real_corpus` | Target corpus folder (canonical root) |
| `--seed` | — | Random seed for reproducibility |

### Multi-source use case

```bash
# Source 1: 350 files from the CIC-EvasivePDF2022 dataset
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/cic_pdf \
    --count 350 --label malicious \
    --output scripts/validation/real_corpus --seed 42

# Source 2: 100 files from MalwareBazaar (appended to the same malicious/)
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/malwarebazaar_pdf \
    --count 100 --label malicious \
    --output scripts/validation/real_corpus --seed 42

# Source 3: 50 benign files from arXiv
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/arxiv_papers \
    --count 50 --label benign \
    --output scripts/validation/real_corpus --seed 42

# Run the analysis on the mixed corpus
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runFinal REPS=2
```

---

## Sizing MAX_INFLIGHT by available RAM

| Machine RAM | MAX_INFLIGHT | K8s quota | Time ~4,000 jobs |
|---|---|---|---|
| 12 Gi | 7 | 20 | ~4h30 |
| 16 Gi | 15 | 30 | ~2h40 |
| 32 Gi | 25 | 50 | ~1h40 |
| 64 Gi+ | 40 | 100 | ~1h20 |

Each sandbox job requests **512 Mi RAM**. The K8s quota must be ≥ MAX_INFLIGHT + 10 (TTL margin).

To change the K8s quota:
```bash
kubectl edit resourcequota sandbox-namespace-quota -n sandbox
# spec.hard.count/jobs.batch: "20" → desired value
```

---

## Individual targets (fine-grained control)

If you want to orchestrate manually:

```bash
# Step 1 — feed the corpus into Kafka + MinIO
make -f scripts/validation/Makefile feed CORPUS=<dir> RUN_ID=<id> REPS=2

# Step 2 — collect the sandbox_layer.result results → DuckDB
make -f scripts/validation/Makefile collect RUN_ID=<id> DRAIN=1

# Step 3 — generate the Markdown report
make -f scripts/validation/Makefile report REPORT_RUN_ID=<id>

# Reset the validation consumer group offset (before a fresh run)
make -f scripts/validation/Makefile reset-offsets
```

---

## DNS architecture (post-Option-B)

The feeder running on the **host** must reach:
- **MinIO via NodePort** for the upload (`MINIO_ENDPOINT = <node-ip>:<nodeport>`)
- **Kafka via NodePort** to publish on `file.requested` (`KAFKA_BOOTSTRAP = <node-ip>:32092`)

The **in-cluster Job** must reach:
- **MinIO via K8s DNS** to download the sample (`minio.minio.svc.cluster.local:9000`)

That's why the feeder uses **2 distinct endpoints**:
- `MINIO_ENDPOINT` — for its upload from the host
- `MINIO_PRESIGN_ENDPOINT` — to generate the URL the Job will consume (in-cluster DNS)

The `Makefile` sets them correctly and automatically.

---

## Interpreting the results

### Section A — Determinism

| Result | Interpretation |
|---|---|
| >95% stable (Δ < 0.05) | ✅ Deterministic sandbox |
| 70–95% stable | ⚠️ Partial instability — check strace timing / ASLR |
| <70% stable | ❌ Non-deterministic — blocker before running section C |

### Section B — Distribution

A healthy histogram is a **bimodal** distribution: a low benign cluster (<0.15) + a high malicious cluster (>0.40).
If everything comes out at 0.0 or everything at 1.0 → scoring is broken.

### Section C — Correctness (3-band verdict)

The sandbox is a **tie-breaker**: it only classifies `malicious` on a strong signal,
`benign` only in the absence of signal, and escalates the ambiguous middle to the LLM via `needs_more_context`.
The matrix reflects these 3 bands (aligned with `run_pdf_analysis._verdict_band`):

```
benign  <  0.04  ≤  needs_more_context  <  0.15  ≤  malicious
```

| Metric | Meaning | v1 target |
|---|---|---|
| Confident precision | when it says *malicious*, is it right | > 0.90 |
| Confident recall | malicious classified *malicious* directly | indicative |
| Recall with escalation | malicious confirmed **or** escalated (never washed) | > 0.95 |
| Misses | malicious washed to benign | **0** (the only true security failure) |

> **Reporting honesty (P0c — read before quoting any figure).**
> - **Always state N and a confidence interval.** A point estimate on a small
>   corpus is not a result. Precision `1.0` on ~8 confident positives has a
>   95% Wilson interval of roughly **[0.67, 1.0]** — i.e. not significant.
>   Report `precision = 1.0 (95% Wilson CI [0.67, 1.0], n=8)`, never a bare `1.0`.
> - **Confident recall is low and that is by design.** On the golden, **6 of 14**
>   labelled malicious do **not** score `malicious` directly — they land in
>   `needs_more_context` (escalated to the LLM) or `benign`. They are **not
>   detected by the sandbox alone**; they are deferred. Do not fold them into a
>   precision/F1 figure as if detected.
> - **The end-to-end verdict (post-LLM) is not yet measured.** Every figure here
>   is the **sandbox in isolation**. "The system catches X" is unproven until the
>   FN corpus + post-LLM measurement (P0d) exists. Until then: "capability
>   deployed, efficacy measurement in progress" — not "detects".

---

## Golden baseline (M3 — anti-regression on scoring changes)

Freeze the per-sample verdicts of a reference run, then gate every scoring
change (`core/scoring.py`, weights, thresholds) behind a comparison:

```bash
# 1. Freeze the reference run (once) → scripts/validation/golden/baseline.json
make -f scripts/validation/Makefile golden-freeze RUN_ID=run_v1.4
git add scripts/validation/golden/baseline.json && git commit -m "test: golden run baseline"

# 2. After a scoring change: replay the SAME corpus under a new RUN_ID, then
make -f scripts/validation/Makefile golden-compare RUN_ID=run_after_D1
```

`golden-compare` exit codes: **0** = no regression, **1** = at least one verdict
washed downward (`malicious`/`needs_more_context` → `benign`) or a labelled
malicious sample changed band. Score drift within a band (> 0.02) is reported
but non-fatal. The baseline stores only sha256 + label + scores + band — never
sample content — so it is safe to commit.

An intentional change (e.g. D1 turning a 0.000 contentless into
`needs_more_context`) shows up as FAIL: review it, then **re-freeze consciously**
with the new run as reference. That is the point — no silent verdict moves.

### Growing the net with trap samples (`golden-extend`)

The golden's value is **curated coverage, not volume**: a small set that holds one
representative of each known failure class. When a benchmark surfaces a new class
(e.g. the passive embedded-dropper that broke d-calib at threshold 0.08), graft
those exact samples onto the baseline instead of re-freezing everything:

```bash
# SHA  = gating prefixes (a wash on these FAILs the gate)
# ACCEPT = documented out-of-scope prefixes (reported, never fatal — e.g. a
#          Windows trojan our Linux detonation cannot execute, like fb87d8a7)
make -f scripts/validation/Makefile golden-extend RUN_ID=big_test \
  SHA="<dropper1> <dropper2> <near_threshold_0.090>" ACCEPT="<fb87d8a7>"
git add scripts/validation/golden/baseline.json
```

Grafted samples are re-aggregated with the **baseline's** thresholds so their bands
stay consistent. `compare` lists an accepted sample's band moves (so a future fix
that finally catches it is visible) but never fails the gate on it.

## Benchmark — large-N accuracy (not a gate)

The golden answers *"did I break a known verdict?"*. The **benchmark** answers
*"how good am I, and where are the unknown holes?"* — large corpus, replayed
on-demand (before a defense, after a new capability like D6), **never a CI gate**:

```bash
# Replays a large corpus and emits the F1 / recall / precision report (M7).
# REPS defaults to 3 for figure stability. CORPUS is required.
make sandbox-benchmark CORPUS=<large_corpus> [RUN_ID=<id> REPS=3]
```

Keep the two separate: the golden (small, stable) keeps **known** failure classes
closed; the benchmark (large, disposable) hunts **unknown** ones. Folding the big
corpus into the golden would make it a noisy gate you'd learn to ignore.

---

## Makefile variables

| Variable | Default | Usage |
|---|---|---|
| `RUN_ID` | `validation_<timestamp>` | Campaign identifier |
| `REPS` | `1` | Repetitions per file (`REPS=2` for the determinism test) |
| `CORPUS` | `scripts/validation/real_corpus` | Corpus root (canonical — samples gitignored) |
| `MAX_INFLIGHT` | `15` | Cap on concurrent K3s jobs |
| `RATE` | _(unlimited)_ | Max msg/s throughput |
| `IDLE_TIMEOUT` | `300` | Seconds of inactivity before auto-drain |
| `REPORT_RUN_ID` | _(all runs)_ | Filter the report to one run |
| `THRESHOLD` | `0.15` | **malicious** band threshold (section C) |
| `SUSPICIOUS_THRESHOLD` | `0.04` | **needs_more_context** band threshold (section C) |

---

## Idempotency — behaviour on crash

| Situation | Behaviour on re-run |
|---|---|
| Feeder crash | Skips the `(run_id, sha256, rep)` already in the DB — resumes where it stopped |
| Validator crash | Resumes from the last committed Kafka offset (stable group_id) |
| K3s Job timeout | Counted in the report's errors, score = null |
| K8s quota exceeded | Retry 3× (10s/20s/40s) then publishes an error to Kafka — a job is never silently lost |
| Double `file.requested` | Impossible: `already_sent()` checks the DB before each `send` |
| File already in MinIO | `stat_object()` before `fput_object()` — upload skipped |
