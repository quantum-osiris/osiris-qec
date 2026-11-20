"""Phase 1: compiler-pass contract regression tests."""
import pytest
from pytket import Circuit, OpType
from pytket.circuit import QubitRegister

import dnalang_wen_plaquette_pass as baseline
import wen_plaquette_pass as fixed
from wen_plaquette_pass import (
    N_TOTAL, WenPlaquetteFeedForwardPass, hash_tket_circuit,
)


def build(pass_cls, **kw):
    b = pass_cls(**kw)
    circ = Circuit()
    b.to_tket_pass().apply(circ)
    return b, circ


def test_empty_input_accepted_and_builds():
    b, circ = build(fixed.WenPlaquetteFeedForwardPass)
    assert circ.n_qubits == N_TOTAL
    reg_names = {r.name: r.size for r in circ.q_registers}
    assert reg_names == {"q": 20}
    creg = {r.name: r.size for r in circ.c_registers}
    assert creg == {"c0_1st": 1, "c1_1st": 1, "c2_1st": 1, "c3_1st": 1, "c4_2nd": 4, "c5_end": 20}
    assert b.last_capsule is not None


def test_nonempty_input_rejected():
    b = fixed.WenPlaquetteFeedForwardPass()
    circ = Circuit(2)
    circ.H(0)
    with pytest.raises(ValueError, match="preparation-only"):
        b.to_tket_pass().apply(circ)


def test_conflicting_q_register_rejected():
    b = fixed.WenPlaquetteFeedForwardPass()
    circ = Circuit()
    circ.add_q_register(QubitRegister("q", 5))  # declared but empty; size conflicts
    with pytest.raises(ValueError, match="size"):
        b.to_tket_pass().apply(circ)


def test_empty_with_matching_declared_register_accepted():
    b = fixed.WenPlaquetteFeedForwardPass()
    circ = Circuit()
    circ.add_q_register(QubitRegister("q", N_TOTAL))  # compatible declaration, no commands
    b.to_tket_pass().apply(circ)
    assert circ.n_qubits == N_TOTAL


def test_deterministic_generation():
    _, c1 = build(fixed.WenPlaquetteFeedForwardPass)
    _, c2 = build(fixed.WenPlaquetteFeedForwardPass)
    assert hash_tket_circuit(c1) == hash_tket_circuit(c2)


def test_output_structure_counts():
    _, circ = build(fixed.WenPlaquetteFeedForwardPass)
    cmds = circ.get_commands()
    cond = sum(1 for c in cmds if c.op.type == OpType.Conditional)
    reset = sum(1 for c in cmds if c.op.type == OpType.Reset)
    meas = sum(1 for c in cmds if c.op.type == OpType.Measure)
    cx = sum(1 for c in cmds if c.op.type == OpType.CX)
    assert (cond, reset, meas, cx) == (20, 8, 24, 32)


def test_regression_identical_to_baseline_on_empty_input():
    """Existing functionality intact: corrected pass produces the identical circuit
    to the original baseline when applied to an empty circuit."""
    _, c_base = build(baseline.WenPlaquetteFeedForwardPass)
    _, c_fixed = build(fixed.WenPlaquetteFeedForwardPass)
    assert hash_tket_circuit(c_base) == hash_tket_circuit(c_fixed)


def test_baseline_silently_discards_nonempty_input_documented():
    """Documents WHY the contract repair was needed: the baseline silently
    replaces a nonempty input circuit."""
    b = baseline.WenPlaquetteFeedForwardPass()
    circ = Circuit(3)
    circ.H(0).CX(0, 1)
    b.to_tket_pass().apply(circ)
    # baseline output has no trace of the input H/CX on q[0..2] prep... it rebuilds fresh
    assert circ.n_qubits == 20  # input was silently discarded, not composed


def test_capsule_fields():
    b, circ = build(fixed.WenPlaquetteFeedForwardPass, target_device="H2-1")
    cap = b.last_capsule
    assert cap.conditional_op_count == 20
    assert cap.reset_op_count == 8
    assert cap.post_pass_circuit_sha256 == hash_tket_circuit(circ)
    assert len(cap.capsule_sha256) == 64
    assert cap.endianness_audit  # nonempty audit log
