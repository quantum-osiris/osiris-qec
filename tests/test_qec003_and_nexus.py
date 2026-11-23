"""
Comprehensive deterministic verification suite for:
  - Deliverable A: OSIRIS-QEC-002 Hash-Locked Quantinuum Nexus (H2-1E) Staging Bundle & CLI
  - Deliverable B: OSIRIS-QEC-003 Full X+Z Toroidal Memory Cycles & Checkerboard Twist Defects
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rfc8785
from pytket import Circuit

from osiris_qec.qec003_memory_twists import (
    CSSBpOsdDecoder,
    compile_memory_rounds_h2_metrics,
    derive_css_parity_matrices,
    run_depolarizing_memory_benchmark,
    run_weight1_postprep_circuit_sweep,
    run_weight2_postprep_fault_sweep,
    verify_twist_anyon_braiding_and_h2_compile,
    verify_twist_defect_algebra,
)
from submission.run_nexus_qec002 import (
    DEFAULT_BUNDLE_DIR,
    EXPECTED_Z_H2_ISA_SHA256,
    MANIFEST_FILENAME,
    X_ISA_FILENAME,
    Z_ISA_FILENAME,
    NexusBundleVerificationError,
    NexusSubmissionBlockedError,
    compute_hqc_metrics,
    submit_nexus_bundle,
    verify_native_h2_isa,
    verify_staged_bundle,
)
from submission.run_nexus_qec002 import (
    main as nexus_cli_main,
)
from wen_plaquette_pass import FROZEN_H2_ISA_SHA256, FROZEN_PRECOMPILE_SHA256

ROOT = Path(__file__).resolve().parent.parent
QEC003_REPORT_PATH = ROOT / "reports" / "qec003_verification_report.json"


# ---------------------------------------------------------------------------
# Module-scoped cached fixtures so multi-test assertions stay fast (< 15s)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_decoder() -> CSSBpOsdDecoder:
    return CSSBpOsdDecoder()


@pytest.fixture(scope="module")
def weight1_sweep_result(shared_decoder: CSSBpOsdDecoder) -> dict[str, Any]:
    return run_weight1_postprep_circuit_sweep(shared_decoder)


@pytest.fixture(scope="module")
def weight2_sweep_result(shared_decoder: CSSBpOsdDecoder) -> dict[str, Any]:
    return run_weight2_postprep_fault_sweep(shared_decoder)


@pytest.fixture(scope="module")
def memory_h2_metrics() -> dict[str, Any]:
    return compile_memory_rounds_h2_metrics((1, 2, 3))


@pytest.fixture(scope="module")
def twist_algebra_result() -> dict[str, Any]:
    return verify_twist_defect_algebra()


@pytest.fixture(scope="module")
def twist_braiding_result() -> dict[str, Any]:
    return verify_twist_anyon_braiding_and_h2_compile()


# ===========================================================================
# 1. Deliverable A — OSIRIS-QEC-002 Nexus H2-1E Bundle & Fail-Closed CLI
# ===========================================================================


def test_nexus_bundle_manifest_is_strict_rfc8785_jcs_and_offline_compiled() -> None:
    manifest_path = DEFAULT_BUNDLE_DIR / MANIFEST_FILENAME
    raw_bytes = manifest_path.read_bytes()
    parsed = json.loads(raw_bytes.decode("utf-8"))

    assert rfc8785.dumps(parsed) == raw_bytes
    assert parsed["protocol_id"] == "OSIRIS-QEC-002"
    assert parsed["evidence_class"] == "OFFLINE_COMPILED"
    assert parsed["provider_job_id"] is None
    assert parsed["hardware_attested"] is False


def test_nexus_bundle_sha256sums_and_frozen_protocol_match() -> None:
    receipt = verify_staged_bundle(DEFAULT_BUNDLE_DIR)
    assert receipt["status"] == "OFFLINE_VERIFIED"
    assert receipt["evidence_class"] == "OFFLINE_VERIFIED"
    assert receipt["provider_job_id"] is None
    assert receipt["hardware_attested"] is False

    manifest = json.loads((DEFAULT_BUNDLE_DIR / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["circuits"]["x_basis"]["precompile_sha256"] == FROZEN_PRECOMPILE_SHA256
    assert manifest["circuits"]["x_basis"]["isa_sha256"] == FROZEN_H2_ISA_SHA256
    assert manifest["circuits"]["z_basis"]["isa_sha256"] == EXPECTED_Z_H2_ISA_SHA256
    assert receipt["verified_sha256sums"][X_ISA_FILENAME] == FROZEN_H2_ISA_SHA256
    assert receipt["verified_sha256sums"][Z_ISA_FILENAME] == EXPECTED_Z_H2_ISA_SHA256


def test_nexus_bundle_x_and_z_circuits_h2_isa_and_opt0_fixed_point() -> None:
    for fname, exp_depth, exp_phasedx in (
        (X_ISA_FILENAME, 19, 72),
        (Z_ISA_FILENAME, 18, 56),
    ):
        circ = Circuit.from_dict(
            json.loads((DEFAULT_BUNDLE_DIR / fname).read_text(encoding="utf-8"))
        )
        audit = verify_native_h2_isa(circ)
        assert audit["native_isa_compliant"] is True
        assert audit["swap_count"] == 0
        assert audit["n_qubits"] == 20
        assert audit["n_clbits"] == 28
        assert audit["depth"] == exp_depth
        assert audit["zzphase_count"] == 32
        assert audit["gate_counts"]["PhasedX"] == exp_phasedx
        assert audit["gate_counts"]["Measure"] == 24
        assert audit["gate_counts"]["Reset"] == 8
        assert audit["gate_counts"]["Conditional"] == 20
        assert audit["isa_sha256"] == audit["opt0_fixed_point_sha256"]


def test_nexus_bundle_hqc_cost_formula_exact_512_1000_2000() -> None:
    x_circ = Circuit.from_dict(
        json.loads((DEFAULT_BUNDLE_DIR / X_ISA_FILENAME).read_text(encoding="utf-8"))
    )
    z_circ = Circuit.from_dict(
        json.loads((DEFAULT_BUNDLE_DIR / Z_ISA_FILENAME).read_text(encoding="utf-8"))
    )
    x_hqc = compute_hqc_metrics(x_circ, (512, 1000, 2000))
    z_hqc = compute_hqc_metrics(z_circ, (512, 1000, 2000))

    # X-basis: N_1q=72, N_2q=32, N_m=24+8=32 => 72 + 320 + 160 = 552 weighted units/shot
    assert x_hqc["weighted_gate_units_per_shot"] == 552
    assert x_hqc["hqc_by_shots"] == {"512": 61.5248, "1000": 115.4, "2000": 225.8}

    # Z-basis: N_1q=56, N_2q=32, N_m=32 => 56 + 320 + 160 = 536 weighted units/shot
    assert z_hqc["weighted_gate_units_per_shot"] == 536
    assert z_hqc["hqc_by_shots"] == {"512": 59.8864, "1000": 112.2, "2000": 219.4}


def test_nexus_bundle_wilson_95_gt_099_acceptance_thresholds() -> None:
    manifest = json.loads((DEFAULT_BUNDLE_DIR / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    gates = manifest["acceptance_criteria"]["thresholds_by_shots"]
    assert gates["512"]["min_passing_shots"] == 512 and gates["512"]["max_failing_shots"] == 0
    assert gates["1000"]["min_passing_shots"] == 997 and gates["1000"]["max_failing_shots"] == 3
    assert gates["2000"]["min_passing_shots"] == 1989 and gates["2000"]["max_failing_shots"] == 11


def test_run_nexus_qec002_cli_dry_run_emits_offline_verified_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt_file = tmp_path / "receipt.json"
    rc = nexus_cli_main(["--dry-run", "--receipt-out", str(receipt_file)])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["status"] == "OFFLINE_VERIFIED"
    assert parsed["evidence_class"] == "OFFLINE_VERIFIED"
    assert parsed["provider_job_id"] is None
    assert receipt_file.read_bytes() == rfc8785.dumps(parsed)


def test_run_nexus_qec002_tampered_bundle_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cloned = tmp_path / "bundle_tampered"
    shutil.copytree(DEFAULT_BUNDLE_DIR, cloned)
    # Corrupt 1 byte in staged Z-basis circuit JSON
    z_path = cloned / Z_ISA_FILENAME
    z_path.write_text(z_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(NexusBundleVerificationError, match="SHA-256 mismatch"):
        verify_staged_bundle(cloned)

    rc = nexus_cli_main(["--dry-run", "--bundle-dir", str(cloned)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "FAILED_VERIFICATION" in err


def test_run_nexus_qec002_submit_blocks_without_operator_token_or_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("QNEXUS_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_API_TOKEN", raising=False)

    # 1. Missing operator approval token -> fail-closed exit 2
    rc_no_tok = nexus_cli_main(["--submit", "--device", "H2-1E"])
    err_no_tok = json.loads(capsys.readouterr().err)
    assert rc_no_tok == 2
    assert err_no_tok["status"] == "BLOCKED_FAIL_CLOSED"
    assert err_no_tok["provider_job_id"] is None
    assert err_no_tok["hardware_attested"] is False

    # 2. Valid token, but no qnexus/credentials -> fail-closed exit 2
    rc_no_cred = nexus_cli_main(
        ["--submit", "--device", "H2-1E", "--operator-approval-token", "OSIRIS-APPROVAL-20261123"]
    )
    err_no_cred = json.loads(capsys.readouterr().err)
    assert rc_no_cred == 2
    assert err_no_cred["status"] == "BLOCKED_FAIL_CLOSED"
    assert err_no_cred["provider_job_id"] is None
    assert err_no_cred["hardware_attested"] is False


@dataclass
class _MockCompiledProgram:
    circuit: Circuit

    def download_circuit(self) -> Circuit:
        return self.circuit


@dataclass
class _MockExecJob:
    id: str
    status: str = "COMPLETED"


class _MockQNexus:
    def __init__(self, *, final_status: str = "COMPLETED", drift_compile: bool = False) -> None:
        self.authenticated = True
        self.final_status = final_status
        self.drift_compile = drift_compile
        self.execute_calls: list[str] = []

        outer = self

        class _Projects:
            @staticmethod
            def get_or_create(name: str) -> dict[str, str]:
                return {"name": name}

        class _Circuits:
            @staticmethod
            def upload(name: str, circuit: Circuit, project: Any) -> _MockCompiledProgram:
                return _MockCompiledProgram(circuit=circuit.copy())

        class _Jobs:
            @staticmethod
            def wait_for(job: _MockExecJob) -> str:
                return outer.final_status

            @staticmethod
            def results(job: _MockExecJob) -> list[dict[str, Any]]:
                return [{"c5_end_bitstrings": ["0" * 16] * 16}]

        self.projects = _Projects()
        self.circuits = _Circuits()
        self.jobs = _Jobs()

    @staticmethod
    def QuantinuumConfig(device_name: str, no_opt: bool = True) -> dict[str, Any]:
        return {"device_name": device_name, "no_opt": no_opt}

    def compile(
        self,
        programs: list[_MockCompiledProgram],
        name: str,
        project: Any,
        optimisation_level: int,
        backend_config: dict[str, Any],
    ) -> list[_MockCompiledProgram]:
        assert optimisation_level == 0
        assert backend_config["no_opt"] is True
        c = programs[0].circuit.copy()
        if self.drift_compile:
            c.Rz(0.25, c.qubits[0])
        return [_MockCompiledProgram(circuit=c)]

    def start_execute_job(
        self,
        programs: list[_MockCompiledProgram],
        n_shots: list[int],
        backend_config: dict[str, Any],
        name: str,
        project: Any,
    ) -> _MockExecJob:
        self.execute_calls.append(name)
        return _MockExecJob(id=f"job-{len(self.execute_calls)}", status=self.final_status)


def test_run_nexus_qec002_submit_h2_1e_never_claims_hardware_attested() -> None:
    mock_qnx = _MockQNexus(final_status="COMPLETED")
    res = submit_nexus_bundle(
        device="H2-1E",
        operator_approval_token="APPROVAL-TOKEN-H21E-OK",
        shots=512,
        qnx_module=mock_qnx,
    )
    assert res["evidence_class"] == "EMULATOR_ATTESTED"
    assert res["hardware_attested"] is False
    assert len(mock_qnx.execute_calls) == 2


def test_run_nexus_qec002_submit_aborts_on_incomplete_or_drifted_nexus_job() -> None:
    # 1. Incomplete job status -> refuses attestation
    mock_queued = _MockQNexus(final_status="QUEUED")
    with pytest.raises(NexusSubmissionBlockedError, match="did not confirm COMPLETED"):
        submit_nexus_bundle(
            device="H2-1",
            operator_approval_token="APPROVAL-TOKEN-H21-OK",
            shots=512,
            qnx_module=mock_queued,
        )

    # 2. Post-compile hash drift -> aborts BEFORE start_execute_job
    mock_drift = _MockQNexus(drift_compile=True)
    with pytest.raises(NexusBundleVerificationError, match="Post-compile ISA hash drift"):
        submit_nexus_bundle(
            device="H2-1E",
            operator_approval_token="APPROVAL-TOKEN-H21E-OK",
            shots=512,
            qnx_module=mock_drift,
        )
    assert mock_drift.execute_calls == []


# ===========================================================================
# 2. Deliverable B (Part 1) — OSIRIS-QEC-003 Full X+Z Toroidal Memory Cycles
# ===========================================================================


def test_qec003_css_parity_matrices_rank_7_and_global_torus_parity(
    shared_decoder: CSSBpOsdDecoder,
) -> None:
    hx, hz, stabs = derive_css_parity_matrices()
    assert hx.shape == (8, 16)
    assert hz.shape == (8, 16)
    assert len(stabs) == 16
    assert shared_decoder.rank_hx == 7
    assert shared_decoder.rank_hz == 7
    # Global torus parity constraints: product of all 8 X-plaquettes = I, all 8 Z-plaquettes = I
    assert np.all((hx.sum(axis=0) % 2) == 0)
    assert np.all((hz.sum(axis=0) % 2) == 0)


def test_qec003_bp_osd_rejects_odd_parity_torus_syndrome(
    shared_decoder: CSSBpOsdDecoder,
) -> None:
    odd_syndrome = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
    with pytest.raises(ValueError, match="Global torus parity violation"):
        shared_decoder.decode_xz(odd_syndrome, np.zeros(8, dtype=np.uint8))


def test_qec003_weight1_postprep_exhaustive_48_of_48_circuit_recovery(
    weight1_sweep_result: dict[str, Any],
) -> None:
    assert weight1_sweep_result["total_faults"] == 48
    # OSIRIS-QEC-002 blind spot: 0/16 X detected, 0/48 post-prep faults logically preserved
    assert weight1_sweep_result["by_pauli"]["X"]["qec002_detected"] == 0
    assert weight1_sweep_result["by_pauli"]["Y"]["qec002_detected"] == 16
    assert weight1_sweep_result["by_pauli"]["Z"]["qec002_detected"] == 16
    assert weight1_sweep_result["qec002_detected_count"] == 32
    assert weight1_sweep_result["qec002_logically_preserved_count"] == 0

    # OSIRIS-QEC-003 full X+Z memory + BP+OSD: 48/48 detected & 48/48 uniquely corrected!
    assert weight1_sweep_result["qec003_detected_count"] == 48
    assert weight1_sweep_result["qec003_uniquely_corrected_count"] == 48
    assert weight1_sweep_result["qec003_logical_error_rate"] == 0.0
    for p_label in ("X", "Y", "Z"):
        assert weight1_sweep_result["by_pauli"][p_label]["qec003_corrected"] == 16


def test_qec003_weight2_postprep_exhaustive_1080_of_1080_detection_and_coset_taxonomy(
    weight2_sweep_result: dict[str, Any],
) -> None:
    assert weight2_sweep_result["total_weight2_faults"] == 1080
    assert weight2_sweep_result["detected_count"] == 1080
    assert weight2_sweep_result["detection_rate"] == 1.0

    # All 240 mixed (X_i, Z_j) two-qubit faults decompose into weight-1 X + weight-1 Z => 100% corrected
    xz_cls = weight2_sweep_result["by_pauli_pair_class"]["XZ_or_ZX"]
    assert xz_cls["total"] == 240
    assert xz_cls["logically_preserved"] == 240
    assert xz_cls["logical_coset_error"] == 0

    # Exact partition across all 1,080 faults on [[16,2,4]]: 672 preserved (560 exact + 112 stab-deg), 408 coset ties
    assert weight2_sweep_result["exact_inverse_count"] == 560
    assert weight2_sweep_result["stabilizer_degenerate_preserved_count"] == 112
    assert weight2_sweep_result["logically_preserved_count"] == 672
    assert weight2_sweep_result["logical_coset_tie_error_count"] == 408


def test_qec003_depolarizing_memory_monte_carlo_sub_threshold_suppression(
    shared_decoder: CSSBpOsdDecoder,
) -> None:
    bench = run_depolarizing_memory_benchmark(
        error_rates=(0.001, 0.005),
        rounds_list=(1, 2),
        n_shots=2000,
        seed=20261123,
        decoder=shared_decoder,
    )
    rows = {(r["physical_error_rate_p"], r["rounds"]): r for r in bench["results"]}
    # At p = 0.001 and p = 0.005, [[16,2,4]] BP+OSD logical error rate is strictly below bare 2-qubit error rate
    assert rows[(0.001, 1)]["logical_error_rate"] < rows[(0.001, 1)]["bare_2q_register_error_rate"]
    assert rows[(0.001, 2)]["logical_error_rate"] < rows[(0.001, 2)]["bare_2q_register_error_rate"]
    assert rows[(0.005, 1)]["logical_error_rate"] < rows[(0.005, 1)]["bare_2q_register_error_rate"]


def test_qec003_memory_rounds_r1_r2_r3_h2_isa_zero_swaps_and_linear_scaling(
    memory_h2_metrics: dict[str, Any],
) -> None:
    r1, r2, r3 = memory_h2_metrics["R=1"], memory_h2_metrics["R=2"], memory_h2_metrics["R=3"]
    for item, exp_zz, exp_meas, exp_reset, exp_clbits in (
        (r1, 96, 40, 24, 40),
        (r2, 160, 56, 40, 56),
        (r3, 224, 72, 56, 72),
    ):
        assert item["n_qubits"] == 20
        assert item["n_clbits"] == exp_clbits
        assert item["swap_count"] == 0
        assert item["zzphase_count"] == exp_zz
        assert item["gate_counts"]["Measure"] == exp_meas
        assert item["gate_counts"]["Reset"] == exp_reset
        assert item["isa_sha256"] == item["nexus_opt0_fixed_point_sha256"]


# ===========================================================================
# 3. Deliverable B (Part 2) — Checkerboard Twist Defects & e <-> m Braiding
# ===========================================================================


def test_twist_defect_all_105_pairs_commute_and_unified_fermion_parity(
    twist_algebra_result: dict[str, Any],
) -> None:
    assert twist_algebra_result["n_generators_total"] == 15
    assert twist_algebra_result["n_weight5_twist_stabilizers"] == 2
    assert twist_algebra_result["n_mixed_branch_cut_stabilizers"] == 1
    assert twist_algebra_result["pairwise_checks_count"] == 105
    assert twist_algebra_result["all_pairs_commute"] is True
    assert twist_algebra_result["anticommuting_pairs"] == []
    assert twist_algebra_result["product_of_all_15_generators_equals_plus_identity"] is True


def test_twist_defect_exact_16_2_4_code_parameters_by_exhaustive_pauli_search(
    twist_algebra_result: dict[str, Any],
) -> None:
    assert twist_algebra_result["symplectic_gf2_rank"] == 14
    assert twist_algebra_result["k_logical_qubits"] == 2
    counts = twist_algebra_result["nontrivial_logical_counts_by_max_weight"]
    assert counts["le_1"] == 0
    assert counts["le_2"] == 0
    assert counts["le_3"] == 0
    assert counts["eq_4"] == 44
    assert twist_algebra_result["exact_code_distance_d"] == 4
    assert twist_algebra_result["code_notation"] == "[[16,2,4]]"


def test_twist_defect_deterministic_vacuum_preparation_all_branches(
    twist_braiding_result: dict[str, Any],
) -> None:
    vac = twist_braiding_result["vacuum_preparation"]
    assert sorted(vac["reachable_prep_syndromes"]) == ["000", "011", "101", "110"]
    assert sorted(vac["unreachable_odd_parity_syndromes"]) == ["001", "010", "100", "111"]
    assert vac["deterministic_codespace_fidelity_100pct"] is True
    assert vac["min_stabilizer_expectation_across_all_branches"] > 0.999999


def test_twist_defect_explicit_e_to_m_anyon_transmutation_and_twist_fusion(
    twist_braiding_result: dict[str, Any],
) -> None:
    assert twist_braiding_result["e_to_m_transmutation_verified"] is True
    traj = twist_braiding_result["anyon_transport_trajectory"]

    # Step 0: vacuum -> 0 excitations
    assert traj[0]["excited_stabilizers"] == []
    # Step 1 (Z2): 2 electric e-anyons above cut, 0 magnetic m-anyons
    assert sorted(traj[1]["electric_e_anyons"]) == ["P_14_X", "P_1_X"]
    assert traj[1]["magnetic_m_anyons"] == []
    # Step 2 (Z2.Z6): enters dislocation branch cut B1
    assert sorted(traj[2]["excited_stabilizers"]) == ["B1_branch_cut", "P_14_X"]
    # Step 3 (Z2.Z6.X10): emerges across cut as 1 electric e-anyon + 1 magnetic m-anyon!
    assert traj[3]["electric_e_anyons"] == ["P_14_X"]
    assert traj[3]["magnetic_m_anyons"] == ["P_10_Z"]
    assert traj[3]["twist_or_branch_excitations"] == []
    # Step 4 (Z2.Z6.X10.X11): transmuted m-anyon fuses into weight-5 twist defect T2
    assert traj[4]["electric_e_anyons"] == ["P_14_X"]
    assert traj[4]["magnetic_m_anyons"] == []
    assert traj[4]["twist_or_branch_excitations"] == ["T2_twist_right"]


def test_twist_defect_circuit_h2_isa_zero_swaps_and_hqc_budget(
    twist_braiding_result: dict[str, Any],
) -> None:
    h2 = twist_braiding_result["h2_isa_compilation"]
    assert h2["n_qubits"] == 20
    assert h2["swap_count"] == 0
    assert h2["zzphase_count"] > 0
    assert h2["isa_sha256"] == h2["nexus_opt0_fixed_point_sha256"]
    assert set(h2["hqc_budget"]["hqc_by_shots"].keys()) == {"512", "1000", "2000"}


def test_qec003_verification_report_rfc8785_jcs_and_provenance_labels() -> None:
    assert QEC003_REPORT_PATH.exists()
    raw = QEC003_REPORT_PATH.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    assert rfc8785.dumps(parsed) == raw
    assert parsed["protocol_id"] == "OSIRIS-QEC-003"
    assert parsed["evidence_class"] == "SIMULATED"
    assert parsed["compilation_evidence_class"] == "OFFLINE_COMPILED"
    assert parsed["provider_job_id"] is None
    assert parsed["hardware_attested"] is False
