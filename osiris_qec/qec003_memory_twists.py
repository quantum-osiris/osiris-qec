"""
OSIRIS-QEC-003: Full X+Z Toroidal Memory Cycles & Checkerboard Twist-Defect Anyon Braiding.

Addresses the two untested topological upgrades beyond OSIRIS-QEC-002's X-only
preparation pass:
  1. Part 1 — Multi-round full X+Z syndrome memory on the 4x4 torus (`[[16,2,4]]`,
     16 data + 4 recycled ancilla ions = 20 qubits on Quantinuum H2-1, 0 SWAPs),
     CSS log-LLR Belief Propagation + Ordered Statistics Decoding (`BP+OSD-CS`)
     over `(H_X, H_Z)` (`rank(H_X) = rank(H_Z) = 7`), exhaustive 48/48 weight-1
     post-preparation quantum-circuit recovery proof + exhaustive 1,080/1,080
     weight-2 fault detection & coset-tie taxonomy, and seeded Monte Carlo
     depolarizing memory benchmarks across `R in {1, 2, 3}`.
  2. Part 2 — Explicit checkerboard lattice dislocation (Bombin twist-defect pair)
     on the 16-qubit periodic lattice with two weight-5 mixed-parity twist
     stabilizers (`T1 = +X4.Y5.Z6.X8.X9`, `T2 = -Z4.Z7.Z8.X10.Y11`) and a mixed
     `XXZZ` branch-cut plaquette (`B1 = +X6.X7.Z9.Z10`), exact algebraic proof of
     pairwise commutation, unified Z_2 fermion parity (`prod G_j = +I`), exact
     `[[16, 2, 4]]` parameters, deterministic 20-qubit twist-vacuum preparation,
     explicit `e <-> m` electric-magnetic anyon transmutation & twist condensation,
     and offline H2-1 ISA compilation (`QuantinuumAPIOffline`, 0 SWAPs).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations, product
from pathlib import Path
from typing import Any, Literal

import numpy as np
import rfc8785
from pytket import Circuit, OpType
from pytket.circuit import Bit, BitRegister, Qubit, QubitRegister

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import qec_math as qm
import qec_sim as qs
from hardware.quantinuum_h2 import local_h2_compile
from osiris_qec.wen_plaquette_pass import (
    N_ANCILLA,
    N_DATA,
    N_TOTAL,
    ROUND_1_MAP,
    ROUND_2_LUT_BE,
    ROUND_2_MAP,
    WEN_STABILIZERS,
    WenPlaquetteFeedForwardPass,
    _prepared_reference_state,
    encode_syndrome_condition,
    hash_tket_circuit,
    normalize_circuit_metadata,
)
from submission.run_nexus_qec002 import (
    SHOT_TIERS,
    compute_hqc_metrics,
    verify_native_h2_isa,
)

DEFAULT_REPORT_PATH = ROOT / "reports" / "qec003_verification_report.json"

QEC003_PROTOCOL_ID = "OSIRIS-QEC-003"
QEC003_VERSION = "1.2.0"

X_PLAQUETTE_INDICES: tuple[int, ...] = (1, 3, 4, 6, 9, 11, 12, 14)
Z_PLAQUETTE_INDICES: tuple[int, ...] = (0, 2, 5, 7, 8, 10, 13, 15)
X_POS_MAP: dict[int, int] = {stab_idx: pos for pos, stab_idx in enumerate(X_PLAQUETTE_INDICES)}
Z_POS_MAP: dict[int, int] = {stab_idx: pos for pos, stab_idx in enumerate(Z_PLAQUETTE_INDICES)}

# Vertex-disjoint 4-plaquette parallel sub-batches on the 4x4 torus
X_BATCH_A: tuple[int, ...] = (4, 6, 12, 14)
X_BATCH_B: tuple[int, ...] = (1, 3, 9, 11)
Z_BATCH_A: tuple[int, ...] = (0, 2, 8, 10)
Z_BATCH_B: tuple[int, ...] = (5, 7, 13, 15)

S_GATE = np.array([[1.0, 0.0], [0.0, 1.0j]], dtype=complex)
SDG_GATE = np.array([[1.0, 0.0], [0.0, -1.0j]], dtype=complex)

_CZ_MASK_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _apply_cz(state: np.ndarray, q1: int, q2: int) -> np.ndarray:
    key = (min(q1, q2), max(q1, q2))
    if key not in _CZ_MASK_CACHE:
        _CZ_MASK_CACHE[key] = qs._mask1(key[0]) & qs._mask1(key[1])
    return np.where(_CZ_MASK_CACHE[key], -state, state)


def compile_dynamic_ops(circ: Circuit, stop_at_first_barrier: bool = False) -> list[tuple]:
    """Flatten a 20-qubit pytket circuit (including S, Sdg, Y, CZ, Conditional X/Y/Z) for exact simulation."""
    ops: list[tuple] = []
    for cmd in circ.get_commands():
        op = cmd.op
        t = op.type
        args = cmd.args
        if t == OpType.Barrier:
            ops.append(("BARRIER",))
            if stop_at_first_barrier:
                break
        elif t == OpType.H:
            ops.append(("H", qs.qidx(args[0])))
        elif t == OpType.S:
            ops.append(("S", qs.qidx(args[0])))
        elif t == OpType.Sdg:
            ops.append(("SDG", qs.qidx(args[0])))
        elif t == OpType.X:
            ops.append(("X", qs.qidx(args[0])))
        elif t == OpType.Y:
            ops.append(("Y", qs.qidx(args[0])))
        elif t == OpType.Z:
            ops.append(("Z", qs.qidx(args[0])))
        elif t == OpType.CX:
            ops.append(("CX", qs.qidx(args[0]), qs.qidx(args[1])))
        elif t == OpType.CZ:
            ops.append(("CZ_2Q", qs.qidx(args[0]), qs.qidx(args[1])))
        elif t == OpType.Measure:
            ops.append(("MEASURE", qs.qidx(args[0]), qs.bitkey(args[1])))
        elif t == OpType.Reset:
            ops.append(("RESET", qs.qidx(args[0])))
        elif t == OpType.Conditional:
            inner = op.op
            bits = tuple(qs.bitkey(b) for b in args[: op.width])
            targets = tuple(qs.qidx(q) for q in args[op.width :])
            if inner.type in (OpType.X, OpType.Y, OpType.Z):
                ops.append(("COND_PAULI", inner.type.name, bits, int(op.value), targets))
            else:
                raise RuntimeError(f"Unsupported conditional inner op: {inner.type}")
        else:
            raise RuntimeError(f"Unsupported op in dynamic statevector simulator: {t}")
    return ops


def run_dynamic_ops(
    ops: Sequence[tuple],
    *,
    initial_state: np.ndarray | None = None,
    outcomes: dict[str, int] | None = None,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, dict[str, int]]:
    """Execute flattened dynamic circuit operations on a 20-qubit statevector."""
    if initial_state is not None:
        state = initial_state.copy()
    else:
        state = np.zeros(qs.DIM, dtype=complex)
        state[0] = 1.0

    if rng is None:
        rng = np.random.default_rng(20261123)

    classical: dict[str, int] = {}
    for op in ops:
        kind = op[0]
        if kind == "BARRIER":
            continue
        elif kind == "H":
            state = qs.apply_1q(state, qs.H_GATE, op[1])
        elif kind == "S":
            state = qs.apply_1q(state, S_GATE, op[1])
        elif kind == "SDG":
            state = qs.apply_1q(state, SDG_GATE, op[1])
        elif kind == "X":
            state = qs.apply_x(state, op[1])
        elif kind == "Y":
            state = qs.apply_1q(state, qs.Y_GATE, op[1])
        elif kind == "Z":
            state = qs.apply_1q(state, qs.Z_GATE, op[1])
        elif kind == "CX":
            state = qs.apply_cx(state, op[1], op[2])
        elif kind == "CZ_2Q":
            state = _apply_cz(state, op[1], op[2])
        elif kind == "COND_PAULI":
            _, pname, bits, val, targets = op
            cond = sum(classical.get(b, 0) << i for i, b in enumerate(bits))
            if cond == val:
                for q in targets:
                    if pname == "X":
                        state = qs.apply_x(state, q)
                    elif pname == "Y":
                        state = qs.apply_1q(state, qs.Y_GATE, q)
                    else:
                        state = qs.apply_1q(state, qs.Z_GATE, q)
        elif kind == "MEASURE":
            _, q, bk = op
            p1 = float(np.sum(np.abs(state[qs._mask1(q)]) ** 2))
            if outcomes is not None and bk in outcomes:
                outcome = int(outcomes[bk])
                if (outcome == 1 and p1 < 1e-12) or (outcome == 0 and p1 > 1.0 - 1e-12):
                    raise qs.UnreachableBranch(f"Forced outcome {outcome} on {bk} has p1={p1}")
            else:
                outcome = 1 if rng.random() < p1 else 0
            state = qs.zero_out(state, q, outcome)
            state /= np.linalg.norm(state)
            classical[bk] = outcome
        elif kind == "RESET":
            _, q = op
            m1 = qs._mask1(q)
            p1 = float(np.sum(np.abs(state[m1]) ** 2))
            if p1 > 0.5:
                state = qs.apply_x(state, q)
            elif p1 > 0.0:
                state = np.where(m1, 0.0, state)
                state /= np.linalg.norm(state)
        else:
            raise RuntimeError(f"Unhandled dynamic op: {kind}")
    return state, classical


# ===========================================================================
# PART 1: Full X+Z Toroidal Syndrome Memory (`[[16,2,4]]`, 20 Ions on H2-1)
# ===========================================================================


def derive_css_parity_matrices() -> tuple[np.ndarray, np.ndarray, list[qm.Pauli]]:
    """Return `(H_X, H_Z, all_stabilizers)` for the 4x4 periodic Wen-plaquette CSS code."""
    all_stabs = [qm.from_support(s.pauli_type, s.support) for s in WEN_STABILIZERS]
    hx_rows = [all_stabs[idx].x for idx in X_PLAQUETTE_INDICES]
    hz_rows = [all_stabs[idx].z for idx in Z_PLAQUETTE_INDICES]
    hx = np.array(hx_rows, dtype=np.uint8)
    hz = np.array(hz_rows, dtype=np.uint8)
    return hx, hz, all_stabs


class BpOsdChannelDecoder:
    """
    Log-domain sum-product Belief Propagation + Ordered Statistics Decoding (`OSD-CS`, order 2)
    over a binary CSS parity-check matrix `H` (`8 x 16`, `rank(H) = 7`).
    """

    def __init__(
        self,
        parity_matrix: np.ndarray,
        *,
        channel_prob: float = 0.01,
        max_iter: int = 16,
        osd_order: int = 2,
    ) -> None:
        self.H = np.asarray(parity_matrix, dtype=np.uint8) % 2
        self.m, self.n = self.H.shape
        self.rank = qm.gf2_rank(self.H.tolist())
        self.p = float(np.clip(channel_prob, 1e-6, 0.49))
        self.max_iter = int(max_iter)
        self.osd_order = int(osd_order)
        self.prior_llr = float(np.log((1.0 - self.p) / self.p))
        self.check_nbrs = [np.flatnonzero(self.H[i]) for i in range(self.m)]
        self.var_nbrs = [np.flatnonzero(self.H[:, j]) for j in range(self.n)]
        self._cache: dict[bytes, np.ndarray] = {}

    def decode(self, syndrome: Sequence[int] | np.ndarray) -> np.ndarray:
        s = (np.asarray(syndrome, dtype=np.uint8) % 2).reshape(-1)
        if s.shape[0] != self.m:
            raise ValueError(f"Expected syndrome of length {self.m}, got {s.shape[0]}")
        if int(s.sum()) % 2 != 0:
            raise ValueError(
                f"Global torus parity violation: odd anyon count ({int(s.sum())}) in syndrome {s.tolist()}"
            )
        if not s.any():
            return np.zeros(self.n, dtype=np.uint8)

        key_bytes = s.tobytes()
        cached = self._cache.get(key_bytes)
        if cached is not None:
            return cached.copy()

        # 1. Log-LLR tanh sum-product message passing on Tanner graph
        q_to_c = np.zeros((self.m, self.n), dtype=np.float64)
        c_to_q = np.zeros((self.m, self.n), dtype=np.float64)
        for i in range(self.m):
            q_to_c[i, self.check_nbrs[i]] = self.prior_llr

        posterior_llr = np.full(self.n, self.prior_llr, dtype=np.float64)
        for _ in range(self.max_iter):
            for i in range(self.m):
                nbrs = self.check_nbrs[i]
                tanh_vals = np.tanh(0.5 * np.clip(q_to_c[i, nbrs], -20.0, 20.0))
                sign = -1.0 if s[i] else 1.0
                for idx_k, j in enumerate(nbrs):
                    prod_other = sign * float(np.prod(np.delete(tanh_vals, idx_k)))
                    prod_other = float(np.clip(prod_other, -1.0 + 1e-12, 1.0 - 1e-12))
                    c_to_q[i, j] = 2.0 * np.arctanh(prod_other)

            for j in range(self.n):
                nbrs = self.var_nbrs[j]
                total = self.prior_llr + float(np.sum(c_to_q[nbrs, j]))
                posterior_llr[j] = total
                for i in nbrs:
                    q_to_c[i, j] = total - c_to_q[i, j]

            e_bp = (posterior_llr < 0.0).astype(np.uint8)
            if int(e_bp.sum()) <= 1 and np.array_equal((self.H @ e_bp) % 2, s):
                self._cache[key_bytes] = e_bp.copy()
                return e_bp

        # 2. OSD-0 + OSD-CS (Combination Sweep up to osd_order)
        order = np.argsort(posterior_llr, kind="stable")
        h_ord = self.H[:, order].copy()
        aug = np.concatenate([h_ord, s.reshape(-1, 1)], axis=1).astype(np.uint8)

        pivots: list[int] = []
        row_rank = 0
        for col in range(self.n):
            piv = None
            for r in range(row_rank, self.m):
                if aug[r, col]:
                    piv = r
                    break
            if piv is None:
                continue
            if piv != row_rank:
                aug[[row_rank, piv]] = aug[[piv, row_rank]]
            for r in range(self.m):
                if r != row_rank and aug[r, col]:
                    aug[r] ^= aug[row_rank]
            pivots.append(col)
            row_rank += 1

        for r in range(row_rank, self.m):
            if aug[r, self.n]:
                raise ValueError("Inconsistent syndrome linear system on torus")

        piv_set = set(pivots)
        free_cols = [c for c in range(self.n) if c not in piv_set]
        s_red = aug[:row_rank, self.n]
        f_mat = aug[:row_rank, free_cols]
        soft_weights = np.log1p(np.exp(np.clip(posterior_llr[order], -20.0, 20.0)))

        candidates: list[tuple[int, ...]] = [()]
        for w in range(1, min(self.osd_order, len(free_cols)) + 1):
            candidates.extend(combinations(range(len(free_cols)), w))

        best_unord: np.ndarray | None = None
        best_key: tuple[int, float, tuple[int, ...]] | None = None

        for active_free in candidates:
            e_free = np.zeros(len(free_cols), dtype=np.uint8)
            if active_free:
                e_free[list(active_free)] = 1
            e_piv = (s_red ^ ((f_mat @ e_free) % 2)) if free_cols else s_red.copy()
            e_ord = np.zeros(self.n, dtype=np.uint8)
            for idx_p, col_p in enumerate(pivots):
                e_ord[col_p] = e_piv[idx_p]
            for idx_f, col_f in enumerate(free_cols):
                e_ord[col_f] = e_free[idx_f]

            unord = np.zeros(self.n, dtype=np.uint8)
            unord[order] = e_ord
            hw = int(unord.sum())
            sc = round(float(np.dot(e_ord, soft_weights)), 9)
            canon_idx = tuple(int(i) for i in np.flatnonzero(unord))
            cand_key = (hw, sc, canon_idx)
            if best_key is None or cand_key < best_key:
                best_key = cand_key
                best_unord = unord

        assert best_unord is not None
        self._cache[key_bytes] = best_unord.copy()
        return best_unord


class CSSBpOsdDecoder:
    """Dual-sector CSS BP+OSD decoder over `(H_X, H_Z)` for the `[[16,2,4]]` Wen-plaquette torus."""

    def __init__(self, channel_prob: float = 0.01, max_iter: int = 16, osd_order: int = 2) -> None:
        hx, hz, all_stabs = derive_css_parity_matrices()
        self.H_X = hx
        self.H_Z = hz
        self.all_stabilizers = all_stabs
        self.rank_hx = qm.gf2_rank(hx.tolist())
        self.rank_hz = qm.gf2_rank(hz.tolist())
        self.z_error_decoder = BpOsdChannelDecoder(
            hx, channel_prob=channel_prob, max_iter=max_iter, osd_order=osd_order
        )
        self.x_error_decoder = BpOsdChannelDecoder(
            hz, channel_prob=channel_prob, max_iter=max_iter, osd_order=osd_order
        )

    def decode_xz(
        self, x_syndrome: Sequence[int] | np.ndarray, z_syndrome: Sequence[int] | np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Given `(s_X, s_Z)`, return estimated `(r_X, r_Z)` data Pauli vectors."""
        rx = self.x_error_decoder.decode(z_syndrome)
        rz = self.z_error_decoder.decode(x_syndrome)
        return rx, rz


def _append_wen_preparation_stage(circ: Circuit, q_reg: QubitRegister) -> None:
    """Append the frozen 2-round OSIRIS-QEC-002 feed-forward state preparation stage."""
    c_regs_1st = [BitRegister(f"c{i}_1st", 1) for i in range(4)]
    for reg in c_regs_1st:
        circ.add_c_register(reg)
    c_reg_2nd = BitRegister("c4_2nd", 4)
    circ.add_c_register(c_reg_2nd)

    for stab_idx, (_, anc_idx, c_idx) in ROUND_1_MAP.items():
        WenPlaquetteFeedForwardPass._measure_stabilizer_nondestructive(
            circ, q_reg, WEN_STABILIZERS[stab_idx], c_regs_1st[c_idx][0], q_reg[anc_idx]
        )
    for stab_idx, (target_q, _, c_idx) in ROUND_1_MAP.items():
        cond_val, _ = encode_syndrome_condition("1", reg_size=1, enforce_even_parity=False)
        circ.Z(q_reg[target_q], condition_bits=c_regs_1st[c_idx], condition_value=cond_val)

    for stab_idx, (anc_idx, c_bit_idx) in ROUND_2_MAP.items():
        WenPlaquetteFeedForwardPass._measure_stabilizer_nondestructive(
            circ, q_reg, WEN_STABILIZERS[stab_idx], c_reg_2nd[c_bit_idx], q_reg[anc_idx]
        )
    for synd_be, target_qubits in ROUND_2_LUT_BE.items():
        cond_val, _ = encode_syndrome_condition(synd_be, reg_size=4, enforce_even_parity=True)
        for q_idx in target_qubits:
            circ.Z(q_reg[q_idx], condition_bits=c_reg_2nd, condition_value=cond_val)


def append_full_xz_memory_round(circ: Circuit, q_reg: QubitRegister, round_idx: int) -> tuple[BitRegister, BitRegister]:
    """
    Append one complete X+Z syndrome extraction cycle measuring all 8 X-plaquettes (e-anyons)
    and all 8 Z-plaquettes (m-anyons) across 4 vertex-disjoint sub-batches using 4 recycled
    ancilla ions `q[16..19]` via mid-circuit `Measure` + `Reset`.
    """
    mx_reg = BitRegister(f"m_r{round_idx}_x", 8)
    mz_reg = BitRegister(f"m_r{round_idx}_z", 8)
    circ.add_c_register(mx_reg)
    circ.add_c_register(mz_reg)

    for batch in (X_BATCH_A, X_BATCH_B):
        for anc_offset, stab_idx in enumerate(batch):
            anc = q_reg[N_DATA + anc_offset]
            circ.H(anc)
            for dq in WEN_STABILIZERS[stab_idx].support:
                circ.CX(anc, q_reg[dq])
            circ.H(anc)
            circ.Measure(anc, mx_reg[X_POS_MAP[stab_idx]])
            circ.add_gate(OpType.Reset, [anc])

    for batch in (Z_BATCH_A, Z_BATCH_B):
        for anc_offset, stab_idx in enumerate(batch):
            anc = q_reg[N_DATA + anc_offset]
            for dq in WEN_STABILIZERS[stab_idx].support:
                circ.CX(q_reg[dq], anc)
            circ.Measure(anc, mz_reg[Z_POS_MAP[stab_idx]])
            circ.add_gate(OpType.Reset, [anc])

    return mx_reg, mz_reg


def build_qec003_memory_circuit(
    rounds: int = 1,
    readout_basis: Literal["X", "Z"] = "Z",
) -> Circuit:
    """Build the 20-qubit multi-round full X+Z Wen-plaquette memory circuit (`R >= 1`)."""
    if rounds < 1:
        raise ValueError(f"rounds must be >= 1, got {rounds}")
    if readout_basis not in ("X", "Z"):
        raise ValueError(f"readout_basis must be 'X' or 'Z', got {readout_basis!r}")

    circ = Circuit()
    q_reg = QubitRegister("q", N_TOTAL)
    circ.add_q_register(q_reg)

    _append_wen_preparation_stage(circ, q_reg)
    circ.add_barrier([q_reg[i] for i in range(N_TOTAL)])

    for r in range(rounds):
        append_full_xz_memory_round(circ, q_reg, round_idx=r)
        circ.add_barrier([q_reg[i] for i in range(N_TOTAL)])

    c_end = BitRegister("c5_end", N_DATA)
    circ.add_c_register(c_end)
    for dq in range(N_DATA):
        if readout_basis == "X":
            circ.H(q_reg[dq])
        circ.Measure(q_reg[dq], c_end[dq])

    normalize_circuit_metadata(circ, compiler_lock=True)
    return circ


def compile_memory_rounds_h2_metrics(rounds_list: Sequence[int] = (1, 2, 3)) -> dict[str, Any]:
    """Compile `R in rounds_list` full X+Z memory circuits to H2-1 ISA via `QuantinuumAPIOffline`."""
    results: dict[str, Any] = {}
    for r in rounds_list:
        pre = build_qec003_memory_circuit(rounds=r, readout_basis="Z")
        pre_sha = hash_tket_circuit(pre)
        isa = local_h2_compile(pre, optimisation_level=2)
        isa_audit = verify_native_h2_isa(isa)
        hqc = compute_hqc_metrics(isa, SHOT_TIERS)
        results[f"R={r}"] = {
            "rounds": r,
            "readout_basis": "Z",
            "precompile_sha256": pre_sha,
            "isa_sha256": isa_audit["isa_sha256"],
            "nexus_opt0_fixed_point_sha256": isa_audit["opt0_fixed_point_sha256"],
            "n_qubits": isa_audit["n_qubits"],
            "n_clbits": isa_audit["n_clbits"],
            "depth": isa_audit["depth"],
            "swap_count": isa_audit["swap_count"],
            "zzphase_count": isa_audit["zzphase_count"],
            "gate_counts": isa_audit["gate_counts"],
            "hqc_budget": hqc,
        }
    return results


def _build_single_memory_round_extraction_ops() -> list[tuple]:
    """Build flattened ops for 1 round of 16-plaquette X+Z mid-circuit syndrome extraction."""
    c = Circuit()
    q_reg = QubitRegister("q", N_TOTAL)
    c.add_q_register(q_reg)
    append_full_xz_memory_round(c, q_reg, round_idx=0)
    return compile_dynamic_ops(c)


def run_weight1_postprep_circuit_sweep(decoder: CSSBpOsdDecoder | None = None) -> dict[str, Any]:
    """
    Exhaustive 48-fault single-qubit post-preparation quantum-circuit sweep (`16 X + 16 Y + 16 Z`).
    Executes the actual 20-qubit mid-circuit X+Z syndrome extraction circuit on the corrupted
    prepared state, decodes `(s_X, s_Z)` via `CSSBpOsdDecoder`, applies Pauli recovery, and
    verifies exact logical & codespace recovery (`48/48`, `100.0%`, `0.0%` logical error).
    """
    dec = decoder or CSSBpOsdDecoder()
    state0 = _prepared_reference_state()
    mem_ops = _build_single_memory_round_extraction_ops()
    rng = np.random.default_rng(20261123)

    records: list[dict[str, Any]] = []
    by_pauli: dict[str, dict[str, int]] = {
        "X": {"total": 0, "qec002_detected": 0, "qec002_preserved": 0, "qec003_detected": 0, "qec003_corrected": 0},
        "Y": {"total": 0, "qec002_detected": 0, "qec002_preserved": 0, "qec003_detected": 0, "qec003_corrected": 0},
        "Z": {"total": 0, "qec002_detected": 0, "qec002_preserved": 0, "qec003_detected": 0, "qec003_corrected": 0},
    }

    for q in range(N_DATA):
        for p_label in ("X", "Y", "Z"):
            corrupted = qs.apply_1q(state0.copy(), qs.PAULIS[p_label], q)
            fid_before = qs.state_fidelity(corrupted, state0)

            post_meas_state, cl = run_dynamic_ops(mem_ops, initial_state=corrupted, rng=rng)
            sx = np.array([cl[f"m_r0_x[{i}]"] for i in range(8)], dtype=np.uint8)
            sz = np.array([cl[f"m_r0_z[{i}]"] for i in range(8)], dtype=np.uint8)

            rx, rz = dec.decode_xz(sx, sz)
            recovered = post_meas_state
            for dq in np.flatnonzero(rx):
                recovered = qs.apply_x(recovered, int(dq))
            for dq in np.flatnonzero(rz):
                recovered = qs.apply_1q(recovered, qs.Z_GATE, int(dq))

            fid_after = qs.state_fidelity(recovered, state0)
            detected_qec003 = bool(sx.any() or sz.any())
            corrected_qec003 = bool(fid_after > 0.999999999)

            # Contrast with OSIRIS-QEC-002 (measures X-plaquettes only during prep, 0 post-prep rounds)
            detected_qec002 = bool(sx.any())
            preserved_qec002 = bool(fid_before > 0.999)

            by_pauli[p_label]["total"] += 1
            by_pauli[p_label]["qec002_detected"] += int(detected_qec002)
            by_pauli[p_label]["qec002_preserved"] += int(preserved_qec002)
            by_pauli[p_label]["qec003_detected"] += int(detected_qec003)
            by_pauli[p_label]["qec003_corrected"] += int(corrected_qec003)

            records.append(
                {
                    "qubit": q,
                    "pauli": p_label,
                    "x_syndrome": "".join(str(int(b)) for b in sx),
                    "z_syndrome": "".join(str(int(b)) for b in sz),
                    "decoded_rx_qubits": [int(i) for i in np.flatnonzero(rx)],
                    "decoded_rz_qubits": [int(i) for i in np.flatnonzero(rz)],
                    "fidelity_uncorrected_qec002": round(fid_before, 12),
                    "fidelity_recovered_qec003": round(fid_after, 12),
                    "qec002_detected": detected_qec002,
                    "qec002_logically_preserved": preserved_qec002,
                    "qec003_detected": detected_qec003,
                    "qec003_uniquely_corrected": corrected_qec003,
                }
            )

    total_corrected = sum(v["qec003_corrected"] for v in by_pauli.values())
    total_detected = sum(v["qec003_detected"] for v in by_pauli.values())
    return {
        "total_faults": len(records),
        "qec002_detected_count": sum(v["qec002_detected"] for v in by_pauli.values()),
        "qec002_logically_preserved_count": sum(v["qec002_preserved"] for v in by_pauli.values()),
        "qec003_detected_count": total_detected,
        "qec003_uniquely_corrected_count": total_corrected,
        "qec003_logical_error_rate": round(1.0 - total_corrected / float(len(records)), 12),
        "by_pauli": by_pauli,
        "records": records,
    }


def run_weight2_postprep_fault_sweep(decoder: CSSBpOsdDecoder | None = None) -> dict[str, Any]:
    """
    Exhaustive sweep over all `C(16,2) * 3^2 = 1,080` two-qubit Pauli faults on `[[16,2,4]]`.
    Proves `1,080/1,080` (`100.0%`) fault detection and characterizes exact inverse recovery,
    stabilizer-degenerate recovery (`e ^ e_hat in S`), and weight-2 non-contractible torus
    logical coset ties (`e ^ e_hat in N(S) \\ S`).
    """
    dec = decoder or CSSBpOsdDecoder()
    hx, hz, stabs = dec.H_X, dec.H_Z, dec.all_stabilizers

    total = 0
    detected = 0
    exact_zero_residual = 0
    stabilizer_degenerate_preserved = 0
    logical_coset_tie_errors = 0

    by_pair_class: dict[str, dict[str, int]] = {}
    for cls_name in ("XX", "ZZ", "XZ_or_ZX", "XY_YX_ZY_YZ", "YY"):
        by_pair_class[cls_name] = {
            "total": 0,
            "detected": 0,
            "logically_preserved": 0,
            "exact_inverse": 0,
            "stabilizer_degenerate": 0,
            "logical_coset_error": 0,
        }

    for q1, q2 in combinations(range(N_DATA), 2):
        for p1, p2 in product(("X", "Y", "Z"), repeat=2):
            total += 1
            pair_tag = p1 + p2
            if pair_tag == "XX":
                cls_key = "XX"
            elif pair_tag == "ZZ":
                cls_key = "ZZ"
            elif pair_tag in ("XZ", "ZX"):
                cls_key = "XZ_or_ZX"
            elif pair_tag == "YY":
                cls_key = "YY"
            else:
                cls_key = "XY_YX_ZY_YZ"

            ex = np.zeros(N_DATA, dtype=np.uint8)
            ez = np.zeros(N_DATA, dtype=np.uint8)
            if p1 in ("X", "Y"):
                ex[q1] = 1
            if p1 in ("Z", "Y"):
                ez[q1] = 1
            if p2 in ("X", "Y"):
                ex[q2] = 1
            if p2 in ("Z", "Y"):
                ez[q2] = 1

            sx = (hx @ ez) % 2
            sz = (hz @ ex) % 2
            is_det = bool(sx.any() or sz.any())
            detected += int(is_det)
            by_pair_class[cls_key]["total"] += 1
            by_pair_class[cls_key]["detected"] += int(is_det)

            rx, rz = dec.decode_xz(sx, sz)
            dx = ex ^ rx
            dz = ez ^ rz
            residual = qm.Pauli(tuple(int(v) for v in dx), tuple(int(v) for v in dz))

            if qm.stabilizer_membership(residual, stabs):
                by_pair_class[cls_key]["logically_preserved"] += 1
                if not dx.any() and not dz.any():
                    exact_zero_residual += 1
                    by_pair_class[cls_key]["exact_inverse"] += 1
                else:
                    stabilizer_degenerate_preserved += 1
                    by_pair_class[cls_key]["stabilizer_degenerate"] += 1
            else:
                logical_coset_tie_errors += 1
                by_pair_class[cls_key]["logical_coset_error"] += 1

    preserved_total = exact_zero_residual + stabilizer_degenerate_preserved
    return {
        "total_weight2_faults": total,
        "detected_count": detected,
        "detection_rate": round(detected / float(total), 12),
        "logically_preserved_count": preserved_total,
        "logically_preserved_fraction": round(preserved_total / float(total), 6),
        "exact_inverse_count": exact_zero_residual,
        "stabilizer_degenerate_preserved_count": stabilizer_degenerate_preserved,
        "logical_coset_tie_error_count": logical_coset_tie_errors,
        "logical_coset_tie_error_fraction": round(logical_coset_tie_errors / float(total), 6),
        "by_pauli_pair_class": by_pair_class,
    }


def _project_valid_torus_syndrome(raw_syn: np.ndarray) -> np.ndarray:
    """Ensure even global parity on an 8-bit noisy syndrome before single-shot spatial decode."""
    s = (np.asarray(raw_syn, dtype=np.uint8) % 2).copy()
    if int(s.sum()) % 2 == 1:
        s[0] ^= 1
    return s


def run_depolarizing_memory_benchmark(
    error_rates: Sequence[float] = (0.001, 0.002, 0.005, 0.01),
    rounds_list: Sequence[int] = (1, 2, 3),
    n_shots: int = 4000,
    seed: int = 20261123,
    decoder: CSSBpOsdDecoder | None = None,
) -> dict[str, Any]:
    """
    Seeded Monte Carlo multi-round CSS memory benchmark over `p in {0.001, 0.002, 0.005, 0.01}`
    and `R in {1, 2, 3}`.
    Model:
      - In each memory round `r = 1..R`, each of the 16 data qubits undergoes independent
        single-qubit depolarizing noise (`X`, `Y`, `Z` each with probability `p / 3`), and
        intermediate ancilla syndrome measurements suffer bit-flip error `p_meas = p / 2`.
      - Between rounds, conservative non-destructive syndrome validation applies feedback only
        when two consecutive rounds agree (or at final destructive readout), preventing single
        measurement bit-flips from injecting hook/data errors while correcting weight-1 data
        errors across multi-round memory cycles.
      - Compares encoded `[[16,2,4]]` logical failure rate against bare 2-qubit physical
        register failure rate `1 - (1 - p)^(2*R)` and single-qubit physical rate `1 - (1 - p)^R`.
    """
    dec = decoder or CSSBpOsdDecoder()
    hx, hz, stabs = dec.H_X, dec.H_Z, dec.all_stabilizers
    rng = np.random.default_rng(seed)

    rows: list[dict[str, Any]] = []
    for p in error_rates:
        for r_rounds in rounds_list:
            logical_failures = 0
            uncorrected_failures = 0

            for _ in range(n_shots):
                cum_ex = np.zeros(N_DATA, dtype=np.uint8)
                cum_ez = np.zeros(N_DATA, dtype=np.uint8)
                raw_uncorr_ex = np.zeros(N_DATA, dtype=np.uint8)
                raw_uncorr_ez = np.zeros(N_DATA, dtype=np.uint8)

                prev_noisy_sx: np.ndarray | None = None
                prev_noisy_sz: np.ndarray | None = None

                for r_idx in range(r_rounds):
                    draws = rng.random(N_DATA)
                    for q in range(N_DATA):
                        u = draws[q]
                        if u < p / 3.0:
                            cum_ex[q] ^= 1
                            raw_uncorr_ex[q] ^= 1
                        elif u < 2.0 * p / 3.0:
                            cum_ex[q] ^= 1
                            cum_ez[q] ^= 1
                            raw_uncorr_ex[q] ^= 1
                            raw_uncorr_ez[q] ^= 1
                        elif u < p:
                            cum_ez[q] ^= 1
                            raw_uncorr_ez[q] ^= 1

                    true_sx = (hx @ cum_ez) % 2
                    true_sz = (hz @ cum_ex) % 2

                    if r_idx < r_rounds - 1:
                        meas_flip_x = (rng.random(8) < (0.5 * p)).astype(np.uint8)
                        meas_flip_z = (rng.random(8) < (0.5 * p)).astype(np.uint8)
                        noisy_sx = true_sx ^ meas_flip_x
                        noisy_sz = true_sz ^ meas_flip_z
                        if (
                            prev_noisy_sx is not None
                            and np.array_equal(noisy_sx, prev_noisy_sx)
                            and noisy_sx.any()
                            and int(noisy_sx.sum()) % 2 == 0
                        ):
                            rz_mid = dec.z_error_decoder.decode(noisy_sx)
                            cum_ez ^= rz_mid
                            noisy_sx = np.zeros(8, dtype=np.uint8)
                        if (
                            prev_noisy_sz is not None
                            and np.array_equal(noisy_sz, prev_noisy_sz)
                            and noisy_sz.any()
                            and int(noisy_sz.sum()) % 2 == 0
                        ):
                            rx_mid = dec.x_error_decoder.decode(noisy_sz)
                            cum_ex ^= rx_mid
                            noisy_sz = np.zeros(8, dtype=np.uint8)
                        prev_noisy_sx = noisy_sx
                        prev_noisy_sz = noisy_sz
                    else:
                        rx_fin, rz_fin = dec.decode_xz(
                            _project_valid_torus_syndrome(true_sx),
                            _project_valid_torus_syndrome(true_sz),
                        )
                        cum_ex ^= rx_fin
                        cum_ez ^= rz_fin

                res_pauli = qm.Pauli(
                    tuple(int(v) for v in cum_ex), tuple(int(v) for v in cum_ez)
                )
                if not qm.stabilizer_membership(res_pauli, stabs):
                    logical_failures += 1

                raw_pauli = qm.Pauli(
                    tuple(int(v) for v in raw_uncorr_ex), tuple(int(v) for v in raw_uncorr_ez)
                )
                if not qm.stabilizer_membership(raw_pauli, stabs):
                    uncorrected_failures += 1

            p_log = logical_failures / float(n_shots)
            p_uncorr = uncorrected_failures / float(n_shots)
            p_phys_1q = 1.0 - (1.0 - p) ** r_rounds
            p_phys_2q = 1.0 - (1.0 - p) ** (2 * r_rounds)
            rows.append(
                {
                    "physical_error_rate_p": p,
                    "rounds": r_rounds,
                    "n_shots": n_shots,
                    "logical_failures": logical_failures,
                    "logical_error_rate": round(p_log, 6),
                    "bare_1q_error_rate": round(p_phys_1q, 6),
                    "bare_2q_register_error_rate": round(p_phys_2q, 6),
                    "uncorrected_16q_error_rate": round(p_uncorr, 6),
                    "suppression_factor_vs_bare_2q": (
                        round(p_phys_2q / p_log, 3) if p_log > 0 else None
                    ),
                    "below_bare_2q_break_even": bool(p_log < p_phys_2q),
                }
            )

    return {
        "noise_model": "per-round 16-qubit depolarizing (p/3 each X,Y,Z) + mid-round syndrome bit-flip (p/2) + BP+OSD-CS recovery",
        "seed": seed,
        "n_shots_per_point": n_shots,
        "results": rows,
    }


# ===========================================================================
# PART 2: Checkerboard Lattice Dislocation Twist Defects & e <-> m Braiding
# ===========================================================================


@dataclass(frozen=True)
class SignedPauliGenerator:
    name: str
    role: Literal[
        "electric_X_plaquette",
        "magnetic_Z_plaquette",
        "twist_defect_weight5",
        "branch_cut_mixed4",
    ]
    sign: Literal[1, -1]
    pauli_map: tuple[tuple[int, Literal["X", "Y", "Z"]], ...]

    @property
    def weight(self) -> int:
        return len(self.pauli_map)

    def to_symplectic(self) -> qm.Pauli:
        x = [0] * N_DATA
        z = [0] * N_DATA
        for q, p in self.pauli_map:
            if p in ("X", "Y"):
                x[q] = 1
            if p in ("Z", "Y"):
                z[q] = 1
        return qm.Pauli(tuple(x), tuple(z))

    def format_string(self) -> str:
        prefix = "+" if self.sign == 1 else "-"
        body = ".".join(f"{p}{q}" for q, p in self.pauli_map)
        return f"{prefix}{body}"


OUTER_PLAQUETTE_INDICES: tuple[int, ...] = (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15)

TWIST_VACUUM_FEEDFORWARD_LUT_BE: dict[str, list[tuple[int, Literal["X", "Z"]]]] = {
    "110": [(4, "Z"), (7, "Z")],
    "101": [(4, "X"), (5, "X")],
    "011": [(8, "X"), (9, "X")],
}

TWIST_ANYON_TRAJECTORY: tuple[tuple[str, tuple[tuple[int, Literal["X", "Z"]], ...], str], ...] = (
    (
        "step0_twist_vacuum",
        (),
        "Twist codespace vacuum |Psi_twist>: 0 anyon excitations across all 15 stabilizers.",
    ),
    (
        "step1_create_electric_e_pair",
        ((2, "Z"),),
        "Apply Z2 above cut: excites two electric e-anyons on X-plaquettes P_1_X and P_14_X (0 m-anyons).",
    ),
    (
        "step2_enter_dislocation_branch_cut",
        ((2, "Z"), (6, "Z")),
        "Apply Z6: mobile e-anyon leaves P_1_X and enters mixed X6.X7.Z9.Z10 branch-cut plaquette B1.",
    ),
    (
        "step3_transmute_e_to_m_across_cut",
        ((2, "Z"), (6, "Z"), (10, "X")),
        "Apply X10 across branch cut: excitation emerges in lower lattice as magnetic m-anyon on Z-plaquette P_10_Z while anchor P_14_X remains electric e-anyon (1 odd e + 1 odd m, impossible without twist!).",
    ),
    (
        "step4_fuse_m_into_weight5_twist_defect",
        ((2, "Z"), (6, "Z"), (10, "X"), (11, "X")),
        "Apply X11: transmuted m-anyon fuses into weight-5 Ising twist defect T2_twist_right (-Z4.Z7.Z8.X10.Y11).",
    ),
)


def build_twist_defect_stabilizers() -> list[SignedPauliGenerator]:
    """
    Construct the 15-generator periodic checkerboard dislocation (twist-defect pair) code:
      - 12 unmodified outer weight-4 X/Z checkerboard plaquettes (strips r=0, 2, 3)
      - T1_twist_left:  + X4 . Y5 . Z6 . X8 . X9   (weight-5 mixed-parity pentagon twist)
      - B1_branch_cut:  + X6 . X7 . Z9 . Z10       (weight-4 mixed XXZZ dislocation branch cut)
      - T2_twist_right: - Z4 . Z7 . Z8 . X10 . Y11 (weight-5 mixed-parity pentagon twist, -1 gauge)
    """
    gens: list[SignedPauliGenerator] = []
    for idx in OUTER_PLAQUETTE_INDICES:
        stab = WEN_STABILIZERS[idx]
        role: Literal["electric_X_plaquette", "magnetic_Z_plaquette"] = (
            "electric_X_plaquette" if stab.pauli_type == "X" else "magnetic_Z_plaquette"
        )
        pmap = tuple((q, stab.pauli_type) for q in sorted(stab.support))
        gens.append(SignedPauliGenerator(f"P_{idx}_{stab.pauli_type}", role, 1, pmap))

    gens.append(
        SignedPauliGenerator(
            "T1_twist_left",
            "twist_defect_weight5",
            1,
            ((4, "X"), (5, "Y"), (6, "Z"), (8, "X"), (9, "X")),
        )
    )
    gens.append(
        SignedPauliGenerator(
            "B1_branch_cut",
            "branch_cut_mixed4",
            1,
            ((6, "X"), (7, "X"), (9, "Z"), (10, "Z")),
        )
    )
    gens.append(
        SignedPauliGenerator(
            "T2_twist_right",
            "twist_defect_weight5",
            -1,
            ((4, "Z"), (7, "Z"), (8, "Z"), (10, "X"), (11, "Y")),
        )
    )
    return gens


_PAULI_MUL_TABLE: dict[tuple[str, str], tuple[complex, str]] = {
    ("I", "I"): (1, "I"),
    ("I", "X"): (1, "X"),
    ("I", "Y"): (1, "Y"),
    ("I", "Z"): (1, "Z"),
    ("X", "I"): (1, "X"),
    ("Y", "I"): (1, "Y"),
    ("Z", "I"): (1, "Z"),
    ("X", "X"): (1, "I"),
    ("Y", "Y"): (1, "I"),
    ("Z", "Z"): (1, "I"),
    ("X", "Y"): (1j, "Z"),
    ("Y", "X"): (-1j, "Z"),
    ("Y", "Z"): (1j, "X"),
    ("Z", "Y"): (-1j, "X"),
    ("Z", "X"): (1j, "Y"),
    ("X", "Z"): (-1j, "Y"),
}


def verify_twist_defect_algebra() -> dict[str, Any]:
    """
    Algebraically prove for the 15-generator checkerboard twist-defect lattice:
      (i)   All 105 generator pairs have symplectic inner product 0 (pairwise commute).
      (ii)  Exact 16-qubit matrix product of all 15 signed generators equals `+I`
            (unified Z_2 fermion parity constraint replacing separate e/m parities).
      (iii) Exact GF(2) symplectic rank = 14 => k = 16 - 14 = 2 logical qubits.
      (iv)  Exhaustive Pauli search over weights 1..4 finds 0 nontrivial logicals of
            weight <= 3 and 44 of weight 4 => exact parameters `[[16, 2, 4]]`.
    """
    gens = build_twist_defect_stabilizers()
    symp = [g.to_symplectic() for g in gens]

    n_pairs = 0
    anticommuting_pairs: list[tuple[str, str]] = []
    for i in range(len(gens)):
        for j in range(i + 1, len(gens)):
            n_pairs += 1
            if not symp[i].commutes_with(symp[j]):
                anticommuting_pairs.append((gens[i].name, gens[j].name))

    phase: complex = 1.0 + 0.0j
    running_pauli = ["I"] * N_DATA
    for g in gens:
        phase *= g.sign
        for q, p_op in g.pauli_map:
            step_ph, next_p = _PAULI_MUL_TABLE[(running_pauli[q], p_op)]
            phase *= step_ph
            running_pauli[q] = next_p

    rank = qm.stabilizer_group_rank(symp)
    k_logical = N_DATA - rank

    logicals_w1 = qm.enumerate_logicals(symp, max_weight=1)
    logicals_w2 = qm.enumerate_logicals(symp, max_weight=2)
    logicals_w3 = qm.enumerate_logicals(symp, max_weight=3)
    logicals_w4 = qm.enumerate_logicals(symp, max_weight=4)
    exact_d = min(p.weight for p in logicals_w4)

    return {
        "n_data_qubits": N_DATA,
        "n_generators_total": len(gens),
        "n_outer_plaquettes": 12,
        "n_weight5_twist_stabilizers": 2,
        "n_mixed_branch_cut_stabilizers": 1,
        "generator_definitions": [
            {"name": g.name, "role": g.role, "weight": g.weight, "operator": g.format_string()}
            for g in gens
        ],
        "pairwise_checks_count": n_pairs,
        "all_pairs_commute": len(anticommuting_pairs) == 0,
        "anticommuting_pairs": anticommuting_pairs,
        "product_of_all_15_generators_equals_plus_identity": (
            abs(phase - 1.0) < 1e-12 and all(p == "I" for p in running_pauli)
        ),
        "symplectic_gf2_rank": rank,
        "k_logical_qubits": k_logical,
        "nontrivial_logical_counts_by_max_weight": {
            "le_1": len(logicals_w1),
            "le_2": len(logicals_w2),
            "le_3": len(logicals_w3),
            "eq_4": len(logicals_w4),
        },
        "exact_code_distance_d": exact_d,
        "code_notation": f"[[{N_DATA},{k_logical},{exact_d}]]",
    }


def append_signed_pauli_measurement(
    circ: Circuit,
    q_reg: QubitRegister,
    gen: SignedPauliGenerator,
    c_bit: Bit,
    anc: Qubit,
) -> None:
    """
    Non-destructively extract an arbitrary signed Pauli generator (`X`, `Y`, `Z` support,
    `sign in {+1, -1}`) onto `anc` (`Measure` + `Reset`), using `Sdg; CX(anc, q); S` for `Y`
    and `H; CX(anc, q); H` for `Z` (`0` routing SWAPs on Quantinuum H2-1!).
    """
    circ.H(anc)
    for dq, p_op in gen.pauli_map:
        if p_op == "X":
            circ.CX(anc, q_reg[dq])
        elif p_op == "Z":
            circ.H(q_reg[dq])
            circ.CX(anc, q_reg[dq])
            circ.H(q_reg[dq])
        elif p_op == "Y":
            circ.Sdg(q_reg[dq])
            circ.CX(anc, q_reg[dq])
            circ.S(q_reg[dq])
        else:
            raise ValueError(f"Unsupported Pauli {p_op}")
    if gen.sign == -1:
        circ.Z(anc)
    circ.H(anc)
    circ.Measure(anc, c_bit)
    circ.add_gate(OpType.Reset, [anc])


def build_twist_anyon_circuit(
    transport_step: int = 3,
    readout_basis: Literal["X", "Z"] = "Z",
) -> Circuit:
    """
    Build the 20-qubit checkerboard twist-defect vacuum preparation, explicit `e <-> m`
    anyon-transport string injection (`step 0..4`), and full 15-stabilizer syndrome
    extraction circuit using 4 recycled ancillas `q[16..19]`.
    """
    if not (0 <= transport_step < len(TWIST_ANYON_TRAJECTORY)):
        raise ValueError(f"transport_step must be in 0..{len(TWIST_ANYON_TRAJECTORY) - 1}")

    gens = build_twist_defect_stabilizers()
    twist_trio = gens[12:15]

    circ = Circuit()
    q_reg = QubitRegister("q", N_TOTAL)
    circ.add_q_register(q_reg)

    _append_wen_preparation_stage(circ, q_reg)

    c_tw_prep = BitRegister("c_tw_prep", 3)
    circ.add_c_register(c_tw_prep)
    for k, gen in enumerate(twist_trio):
        append_signed_pauli_measurement(circ, q_reg, gen, c_tw_prep[k], q_reg[N_DATA + k])

    for synd_be, pauli_targets in TWIST_VACUUM_FEEDFORWARD_LUT_BE.items():
        cond_val, _ = encode_syndrome_condition(synd_be, reg_size=3, enforce_even_parity=True)
        for dq, p_op in pauli_targets:
            if p_op == "X":
                circ.X(q_reg[dq], condition_bits=c_tw_prep, condition_value=cond_val)
            else:
                circ.Z(q_reg[dq], condition_bits=c_tw_prep, condition_value=cond_val)

    circ.add_barrier([q_reg[i] for i in range(N_TOTAL)])

    _, string_ops, _ = TWIST_ANYON_TRAJECTORY[transport_step]
    for dq, p_op in string_ops:
        if p_op == "X":
            circ.X(q_reg[dq])
        else:
            circ.Z(q_reg[dq])

    circ.add_barrier([q_reg[i] for i in range(N_TOTAL)])

    c_tw_syn = BitRegister("c_tw_syn", len(gens))
    circ.add_c_register(c_tw_syn)
    batches = [gens[0:4], gens[4:8], gens[8:12], gens[12:15]]
    offset = 0
    for batch in batches:
        for anc_k, gen in enumerate(batch):
            append_signed_pauli_measurement(
                circ, q_reg, gen, c_tw_syn[offset + anc_k], q_reg[N_DATA + anc_k]
            )
        offset += len(batch)

    circ.add_barrier([q_reg[i] for i in range(N_TOTAL)])
    c_end = BitRegister("c5_end", N_DATA)
    circ.add_c_register(c_end)
    for dq in range(N_DATA):
        if readout_basis == "X":
            circ.H(q_reg[dq])
        circ.Measure(q_reg[dq], c_end[dq])

    normalize_circuit_metadata(circ, compiler_lock=True)
    return circ


def signed_generator_expectation(state: np.ndarray, gen: SignedPauliGenerator) -> float:
    """Exact statevector expectation value `<psi | G | psi>` of a `SignedPauliGenerator`."""
    s = state.copy()
    for dq, p_op in reversed(gen.pauli_map):
        if p_op == "X":
            s = qs.apply_x(s, dq)
        elif p_op == "Y":
            s = qs.apply_1q(s, qs.Y_GATE, dq)
        else:
            s = np.where(qs._mask1(dq), -s, s)
    return float(gen.sign) * float(np.real(np.vdot(state, s)))


def verify_twist_anyon_braiding_and_h2_compile() -> dict[str, Any]:
    """
    Execute 20-qubit quantum circuit verification of:
      1. Deterministic twist-vacuum preparation across all 4 reachable `(T1,B1,T2)` branches
         (`000, 110, 101, 011`), proving all 15 stabilizer expectations == `+1.0`.
      2. All 5 steps of explicit `e <-> m` electric-magnetic anyon transmutation & twist
         condensation via actual mid-circuit ancilla syndrome extraction.
      3. Offline H2-1 ISA compilation (`QuantinuumAPIOffline`) of the full twist-defect
         anyon-transmutation demonstration circuit (`transport_step=3`) with `0` SWAPs
         and exact HQC costs at `512`, `1,000`, and `2,000` shots.
    """
    gens = build_twist_defect_stabilizers()
    state0 = _prepared_reference_state()

    prep_only = Circuit()
    q_reg = QubitRegister("q", N_TOTAL)
    prep_only.add_q_register(q_reg)
    c_tw_prep = BitRegister("c_tw_prep", 3)
    prep_only.add_c_register(c_tw_prep)
    for k, gen in enumerate(gens[12:15]):
        append_signed_pauli_measurement(prep_only, q_reg, gen, c_tw_prep[k], q_reg[N_DATA + k])
    for synd_be, pauli_targets in TWIST_VACUUM_FEEDFORWARD_LUT_BE.items():
        cond_val, _ = encode_syndrome_condition(synd_be, reg_size=3, enforce_even_parity=True)
        for dq, p_op in pauli_targets:
            if p_op == "X":
                prep_only.X(q_reg[dq], condition_bits=c_tw_prep, condition_value=cond_val)
            else:
                prep_only.Z(q_reg[dq], condition_bits=c_tw_prep, condition_value=cond_val)
    prep_ops = compile_dynamic_ops(prep_only)

    reachable_branches: list[str] = []
    unreachable_branches: list[str] = []
    vacuum_state: np.ndarray | None = None
    min_branch_exp = 1.0

    for b0, b1, b2 in product((0, 1), repeat=3):
        b_str = f"{b0}{b1}{b2}"
        forced = {"c_tw_prep[0]": b0, "c_tw_prep[1]": b1, "c_tw_prep[2]": b2}
        try:
            st_tw, _ = run_dynamic_ops(prep_ops, initial_state=state0, outcomes=forced)
        except qs.UnreachableBranch:
            unreachable_branches.append(b_str)
            continue
        reachable_branches.append(b_str)
        exps = [signed_generator_expectation(st_tw, g) for g in gens]
        min_branch_exp = min(min_branch_exp, min(exps))
        if vacuum_state is None:
            vacuum_state = st_tw

    assert vacuum_state is not None

    ext_circ = Circuit()
    q_ext = QubitRegister("q", N_TOTAL)
    ext_circ.add_q_register(q_ext)
    c_tw_syn = BitRegister("c_tw_syn", len(gens))
    ext_circ.add_c_register(c_tw_syn)
    batches = [gens[0:4], gens[4:8], gens[8:12], gens[12:15]]
    off = 0
    for batch in batches:
        for anc_k, gen in enumerate(batch):
            append_signed_pauli_measurement(
                ext_circ, q_ext, gen, c_tw_syn[off + anc_k], q_ext[N_DATA + anc_k]
            )
        off += len(batch)
    ext_ops = compile_dynamic_ops(ext_circ)

    trajectory_results: list[dict[str, Any]] = []
    rng = np.random.default_rng(20261123)
    for step_idx, (step_name, string_ops, description) in enumerate(TWIST_ANYON_TRAJECTORY):
        st_step = vacuum_state.copy()
        for dq, p_op in string_ops:
            if p_op == "X":
                st_step = qs.apply_x(st_step, dq)
            else:
                st_step = qs.apply_1q(st_step, qs.Z_GATE, dq)

        _, cl_syn = run_dynamic_ops(ext_ops, initial_state=st_step, rng=rng)
        syn_bits = [int(cl_syn[f"c_tw_syn[{i}]"]) for i in range(len(gens))]
        excited_names = [gens[i].name for i, bit in enumerate(syn_bits) if bit == 1]
        excited_e = [
            gens[i].name
            for i, bit in enumerate(syn_bits)
            if bit == 1 and gens[i].role == "electric_X_plaquette"
        ]
        excited_m = [
            gens[i].name
            for i, bit in enumerate(syn_bits)
            if bit == 1 and gens[i].role == "magnetic_Z_plaquette"
        ]
        excited_twist_or_cut = [
            gens[i].name
            for i, bit in enumerate(syn_bits)
            if bit == 1 and gens[i].role in ("twist_defect_weight5", "branch_cut_mixed4")
        ]

        trajectory_results.append(
            {
                "step_index": step_idx,
                "step_name": step_name,
                "applied_string": [f"{p}{q}" for q, p in string_ops],
                "description": description,
                "syndrome_15bit": "".join(str(b) for b in syn_bits),
                "total_anyon_parity_mod2": sum(syn_bits) % 2,
                "excited_stabilizers": excited_names,
                "electric_e_anyons": excited_e,
                "magnetic_m_anyons": excited_m,
                "twist_or_branch_excitations": excited_twist_or_cut,
            }
        )

    full_twist_circ = build_twist_anyon_circuit(transport_step=3, readout_basis="Z")
    pre_sha = hash_tket_circuit(full_twist_circ)
    twist_isa = local_h2_compile(full_twist_circ, optimisation_level=2)
    isa_audit = verify_native_h2_isa(twist_isa)
    twist_hqc = compute_hqc_metrics(twist_isa, SHOT_TIERS)

    step1 = trajectory_results[1]
    step3 = trajectory_results[3]
    step4 = trajectory_results[4]
    transmutation_verified = (
        len(step1["electric_e_anyons"]) == 2
        and len(step1["magnetic_m_anyons"]) == 0
        and len(step3["electric_e_anyons"]) == 1
        and len(step3["magnetic_m_anyons"]) == 1
        and len(step3["twist_or_branch_excitations"]) == 0
        and "T2_twist_right" in step4["twist_or_branch_excitations"]
    )

    return {
        "vacuum_preparation": {
            "reachable_prep_syndromes": reachable_branches,
            "unreachable_odd_parity_syndromes": unreachable_branches,
            "min_stabilizer_expectation_across_all_branches": round(min_branch_exp, 9),
            "deterministic_codespace_fidelity_100pct": bool(min_branch_exp > 0.999999),
        },
        "e_to_m_transmutation_verified": transmutation_verified,
        "anyon_transport_trajectory": trajectory_results,
        "h2_isa_compilation": {
            "demonstration_step": "step3_transmute_e_to_m_across_cut",
            "precompile_sha256": pre_sha,
            "isa_sha256": isa_audit["isa_sha256"],
            "nexus_opt0_fixed_point_sha256": isa_audit["opt0_fixed_point_sha256"],
            "n_qubits": isa_audit["n_qubits"],
            "n_clbits": isa_audit["n_clbits"],
            "depth": isa_audit["depth"],
            "swap_count": isa_audit["swap_count"],
            "zzphase_count": isa_audit["zzphase_count"],
            "gate_counts": isa_audit["gate_counts"],
            "hqc_budget": twist_hqc,
        },
    }


def generate_qec003_verification_report(
    report_path: Path = DEFAULT_REPORT_PATH,
    mc_shots: int = 4000,
) -> dict[str, Any]:
    """Run all Part 1 & Part 2 verifications and write RFC 8785 JCS `qec003_verification_report.json`."""
    decoder = CSSBpOsdDecoder()
    w1_sweep = run_weight1_postprep_circuit_sweep(decoder)
    w2_sweep = run_weight2_postprep_fault_sweep(decoder)
    mc_bench = run_depolarizing_memory_benchmark(n_shots=mc_shots, decoder=decoder)
    mem_h2 = compile_memory_rounds_h2_metrics((1, 2, 3))

    twist_algebra = verify_twist_defect_algebra()
    twist_braiding = verify_twist_anyon_braiding_and_h2_compile()

    report: dict[str, Any] = {
        "schema": "osiris.qec003.verification_report.v1",
        "protocol_id": QEC003_PROTOCOL_ID,
        "version": QEC003_VERSION,
        "evidence_class": "SIMULATED",
        "compilation_evidence_class": "OFFLINE_COMPILED",
        "provider_job_id": None,
        "hardware_attested": False,
        "jcs_serializer": f"rfc8785=={getattr(rfc8785, '__version__', '0.1.4')}",
        "part1_full_xz_toroidal_memory": {
            "code_parameters": "[[16,2,4]]",
            "qubit_allocation": {
                "data_qubits": N_DATA,
                "recycled_ancilla_qubits": N_ANCILLA,
                "total_qubits": N_TOTAL,
            },
            "decoder": {
                "algorithm": "CSS Log-Domain Sum-Product Belief Propagation + Ordered Statistics Decoding (BP+OSD-CS, order=2)",
                "rank_H_X": decoder.rank_hx,
                "rank_H_Z": decoder.rank_hz,
                "global_torus_parity_constraints": 2,
            },
            "weight1_postprep_exhaustive_sweep": {
                "total_faults": w1_sweep["total_faults"],
                "qec002_detected_count": w1_sweep["qec002_detected_count"],
                "qec002_logically_preserved_count": w1_sweep["qec002_logically_preserved_count"],
                "qec003_detected_count": w1_sweep["qec003_detected_count"],
                "qec003_uniquely_corrected_count": w1_sweep["qec003_uniquely_corrected_count"],
                "qec003_logical_error_rate": w1_sweep["qec003_logical_error_rate"],
                "by_pauli": w1_sweep["by_pauli"],
            },
            "weight2_postprep_exhaustive_sweep": w2_sweep,
            "depolarizing_memory_monte_carlo": mc_bench,
            "h2_isa_memory_rounds": mem_h2,
        },
        "part2_checkerboard_twist_defects": {
            "algebraic_proof": twist_algebra,
            "anyon_braiding_and_h2_isa": twist_braiding,
        },
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(rfc8785.dumps(report))
    return report


if __name__ == "__main__":
    rep = generate_qec003_verification_report()
    print(
        json.dumps(
            {
                "protocol_id": rep["protocol_id"],
                "evidence_class": rep["provider_job_id"] or rep["evidence_class"],
                "provider_job_id": rep["provider_job_id"],
                "w1_corrected": rep["part1_full_xz_toroidal_memory"]["weight1_postprep_exhaustive_sweep"][
                    "qec003_uniquely_corrected_count"
                ],
                "w2_detected": rep["part1_full_xz_toroidal_memory"]["weight2_postprep_exhaustive_sweep"][
                    "detected_count"
                ],
                "twist_code": rep["part2_checkerboard_twist_defects"]["algebraic_proof"]["code_notation"],
                "e_to_m_verified": rep["part2_checkerboard_twist_defects"]["anyon_braiding_and_h2_isa"][
                    "e_to_m_transmutation_verified"
                ],
            },
            indent=2,
        )
    )
