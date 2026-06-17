"""P0d — confidence intervals on the accuracy figures.

A point estimate on a small corpus is not a result (P0c). Every rate the report
quotes (precision, recall, false-negative rate) must carry a Wilson score
interval. These tests pin the maths against hand-computed references.

Runnable on a plain host (pure module, no duckdb).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stats import wilson_interval


def _approx(a: float, b: float, tol: float = 1e-3) -> bool:
    return math.isclose(a, b, abs_tol=tol)


def test_perfect_precision_small_n_is_not_significant():
    # precision 1.0 on n=8 → 95% Wilson ≈ [0.676, 1.0]: the P0c example.
    lo, hi = wilson_interval(8, 8)
    assert _approx(lo, 0.6756), lo
    assert _approx(hi, 1.0), hi


def test_zero_successes_capped_at_zero_lower():
    lo, hi = wilson_interval(0, 8)
    assert _approx(lo, 0.0)
    assert hi < 1.0  # upper is informative, lower clamped to 0


def test_half_is_symmetric_around_one_half():
    lo, hi = wilson_interval(50, 100)
    assert _approx((lo + hi) / 2, 0.5, tol=1e-6)


def test_larger_n_tightens_interval():
    _, hi_small = wilson_interval(8, 8)
    lo_big, hi_big = wilson_interval(800, 800)
    # 1.0 on n=800 is far tighter than on n=8.
    assert (hi_big - lo_big) < (hi_small - wilson_interval(8, 8)[0])
    assert lo_big > 0.99


def test_n_zero_returns_full_uninformative_interval():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_bounds_clamped_to_unit_interval():
    lo, hi = wilson_interval(8, 8)
    assert 0.0 <= lo <= hi <= 1.0


def test_successes_cannot_exceed_n():
    try:
        wilson_interval(9, 8)
    except ValueError:
        return
    raise AssertionError("expected ValueError for successes > n")
