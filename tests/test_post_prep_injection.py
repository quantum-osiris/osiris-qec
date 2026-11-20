"""Check 1 (reviewer): post-PREPARATION error injection, reported separately from
pre-preparation injection. After the prep circuit there are no further syndrome
rounds, so a post-prep error cannot be corrected by this circuit; we verify it is
at least DETECTABLE (nonzero X-syndrome for Z errors) and record that no
correction is applied."""
import json
from pathlib import Path

import numpy as np
import pytest

import qec_sim as qs
import qec_verify as qv
from wen_plaquette_pass import WEN_STABILIZERS

REPORT = Path(__file__).parent.parent / "reports" / "POST_PREP_INJECTION.json"

X_STABS = [(i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "X"]
Z_STABS = [(i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "Z"]
ALL = [(s.pauli_type, s.support) for s in WEN_STABILIZERS]


def prep_state():
    """Prepared state on the all-zero (reachable) branch, before the final barrier."""
    ops = qv.build_ops()
    st, _ = qs.run_ops(ops, outcomes={bk: 0 for bk in qv.MEAS_BITKEYS})
    return st


def syndrome_of(state):
    xs = [qs.expectation(state, "X", sup) for _, sup in X_STABS]
    zs = [qs.expectation(state, "Z", sup) for _, sup in Z_STABS]
    return xs, zs


def test_post_prep_z_error_detectable_but_not_corrected():
    state0 = prep_state()
    # sanity: prepared state is in the codespace
    assert all(e > 0.999 for e in [qs.expectation(state0, t, s) for t, s in ALL])
    results = []
    for q in range(16):
        st = qs.apply_1q(state0.copy(), qs.Z_GATE, q)  # error AFTER preparation
        xs, zs = syndrome_of(st)
        x_syn = [i for i, (_, sup) in enumerate(X_STABS) if xs[i] < 0.999]
        in_code = all(e > 0.999 for e in xs + zs)
        results.append({
            "error": f"Z on data q{q} AFTER prep",
            "x_syndrome_plaquettes": x_syn,
            "detected": len(x_syn) > 0,
            "in_codespace": in_code,
            "corrected": False,
            "classification": "detected_by_x_syndrome_but_NOT_corrected (no post-prep syndrome round)",
        })
    # contrast: same Z error BEFORE preparation is corrected
    ops = qv.build_ops()
    st_pre, _ = qs.run_ops(ops, outcomes={bk: 0 for bk in qv.MEAS_BITKEYS}, initial_paulis={5: "Z"})
    results.append({
        "error": "Z on data q5 BEFORE prep (contrast)",
        "detected": True,
        "in_codespace": all(e > 0.999 for e in [qs.expectation(st_pre, t, s) for t, s in ALL]),
        "corrected": True,
        "classification": "corrected_by_feedforward",
        "fidelity_to_prepared_state": qs.state_fidelity(st_pre, state0),
    })
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=1))
    # every post-prep single Z error produces a nonzero X-syndrome (detectable) ...
    assert all(r["detected"] for r in results[:16])
    # ... but the circuit has no post-prep correction stage, so none is recovered
    assert all(not r["in_codespace"] for r in results[:16])
    assert results[16]["corrected"] and results[16]["in_codespace"]


def test_post_prep_x_error_undetected_by_x_syndrome():
    state0 = prep_state()
    recs = []
    # X errors: flip only Z stabilizers (never measured) -> UNDETECTED by this circuit
    for q in (0, 5, 15):
        st = qs.apply_1q(state0.copy(), qs.X_GATE, q)
        xs, zs = syndrome_of(st)
        x_syn = [i for i, (_, sup) in enumerate(X_STABS) if xs[i] < 0.999]
        z_syn = [i for i, (_, sup) in enumerate(Z_STABS) if zs[i] < 0.999]
        recs.append({
            "error": f"X on data q{q} AFTER prep",
            "x_syndrome_plaquettes": x_syn,
            "z_syndrome_plaquettes": z_syn,
            "detected": len(x_syn) > 0,
            "in_codespace": all(e > 0.999 for e in xs + zs),
            "corrected": False,
            "classification": "UNDETECTED (X-syndrome zero; Z-syndrome nonzero but Z generators never measured)",
        })
    # Y errors: flip both -> X-syndrome nonzero (partially detected) but still not corrected
    for q in (0, 5, 15):
        st = qs.apply_1q(state0.copy(), qs.Y_GATE, q)
        xs, zs = syndrome_of(st)
        x_syn = [i for i, (_, sup) in enumerate(X_STABS) if xs[i] < 0.999]
        z_syn = [i for i, (_, sup) in enumerate(Z_STABS) if zs[i] < 0.999]
        recs.append({
            "error": f"Y on data q{q} AFTER prep",
            "x_syndrome_plaquettes": x_syn,
            "z_syndrome_plaquettes": z_syn,
            "detected": len(x_syn) > 0,
            "in_codespace": all(e > 0.999 for e in xs + zs),
            "corrected": False,
            "classification": "PARTIALLY_DETECTED (X-syndrome nonzero) but NOT corrected; Z-syndrome unmeasured",
        })
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(REPORT.read_text()) if REPORT.exists() else []
    REPORT.write_text(json.dumps(existing + recs, indent=1))
    x_recs = [r for r in recs if r["error"].startswith("X ")]
    y_recs = [r for r in recs if r["error"].startswith("Y ")]
    assert all(not r["detected"] and not r["in_codespace"] and len(r["z_syndrome_plaquettes"]) == 2
               for r in x_recs)
    assert all(r["detected"] and not r["in_codespace"] and len(r["x_syndrome_plaquettes"]) == 2
               and len(r["z_syndrome_plaquettes"]) == 2 for r in y_recs)


def test_prep_vs_post_prep_contrast():
    """Same Z error: before prep -> corrected (fidelity 1); after prep -> not recovered."""
    ops = qv.build_ops()
    state0 = prep_state()
    # pre-prep injection, same all-zero branch
    st_pre, _ = qs.run_ops(ops, outcomes={bk: 0 for bk in qv.MEAS_BITKEYS}, initial_paulis={5: "Z"})
    fid_pre = qs.state_fidelity(st_pre, state0)
    # post-prep injection
    st_post = qs.apply_1q(state0.copy(), qs.Z_GATE, 5)
    fid_post = qs.state_fidelity(st_post, state0)
    assert fid_pre > 0.999      # corrected by feed-forward
    assert fid_post < 0.001     # not corrected: no syndrome round after prep
