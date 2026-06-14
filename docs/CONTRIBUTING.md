# Contributing & Code Style

This document is the **source of truth for code style and engineering standards** in this
repository. It is not a list of suggestions — items marked **MUST** / **MUST NOT** are
enforced in review and a PR that violates them will be sent back for changes.

It applies to **all code**: Python services and workers (`apps/`, `packages/`), the Vue/WXT
frontend (`apps/frontend/`), infrastructure manifests, and scripts.

> **Why this exists.** We are a security product with hard constraints (100% async,
> false-positive rate < 0.5%). Code that another engineer cannot read and reason about in
> minutes is a liability, not an asset. AI-assisted code is welcome — code that reads like an
> AI dumped it (essay docstrings, step-by-step narration, copy-pasted near-duplicates,
> mixed-language strings) is not. **You own what you submit; "the model wrote it" is not a
> defense in review.**

---

## Table of contents

1. [The golden rules (TL;DR)](#the-golden-rules-tldr)
2. [Language: English only](#1-language-english-only)
3. [Naming](#2-naming)
4. [Functions](#3-functions)
5. [Comments](#4-comments)
6. [Docstrings](#5-docstrings)
7. [SOLID](#6-solid)
8. [DRY — don't repeat yourself](#7-dry--dont-repeat-yourself)
9. [Separation of concerns & architecture](#8-separation-of-concerns--architecture)
10. [Error handling](#9-error-handling)
11. [Constants — no magic values](#10-constants--no-magic-values)
12. [Types](#11-types)
13. [Tests](#12-tests)
14. [Formatting & tooling](#13-formatting--tooling)
15. [Git & pull requests](#14-git--pull-requests)
16. [Definition of Done](#15-definition-of-done)
17. [Reviewer checklist](#16-reviewer-checklist)

---

## The golden rules (TL;DR)

1. **English only.** Everything: identifiers, comments, docstrings, log messages, user-facing
   strings, tests, commit messages, PR descriptions.
2. **Code speaks for itself.** No explanatory comments inside function bodies. If you need a
   comment to explain *what* the code does, rename or extract until you don't.
3. **One docstring per file** — the module docstring. Functions, classes and methods carry
   *none*; their names and signatures must do the talking.
4. **Small functions, one responsibility.** Target ≤ 40 lines and one level of abstraction.
5. **Names reveal intent.** No cryptic internal codes (`D1`, `M4`, `P0c`, `tranche_b`) in
   identifiers or strings. Spell out the purpose.
6. **DRY, SOLID, separation of concerns** are not optional.
7. **No magic numbers.** Name them.
8. **One logical change per PR.** Keep it small and reviewable; stacked PRs are based on their
   parent branch, never re-diffed against `main`.

---

## 1. Language: English only

**MUST:** every character a developer or a user reads — identifiers, comments, docstrings,
log lines, exception messages, commit messages, test names and test data, and **user-facing
output strings** — is written in **English**.

This has been raised in review before (see PR #7: *"No french. English only."*). It is now a
written rule.

```python
# ❌ Forbidden — French identifiers, comments, and output strings
# Seuils de verdict — la logique vit dans core/scoring
SEUIL_MALVEILLANT = 0.15
behavior_summary = f"Verdict sandbox : l'analyse a échoué ({exc})."

REASONS = {
    "missing_pdf_magic": "Le fichier prétend être un PDF mais son entête est d'un autre type",
}
```

```python
# ✅ Required — English throughout
MALICIOUS_THRESHOLD = 0.15
behavior_summary = f"Sandbox verdict: analysis failed ({exc})."

REASONS = {
    "missing_pdf_magic": "File claims to be a PDF but its header is another type",
}
```

### Localized product output

If a feature genuinely needs to render text in another language to the end user, that is a
**product/i18n decision, not a coding-language decision**:

- The **keys, code, and developer-facing strings stay English.**
- Translatable copy lives behind **i18n keys** in a dedicated catalogue (e.g. a
  `locales/fr.json`), never hardcoded in business logic and never split between a dict and
  inline f-strings.
- "It's the product's output language" does **not** license French *comments*, *identifiers*,
  or *log lines*.

---

## 2. Naming

Names are the primary documentation. A good name removes the need for a comment.

**MUST:**
- Use **intention-revealing** names: `compute_anomaly_score`, not `calc` or `process`.
- Make names **pronounceable and searchable**. Avoid one-letter names except a tight loop
  index.
- Keep a **single vocabulary** per concept across the codebase (don't mix `fetch` / `get` /
  `retrieve` for the same idea).
- Name booleans as predicates: `is_malicious`, `has_payload`, `liveness_ok`.

**MUST NOT:**
- Encode **internal project jargon or ticket codes** into identifiers or runtime strings:
  `D1`, `D1bis`, `M4`, `P0a`, `tranche_b`, `charon_v1`. These mean nothing to a reader six
  months from now. Put the ticket reference in the **commit message or PR**, and name the code
  after **what it does**.
- Use noise words (`data`, `info`, `manager`, `helper`, `_v2`) that carry no meaning.
- Abbreviate to save typing (`evt`, `res`, `ctx2`) — clarity beats brevity.

```python
# ❌  what is D1? what is a "guard" guarding?
def guarded_verdict_d1(s, mt, st, *, lv): ...

# ✅  the name states the rule it enforces
def verdict_with_liveness_guard(score, malicious_threshold, suspicious_threshold,
                                *, execution_observed): ...
```

> If a name needs a comment to explain it, the name is wrong.

---

## 3. Functions

**MUST:**
- Do **one thing** at **one level of abstraction**. A function either orchestrates *or* does
  detail work — not both.
- Be **short**. Target **≤ 40 lines**; anything past ~60 needs a very good reason and will be
  scrutinised. A 150–250-line function is automatically a change request.
- Take **few parameters** (≤ 3 ideally). Prefer a small dataclass / object over a long
  positional list. Avoid **boolean flag arguments** — they mean the function does two things;
  split it.
- Respect **command/query separation**: a function either returns a value *or* has a side
  effect, not both.

**The "numbered steps" smell.** If your function body looks like:

```python
def run_pdf_analysis(...):
    # 1. download
    ...
    # 2. static layer
    ...
    # 3. snapshot before
    ...
    # 9. publish
    ...
```

…those numbered comments are a **map of the functions you should extract**. Each step becomes
a named function and the orchestrator reads as a table of contents:

```python
def run_pdf_analysis(job_id: str, s3_url: str) -> None:
    sample = download_sample(s3_url)
    static = run_static_layer(sample)
    signals = run_dynamic_layers(sample)
    verdict = score_and_decide(static, signals)
    publish_result(job_id, verdict)
```

No comments needed — the names *are* the narration.

---

## 4. Comments

**Code must be self-explanatory.** A comment is most often an apology for code that does not
read clearly — fix the code instead.

**MUST NOT:**
- Write **explanatory comments inside function bodies** (the `# now we loop over the results`
  kind). Rename and extract until the code says it itself.
- Leave **commented-out code**. Git is our history; delete it.
- Write **redundant / noise** comments (`i += 1  # increment i`) or changelog comments
  (`# modified by X on date`).

**Permitted in a function body — these are directives or trackers, not prose:**
- Tooling pragmas with a reason: `# noqa: S310 — URL validated above`, `# type: ignore[...]`,
  `# pragma: no cover`.
- `# TODO(#123): …` / `# FIXME(#123): …` tied to a **tracked issue**.

**Permitted outside function bodies:**
- The single **module docstring** (see §5).
- A **rare** module- or block-level `# why` note for a genuinely non-obvious decision — and it
  must explain **why**, never **what**. If you find yourself writing several of these, the
  design is too clever; simplify it. This is the exception, not the habit.

```python
# ❌  narrating what the code plainly does
def evaluate(signals):
    score = 0.0
    # long cumulated sleep is an anti-sandbox stall
    if signals.sleep_cumulated_s > 60.0:
        score += 0.40
    # ptrace TRACEME means anti-debug
    if has_traceme(signals):
        score += 0.30
    ...

# ✅  the rule table is data; the code reads itself
EVASION_SIGNALS = (
    EvasionSignal("long_sleep_stall", weight=0.40, detect=is_long_cumulated_sleep),
    EvasionSignal("anti_debug_traceme", weight=0.30, detect=uses_ptrace_traceme),
)

def evaluate(signals):
    return sum(s.weight for s in EVASION_SIGNALS if s.detect(signals))
```

---

## 5. Docstrings

**MUST: exactly one docstring per file — the module docstring.** It states what the module is
for in a few lines.

**MUST NOT:** add docstrings to functions, methods, or classes. Their **names and type
signatures** carry the contract. A per-function docstring that restates the signature is noise
that drifts out of date; a multi-paragraph essay docstring is worse.

This is a deliberate house rule and it **overrides** the common "docstring every public
function" convention. We optimise for names + types + tests as the contract.

```python
# ✅  module docstring — the one allowed docstring in the file
"""Anomaly scoring and verdict banding for the sandbox layer (pure, no I/O)."""

from __future__ import annotations


def compute_anomaly_score(results: dict[str, Hypothesis], weights: dict[str, float]) -> float:
    score = sum(weights.get(name, 0.0) * r.score for name, r in results.items())
    return round(min(score, 1.0), 3)
```

```python
# ❌  per-function essay docstring — not allowed
def compute_anomaly_score(results, weights):
    """Weighted sum of hypothesis scores, capped at 1.0, rounded to 3 decimals.

    results : {name: object with a `.score` attribute in [0, 1]}.
    weights : {name: weight}. A key missing from the weights contributes 0.
    ...
    """
```

If a function is so subtle that you feel it *needs* a docstring, that is a signal to **rename
it, shrink it, or cover the behaviour with a well-named test** — the test documents intent and
stays honest because CI runs it.

---

## 6. SOLID

Applies to classes **and** modules of functions.

- **S — Single Responsibility.** A module/class/function has one reason to change. The sandbox
  agent's split (pure `core/` scoring + report, `hypotheses/` detectors, imperative
  orchestrator) is the model to follow — keep responsibilities separated, don't collapse them
  back into one mega-function.
- **O — Open/Closed.** Add a new hypothesis/detector by adding a module and registering it in a
  table, not by editing a giant `if/elif` chain.
- **L — Liskov.** Subtypes and alternative implementations must honour the base contract; no
  surprising overrides.
- **I — Interface Segregation.** Small, focused interfaces. Don't force callers to depend on
  fields/methods they don't use.
- **D — Dependency Inversion.** Business logic depends on abstractions (a publisher interface,
  a clock), not on `aiokafka`/`datetime.now()` directly — this is also what makes it testable.

---

## 7. DRY — don't repeat yourself

**MUST NOT** copy-paste a block and tweak it. Two near-identical 200-line orchestrators (one
for ELF, one for PDF) sharing their download/publish/config/IOC scaffolding is the canonical
violation: extract the shared **runner**, and keep only the format-specific pipeline per
agent.

Rule of thumb: **the third occurrence is a refactor, not a copy.** Knowledge — a threshold, a
MITRE mapping, a magic-byte table — must have **one** authoritative home.

> Caveat: DRY is about *knowledge*, not coincidental textual similarity. Don't couple two
> things that merely look alike today but change for different reasons.

---

## 8. Separation of concerns & architecture

- **Functional core, imperative shell.** Keep decision logic in **pure functions** (no I/O, no
  globals, deterministic) and push Kafka / MinIO / Kubernetes / clock at the edges. Pure cores
  are trivial to test and reason about.
- **One layer per module.** Parsing ≠ scoring ≠ reporting ≠ transport. Don't build a Kubernetes
  Job spec, parse magic bytes, and publish to Kafka in the same function.
- **No business logic in transport handlers**, and no transport calls inside business logic.
- Respect the documented event-flow boundaries (`docs/architecture/`) and the Kafka data
  contracts in `packages/kafka-schemas/`.

---

## 9. Error handling

- **Fail loud, not silent.** Never swallow an exception into a `0.0` score or an empty result
  that downstream reads as "benign/clean". For a security verdict, *absence of signal is not
  proof of safety* — surface the error explicitly.
- **No bare `except:`** and avoid broad `except Exception` unless you **re-raise or log with
  full context and a `job_id`**. Catch the narrowest exception you can handle.
- Raise **specific** exceptions with actionable messages; don't return sentinel `None` that
  callers must remember to check.
- Validate inputs at the boundary (e.g. SSRF/scheme checks on URLs) and keep the happy path
  unindented below the guards.

---

## 10. Constants — no magic values

**MUST NOT** sprinkle literals (`0.40`, `60.0`, `35`, `120`, `"charon-seccomp.json"`) through
the code. Name them once, near the top of the module or in a config object, so the *meaning*
and the *tuning point* are explicit and searchable.

```python
# ❌
if signals.sleep_cumulated_s > 60.0:
    score += 0.40

# ✅
LONG_SLEEP_THRESHOLD_S = 60.0
SLEEP_STALL_WEIGHT = 0.40

if signals.sleep_cumulated_s > LONG_SLEEP_THRESHOLD_S:
    score += SLEEP_STALL_WEIGHT
```

---

## 11. Types

- **MUST** fully type-annotate all Python (parameters, returns, attributes). `mypy --strict`
  is enforced.
- Prefer precise types (`dict[str, float]`, a `TypedDict`/dataclass/Pydantic model) over bare
  `dict` / `Any`. Use `Any` only with a justifying `# type: ignore`-style note.
- Model events and payloads with the shared **Pydantic v2** models in
  `packages/core/src/zt_shared/models/` — do not pass raw dicts across module boundaries.
- Frontend: no implicit `any`; `vue-tsc` type-check (`npm run typecheck`) must pass.

---

## 12. Tests

- **TDD.** Write the test first; let it drive small, single-purpose functions.
- **100% coverage is enforced** (`fail_under = 100`). Coverage is a floor, not a goal — cover
  behaviour and edge cases, not lines for their own sake.
- **FIRST**: Fast, Independent, Repeatable, Self-validating, Timely.
- One concept per test; the **test name states the behaviour**
  (`test_quiet_run_escalates_to_needs_more_context`). Test names follow the English-only rule.
- `pytest` with `asyncio_mode = "auto"`; put tests under `tests/`.
- Tests are first-class code — the style rules in this document apply to them too.

---

## 13. Formatting & tooling

Formatting is **not a matter of taste** — let the tools decide and never hand-format.

| Concern | Tool / setting | Command |
|---|---|---|
| Format | Ruff formatter | `make format` |
| Lint | Ruff — line length **100**, rules `E, F, B, I` | `make lint` |
| Types (Python) | MyPy **strict** (+ pydantic plugin) | `poetry run mypy src/` |
| Tests + coverage | pytest, `asyncio_mode=auto`, coverage `fail_under=100` | `make test` / `poetry run pytest --cov` |
| Types (frontend) | `vue-tsc` | `npm run typecheck` |
| Frontend tests | Vitest (unit), Playwright (e2e) | `npm run test:unit` / `npm run test:e2e` |

CI also runs yamllint, kubeconform, hadolint, gitleaks (secrets), and schema-compatibility
checks. **Run `make lint` and `make test` locally before pushing** — a red CI is your
responsibility, not the reviewer's.

---

## 14. Git & pull requests

### Commits
- **Conventional Commits**, in English: `feat(sandbox): add liveness guard to verdict`,
  `fix(core-backend): reject oversized uploads`, `refactor`, `test`, `docs`, `chore`, `ci`.
- Small, atomic commits that each build and pass tests.

### Pull requests — keep them reviewable
- **One logical change per PR.** A PR that mixes a feature, a refactor, and infra churn is
  hard to review and hard to revert. Split it.
- **Keep PRs small** — aim for a few hundred changed lines. A 2,000-line PR will be reviewed
  slowly and shallowly, which is bad for everyone.
- **Stacked PRs MUST be based on their parent branch, not `main`.** If PR B depends on PR A,
  branch B off A and set B's base to A. Do **not** point a chain of dependent branches all at
  `main` — that makes every PR re-show its predecessors' diffs, and merging them out of order
  corrupts history. Merge the stack bottom-up, rebasing as each parent lands.
- No empty/near-empty PRs that only re-diff another open branch — fold them in.
- PR description in English: **what** changed, **why**, how it was tested. Reference the issue.

### Hard gates
- **No secrets** in code or history (gitleaks will block it).
- **Kafka schema changes** must be `BACKWARD_TRANSITIVE` compatible (adding optional fields is
  fine; removing/renaming required fields breaks CI). Schemas in `packages/kafka-schemas/` are
  the contract.
- No `.DS_Store`, `*.pyc`, `__pycache__`, or merge-conflict markers (sanity CI will block it).

---

## 15. Definition of Done

A change is done when **all** of these are true:

- [ ] English everywhere — no other language in code, comments, strings, logs, tests.
- [ ] No explanatory comments inside function bodies; only directives/TODOs remain.
- [ ] One docstring per file (module level); none on functions/classes.
- [ ] Functions are small and single-purpose; no mega-function.
- [ ] Names reveal intent; no internal codes (`D1`, `P0c`, …) in identifiers/strings.
- [ ] No duplicated logic; no magic numbers.
- [ ] Errors are surfaced, not swallowed.
- [ ] Fully typed; `mypy --strict` clean.
- [ ] Tests written, behaviour-named, 100% coverage, all green.
- [ ] `make lint` and `make test` pass locally.
- [ ] PR is single-purpose, correctly based (stacked PRs on their parent), described in English.

---

## 16. Reviewer checklist

Reviewers enforce this document. Request changes when you see:

- Any non-English text in code/comments/strings/logs/tests.
- Comments narrating what the code does, or commented-out code.
- More than one docstring in a file, or essay docstrings on functions.
- Functions doing several things / over ~60 lines / numbered-step bodies.
- Copy-pasted near-duplicates instead of a shared abstraction.
- Cryptic names or ticket codes leaking into identifiers and runtime strings.
- Magic numbers, swallowed exceptions, missing types, missing/!100% tests.
- Oversized or mis-based PRs (a dependent branch pointed at `main`).

Be specific and cite the file/line and the relevant section here, so feedback is actionable
and consistent across reviewers.
