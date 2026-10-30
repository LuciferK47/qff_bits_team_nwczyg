"""Joint block bootstrap of the whole analysis pipeline.

Every leaf of ``data`` is a counts dict (one execution block / circuit / calibration circuit). A replicate
redraws EACH block multinomially with its own shot total (identical in distribution to resampling the shot
records with replacement), then re-runs the entire pipeline: moments, readout correction, C/kappa, ZNE.
"""
from __future__ import annotations

import numpy as np


def resample_counts(counts: dict[str, int], rng: np.random.Generator) -> dict[str, int]:
    keys = list(counts)
    c = np.array([counts[k] for k in keys], dtype=np.int64)
    new = rng.multinomial(int(c.sum()), c / c.sum())
    return {k: int(v) for k, v in zip(keys, new) if v}


def _map(data, f):
    if isinstance(data, dict) and data and all(isinstance(v, (int, np.integer)) for v in data.values()):
        return f(data)
    if isinstance(data, dict):
        return {k: _map(v, f) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return type(data)(_map(v, f) for v in data)
    return data


def bootstrap(data, pipeline, B: int = 2000, seed: int = 20261029, alpha: float = 0.05,
              min_valid_fraction: float = 0.99):
    """pipeline(data) -> {label: float}; labels may be any hashable (tuples are fine).

    Returns {label: dict(point, lo, hi, se, bias, n_valid, B, valid_fraction, failed_reason)}.
    An interval is reported ONLY if the point estimate is finite and at least ``min_valid_fraction`` of the
    replicates are finite; otherwise lo/hi/se are NaN and ``failed_reason`` says why. An interval is never built
    from a subset of replicates when the estimator is not reliably defined.
    """
    point = pipeline(data)
    rng = np.random.default_rng(seed)
    reps = {k: np.empty(B) for k in point}
    for b in range(B):
        res = pipeline(_map(data, lambda c: resample_counts(c, rng)))
        for k in point:
            reps[k][b] = res[k]
    out = {}
    for k, v in point.items():
        r = reps[k][np.isfinite(reps[k])]
        frac = r.size / B
        rec = dict(point=v, lo=float("nan"), hi=float("nan"), se=float("nan"), bias=float("nan"),
                   n_valid=int(r.size), B=B, valid_fraction=frac, failed_reason=None)
        if not np.isfinite(v):
            rec["failed_reason"] = "non_finite_point"
        elif r.size < 2 or frac < min_valid_fraction:
            rec["failed_reason"] = "insufficient_finite_bootstrap"
        else:
            rec.update(lo=float(np.percentile(r, 100 * alpha / 2)), hi=float(np.percentile(r, 100 * (1 - alpha / 2))),
                       se=float(r.std(ddof=1)), bias=float(r.mean() - v))
        out[k] = rec
    return out
