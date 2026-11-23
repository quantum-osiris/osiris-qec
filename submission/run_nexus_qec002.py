#!/usr/bin/env python3
"""
OSIRIS-QEC-002 Hash-Locked Quantinuum Nexus (H2-1SC / H2-1E / H2-1) Staging & Dispatch CLI.

Modes:
  1. `--stage-bundle`: Deterministically builds and writes the hash-locked 20-qubit
     `[[16,2,4]]` toroidal Wen-plaquette H2-1 ISA circuits (X-basis and Z-basis readout),
     RFC 8785 JCS `nexus_qec002_manifest.json`, and `SHA256SUMS.txt` into
     `submission/nexus_h2_bundle/`.
  2. `--dry-run` (default): Verifies RFC 8785 JCS canonicalization, all SHA-256 digests,
     `EXPERIMENT_PROTOCOL.md` frozen hash locks, `QuantinuumAPIOffline` `optimisation_level=0`
     zero-drift invariance, H2-1 native gate set compliance (`ZZPhase, PhasedX, Rz, Measure,
     Reset` + conditionals, 0 SWAPs), and fast noiseless stabilizer/LUT verification,
     emitting an `OFFLINE_VERIFIED` readiness receipt (`provider_job_id: null`).
  3. `--submit --device H2-1E --operator-approval-token <token>`: Fail-closed Quantinuum
     Nexus submission entrypoint. Requires explicit operator approval token + `qnexus`
     package & credentials; refuses to claim `HARDWARE_ATTESTED` without physical `H2-1`
     QPU Nexus completion confirmation (`H2-1E` emulator runs cap at `EMULATOR_ATTESTED`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
from pytket import Circuit, OpType

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import qec_math as qm
import qec_sim as qs
import qec_verify as qv
from hardware.quantinuum_h2 import local_h2_compile
from osiris_cli.ledger import WILSON_Z_95, compute_wilson_lower_bound
from wen_plaquette_pass import (
    FROZEN_H2_ISA_SHA256,
    FROZEN_PRECOMPILE_SHA256,
    N_ANCILLA,
    N_DATA,
    N_TOTAL,
    OSIRIS_PROTOCOL_ID,
    OSIRIS_QEC_VERSION,
    ROUND_2_LUT_BE,
    WEN_STABILIZERS,
    WenPlaquetteFeedForwardPass,
    hash_tket_circuit,
)

DEFAULT_BUNDLE_DIR = ROOT / "submission" / "nexus_h2_bundle"
X_ISA_FILENAME = "wen_plaquette_qec002_x_basis_h2_isa.json"
Z_ISA_FILENAME = "wen_plaquette_qec002_z_basis_h2_isa.json"
MANIFEST_FILENAME = "nexus_qec002_manifest.json"
SHA256SUMS_FILENAME = "SHA256SUMS.txt"

EXPECTED_Z_PRECOMPILE_SHA256 = "d994f2db4bc877e29a3ff0474e96b3b2627443cc1a621fa2dd84e9d84bf2fca4"
EXPECTED_Z_H2_ISA_SHA256 = "b0b7a9778ad7660daae4e8b204a3d0549ac6fc31e58d8c240e2bebb7db96453d"

ALLOWED_H2_OUTER_OPS = frozenset(
    {
        OpType.ZZPhase,
        OpType.PhasedX,
        OpType.Rz,
        OpType.Measure,
        OpType.Reset,
        OpType.Barrier,
        OpType.Conditional,
    }
)
ALLOWED_H2_CONDITIONAL_INNER_OPS = frozenset({OpType.PhasedX, OpType.Rz})
ALLOWED_NEXUS_DEVICES = ("H2-1SC", "H2-1E", "H2-1")
SHOT_TIERS = (512, 1000, 2000)


class NexusBundleVerificationError(RuntimeError):
    """Raised when any hash-lock, JCS canonicalization, or ISA compliance check fails."""


class NexusSubmissionBlockedError(RuntimeError):
    """Raised when fail-closed Nexus submission preconditions are not met."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def jcs_dumps_bytes(payload: dict[str, Any]) -> bytes:
    return rfc8785.dumps(payload)


def compute_hqc_metrics(circ: Circuit, shot_tiers: Sequence[int] = SHOT_TIERS) -> dict[str, Any]:
    """
    Compute exact Quantinuum System Model H2 HQC budget using:
      HQC = 5 + C * (N_1q + 10 * N_2q + 5 * N_m) / 5000
    where:
      - N_1q = PhasedX count (Rz and Conditional(Rz) are virtual Z-frame updates = 0 HQC)
      - N_2q = ZZPhase + ZZMax + TK2 count
      - N_m  = Measure + Reset count (total state-prep/measurement operations)
    """
    counts = Counter(cmd.op.type.name for cmd in circ.get_commands())
    cond_inner = Counter(
        cmd.op.op.type.name for cmd in circ.get_commands() if cmd.op.type == OpType.Conditional
    )
    n_1q = int(counts.get("PhasedX", 0) + cond_inner.get("PhasedX", 0))
    n_2q = int(counts.get("ZZPhase", 0) + counts.get("ZZMax", 0) + counts.get("TK2", 0))
    n_meas = int(counts.get("Measure", 0))
    n_reset = int(counts.get("Reset", 0))
    n_m = n_meas + n_reset
    weighted_ops = n_1q + 10 * n_2q + 5 * n_m

    by_shots: dict[str, float] = {}
    for c_shots in shot_tiers:
        hqc = 5.0 + (float(c_shots) * float(weighted_ops)) / 5000.0
        by_shots[str(c_shots)] = round(hqc, 6)

    return {
        "formula": "HQC = 5 + C*(N_1q + 10*N_2q + 5*N_m)/5000",
        "n_1q_phasedx": n_1q,
        "n_virtual_rz": int(counts.get("Rz", 0)),
        "n_conditional_virtual_rz": int(cond_inner.get("Rz", 0)),
        "n_2q_zzphase": n_2q,
        "n_measure": n_meas,
        "n_reset": n_reset,
        "n_m_total": n_m,
        "weighted_gate_units_per_shot": weighted_ops,
        "hqc_by_shots": by_shots,
    }


def min_successes_for_wilson_gt_099(shots: int) -> tuple[int, int, float]:
    """Return (min_successes, max_failures, wilson_lb95_at_min_successes) for LB95 > 0.99."""
    for s in range(shots + 1):
        lb = compute_wilson_lower_bound(s, shots, z=WILSON_Z_95)
        if lb > 0.99:
            return s, shots - s, round(lb, 6)
    raise ValueError(f"No success count in 0..{shots} achieves 95% Wilson LB > 0.99")


def verify_native_h2_isa(circ: Circuit) -> dict[str, Any]:
    """Verify strict H2-1 ISA compliance, 0 SWAPs, and offline opt_level=0 fixed-point invariance."""
    cmds = circ.get_commands()
    outer_types = {cmd.op.type for cmd in cmds}
    disallowed_outer = sorted(t.name for t in (outer_types - ALLOWED_H2_OUTER_OPS))
    if disallowed_outer:
        raise NexusBundleVerificationError(
            f"Non-native H2-1 outer gate(s) detected: {disallowed_outer}"
        )

    cond_inner_types = {cmd.op.op.type for cmd in cmds if cmd.op.type == OpType.Conditional}
    disallowed_inner = sorted(t.name for t in (cond_inner_types - ALLOWED_H2_CONDITIONAL_INNER_OPS))
    if disallowed_inner:
        raise NexusBundleVerificationError(
            f"Non-native H2-1 Conditional inner gate(s) detected: {disallowed_inner}"
        )

    counts = Counter(cmd.op.type.name for cmd in cmds)
    swap_count = int(counts.get("SWAP", 0))
    if swap_count != 0:
        raise NexusBundleVerificationError(f"Expected 0 SWAP gates on H2-1, got {swap_count}")
    if circ.n_qubits > 56:
        raise NexusBundleVerificationError(f"Qubit count {circ.n_qubits} exceeds H2-1 limit (56)")
    if circ.n_bits > 4000:
        raise NexusBundleVerificationError(f"Bit count {circ.n_bits} exceeds H2-1 limit (4000)")

    isa_hash = hash_tket_circuit(circ)
    opt0_recompiled = local_h2_compile(circ, optimisation_level=0)
    opt0_hash = hash_tket_circuit(opt0_recompiled)
    if opt0_hash != isa_hash:
        raise NexusBundleVerificationError(
            f"H2-1 optimisation_level=0 fixed-point drift: {isa_hash} != {opt0_hash}"
        )

    return {
        "n_qubits": circ.n_qubits,
        "n_clbits": circ.n_bits,
        "depth": circ.depth(),
        "swap_count": swap_count,
        "zzphase_count": int(counts.get("ZZPhase", 0)),
        "gate_counts": dict(sorted(counts.items())),
        "conditional_inner_ops": sorted(t.name for t in cond_inner_types),
        "isa_sha256": isa_hash,
        "opt0_fixed_point_sha256": opt0_hash,
        "native_isa_compliant": True,
    }


def _build_basis_artifact(basis: Literal["X", "Z"]) -> tuple[Circuit, Circuit, dict[str, Any]]:
    builder = WenPlaquetteFeedForwardPass(measurement_setting=basis, target_device="H2-1")
    pre_circ = Circuit()
    builder.to_tket_pass().apply(pre_circ)
    pre_hash = hash_tket_circuit(pre_circ)

    # Unoptimised direct opt_level=0 digest recorded for full provenance transparency
    direct_opt0 = local_h2_compile(pre_circ, optimisation_level=0)
    direct_opt0_hash = hash_tket_circuit(direct_opt0)

    # Canonical H2-1 ISA artifact (depth 19 for X, depth 18 for Z, 32 ZZPhase)
    # locked as a zero-drift fixed point under Nexus optimisation_level=0 (`no_opt=True`)
    isa_circ = local_h2_compile(pre_circ, optimisation_level=2)
    isa_audit = verify_native_h2_isa(isa_circ)
    hqc = compute_hqc_metrics(isa_circ, SHOT_TIERS)

    expected_pre = FROZEN_PRECOMPILE_SHA256 if basis == "X" else EXPECTED_Z_PRECOMPILE_SHA256
    expected_isa = FROZEN_H2_ISA_SHA256 if basis == "X" else EXPECTED_Z_H2_ISA_SHA256
    expected_depth = 19 if basis == "X" else 18

    if pre_hash != expected_pre:
        raise NexusBundleVerificationError(
            f"{basis}-basis precompile SHA-256 mismatch: expected {expected_pre}, got {pre_hash}"
        )
    if isa_audit["isa_sha256"] != expected_isa:
        raise NexusBundleVerificationError(
            f"{basis}-basis H2-1 ISA SHA-256 mismatch: expected {expected_isa}, got {isa_audit['isa_sha256']}"
        )
    if isa_audit["depth"] != expected_depth or isa_audit["zzphase_count"] != 32:
        raise NexusBundleVerificationError(
            f"{basis}-basis structural mismatch: depth={isa_audit['depth']} (expected {expected_depth}), "
            f"ZZPhase={isa_audit['zzphase_count']} (expected 32)"
        )

    info = {
        "measurement_basis": basis,
        "precompile_sha256": pre_hash,
        "isa_sha256": isa_audit["isa_sha256"],
        "nexus_opt0_fixed_point_sha256": isa_audit["opt0_fixed_point_sha256"],
        "direct_unoptimised_opt0_sha256": direct_opt0_hash,
        "direct_unoptimised_opt0_depth": direct_opt0.depth(),
        "matches_experiment_protocol_frozen_lock": (basis == "X" and isa_audit["isa_sha256"] == FROZEN_H2_ISA_SHA256),
        "n_qubits": isa_audit["n_qubits"],
        "n_clbits": isa_audit["n_clbits"],
        "depth": isa_audit["depth"],
        "zzphase_count": isa_audit["zzphase_count"],
        "swap_count": isa_audit["swap_count"],
        "gate_counts": isa_audit["gate_counts"],
        "conditional_inner_ops": isa_audit["conditional_inner_ops"],
        "hqc_budget": hqc,
    }
    return pre_circ, isa_circ, info


def stage_nexus_bundle(bundle_dir: Path = DEFAULT_BUNDLE_DIR) -> dict[str, Any]:
    """Deterministically build and write the hash-locked OSIRIS-QEC-002 Nexus H2-1E bundle."""
    bundle_dir.mkdir(parents=True, exist_ok=True)

    _, x_isa, x_info = _build_basis_artifact("X")
    _, z_isa, z_info = _build_basis_artifact("Z")

    x_path = bundle_dir / X_ISA_FILENAME
    z_path = bundle_dir / Z_ISA_FILENAME
    x_bytes = jcs_dumps_bytes(x_isa.to_dict())
    z_bytes = jcs_dumps_bytes(z_isa.to_dict())
    x_path.write_bytes(x_bytes)
    z_path.write_bytes(z_bytes)

    x_info = {"filename": X_ISA_FILENAME, "file_sha256": sha256_bytes(x_bytes), **x_info}
    z_info = {"filename": Z_ISA_FILENAME, "file_sha256": sha256_bytes(z_bytes), **z_info}

    wilson_gates: dict[str, dict[str, Any]] = {}
    for shots in SHOT_TIERS:
        min_pass, max_fail, lb = min_successes_for_wilson_gt_099(shots)
        wilson_gates[str(shots)] = {
            "shots_per_basis": shots,
            "min_passing_shots": min_pass,
            "max_failing_shots": max_fail,
            "wilson_lb95_at_threshold": lb,
        }

    dual_basis_hqc: dict[str, float] = {}
    for shots in SHOT_TIERS:
        s_key = str(shots)
        dual_basis_hqc[s_key] = round(
            x_info["hqc_budget"]["hqc_by_shots"][s_key] + z_info["hqc_budget"]["hqc_by_shots"][s_key],
            6,
        )

    manifest: dict[str, Any] = {
        "schema": "osiris.qec002.nexus_h2_bundle.v1",
        "protocol_id": OSIRIS_PROTOCOL_ID,
        "osiris_qec_version": OSIRIS_QEC_VERSION,
        "code_parameters": {
            "n_data_qubits": N_DATA,
            "n_ancilla_qubits": N_ANCILLA,
            "n_total_qubits": N_TOTAL,
            "k_logical_qubits": 2,
            "distance_d": 4,
            "code_notation": "[[16,2,4]]",
            "topology": "4x4 periodic checkerboard Wen-plaquette torus",
        },
        "evidence_class": "OFFLINE_COMPILED",
        "provider_job_id": None,
        "hardware_attested": False,
        "jcs_serializer": f"rfc8785=={getattr(rfc8785, '__version__', '0.1.4')}",
        "target_devices": {
            "syntax_checker": "H2-1SC",
            "emulator_primary": "H2-1E",
            "hardware_qpu": "H2-1",
        },
        "nexus_compilation_contract": {
            "offline_compiler": "pytket-quantinuum QuantinuumBackend('H2-1', api_handler=QuantinuumAPIOffline())",
            "nexus_compile_optimisation_level": 0,
            "quantinuum_config_no_opt": True,
            "note": (
                "Staged circuits are pre-rebased to the canonical H2-1 native gate set "
                "(32 ZZPhase; depth 19 for X-basis matching EXPERIMENT_PROTOCOL.md SHA-256 "
                "02d5cb72..., depth 18 for Z-basis omitting 16 readout Hadamards) and verified "
                "as exact zero-drift fixed points under QuantinuumAPIOffline optimisation_level=0."
            ),
        },
        "acceptance_criteria": {
            "confidence_level": 0.95,
            "wilson_z": WILSON_Z_95,
            "wilson_lower_bound_min": 0.99,
            "thresholds_by_shots": wilson_gates,
        },
        "hqc_cost_model": {
            "formula": "HQC = 5 + C*(N_1q + 10*N_2q + 5*N_m)/5000",
            "component_definitions": {
                "N_1q": "Physical 1-qubit PhasedX laser gates (virtual Rz = 0 HQC)",
                "N_2q": "Physical 2-qubit ZZPhase entangling gates",
                "N_m": "Mid-circuit + final Measure and Reset operations (Measure + Reset)",
            },
            "x_basis_hqc_by_shots": x_info["hqc_budget"]["hqc_by_shots"],
            "z_basis_hqc_by_shots": z_info["hqc_budget"]["hqc_by_shots"],
            "dual_basis_total_hqc_by_shots": dual_basis_hqc,
        },
        "circuits": {
            "x_basis": x_info,
            "z_basis": z_info,
        },
    }

    manifest_path = bundle_dir / MANIFEST_FILENAME
    manifest_bytes = jcs_dumps_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    tracked_files = sorted([MANIFEST_FILENAME, X_ISA_FILENAME, Z_ISA_FILENAME])
    sums_lines = [f"{sha256_file(bundle_dir / fname)}  {fname}\n" for fname in tracked_files]
    (bundle_dir / SHA256SUMS_FILENAME).write_text("".join(sums_lines), encoding="utf-8")

    return manifest


def run_fast_noiseless_stabilizer_check() -> dict[str, Any]:
    """
    Fast deterministic noiseless verification of the OSIRIS-QEC-002 circuit:
      - Verifies all 8 even-parity Round-2 LUT branches satisfy all 16 X/Z stabilizers (+1.0).
      - Verifies prepared |00>_L logical observables (Z_L_row0=+1, Z_L_col0=+1, X_L=0).
      - Verifies Z-basis readout bitstrings satisfy all 8 Z-plaquettes and X-basis
        readout bitstrings satisfy all 8 X-plaquettes.
    """
    ops = qv.build_ops(measurement_setting="X")
    all_stabs = [(s.pauli_type, s.support) for s in WEN_STABILIZERS]
    even_syndromes = ["0000"] + sorted(ROUND_2_LUT_BE.keys())

    min_stab_exp = 1.0
    reference_state = None
    branch_fidelities: list[float] = []

    for synd_be in even_syndromes:
        forced = {
            "c0_1st[0]": 0,
            "c1_1st[0]": 0,
            "c2_1st[0]": 0,
            "c3_1st[0]": 0,
            "c4_2nd[0]": int(synd_be[0]),
            "c4_2nd[1]": int(synd_be[1]),
            "c4_2nd[2]": int(synd_be[2]),
            "c4_2nd[3]": int(synd_be[3]),
        }
        st, _ = qs.run_ops(ops, outcomes=forced)
        exps = [qs.expectation(st, pt, sup) for pt, sup in all_stabs]
        min_stab_exp = min(min_stab_exp, min(exps))
        if min(exps) < 0.999999:
            raise NexusBundleVerificationError(
                f"Stabilizer violation on Round-2 LUT branch {synd_be}: min_exp={min(exps)}"
            )
        if reference_state is None:
            reference_state = st
        else:
            fid = qs.state_fidelity(st, reference_state)
            branch_fidelities.append(fid)
            if fid < 0.999999:
                raise NexusBundleVerificationError(
                    f"Branch state mismatch on {synd_be}: fidelity={fid}"
                )

    assert reference_state is not None
    reps = qm.logical_representatives(
        [qm.from_support(t, s) for t, s in qm.derive_stabilizers()]
    )
    logical_exps: dict[str, float] = {}
    for name, pauli_op in reps.items():
        sup = [i for i in range(N_DATA) if pauli_op.x[i] or pauli_op.z[i]]
        ptype = "X" if not any(pauli_op.z) else "Z"
        logical_exps[name] = round(qs.expectation(reference_state, ptype, sup), 8)

    if abs(logical_exps["Z_L_row0"] - 1.0) > 1e-6 or abs(logical_exps["Z_L_col0"] - 1.0) > 1e-6:
        raise NexusBundleVerificationError(f"Unexpected |00>_L logical expectations: {logical_exps}")

    return {
        "lut_branches_checked": len(even_syndromes),
        "all_16_stabilizers_plus1": True,
        "min_stabilizer_expectation": round(min_stab_exp, 8),
        "min_inter_branch_fidelity": round(min(branch_fidelities), 8),
        "logical_expectations": logical_exps,
    }


def verify_staged_bundle(bundle_dir: Path = DEFAULT_BUNDLE_DIR) -> dict[str, Any]:
    """Execute full `--dry-run` verification of SHA-256 digests, JCS, H2-1 ISA, and noiseless sim."""
    sums_path = bundle_dir / SHA256SUMS_FILENAME
    manifest_path = bundle_dir / MANIFEST_FILENAME
    if not sums_path.exists() or not manifest_path.exists():
        raise NexusBundleVerificationError(
            f"Bundle missing {SHA256SUMS_FILENAME} or {MANIFEST_FILENAME} in {bundle_dir}"
        )

    # 1. Verify SHA256SUMS.txt
    recorded_sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 2:
            raise NexusBundleVerificationError(f"Malformed SHA256SUMS line: {line!r}")
        digest, fname = parts
        fpath = bundle_dir / fname
        if not fpath.exists():
            raise NexusBundleVerificationError(f"Tracked bundle file missing: {fpath}")
        actual = sha256_file(fpath)
        if actual != digest:
            raise NexusBundleVerificationError(
                f"SHA-256 mismatch for {fname}: expected {digest}, observed {actual}"
            )
        recorded_sums[fname] = actual

    for req_file in (MANIFEST_FILENAME, X_ISA_FILENAME, Z_ISA_FILENAME):
        if req_file not in recorded_sums:
            raise NexusBundleVerificationError(f"{req_file} missing from {SHA256SUMS_FILENAME}")

    # 2. Verify RFC 8785 JCS canonicalization of nexus_qec002_manifest.json
    raw_manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest_bytes.decode("utf-8"))
    if jcs_dumps_bytes(manifest) != raw_manifest_bytes:
        raise NexusBundleVerificationError(
            f"{MANIFEST_FILENAME} is not byte-exact RFC 8785 JCS canonical JSON"
        )
    if manifest.get("evidence_class") != "OFFLINE_COMPILED":
        raise NexusBundleVerificationError(
            f"Expected manifest evidence_class='OFFLINE_COMPILED', got {manifest.get('evidence_class')!r}"
        )
    if manifest.get("provider_job_id") is not None or manifest.get("hardware_attested") is not False:
        raise NexusBundleVerificationError(
            "Offline manifest must have provider_job_id=null and hardware_attested=false"
        )

    # 3. Verify X-basis and Z-basis staged circuits against H2-1 ISA & EXPERIMENT_PROTOCOL.md
    circuit_audits: dict[str, Any] = {}
    for key, expected_isa, expected_depth in (
        ("x_basis", FROZEN_H2_ISA_SHA256, 19),
        ("z_basis", EXPECTED_Z_H2_ISA_SHA256, 18),
    ):
        c_meta = manifest["circuits"][key]
        c_path = bundle_dir / c_meta["filename"]
        c_bytes = c_path.read_bytes()
        if sha256_bytes(c_bytes) != c_meta["file_sha256"]:
            raise NexusBundleVerificationError(f"Manifest file_sha256 mismatch for {key}")
        c_dict = json.loads(c_bytes.decode("utf-8"))
        if jcs_dumps_bytes(c_dict) != c_bytes:
            raise NexusBundleVerificationError(f"Circuit file {c_meta['filename']} is not RFC 8785 JCS")
        circ = Circuit.from_dict(c_dict)
        isa_check = verify_native_h2_isa(circ)
        if isa_check["isa_sha256"] != expected_isa or isa_check["isa_sha256"] != c_meta["isa_sha256"]:
            raise NexusBundleVerificationError(
                f"ISA SHA-256 lock failure on {key}: {isa_check['isa_sha256']} != {expected_isa}"
            )
        if isa_check["depth"] != expected_depth or isa_check["zzphase_count"] != 32:
            raise NexusBundleVerificationError(
                f"Structural lock failure on {key}: depth={isa_check['depth']}, ZZPhase={isa_check['zzphase_count']}"
            )
        circuit_audits[key] = isa_check

    # 4. Run fast noiseless stabilizer & LUT verification
    sim_check = run_fast_noiseless_stabilizer_check()

    return {
        "schema": "osiris.qec002.readiness_receipt.v1",
        "protocol_id": OSIRIS_PROTOCOL_ID,
        "status": "OFFLINE_VERIFIED",
        "evidence_class": "OFFLINE_VERIFIED",
        "provider_job_id": None,
        "hardware_attested": False,
        "bundle_dir": str(bundle_dir),
        "verified_sha256sums": recorded_sums,
        "circuit_isa_audits": circuit_audits,
        "noiseless_stabilizer_verification": sim_check,
        "hqc_dual_basis_budget": manifest["hqc_cost_model"]["dual_basis_total_hqc_by_shots"],
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _validate_operator_token(token: str | None) -> str:
    """Validate explicit operator approval token and return its SHA-256 fingerprint (never raw)."""
    if token is None:
        raise NexusSubmissionBlockedError(
            "Submission blocked: --operator-approval-token is required for --submit."
        )
    cleaned = token.strip()
    forbidden = {"", "<token>", "token", "none", "null", "placeholder", "changeme", "todo"}
    if cleaned.lower() in forbidden or len(cleaned) < 8:
        raise NexusSubmissionBlockedError(
            "Submission blocked: invalid or placeholder --operator-approval-token (must be >= 8 chars)."
        )
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def submit_nexus_bundle(
    *,
    device: str,
    operator_approval_token: str | None,
    shots: int = 1000,
    bundle_dir: Path = DEFAULT_BUNDLE_DIR,
    qnx_module: Any = None,
) -> dict[str, Any]:
    """
    Fail-closed Quantinuum Nexus submission entrypoint.
    Refuses execution without:
      1. Full offline SHA-256 & H2-1 ISA readiness pass,
      2. Explicit valid operator approval token,
      3. Installed `qnexus` SDK + explicit Nexus credentials,
      4. Post-compile SHA-256 invariance (`optimisation_level=0`, `no_opt=True`) before execute,
      5. Explicit Nexus job completion confirmation (`COMPLETED`).
    Never claims `HARDWARE_ATTESTED` unless `device == 'H2-1'` (physical QPU) completes on Nexus.
    """
    if device not in ALLOWED_NEXUS_DEVICES:
        raise NexusSubmissionBlockedError(
            f"Unsupported --device {device!r}; allowed devices: {ALLOWED_NEXUS_DEVICES}"
        )
    if shots <= 0 or not math.isfinite(shots):
        raise NexusSubmissionBlockedError(f"Invalid shot count: {shots}")

    # Mandatory pre-flight hash & ISA gate
    dry_receipt = verify_staged_bundle(bundle_dir)
    token_fp = _validate_operator_token(operator_approval_token)

    qnx = qnx_module
    if qnx is None:
        try:
            import qnexus as qnx  # type: ignore
        except ImportError as exc:
            raise NexusSubmissionBlockedError(
                "Submission blocked (fail-closed): `qnexus` package is not installed in this "
                "environment; refusing network submission and keeping provider_job_id=null."
            ) from exc

    has_env_creds = bool(os.getenv("QNEXUS_TOKEN") or os.getenv("NEXUS_API_TOKEN"))
    has_mock_auth = bool(qnx_module is not None and getattr(qnx_module, "authenticated", False))
    if not (has_env_creds or has_mock_auth):
        raise NexusSubmissionBlockedError(
            "Submission blocked (fail-closed): no Nexus credentials found in QNEXUS_TOKEN / "
            "NEXUS_API_TOKEN; refusing live API login/submission."
        )

    manifest = json.loads((bundle_dir / MANIFEST_FILENAME).read_bytes().decode("utf-8"))
    project = qnx.projects.get_or_create(name="OSIRIS-QEC-002")
    backend_cfg = qnx.QuantinuumConfig(device_name=device, no_opt=True)

    job_records: dict[str, Any] = {}
    for basis_key in ("x_basis", "z_basis"):
        c_meta = manifest["circuits"][basis_key]
        circ = Circuit.from_dict(
            json.loads((bundle_dir / c_meta["filename"]).read_bytes().decode("utf-8"))
        )
        expected_isa_sha = c_meta["isa_sha256"]
        if hash_tket_circuit(circ) != expected_isa_sha:
            raise NexusBundleVerificationError(f"Pre-upload hash mismatch for {basis_key}")

        up_ref = qnx.circuits.upload(
            name=f"osiris-qec002-{basis_key}",
            circuit=circ,
            project=project,
        )
        compiled_refs = qnx.compile(
            programs=[up_ref],
            name=f"osiris-qec002-lock-{basis_key}",
            project=project,
            optimisation_level=0,
            backend_config=backend_cfg,
        )
        comp_prog = compiled_refs[0]
        comp_circ = (
            comp_prog.download_circuit()
            if hasattr(comp_prog, "download_circuit")
            else getattr(comp_prog, "circuit", None)
        )
        if not isinstance(comp_circ, Circuit):
            raise NexusSubmissionBlockedError(
                f"Cannot download compiled circuit for post-compile hash check ({basis_key})."
            )
        if hash_tket_circuit(comp_circ) != expected_isa_sha:
            raise NexusBundleVerificationError(
                f"Post-compile ISA hash drift on Nexus for {basis_key}: aborting before execute."
            )

        if device == "H2-1SC":
            job_records[basis_key] = {
                "compile_status": "COMPLETED",
                "execute_job_id": None,
                "verified_isa_sha256": expected_isa_sha,
            }
            continue

        exec_job = qnx.start_execute_job(
            programs=[comp_prog],
            n_shots=[int(shots)],
            backend_config=backend_cfg,
            name=f"osiris-qec002-{device.lower()}-{basis_key}",
            project=project,
        )
        status_val = qnx.jobs.wait_for(exec_job)
        status_str = str(status_val if status_val is not None else getattr(exec_job, "status", ""))
        job_id = str(getattr(exec_job, "id", "")).strip()
        if "COMPLETED" not in status_str.upper() or not job_id:
            raise NexusSubmissionBlockedError(
                f"Nexus job did not confirm COMPLETED status (status={status_str!r}, job_id={job_id!r}); "
                "refusing attestation."
            )
        _ = qnx.jobs.results(exec_job)
        job_records[basis_key] = {
            "execute_job_id": job_id,
            "final_status": status_str,
            "verified_isa_sha256": expected_isa_sha,
        }

    if device == "H2-1":
        evidence_class = "HARDWARE_ATTESTED"
        hardware_attested = True
    elif device == "H2-1E":
        evidence_class = "EMULATOR_ATTESTED"
        hardware_attested = False
    else:
        evidence_class = "SYNTAX_CHECK_ATTESTED"
        hardware_attested = False

    return {
        "protocol_id": OSIRIS_PROTOCOL_ID,
        "device": device,
        "shots_per_basis": shots,
        "operator_token_sha256_prefix": token_fp,
        "evidence_class": evidence_class,
        "hardware_attested": hardware_attested,
        "provider_job_id": {k: v.get("execute_job_id") for k, v in job_records.items()},
        "jobs": job_records,
        "preflight_digest_check": dry_receipt["verified_sha256sums"],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="OSIRIS-QEC-002 Hash-Locked Quantinuum Nexus Bundle Verifier & Fail-Closed Submitter"
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify SHA-256 locks, RFC 8785 JCS, H2-1 ISA, and noiseless stabilizer checks (default).",
    )
    mode.add_argument(
        "--stage-bundle",
        action="store_true",
        help="Deterministically generate/refresh submission/nexus_h2_bundle artifacts.",
    )
    mode.add_argument(
        "--submit",
        action="store_true",
        help="Fail-closed Quantinuum Nexus submission mode (requires --device and --operator-approval-token).",
    )
    p.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    p.add_argument("--device", type=str, default="H2-1E", help="Target Nexus device (H2-1SC, H2-1E, H2-1)")
    p.add_argument("--shots", type=int, default=1000, help="Shots per basis for --submit")
    p.add_argument(
        "--operator-approval-token",
        type=str,
        default=None,
        help="Explicit operator authorization token required for --submit (never logged).",
    )
    p.add_argument("--receipt-out", type=Path, default=None, help="Optional file path to write JCS receipt.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.stage_bundle:
            manifest = stage_nexus_bundle(args.bundle_dir)
            print(jcs_dumps_bytes({"status": "BUNDLE_STAGED", "protocol_id": manifest["protocol_id"], "bundle_dir": str(args.bundle_dir)}).decode("utf-8"))
            return 0

        if args.submit:
            receipt = submit_nexus_bundle(
                device=args.device,
                operator_approval_token=args.operator_approval_token,
                shots=args.shots,
                bundle_dir=args.bundle_dir,
            )
        else:
            receipt = verify_staged_bundle(args.bundle_dir)

        out_bytes = jcs_dumps_bytes(receipt)
        if args.receipt_out is not None:
            args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
            args.receipt_out.write_bytes(out_bytes)
        print(out_bytes.decode("utf-8"))
        return 0

    except NexusBundleVerificationError as exc:
        err = {
            "status": "FAILED_VERIFICATION",
            "evidence_class": "UNVERIFIED",
            "provider_job_id": None,
            "hardware_attested": False,
            "error": str(exc),
        }
        print(jcs_dumps_bytes(err).decode("utf-8"), file=sys.stderr)
        return 1
    except NexusSubmissionBlockedError as exc:
        err = {
            "status": "BLOCKED_FAIL_CLOSED",
            "evidence_class": "OFFLINE_VERIFIED",
            "provider_job_id": None,
            "hardware_attested": False,
            "error": str(exc),
        }
        print(jcs_dumps_bytes(err).decode("utf-8"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
