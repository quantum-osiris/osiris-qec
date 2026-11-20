"""Shared verification helpers: branch enumeration (exact), Aer cross-check,
error-injection runner. Worker functions are top-level for multiprocessing."""
from __future__ import annotations

import itertools
import multiprocessing as mp
from typing import Dict, List, Optional, Tuple

import numpy as np
from pytket import Circuit

from wen_plaquette_pass import (
    ROUND_1_MAP, ROUND_2_MAP, WEN_STABILIZERS, WenPlaquetteFeedForwardPass,
)
import qec_sim as qs

# The 8 mid-circuit stabilizer-measurement bit keys, in circuit order:
# round 1 -> c{i}_1st[0], round 2 -> c4_2nd[0..3]
MEAS_BITKEYS: List[str] = (
    [f"c{ROUND_1_MAP[s][2]}_1st[0]" for s in sorted(ROUND_1_MAP)]
    + [f"c4_2nd[{ROUND_2_MAP[s][1]}]" for s in sorted(ROUND_2_MAP)]
)

ALL_STABS = [(s.pauli_type, tuple(s.support)) for s in WEN_STABILIZERS]
X_STABS = [(i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "X"]
Z_STABS = [(i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "Z"]

_OPS = None


def build_ops(**kw) -> list:
    b = WenPlaquetteFeedForwardPass(**kw)
    c = Circuit()
    b.to_tket_pass().apply(c)
    return qs.compile_circuit(c)


def get_ops() -> list:
    global _OPS
    if _OPS is None:
        _OPS = build_ops()
    return _OPS


def stabilizer_expectations(state) -> List[float]:
    return [qs.expectation(state, t, sup) for t, sup in ALL_STABS]


def run_branch(outcome_bits: Tuple[int, ...], ops: Optional[list] = None,
               initial_paulis: Optional[Dict[int, str]] = None):
    """Deterministic branch: force all 8 stabilizer-measurement outcomes."""
    ops = ops if ops is not None else get_ops()
    outcomes = {bk: int(v) for bk, v in zip(MEAS_BITKEYS, outcome_bits)}
    state, classical = qs.run_ops(ops, outcomes=outcomes, initial_paulis=initial_paulis)
    exps = stabilizer_expectations(state)
    return outcome_bits, exps, classical


def _branch_worker(args):
    outcome_bits, initial_paulis = args
    try:
        ob, exps, classical = run_branch(outcome_bits, initial_paulis=initial_paulis)
    except qs.UnreachableBranch:
        return outcome_bits, None, None  # parity-forbidden branch: zero probability
    return outcome_bits, min(exps), all(e > 0.999 for e in exps)


def _pool_init():
    # keep BLAS single-threaded inside workers to avoid oversubscription
    import os
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = "1"


def enumerate_all_branches(n_proc: int = 16) -> Dict[str, object]:
    """Exhaustive exact enumeration of all 2^8 measurement branches.
    Branches with odd popcount are parity-forbidden (product of all 8 X
    generators = identity => even number of -1 outcomes): they must be
    unreachable (zero probability), and all reachable ones must be in the
    codespace."""
    combos = list(itertools.product([0, 1], repeat=len(MEAS_BITKEYS)))
    with mp.Pool(n_proc, initializer=_pool_init) as pool:
        results = pool.map(_branch_worker, [(c, None) for c in combos], chunksize=4)
    reachable = [(ob, w, ok) for ob, w, ok in results if ok is not None]
    unreachable = [ob for ob, w, ok in results if ok is None]
    n_ok = sum(1 for _, _, ok in reachable if ok)
    worst = min(w for _, w, _ in reachable)
    return {
        "n_branches_total": len(combos),
        "n_reachable": len(reachable),
        "n_unreachable": len(unreachable),
        "n_reachable_in_codespace": n_ok,
        "worst_stabilizer_expectation_on_reachable": worst,
        "all_reachable_branches_ok": n_ok == len(reachable) and len(reachable) > 0,
    }


def run_shots(n_shots: int, seed: int, ops: Optional[list] = None,
              initial_paulis: Optional[Dict[int, str]] = None,
              noise: Optional[Dict[str, float]] = None,
              target: Optional[np.ndarray] = None):
    """Sampled shots; returns per-shot metrics."""
    ops = ops if ops is not None else get_ops()
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_shots):
        state, classical = qs.run_ops(ops, rng=rng, initial_paulis=initial_paulis, noise=noise)
        exps = stabilizer_expectations(state)
        row = {
            "min_stab_exp": min(exps),
            "all_x_plus1": all(e > 0.999 for (i, sup) in X_STABS
                               for e in [qs.expectation(state, "X", sup)]),
            "in_codespace": all(e > 0.999 for e in exps),
            "fidelity_to_target": (qs.state_fidelity(state, target)
                                   if target is not None else None),
        }
        rows.append(row)
    return rows


def _shot_worker(args):
    n_shots, seed, initial_paulis, noise = args
    return run_shots(n_shots, seed, initial_paulis=initial_paulis, noise=noise)


def aer_cross_check(n_shots: int = 512, measurement_setting: str = "X") -> Dict[str, object]:
    """Run on qiskit AerBackend (C++ simulator) and validate the final readout
    against the parity constraints of the basis the circuit actually measures.

    measurement_setting="X": final readout is X-basis (H + Measure); prepared state
      has all X stabilizers = +1, so outcome strings must have even parity on every
      X plaquette.
    measurement_setting="Z": final readout is Z-basis; Z-plaquette parity must be even.
    A single destructive readout verifies only one basis; the other requires a
    second run (or direct state inspection, done in the statevector tests).
    """
    from pytket.extensions.qiskit import AerBackend

    b = WenPlaquetteFeedForwardPass(measurement_setting=measurement_setting)
    c = Circuit()
    b.to_tket_pass().apply(c)
    be = AerBackend()
    cc = be.get_compiled_circuit(c)
    res = be.run_circuit(cc, n_shots=n_shots)
    counts = res.get_counts()
    bits = list(cc.bits)  # order of outcome tuples
    end_idx = sorted(
        (i for i, bt in enumerate(bits) if str(bt).startswith("c5_end")),
        key=lambda i: int(str(bits[i]).split("[")[1].rstrip("]")),
    )
    stabs = X_STABS if measurement_setting == "X" else Z_STABS
    ptype = "X" if measurement_setting == "X" else "Z"
    violations = 0
    checked = 0
    for outcome, n in counts.items():
        x = [outcome[i] for i in end_idx]  # c5_end[0..15] in register order
        for _, sup in stabs:
            if sum(x[q] for q in sup) % 2 != 0:
                violations += 1
                break
        checked += n
    return {
        "backend": "qiskit-aer AerBackend (dynamic circuit, mid-circuit measurement + feed-forward)",
        "measurement_setting": measurement_setting,
        "n_shots": n_shots,
        "distinct_outcomes": len(counts),
        "outcomes_checked": checked,
        f"{ptype.lower()}_plaquette_parity_violations": violations,
        "passed": violations == 0 and checked == n_shots,
    }
