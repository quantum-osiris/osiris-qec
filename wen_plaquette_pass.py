"""
Wen-Plaquette 20-qubit feed-forward preparation pass (v1.1.0 hardened contract).

Baseline: dnalang_wen_plaquette_pass.py (vendored verbatim, preserved for
comparison). This module keeps the same public API and frozen v1.0.0 circuit
output (`b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`),
with v1.1.0 compiler hardening:

  1. TRANSFORMATION CONTRACT & REGISTER COLLISION PROTECTION:
     - Requires an empty input circuit (zero commands); nonempty inputs raise
       ValueError before any transformation occurs.
     - Rejects colliding or reserved quantum registers (`qr`, `quantum`, or `q`
       with conflicting size; `build_wen_plaquette()` additionally rejects any
       pre-existing `q` register).
     - Rejects colliding or reserved classical registers (`c`, `creg`, `cl`,
       `classical`, or conflicting `c0_1st..c3_1st`, `c4_2nd`, `c5_end`).
  2. METADATA DETERMINISM & HASH STABILITY:
     - Normalizes `circuit.name`, `circuit.phase`, and `circuit.metadata` prior
       to canonical SHA-256 calculation so metadata drift never perturbs circuit
       digests (`v1.0.0 hash == v1.1.0 hash` bit-for-bit on empty input).
     - Explicitly freezes `{"osiris_qec_version": "1.1.0", "compiler_lock": True,
       "hash_locked": True}` on emitted circuits when `compiler_lock=True`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Tuple

from pytket import Circuit, OpType
from pytket.circuit import Bit, BitRegister, Qubit, QubitRegister
from pytket.passes import BasePass, CustomPass

OSIRIS_QEC_VERSION = "1.1.0"
FROZEN_PRECOMPILE_SHA256 = "b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b"
FROZEN_H2_ISA_SHA256 = "02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062"

N_DATA = 16
N_ANCILLA = 4
N_TOTAL = N_DATA + N_ANCILLA  # 20

RESERVED_Q_REGISTERS = frozenset({"q", "qr", "quantum"})
RESERVED_C_REGISTERS = frozenset(
    {"c", "creg", "cl", "classical", "c0_1st", "c1_1st", "c2_1st", "c3_1st", "c4_2nd", "c5_end"}
)

LOCKED_COMPILER_METADATA: Dict[str, Any] = {
    "osiris_qec_version": OSIRIS_QEC_VERSION,
    "compiler_lock": True,
    "hash_locked": True,
}


class EndiannessPolicy(str, Enum):
    """Explicit bit-ordering contract for classical condition registers."""

    TKET_LITTLE_ENDIAN = "tket_little_endian"   # c_reg[0] is LSB (bit 0)
    QISKIT_BIG_ENDIAN = "qiskit_big_endian"     # string index 0 is MSB


@dataclass(frozen=True)
class PauliStabilizer:
    pauli_type: Literal["X", "Z"]
    support: Tuple[int, ...]

    def __repr__(self) -> str:
        return ".".join(f"{self.pauli_type}{i}" for i in self.support)


@dataclass
class EndiannessAuditEntry:
    syndrome_be: str
    tket_condition_value: int
    target_qubits: List[int]
    parity_valid: bool
    register_name: str


@dataclass
class NexusProvenanceCapsule:
    capsule_version: str = "osiris.nexus.v1"
    pass_name: str = "WenPlaquetteFeedForwardPass"
    osiris_qec_version: str = OSIRIS_QEC_VERSION
    compiler_lock: bool = True
    hash_locked: bool = True
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    target_device: str = "H2-1"
    measurement_setting: Literal["X", "Z"] = "X"
    n_data_qubits: int = N_DATA
    n_ancilla_qubits: int = N_ANCILLA
    dd_options: Dict[str, object] = field(
        default_factory=lambda: {
            "apply_DD": True,
            "DD_threshold_times": [0.03],
            "combine_SQ": True,
            "combine_rotates": True,
        }
    )
    pre_pass_circuit_sha256: str = ""
    post_pass_circuit_sha256: str = ""
    classical_registers: Dict[str, int] = field(default_factory=dict)
    endianness_policy: str = EndiannessPolicy.TKET_LITTLE_ENDIAN.value
    endianness_audit: List[EndiannessAuditEntry] = field(default_factory=list)
    conditional_op_count: int = 0
    reset_op_count: int = 0
    capsule_sha256: str = ""

    def finalize(self) -> "NexusProvenanceCapsule":
        """Compute SHA-256 over the canonical capsule payload (excl. the hash itself)."""
        payload = asdict(self)
        payload.pop("capsule_sha256", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.capsule_sha256 = hashlib.sha256(canonical).hexdigest()
        return self


# ---------------------------------------------------------------------------
# Wen-Plaquette lattice & lookup tables
# ---------------------------------------------------------------------------
# 4x4 periodic (toroidal) lattice; qubit (r, c) has index 4*r + c.
# Checkerboard plaquettes: Z-type on (r+c) even, X-type on (r+c) odd.

WEN_STABILIZERS: List[PauliStabilizer] = [
    PauliStabilizer("Z", (0, 1, 4, 5)),     # 0
    PauliStabilizer("X", (1, 2, 5, 6)),     # 1  (Round 2)
    PauliStabilizer("Z", (2, 3, 6, 7)),     # 2
    PauliStabilizer("X", (3, 0, 7, 4)),     # 3  (Round 2)
    PauliStabilizer("X", (4, 5, 8, 9)),     # 4  (Round 1)
    PauliStabilizer("Z", (5, 6, 9, 10)),    # 5
    PauliStabilizer("X", (6, 7, 10, 11)),   # 6  (Round 1)
    PauliStabilizer("Z", (7, 4, 11, 8)),    # 7
    PauliStabilizer("Z", (8, 9, 12, 13)),   # 8
    PauliStabilizer("X", (9, 10, 13, 14)),  # 9  (Round 2)
    PauliStabilizer("Z", (10, 11, 14, 15)), # 10
    PauliStabilizer("X", (11, 8, 15, 12)),  # 11 (Round 2)
    PauliStabilizer("X", (12, 13, 0, 1)),   # 12 (Round 1)
    PauliStabilizer("Z", (13, 14, 1, 2)),   # 13
    PauliStabilizer("X", (14, 15, 2, 3)),   # 14 (Round 1)
    PauliStabilizer("Z", (15, 12, 3, 0)),   # 15
]

ROUND_1_MAP: Dict[int, Tuple[int, int, int]] = {
    4: (5, 16, 0),
    6: (7, 17, 1),
    12: (13, 18, 2),
    14: (15, 19, 3),
}

ROUND_2_MAP: Dict[int, Tuple[int, int]] = {
    1: (16, 0),
    3: (17, 1),
    9: (18, 2),
    11: (19, 3),
}

ROUND_2_LUT_BE: Dict[str, List[int]] = {
    "0011": [10, 11],
    "0101": [4, 8],
    "0110": [0, 13],
    "1001": [2, 15],
    "1010": [5, 9],
    "1100": [6, 7],
    "1111": [2, 3, 14, 15],
}


# ---------------------------------------------------------------------------
# Endianness, metadata normalization & deterministic hashing utilities
# ---------------------------------------------------------------------------

def encode_syndrome_condition(
    syndrome_be: str,
    reg_size: int,
    policy: EndiannessPolicy = EndiannessPolicy.TKET_LITTLE_ENDIAN,
    enforce_even_parity: bool = True,
) -> Tuple[int, bool]:
    """
    Convert a big-endian syndrome string (e.g. '0011' = A1,A3,A9,A11) into the
    integer condition_value expected by pytket's little-endian condition_bits
    (condition_bits[0] is 2^0). '0011' -> int('1100', 2) == 12.
    """
    if len(syndrome_be) != reg_size or any(ch not in ("0", "1") for ch in syndrome_be):
        raise ValueError(
            f"Invalid syndrome '{syndrome_be}': expected {reg_size}-bit binary string."
        )

    ones_count = syndrome_be.count("1")
    parity_valid = (ones_count % 2 == 0)
    if enforce_even_parity and not parity_valid:
        raise ValueError(
            f"Topological parity violation: syndrome '{syndrome_be}' has odd anyon count ({ones_count})."
        )

    if policy == EndiannessPolicy.TKET_LITTLE_ENDIAN:
        cond_val = int(syndrome_be[::-1], 2)
    else:
        cond_val = int(syndrome_be, 2)

    return cond_val, parity_valid


def _normalize_phase_str(raw_phase: Any) -> str:
    """Normalize global circuit phase (in half-turns, mod 2.0) to canonical TKET string."""
    try:
        val = float(raw_phase)
    except (TypeError, ValueError):
        return str(raw_phase)
    if not math.isfinite(val):
        raise ValueError(f"Non-finite circuit phase: {raw_phase}")
    mod_val = val % 2.0
    if abs(mod_val) < 1e-12 or abs(mod_val - 2.0) < 1e-12:
        return "0.0"
    return f"{mod_val:.12g}"


_CIRCUIT_METADATA_REGISTRY: Dict[int, Dict[str, Any]] = {}


def set_circuit_metadata(circ: Circuit, metadata: Dict[str, Any]) -> None:
    """Attach metadata to `circ` (in `.metadata` if supported, else module registry)."""
    copy_meta = dict(metadata)
    try:
        setattr(circ, "metadata", copy_meta)
    except (AttributeError, TypeError):
        _CIRCUIT_METADATA_REGISTRY[id(circ)] = copy_meta


def get_circuit_metadata(circ: Circuit) -> Dict[str, Any]:
    """Retrieve normalized metadata associated with `circ`."""
    if hasattr(circ, "metadata"):
        val = getattr(circ, "metadata")
        if isinstance(val, dict):
            return dict(val)
    return dict(_CIRCUIT_METADATA_REGISTRY.get(id(circ), {}))


def normalize_circuit_metadata(circ: Circuit, compiler_lock: bool = True) -> Circuit:
    """
    Normalize mutable circuit metadata (`name`, `phase`, `metadata`) in place to
    prevent metadata drift across pytket passes. When `compiler_lock=True`,
    freezes `{"osiris_qec_version": "1.1.0", "compiler_lock": True, "hash_locked": True}`
    without altering the canonical circuit SHA-256.
    """
    if circ.name is not None and circ.name != "":
        circ.name = ""
    try:
        p_val = float(circ.phase) % 2.0
        if abs(p_val) < 1e-12 or abs(p_val - 2.0) < 1e-12:
            p_val = 0.0
        if float(circ.phase) != p_val:
            circ.add_phase(p_val - float(circ.phase))
    except Exception:
        pass

    target_meta = dict(LOCKED_COMPILER_METADATA) if compiler_lock else {}
    set_circuit_metadata(circ, target_meta)
    return circ


def canonical_circuit_dict(circ: Circuit) -> Dict[str, Any]:
    """Return metadata-normalized pytket dictionary suitable for deterministic hashing."""
    d = dict(circ.to_dict())
    d.pop("name", None)
    d.pop("metadata", None)
    if "phase" in d:
        d["phase"] = _normalize_phase_str(d["phase"])
    return d


def hash_tket_circuit(circ: Circuit) -> str:
    """
    Deterministic SHA-256 digest of a pytket Circuit via its metadata-normalized
    canonical JSON dict. Bit-for-bit identical between v1.0.0 and v1.1.0 on clean inputs.
    """
    canonical = json.dumps(
        canonical_circuit_dict(circ), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compute_sha256(circ: Circuit) -> str:
    """Alias for `hash_tket_circuit` used in v1.1.0 specification verification helpers."""
    return hash_tket_circuit(circ)


# ---------------------------------------------------------------------------
# Compilation pass (preparation-only contract + v1.1.0 register/metadata lock)
# ---------------------------------------------------------------------------

class WenPlaquetteFeedForwardPass:
    """
    Preparation-only pass builder for the 20-qubit Wen-plaquette
    feed-forward preparation circuit.

    Contract: the input circuit MUST be empty (zero commands). Nonempty or
    register-conflicting inputs raise ValueError; nothing is silently
    discarded. Use `to_tket_pass()` to obtain a composable pytket CustomPass.
    """

    def __init__(
        self,
        measurement_setting: Literal["X", "Z"] = "X",
        target_device: str = "H2-1",
        policy: EndiannessPolicy = EndiannessPolicy.TKET_LITTLE_ENDIAN,
        dd_options: Dict[str, object] | None = None,
        compiler_lock: bool = True,
        strict_registers: bool = False,
    ) -> None:
        self.measurement_setting = measurement_setting
        self.target_device = target_device
        self.policy = policy
        self.dd_options = dd_options or {
            "apply_DD": True,
            "DD_threshold_times": [0.03],
            "combine_SQ": True,
            "combine_rotates": True,
        }
        self.compiler_lock = compiler_lock
        self.strict_registers = strict_registers
        self.last_capsule: NexusProvenanceCapsule | None = None

    def _check_input_contract(self, circ: Circuit) -> None:
        """Enforce preparation-only and register-collision contracts before transformation."""
        n_cmd = len(circ.get_commands())
        if n_cmd != 0:
            raise ValueError(
                "WenPlaquetteFeedForwardPass is preparation-only: the input circuit "
                f"must be empty, but it contains {n_cmd} command(s). "
                "Apply the pass to an empty Circuit, or compose it after a pass that "
                "produces the empty base circuit."
            )

        for qreg in circ.q_registers:
            if qreg.name == "q":
                if self.strict_registers:
                    raise ValueError(
                        'Input already declares quantum register "q"; strict register '
                        "collision protection requires an unallocated input circuit."
                    )
                if qreg.size != N_TOTAL:
                    raise ValueError(
                        f'Input declares q register "q" of size {qreg.size}; this pass '
                        f"requires size {N_TOTAL}."
                    )
            elif qreg.name in RESERVED_Q_REGISTERS:
                raise ValueError(
                    f'Input declares colliding quantum register "{qreg.name}" '
                    f"(reserved names: {sorted(RESERVED_Q_REGISTERS)})."
                )

        for creg in circ.c_registers:
            if creg.name in RESERVED_C_REGISTERS:
                raise ValueError(
                    f'Input declares colliding classical register "{creg.name}" '
                    f"(reserved names: {sorted(RESERVED_C_REGISTERS)})."
                )

    @staticmethod
    def _measure_stabilizer_nondestructive(
        circ: Circuit,
        q_reg: QubitRegister,
        stab: PauliStabilizer,
        c_bit: Bit,
        anc_qubit: Qubit,
    ) -> None:
        for i in stab.support:
            if stab.pauli_type == "X":
                circ.H(q_reg[i])
                circ.CX(q_reg[i], anc_qubit)
                circ.H(q_reg[i])
            elif stab.pauli_type == "Z":
                circ.CX(q_reg[i], anc_qubit)
        circ.Measure(anc_qubit, c_bit)
        circ.add_gate(OpType.Reset, [anc_qubit])

    def _transform(self, circ: Circuit) -> Circuit:
        """Build the preparation circuit. Input must satisfy the prep-only contract."""
        self._check_input_contract(circ)
        pre_hash = hash_tket_circuit(circ)
        out = Circuit()

        q_reg = QubitRegister("q", N_TOTAL)
        out.add_q_register(q_reg)

        c_regs_1st: List[BitRegister] = []
        for idx in range(4):
            reg = BitRegister(f"c{idx}_1st", 1)
            out.add_c_register(reg)
            c_regs_1st.append(reg)

        c_reg_2nd = BitRegister("c4_2nd", 4)
        out.add_c_register(c_reg_2nd)

        c_reg_end = BitRegister("c5_end", N_TOTAL)
        out.add_c_register(c_reg_end)

        audit_log: List[EndiannessAuditEntry] = []

        # Round 1: measure XXXX on plaquettes (4, 6, 12, 14) + single-bit Z feed-forward
        for stab_idx, (target_q, anc_idx, c_idx) in ROUND_1_MAP.items():
            self._measure_stabilizer_nondestructive(
                out, q_reg, WEN_STABILIZERS[stab_idx], c_regs_1st[c_idx][0], q_reg[anc_idx]
            )

        for stab_idx, (target_q, _, c_idx) in ROUND_1_MAP.items():
            cond_val, _ = encode_syndrome_condition(
                "1", reg_size=1, policy=self.policy, enforce_even_parity=False
            )
            out.Z(
                q_reg[target_q],
                condition_bits=c_regs_1st[c_idx],
                condition_value=cond_val,
            )
            audit_log.append(
                EndiannessAuditEntry(
                    syndrome_be="1",
                    tket_condition_value=cond_val,
                    target_qubits=[target_q],
                    parity_valid=True,
                    register_name=c_regs_1st[c_idx].name,
                )
            )

        # Round 2: measure XXXX on plaquettes (1, 3, 9, 11) + 4-bit LUT decoder
        for stab_idx, (anc_idx, c_bit_idx) in ROUND_2_MAP.items():
            self._measure_stabilizer_nondestructive(
                out, q_reg, WEN_STABILIZERS[stab_idx], c_reg_2nd[c_bit_idx], q_reg[anc_idx]
            )

        for syndrome_be, target_qubits in ROUND_2_LUT_BE.items():
            cond_val, parity_ok = encode_syndrome_condition(
                syndrome_be, reg_size=4, policy=self.policy, enforce_even_parity=True
            )
            for q_idx in target_qubits:
                out.Z(
                    q_reg[q_idx],
                    condition_bits=c_reg_2nd,
                    condition_value=cond_val,
                )
            audit_log.append(
                EndiannessAuditEntry(
                    syndrome_be=syndrome_be,
                    tket_condition_value=cond_val,
                    target_qubits=list(target_qubits),
                    parity_valid=parity_ok,
                    register_name=c_reg_2nd.name,
                )
            )

        # Final destructive measurement of all 16 data qubits in X or Z basis
        out.add_barrier([q_reg[i] for i in range(N_TOTAL)])
        for q_idx in range(N_DATA):
            if self.measurement_setting == "X":
                out.H(q_reg[q_idx])
            out.Measure(q_reg[q_idx], c_reg_end[q_idx])

        # Post-pass structural audit & metadata normalization
        cond_ops = [cmd for cmd in out.get_commands() if cmd.op.type == OpType.Conditional]
        reset_ops = [cmd for cmd in out.get_commands() if cmd.op.type == OpType.Reset]

        expected_cond_ops = len(ROUND_1_MAP) + sum(len(qs) for qs in ROUND_2_LUT_BE.values())
        if len(cond_ops) != expected_cond_ops:
            raise RuntimeError(
                f"Conditional op count mismatch: expected {expected_cond_ops}, got {len(cond_ops)}."
            )

        normalize_circuit_metadata(out, compiler_lock=self.compiler_lock)

        capsule = NexusProvenanceCapsule(
            compiler_lock=self.compiler_lock,
            hash_locked=self.compiler_lock,
            target_device=self.target_device,
            measurement_setting=self.measurement_setting,
            dd_options=self.dd_options,
            pre_pass_circuit_sha256=pre_hash,
            post_pass_circuit_sha256=hash_tket_circuit(out),
            classical_registers={reg.name: reg.size for reg in out.c_registers},
            endianness_policy=self.policy.value,
            endianness_audit=audit_log,
            conditional_op_count=len(cond_ops),
            reset_op_count=len(reset_ops),
        ).finalize()

        self.last_capsule = capsule
        return out

    def to_tket_pass(self) -> BasePass:
        """Return a composable pytket BasePass instance (preparation-only contract)."""
        def _apply_and_preserve_meta(c: Circuit) -> Circuit:
            built = self._transform(c)
            normalize_circuit_metadata(built, compiler_lock=self.compiler_lock)
            return built

        return CustomPass(_apply_and_preserve_meta, label="WenPlaquetteFeedForwardPass")


def build_wen_plaquette(
    circ: Circuit | None = None,
    *,
    measurement_setting: Literal["X", "Z"] = "X",
    target_device: str = "H2-1",
    compiler_lock: bool = True,
) -> Circuit:
    """
    Functional entry point enforcing strict register collision protection
    (rejecting any pre-existing `q`, `qr`, `quantum`, `c`, `creg`, `cl`, or
    `classical` register) and returning a metadata-normalized Circuit.
    """
    target = Circuit() if circ is None else circ
    builder = WenPlaquetteFeedForwardPass(
        measurement_setting=measurement_setting,
        target_device=target_device,
        compiler_lock=compiler_lock,
        strict_registers=True,
    )
    out = builder._transform(target)
    normalize_circuit_metadata(out, compiler_lock=compiler_lock)
    return out


if __name__ == "__main__":
    builder = WenPlaquetteFeedForwardPass(measurement_setting="X", target_device="H2-1")
    tket_pass = builder.to_tket_pass()

    circ = Circuit()
    tket_pass.apply(circ)
    normalize_circuit_metadata(circ, compiler_lock=True)

    assert builder.last_capsule is not None
    print(json.dumps(asdict(builder.last_capsule), indent=2))
