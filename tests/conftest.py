"""Cap multiprocessing.Pool worker count during pytest to prevent 20-qubit statevector OOM under pytest-cov."""

from __future__ import annotations

import multiprocessing as _mp

_orig_pool = _mp.Pool


def _bounded_pool(processes=None, *args, **kwargs):
    if isinstance(processes, int) and processes > 2:
        processes = 2
    return _orig_pool(processes, *args, **kwargs)


_mp.Pool = _bounded_pool  # type: ignore[assignment]
