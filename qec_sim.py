"""
Exact statevector simulator for the 20-qubit preparation circuit.

Handles H, CX, Z, mid-circuit Measure, Reset, Barrier, and pytket Conditional
(OpType.Conditional wrapping a gate) with condition_bits[0] as LSB.

Two execution modes:
  - run_branch(..., outcomes={bitkey: 0/1}): deterministic branch enumeration
    (feed every measurement outcome explicitly) -> EXACT, no sampling.
  - run_shot(..., rng=...): sampled outcomes + optional Pauli noise model
    (Monte Carlo trajectories for the noisy benchmark).

Qubit q[i] maps to statevector bit i (little-endian), state size 2^20.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from pytket import Circuit, OpType

N_TOTAL = 20
DIM = 1 << N_TOTAL
IDX = np.arange(DIM)

H_GATE = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
Z_GATE = np.array([[1, 0], [0, -1]], dtype=complex)
X_GATE = np.array([[0, 1], [1, 0]], dtype=complex)
Y_GATE = np.array([[0, -1j], [1j, 0]], dtype=complex)
PAULIS = {"X": X_GATE, "Z": Z_GATE, "Y": Y_GATE, "I": np.eye(2, dtype=complex)}


class UnreachableBranch(Exception):
    """Raised when a forced measurement outcome has zero probability."""


def qidx(q) -> int:
    return q.index[0] if hasattr(q, "index") else q[1]


def bitkey(b) -> str:
    return str(b)


def compile_circuit(circ: Circuit) -> List[tuple]:
    """Flatten a pytket circuit into plain op tuples (stops at first Barrier)."""
    ops: List[tuple] = []
    for cmd in circ.get_commands():
        op = cmd.op
        t = op.type
        args = cmd.args
        if t == OpType.Barrier:
            ops.append(("BARRIER",))
            break
        elif t == OpType.H:
            ops.append(("H", qidx(args[0])))
        elif t == OpType.CX:
            ops.append(("CX", qidx(args[0]), qidx(args[1])))
        elif t == OpType.Z:
            ops.append(("Z", qidx(args[0])))
        elif t == OpType.X:
            ops.append(("X", qidx(args[0])))
        elif t == OpType.Measure:
            ops.append(("MEASURE", qidx(args[0]), bitkey(args[1])))
        elif t == OpType.Reset:
            ops.append(("RESET", qidx(args[0])))
        elif t == OpType.Conditional:
            inner = op.op
            bits = [bitkey(b) for b in args[: op.width]]
            targets = [qidx(q) for q in args[op.width:]]
            if inner.type == OpType.Z:
                ops.append(("CZ", tuple(bits), int(op.value), tuple(targets)))
            else:
                raise RuntimeError(f"unsupported conditional inner op {inner.type}")
        else:
            raise RuntimeError(f"unsupported op {t}")
    return ops


_MASK1_CACHE: Dict[int, np.ndarray] = {}
_CX_CACHE: Dict[tuple, tuple] = {}


def _mask1(q: int) -> np.ndarray:
    if q not in _MASK1_CACHE:
        _MASK1_CACHE[q] = (IDX >> q) & 1 == 1
    return _MASK1_CACHE[q]


def apply_1q(state: np.ndarray, m: np.ndarray, q: int) -> np.ndarray:
    s = state.reshape(1 << (N_TOTAL - 1 - q), 2, 1 << q)
    a = s[:, 0, :].copy()
    b = s[:, 1, :]
    s[:, 0, :] = m[0, 0] * a + m[0, 1] * b
    s[:, 1, :] = m[1, 0] * a + m[1, 1] * b
    return state


def apply_cx(state: np.ndarray, c: int, t: int) -> np.ndarray:
    key = (c, t)
    if key not in _CX_CACHE:
        m = _mask1(c)
        _CX_CACHE[key] = (IDX[m], IDX[m] ^ (1 << t))
    src, tgt = _CX_CACHE[key]
    tmp = state[tgt].copy()
    state[tgt] = state[src]
    state[src] = tmp
    return state


def apply_x(state: np.ndarray, q: int) -> np.ndarray:
    return state[IDX ^ (1 << q)]


def zero_out(state: np.ndarray, q: int, keep_bit: int) -> np.ndarray:
    return np.where(_mask1(q) == (keep_bit == 1), state, 0.0)


def run_ops(
    ops: Sequence[tuple],
    outcomes: Optional[Dict[str, int]] = None,
    rng: Optional[np.random.Generator] = None,
    initial_paulis: Optional[Dict[int, str]] = None,
    noise: Optional[Dict[str, float]] = None,
) -> Tuple[np.ndarray, Dict[str, int]]:
    """
    Execute compiled ops on |0...0> (plus optional initial Pauli errors).

    outcomes: explicit measurement results keyed by bitkey (deterministic branch).
              If None, outcomes are sampled with rng.
    noise: optional dict with keys p_1q, p_2q, p_meas, p_reset (depolarizing /
           bit-flip probabilities applied after the corresponding op).
    Returns (final_state_before_barrier, classical_register_dict).
    """
    state = np.zeros(DIM, dtype=complex)
    state[0] = 1.0
    if initial_paulis:
        for q, p in initial_paulis.items():
            state = apply_1q(state, PAULIS[p], q)
    classical: Dict[str, int] = {}

    def maybe_noise(kind: str) -> None:
        if noise and noise.get(kind, 0.0) > 0 and rng is not None:
            p = noise[kind]
            if rng.random() < p:
                q = int(rng.integers(0, N_TOTAL))
                state[...] = apply_1q(state, PAULIS["XYZ"[int(rng.integers(0, 3))]], q)

    for op in ops:
        kind = op[0]
        if kind == "BARRIER":
            break
        elif kind == "H":
            state = apply_1q(state, H_GATE, op[1])
            maybe_noise("p_1q")
        elif kind == "X":
            state = apply_1q(state, X_GATE, op[1])
        elif kind == "Z":
            state = apply_1q(state, Z_GATE, op[1])
            maybe_noise("p_1q")
        elif kind == "CX":
            state = apply_cx(state, op[1], op[2])
            maybe_noise("p_2q")
        elif kind == "CZ":
            _, bits, value, targets = op
            cond = sum(classical.get(b, 0) << i for i, b in enumerate(bits))
            if cond == value:
                for q in targets:
                    state = apply_1q(state, Z_GATE, q)
                maybe_noise("p_1q")
        elif kind == "MEASURE":
            _, q, bk = op
            p1 = float(np.sum(np.abs(state[_mask1(q)]) ** 2))
            if outcomes is not None:
                outcome = outcomes[bk]
                assert outcome in (0, 1)
                if (outcome == 1 and p1 < 1e-12) or (outcome == 0 and p1 > 1 - 1e-12):
                    raise UnreachableBranch(f"forced outcome {outcome} for {bk} has p={p1}")
            else:
                outcome = 1 if rng.random() < p1 else 0
            state = zero_out(state, q, outcome)
            state /= np.linalg.norm(state)
            classical[bk] = outcome
            if noise and noise.get("p_meas", 0.0) > 0 and rng is not None:
                if rng.random() < noise["p_meas"]:
                    classical[bk] ^= 1  # recorded bit flips; correction logic sees wrong bit
        elif kind == "RESET":
            # Reset-to-|0> on a qubit that (post-measurement) is in a product
            # state |b>: if b==1 this is an X flip; if b==0 it is a no-op.
            _, q = op
            m1 = _mask1(q)
            p1 = float(np.sum(np.abs(state[m1]) ** 2))
            if p1 > 0.5:
                state = apply_x(state, q)
            elif p1 > 0:
                state = np.where(m1, 0.0, state)
                state /= np.linalg.norm(state)
            maybe_noise("p_reset")
        else:
            raise RuntimeError(f"unhandled op {kind}")
    return state, classical


def expectation(state: np.ndarray, ptype: str, support: Sequence[int]) -> float:
    s = state
    if ptype in ("X", "Y"):
        for q in support:
            s = apply_x(s, q) if ptype == "X" else apply_1q(s, Y_GATE, q)
    elif ptype == "Z":
        idx_mask = np.zeros(DIM, dtype=bool)
        for q in support:
            idx_mask ^= _mask1(q)
        s = np.where(idx_mask, -state, state)
    return float(np.real(np.vdot(state, s)))


def state_fidelity(state: np.ndarray, target: np.ndarray) -> float:
    return float(abs(np.vdot(target, state)) ** 2)
