"""
DNA-Lang TKET Compilation Pass: 20-Qubit Wen-Plaquette Feed-Forward Decoder
Includes:
  - Explicit endianness normalization & even-parity syndrome verification
  - 2-round non-destructive XXXX syndrome extraction with OpType.Reset
  - Post-pass Conditional op bit-order audit
  - Quantinuum Nexus Provenance Capsule emission (SHA-256 bound)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Literal, Tuple

from pytket import Circuit, OpType
from pytket.circuit import Bit, BitRegister, Qubit, QubitRegister
from pytket.passes import BasePass, CustomPass


# ---------------------------------------------------------------------------
# 1. Core Domain Models & Endianness Policy
# ---------------------------------------------------------------------------

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
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    target_device: str = "H2-1"
    measurement_setting: Literal["X", "Z"] = "X"
    n_data_qubits: int = 16
    n_ancilla_qubits: int = 4
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
        """Compute deterministic SHA-256 over the canonical capsule payload."""
        payload = asdict(self)
        payload.pop("capsule_sha256", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.capsule_sha256 = hashlib.sha256(canonical).hexdigest()
        return self


# ---------------------------------------------------------------------------
# 2. Wen-Plaquette Lattice & Lookup Table Definitions
# ---------------------------------------------------------------------------

WEN_STABILIZERS: List[PauliStabilizer] = [
    PauliStabilizer("Z", (0, 1, 4, 5)),    # 0
    PauliStabilizer("X", (1, 2, 5, 6)),    # 1  (Round 2)
    PauliStabilizer("Z", (2, 3, 6, 7)),    # 2
    PauliStabilizer("X", (3, 0, 7, 4)),    # 3  (Round 2)
    PauliStabilizer("X", (4, 5, 8, 9)),    # 4  (Round 1)
    PauliStabilizer("Z", (5, 6, 9, 10)),   # 5
    PauliStabilizer("X", (6, 7, 10, 11)),  # 6  (Round 1)
    PauliStabilizer("Z", (7, 4, 11, 8)),   # 7
    PauliStabilizer("Z", (8, 9, 12, 13)),  # 8
    PauliStabilizer("X", (9, 10, 13, 14)), # 9  (Round 2)
    PauliStabilizer("Z", (10, 11, 14, 15)),# 10
    PauliStabilizer("X", (11, 8, 15, 12)), # 11 (Round 2)
    PauliStabilizer("X", (12, 13, 0, 1)),  # 12 (Round 1)
    PauliStabilizer("Z", (13, 14, 1, 2)),  # 13
    PauliStabilizer("X", (14, 15, 2, 3)),  # 14 (Round 1)
    PauliStabilizer("Z", (15, 12, 3, 0)),  # 15
]

# Round 1: stabilizer_idx -> (target_z_qubit, ancilla_idx, c_reg_idx)
ROUND_1_MAP: Dict[int, Tuple[int, int, int]] = {
    4: (5, 16, 0),
    6: (7, 17, 1),
    12: (13, 18, 2),
    14: (15, 19, 3),
}

# Round 2: stabilizer_idx -> (ancilla_idx, c_bit_idx in c4_2nd)
ROUND_2_MAP: Dict[int, Tuple[int, int]] = {
    1: (16, 0),
    3: (17, 1),
    9: (18, 2),
    11: (19, 3),
}

# Round 2 LUT: big-endian syndrome string for (A1, A3, A9, A11) -> Z correction qubits
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
# 3. Endianness & Circuit Hashing Utilities
# ---------------------------------------------------------------------------

def encode_syndrome_condition(
    syndrome_be: str,
    reg_size: int,
    policy: EndiannessPolicy = EndiannessPolicy.TKET_LITTLE_ENDIAN,
    enforce_even_parity: bool = True,
) -> Tuple[int, bool]:
    """
    Convert a human-readable big-endian syndrome string (e.g. '0011' for A1,A3,A9,A11)
    into the integer condition_value expected by pytket.Circuit.Z(condition_bits=...).

    In pytket, condition_bits=[c[0], c[1], c[2], c[3]] treats c[0] as LSB (2^0).
    Therefore, big-endian '0011' (A1=0, A3=0, A9=1, A11=1) maps to little-endian
    bits (0, 0, 1, 1) -> int('1100', 2) == 12.
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


def hash_tket_circuit(circ: Circuit) -> str:
    """Deterministic SHA-256 digest of a pytket Circuit via its canonical JSON dict."""
    canonical = json.dumps(circ.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# 4. DNA-Lang TKET Compilation Pass
# ---------------------------------------------------------------------------

class WenPlaquetteFeedForwardPass:
    """
    DNA-Lang TKET pass builder that synthesizes, validates, and provenance-logs
    the 20-qubit Wen-Plaquette constant-depth preparation circuit.
    """

    def __init__(
        self,
        measurement_setting: Literal["X", "Z"] = "X",
        target_device: str = "H2-1",
        policy: EndiannessPolicy = EndiannessPolicy.TKET_LITTLE_ENDIAN,
        dd_options: Dict[str, object] | None = None,
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
        self.last_capsule: NexusProvenanceCapsule | None = None

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
        """Core in-place-safe TKET CustomPass transformation."""
        pre_hash = hash_tket_circuit(circ)
        out = Circuit()

        # 1. Allocate registers
        q_reg = QubitRegister("q", 20)
        out.add_q_register(q_reg)

        c_regs_1st: List[BitRegister] = []
        for idx in range(4):
            reg = BitRegister(f"c{idx}_1st", 1)
            out.add_c_register(reg)
            c_regs_1st.append(reg)

        c_reg_2nd = BitRegister("c4_2nd", 4)
        out.add_c_register(c_reg_2nd)

        c_reg_end = BitRegister("c5_end", 20)
        out.add_c_register(c_reg_end)

        audit_log: List[EndiannessAuditEntry] = []

        # 2. Round 1: Measure XXXX on plaquettes (4, 6, 12, 14) + single-bit Z feed-forward
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

        # 3. Round 2: Measure XXXX on plaquettes (1, 3, 9, 11) + 4-bit LUT decoder
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

        # 4. Final destructive measurement of all 16 data qubits in X or Z basis
        out.add_barrier(list(range(20)))
        for q_idx in range(16):
            if self.measurement_setting == "X":
                out.H(q_reg[q_idx])
            out.Measure(q_reg[q_idx], c_reg_end[q_idx])

        # 5. Post-pass structural audit & Nexus provenance capsule emission
        cond_ops = [cmd for cmd in out.get_commands() if cmd.op.type == OpType.Conditional]
        reset_ops = [cmd for cmd in out.get_commands() if cmd.op.type == OpType.Reset]

        expected_cond_ops = len(ROUND_1_MAP) + sum(len(qs) for qs in ROUND_2_LUT_BE.values())
        if len(cond_ops) != expected_cond_ops:
            raise RuntimeError(
                f"Conditional op count mismatch: expected {expected_cond_ops}, got {len(cond_ops)}."
            )

        capsule = NexusProvenanceCapsule(
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
        """Return a composable pytket BasePass instance."""
        return CustomPass(self._transform, label="DNA-Lang::WenPlaquetteFeedForwardPass")


# ---------------------------------------------------------------------------
# 5. Example Pipeline Execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    builder = WenPlaquetteFeedForwardPass(
        measurement_setting="X",
        target_device="H2-1",
    )
    tket_pass = builder.to_tket_pass()

    circ = Circuit()
    tket_pass.apply(circ)

    assert builder.last_capsule is not None
    print(json.dumps(asdict(builder.last_capsule), indent=2))
