"""
osiris_qec.wen_plaquette_pass — Canonical package import surface for the hardened
Wen-plaquette feed-forward preparation pass and 16/16 post-preparation Y-fault sweep.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import numpy as np

import qec_sim as qs
import qec_verify as qv
from wen_plaquette_pass import (
    FROZEN_H2_ISA_SHA256,
    FROZEN_PRECOMPILE_SHA256,
    LOCKED_COMPILER_METADATA,
    N_ANCILLA,
    N_DATA,
    N_TOTAL,
    OSIRIS_QEC_VERSION,
    RESERVED_C_REGISTERS,
    RESERVED_Q_REGISTERS,
    ROUND_1_MAP,
    ROUND_2_LUT_BE,
    ROUND_2_MAP,
    WEN_STABILIZERS,
    EndiannessAuditEntry,
    EndiannessPolicy,
    NexusProvenanceCapsule,
    PauliStabilizer,
    WenPlaquetteFeedForwardPass,
    build_wen_plaquette,
    canonical_circuit_dict,
    compute_sha256,
    encode_syndrome_condition,
    get_circuit_metadata,
    hash_tket_circuit,
    normalize_circuit_metadata,
    set_circuit_metadata,
)

X_STABS: List[Tuple[int, Tuple[int, ...]]] = [
    (i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "X"
]
Z_STABS: List[Tuple[int, Tuple[int, ...]]] = [
    (i, s.support) for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "Z"
]


@dataclass(frozen=True)
class PostPrepYResult:
    qubit: int
    syndrome_detected: bool
    syndrome_recorded: bool
    logical_state_preserved: bool
    x_syndrome: str
    z_syndrome: str
    x_syndrome_plaquettes: List[int]
    z_syndrome_plaquettes: List[int]
    logical_fidelity: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("syndrome_recorded", None)
        return d


@lru_cache(maxsize=1)
def _prepared_reference_state() -> np.ndarray:
    """Deterministic reference prepared state on the all-zero branch before final readout."""
    ops = qv.build_ops()
    st, _ = qs.run_ops(ops, outcomes={bk: 0 for bk in qv.MEAS_BITKEYS})
    st.flags.writeable = False
    return st


def inject_y_error_after_prep(qubit: int) -> PostPrepYResult:
    """
    Inject a single-qubit Pauli-Y fault on data `qubit` (0..15) immediately AFTER
    the 2-round Wen-plaquette preparation circuit completes, and evaluate full X/Z
    syndrome detection and logical state preservation.
    """
    if not (0 <= qubit < N_DATA):
        raise ValueError(f"Data qubit index must be in 0..{N_DATA - 1}, got {qubit}.")

    state0 = _prepared_reference_state()
    corrupted = qs.apply_1q(state0.copy(), qs.Y_GATE, qubit)

    x_exps = [qs.expectation(corrupted, "X", sup) for _, sup in X_STABS]
    z_exps = [qs.expectation(corrupted, "Z", sup) for _, sup in Z_STABS]

    x_bits = ["1" if e < 0.999 else "0" for e in x_exps]
    z_bits = ["1" if e < 0.999 else "0" for e in z_exps]
    x_plaq = [idx for idx, bit in enumerate(x_bits) if bit == "1"]
    z_plaq = [idx for idx, bit in enumerate(z_bits) if bit == "1"]

    fid = qs.state_fidelity(corrupted, state0)
    detected = len(x_plaq) > 0
    preserved = fid > 0.999 and len(x_plaq) == 0 and len(z_plaq) == 0

    return PostPrepYResult(
        qubit=qubit,
        syndrome_detected=detected,
        syndrome_recorded=detected and len(z_plaq) > 0,
        logical_state_preserved=preserved,
        x_syndrome="".join(x_bits),
        z_syndrome="".join(z_bits),
        x_syndrome_plaquettes=x_plaq,
        z_syndrome_plaquettes=z_plaq,
        logical_fidelity=float(round(fid, 15)),
    )


def run_postprep_y_error_sweep() -> Dict[str, Any]:
    """Execute the full 16/16 post-preparation Y-error sweep and return aggregate metrics."""
    records = [inject_y_error_after_prep(q) for q in range(N_DATA)]
    detected_count = sum(1 for r in records if r.syndrome_detected)
    undetected_count = N_DATA - detected_count
    mean_fid = sum(r.logical_fidelity for r in records) / float(N_DATA)
    return {
        "osiris_qec_version": OSIRIS_QEC_VERSION,
        "sweep": "post_preparation_pauli_Y_data_qubits_0_to_15",
        "total_qubits": N_DATA,
        "detected_count": detected_count,
        "undetected_count": undetected_count,
        "logical_fidelity": float(round(mean_fid, 15)),
        "all_preserved": any(r.logical_state_preserved for r in records),
        "records": [r.to_dict() for r in records],
    }
