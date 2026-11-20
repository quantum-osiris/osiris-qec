"""Phase 3: systematic single-qubit Pauli error injection (pre-preparation)."""
import json
from pathlib import Path

import numpy as np
import pytest

import qec_verify as qv

REPORT = Path(__file__).parent.parent / "reports" / "ERROR_CORRECTION_MATRIX.json"

N_SHOTS = 16


def _case_worker(args):
    pauli, qubits, seed = args
    initial = {q: pauli for q in qubits}
    rows = qv.run_shots(N_SHOTS, seed=seed, initial_paulis=initial)
    # detection: did any shot show a violated X stabilizer (syndrome != 0)?
    # with injected pre-prep errors, the X-syndrome is nonzero pre-correction; the
    # question is whether the FINAL state is in the codespace after feed-forward.
    in_code = sum(1 for r in rows if r["in_codespace"])
    return {
        "error": f"{pauli} on {list(qubits)}",
        "pauli": pauli,
        "qubits": list(qubits),
        "timing": "injected_before_preparation",
        "shots": N_SHOTS,
        "shots_in_codespace_after_feedforward": in_code,
        "corrected_fraction": in_code / N_SHOTS,
    }


@pytest.fixture(scope="module")
def matrix():
    cases = []
    for q in range(16):
        for p in ("X", "Y", "Z"):
            cases.append((p, [q], 1000 + q))
    # selected weight-2 Z errors (distance is 4, so t=1: weight-2 is NOT guaranteed)
    for pair in [(0, 1), (0, 4), (5, 6), (0, 5)]:
        cases.append(("Z", list(pair), 2000 + pair[0] * 16 + pair[1]))
    # ancilla error before round 1
    cases.append(("X", [16], 3000))
    cases.append(("Z", [16], 3001))

    import multiprocessing as mp
    with mp.Pool(16, initializer=qv._pool_init) as pool:
        results = pool.map(_case_worker, cases)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=1))
    return results


def test_z_errors_all_corrected(matrix):
    z_single = [r for r in matrix if r["pauli"] == "Z"
                and len(r["qubits"]) == 1 and r["qubits"][0] < 16]
    assert len(z_single) == 16
    assert all(r["corrected_fraction"] == 1.0 for r in z_single), \
        [r for r in z_single if r["corrected_fraction"] != 1.0]


def test_xy_errors_not_detected_by_x_syndrome(matrix):
    """X/Y errors flip Z-type generators, which this circuit never measures:
    after feed-forward the state is NOT in the codespace (limitation, recorded)."""
    xy = [r for r in matrix if r["pauli"] in ("X", "Y")
          and len(r["qubits"]) == 1 and r["qubits"][0] < 16]
    assert len(xy) == 32
    assert all(r["corrected_fraction"] == 0.0 for r in xy), \
        [r for r in xy if r["corrected_fraction"] != 0.0]


def test_weight2_z_recorded_not_guaranteed(matrix):
    w2 = [r for r in matrix if r["pauli"] == "Z" and len(r["qubits"]) == 2]
    # d=4 -> only t=1 guaranteed; just record outcomes, no assertion on success
    assert len(w2) == 4
