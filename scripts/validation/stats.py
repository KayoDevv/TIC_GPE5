"""Pure statistics helpers for the validation report (P0d).

No I/O, no duckdb — golden-tested in tests/test_stats.py. The point: a rate
measured on a small corpus must never be reported as a bare number. The Wilson
score interval gives an honest band (and, unlike the normal approximation, stays
inside [0, 1] and behaves at the p=0 / p=1 extremes — exactly our case, where
precision is often 1.0 on a handful of positives).
"""

from __future__ import annotations

import math

# 95% two-sided normal quantile. Kept as the single default; expose z so a
# report can widen to 99% if ever needed.
Z_95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Returns (low, high), both clamped to [0, 1]. With no observations (n == 0)
    the proportion is undefined, so we return the fully uninformative [0, 1].
    """
    if successes < 0 or n < 0:
        raise ValueError("successes and n must be non-negative")
    if successes > n:
        raise ValueError(f"successes ({successes}) cannot exceed n ({n})")
    if n == 0:
        return (0.0, 1.0)

    phat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def fmt_rate(successes: int, n: int, z: float = Z_95) -> str:
    """Render a rate as 'value (95% CI [lo, hi], n=N)' — the P0c reporting rule.

    On an empty denominator, says so rather than printing a fake 0.000.
    """
    if n == 0:
        return "n/a (n=0)"
    lo, hi = wilson_interval(successes, n, z)
    return f"{successes / n:.3f} (95% CI [{lo:.3f}, {hi:.3f}], n={n})"
