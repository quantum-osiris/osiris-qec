"""Phase 2: behavioral verification of the syndrome-assisted preparation."""
import numpy as np
import pytest
from pytket import Circuit, OpType

import qec_sim as qs
import qec_verify as qv
from wen_plaquette_pass import (
    ROUND_2_LUT_BE, WEN_STABILIZERS, WenPlaquetteFeedForwardPass,
    encode_syndrome_condition, hash_tket_circuit, EndiannessPolicy,
)


@pytest.fixture(scope="module")
def ops():
    return qv.build_ops()


# --- 1. Noiseless preparation: exact enumeration of ALL 256 measurement branches ---
def test_noiseless_preparation_all_branches_exact(ops):
    res = qv.enumerate_all_branches(n_proc=16)
    assert res["n_branches_total"] == 256
    # Exactly 128 of the 256 outcome combinations are reachable (the rest have
    # exactly zero probability and raise UnreachableBranch in the simulator);
    # every reachable branch must land in the codespace.
    assert res["n_reachable"] == 128 and res["n_unreachable"] == 128
    assert res["all_reachable_branches_ok"], (
        f"only {res['n_reachable_in_codespace']}/{res['n_reachable']} reachable branches "
        f"in codespace, worst expectation {res['worst_stabilizer_expectation_on_reachable']}"
    )


# --- 2. Stabilizer expectation verification on sampled shots ---
def test_stabilizer_expectations_sampled(ops):
    rows = qv.run_shots(10, seed=101, ops=ops)
    assert all(r["in_codespace"] for r in rows)
    assert min(r["min_stab_exp"] for r in rows) > 0.999


# --- 3. Feed-forward correctness: force each LUT syndrome on round 2 ---
@pytest.mark.parametrize("syndrome_be", sorted(ROUND_2_LUT_BE.keys()))
def test_feedforward_each_lut_syndrome(ops, syndrome_be):
    # round-1 outcomes all 0; round-2 outcome = syndrome bits (A1,A3,A9,A11)
    r2_bits = [int(ch) for ch in syndrome_be]
    outcome = (0, 0, 0, 0) + tuple(r2_bits)
    _, exps, _ = qv.run_branch(outcome, ops=ops)
    assert all(e > 0.999 for e in exps), f"syndrome {syndrome_be}: exps={exps}"


# --- 4. Syndrome-bit ordering ---
def test_syndrome_bit_ordering_unit():
    for s in ROUND_2_LUT_BE:
        v, p = encode_syndrome_condition(s, 4)
        assert v == int(s[::-1], 2) and p
    v, _ = encode_syndrome_condition("1", 1, enforce_even_parity=False)
    assert v == 1


def test_syndrome_bit_ordering_in_circuit(ops):
    # emitted 4-bit conditional values must equal the reversed BE syndrome strings
    b = WenPlaquetteFeedForwardPass()
    c = Circuit()
    b.to_tket_pass().apply(c)
    vals = sorted({cmd.op.value for cmd in c.get_commands()
                   if cmd.op.type == OpType.Conditional and cmd.op.width == 4})
    assert vals == sorted({int(s[::-1], 2) for s in ROUND_2_LUT_BE})


def test_odd_parity_syndrome_rejected():
    with pytest.raises(ValueError, match="parity"):
        encode_syndrome_condition("0001", 4, enforce_even_parity=True)


# --- 5. Deterministic reproducibility ---
def test_deterministic_circuit_and_branch():
    c1, c2 = Circuit(), Circuit()
    WenPlaquetteFeedForwardPass().to_tket_pass().apply(c1)
    WenPlaquetteFeedForwardPass().to_tket_pass().apply(c2)
    assert hash_tket_circuit(c1) == hash_tket_circuit(c2)
    ops = qv.build_ops()
    _, e1, _ = qv.run_branch((1, 0, 1, 1, 0, 1, 1, 0), ops=ops)
    _, e2, _ = qv.run_branch((1, 0, 1, 1, 0, 1, 1, 0), ops=ops)
    assert e1 == e2


# --- 6. Incorrect lookup-table detection (negative test) ---
def test_corrupted_lut_is_detected(ops, monkeypatch):
    import wen_plaquette_pass as wpp
    corrupted = dict(ROUND_2_LUT_BE)
    corrupted["0011"] = [10, 12]  # wrong second qubit
    monkeypatch.setattr(wpp, "ROUND_2_LUT_BE", corrupted)
    bad_ops = qv.build_ops()
    # force the corrupted syndrome branch: round-2 bits 0,0,1,1
    _, exps, _ = qv.run_branch((0, 0, 0, 0, 0, 0, 1, 1), ops=bad_ops)
    assert not all(e > 0.999 for e in exps), "corrupted LUT entry was NOT detected"


# --- 7. Circuit transformation integrity ---
def test_pass_rejects_nonempty_input():
    c = Circuit(2)
    c.H(0)
    with pytest.raises(ValueError):
        WenPlaquetteFeedForwardPass().to_tket_pass().apply(c)


# --- 8. Independent Aer (C++) cross-check of the full dynamic circuit ---
def test_aer_backend_cross_check():
    res = qv.aer_cross_check(n_shots=512, measurement_setting="X")
    assert res["passed"], res


# --- 8b. Measurement-basis verification (reviewer check 2) ---
def test_final_measurement_basis_is_explicit():
    """X setting: an H on q[i] must appear before the c5_end[i] Measure (X-basis
    readout). Z setting: no H on q[i] before it (Z-basis readout)."""
    for setting, expect_h in (("X", True), ("Z", False)):
        c = Circuit()
        WenPlaquetteFeedForwardPass(measurement_setting=setting).to_tket_pass().apply(c)
        cmds = c.get_commands()
        # only consider the final readout segment: after the last Barrier
        last_barrier = max(i for i, cc in enumerate(cmds) if cc.op.type == OpType.Barrier)
        tail = cmds[last_barrier + 1:]
        end_measures = [cmd for cmd in tail
                        if cmd.op.type == OpType.Measure and str(cmd.args[1]).startswith("c5_end")]
        assert len(end_measures) == 16
        for cmd in end_measures:
            q = cmd.args[0]
            h_in_tail = any(cc.op.type == OpType.H and cc.args[0] == q for cc in tail)
            assert h_in_tail == expect_h, \
                f"setting {setting}: H in final readout segment on {q} is {h_in_tail}, expected {expect_h}"


def test_aer_backend_cross_check_z_basis():
    """Z-basis readout must satisfy Z-plaquette parity (not X)."""
    res = qv.aer_cross_check(n_shots=256, measurement_setting="Z")
    assert res["passed"], res
