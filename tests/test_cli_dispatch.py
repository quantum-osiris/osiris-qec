"""
v1.1.0 CLI Dispatch, Argparse Contract, Selene Local Execution, and Mock QNexus
API Integration Tests (including exponential-backoff retries and post-compile
ISA hash drift fail-closed enforcement).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

import pytest
from pytket import Circuit

from hardware.quantinuum_h2 import local_h2_compile
from osiris_cli.ledger import read_ledger, verify_ledger_file
from osiris_cli.qec_runner import build_parser, load_manifest, main
from osiris_cli.qnexus_client import (
    EXPECTED_ISA,
    HashMismatchError,
    QNexusAPIError,
    execute_h2_qnexus,
)
from wen_plaquette_pass import WenPlaquetteFeedForwardPass

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_V1_0 = str(ROOT / "hardware" / "experiment_manifest_v1_0_0.json")
MANIFEST_V1_1 = str(ROOT / "hardware" / "experiment_manifest_v1_1_0.json")


# ---------------------------------------------------------------------------
# Section 11A: Argparse CLI Contract Tests
# ---------------------------------------------------------------------------

def test_verify_help() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["qec", "verify", "--help"])
    assert exc.value.code == 0


def test_target_validation() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["qec", "run", "--target", "ibm", "--manifest", MANIFEST_V1_1])


def test_shot_validation() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["qec", "run", "--target", "selene", "--shots", "5000", "--manifest", MANIFEST_V1_1]
    )
    assert args.shots == 5000


def test_manifest_required() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["qec", "run", "--target", "selene"])


# ---------------------------------------------------------------------------
# Section 11 & 15: End-to-End CLI Verify, Manifest, Selene & Ledger Commands
# ---------------------------------------------------------------------------

def test_cli_verify_frozen_manifests_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["qec", "verify", "--manifest", MANIFEST_V1_0]) == 0
    out0 = capsys.readouterr().out
    assert "[PASS] Pre-compile SHA256 matches" in out0
    assert "[PASS] H2-1 ISA SHA256 matches" in out0

    assert main(["qec", "verify", "--manifest", MANIFEST_V1_1, "--strict"]) == 0
    out1 = capsys.readouterr().out
    assert "[PASS] Manifest version valid (1.1.0)" in out1


def test_cli_verify_modified_circuit_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    modified = tmp_path / "modified.qasm"
    modified.write_text("OPENQASM 2.0;\nqreg q[20];\nh q[0];\n", encoding="utf-8")

    rc = main(["qec", "verify", "--manifest", MANIFEST_V1_0, "--circuit", str(modified)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[FAIL]" in out
    assert "hash mismatch" in out


def test_cli_manifest_show_hashes_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["qec", "manifest", "--file", MANIFEST_V1_1, "--show-hashes"]) == 0
    out = capsys.readouterr().out
    assert "Manifest: v1.1.0" in out
    assert EXPECTED_ISA in out

    assert main(["qec", "manifest", "--file", MANIFEST_V1_1, "--json"]) == 0
    jout = capsys.readouterr().out
    assert '"manifest_version": "1.1.0"' in jout


def test_cli_selene_run_and_ledger_verify_and_show(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger_dir = tmp_path / "ledger"
    rc = main(
        [
            "qec",
            "run",
            "--target",
            "selene",
            "--shots",
            "1000",
            "--manifest",
            MANIFEST_V1_1,
            "--ledger",
            str(ledger_dir),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "mid-circuit Reset supported" in out
    assert "classical LUT branches validated" in out
    assert "execution not submitted to hardware" in out

    ledger_files = list(ledger_dir.glob("run-*.json"))
    assert len(ledger_files) == 1
    lf = str(ledger_files[0])

    assert main(["qec", "ledger", "verify", lf]) == 0
    vout = capsys.readouterr().out
    assert "RFC8785 canonical form valid" in vout
    assert "Entry chain valid (2 entries)" in vout

    # Also test root `osiris ledger show --summary` alias (Section 15)
    assert main(["ledger", "show", lf, "--summary"]) == 0
    sout = capsys.readouterr().out
    assert "Target: selene" in sout
    assert "PASS" in sout


# ---------------------------------------------------------------------------
# Mock QNexus API Integration Suite (Retries, Error Handling & Post-Compile Lock)
# ---------------------------------------------------------------------------

@dataclass
class _MockCircuitRef:
    id: str
    _circuit: Circuit

    def download_circuit(self) -> Circuit:
        return self._circuit.copy()


@dataclass
class _MockJobRef:
    id: str


class MockHTTP504Error(RuntimeError):
    def __init__(self, msg: str = "504 Gateway Timeout"):
        super().__init__(msg)
        self.status_code = 504


class MockHTTP401Error(RuntimeError):
    def __init__(self, msg: str = "401 Unauthorized"):
        super().__init__(msg)
        self.status_code = 401


class MockQNexusModule:
    """Deterministic in-memory mock of `qnexus` 0.51.4 API surface."""

    __version__ = "0.51.4"

    def __init__(
        self,
        compiled_circuit_override: Circuit | None = None,
        transient_upload_failures: int = 0,
        transient_results_failures: int = 0,
        auth_error: bool = False,
    ) -> None:
        self.compiled_circuit_override = compiled_circuit_override
        self.transient_upload_failures = transient_upload_failures
        self.transient_results_failures = transient_results_failures
        self.auth_error = auth_error

        self.login_calls = 0
        self.upload_calls = 0
        self.compile_calls: List[dict] = []
        self.execute_calls: List[dict] = []
        self.wait_calls = 0
        self.results_calls = 0

        parent = self

        class _Projects:
            @staticmethod
            def get_or_create(name: str) -> dict:
                return {"name": name, "id": "proj-osiris-qec"}

        class _Circuits:
            @staticmethod
            def upload(name: str, circuit: Circuit, project: Any) -> _MockCircuitRef:
                parent.upload_calls += 1
                if parent.upload_calls <= parent.transient_upload_failures:
                    raise ConnectionError("Simulated transient reset during circuit upload")
                return _MockCircuitRef(id=f"cref-{parent.upload_calls}", _circuit=circuit.copy())

        class _Jobs:
            @staticmethod
            def wait_for(job_ref: _MockJobRef) -> None:
                parent.wait_calls += 1

            @staticmethod
            def results(job_ref: _MockJobRef) -> List[dict]:
                parent.results_calls += 1
                if parent.results_calls <= parent.transient_results_failures:
                    raise MockHTTP504Error("Simulated upstream 504 Gateway Timeout")
                # All-zero 16-bit X-readout satisfies even parity on all 8 X-plaquettes
                return [
                    {
                        "c5_end_bitstrings": ["0" * 16] * 1000,
                        "syndrome_trajectories": ["0000:0000"] * 16,
                    }
                ]

        self.projects = _Projects()
        self.circuits = _Circuits()
        self.jobs = _Jobs()

    def login(self) -> None:
        self.login_calls += 1
        if self.auth_error:
            raise MockHTTP401Error("Invalid or expired QNexus token")

    @staticmethod
    def QuantinuumConfig(*, device_name: str, no_opt: bool = True, **kwargs: Any) -> dict:
        return {"device_name": device_name, "no_opt": no_opt, **kwargs}

    def compile(
        self,
        *,
        programs: List[_MockCircuitRef],
        name: str,
        project: Any,
        optimisation_level: int,
        backend_config: dict,
    ) -> List[_MockCircuitRef]:
        self.compile_calls.append(
            {
                "name": name,
                "optimisation_level": optimisation_level,
                "backend_config": backend_config,
            }
        )
        out_circ = (
            self.compiled_circuit_override.copy()
            if self.compiled_circuit_override is not None
            else programs[0].download_circuit()
        )
        return [_MockCircuitRef(id="cref-compiled-locked", _circuit=out_circ)]

    def start_execute_job(
        self,
        *,
        programs: List[_MockCircuitRef],
        n_shots: List[int],
        backend_config: dict,
        name: str,
        project: Any,
    ) -> _MockJobRef:
        self.execute_calls.append(
            {"n_shots": n_shots, "backend_config": backend_config, "name": name}
        )
        return _MockJobRef(id="job-h2-mock-001")


def _frozen_isa_circuit() -> Circuit:
    b = WenPlaquetteFeedForwardPass(measurement_setting="X", target_device="H2-1")
    pre = Circuit()
    b.to_tket_pass().apply(pre)
    return local_h2_compile(pre, optimisation_level=2)


def test_mock_qnexus_h2_happy_path_and_transient_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QNEXUS_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_API_TOKEN", raising=False)

    isa_circ = _frozen_isa_circuit()
    manifest = load_manifest(MANIFEST_V1_1)
    delays: List[float] = []

    mock_qnx = MockQNexusModule(transient_upload_failures=2, transient_results_failures=1)
    res = execute_h2_qnexus(
        isa_circuit=isa_circ,
        manifest=manifest,
        shots=1000,
        qnx_module=mock_qnx,
        max_retries=3,
        sleep_fn=delays.append,
    )

    assert mock_qnx.upload_calls == 3  # 2 transient failures + 1 success
    assert mock_qnx.results_calls == 2  # 1 HTTP 504 + 1 success
    assert len(delays) == 3
    assert mock_qnx.compile_calls[0]["optimisation_level"] == 0
    assert mock_qnx.compile_calls[0]["backend_config"]["no_opt"] is True
    assert len(mock_qnx.execute_calls) == 1
    assert res["verified_compiled_isa_sha256"] == EXPECTED_ISA
    assert res["raw_fidelity"] == 1.0
    assert res["wilson_lower_bound"] > 0.99
    assert res["pass"] is True


def test_mock_qnexus_aborts_before_execute_on_compiled_isa_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QNEXUS_TOKEN", "ephemeral-test-token")
    isa_circ = _frozen_isa_circuit()
    drifted_circ = isa_circ.copy()
    drifted_circ.Rz(0.125, drifted_circ.qubits[0])  # Simulate unauthorized backend gate mutation

    manifest = load_manifest(MANIFEST_V1_1)
    mock_qnx = MockQNexusModule(compiled_circuit_override=drifted_circ)

    with pytest.raises(HashMismatchError, match="Compiled ISA hash drift detected"):
        execute_h2_qnexus(
            isa_circuit=isa_circ,
            manifest=manifest,
            shots=1000,
            qnx_module=mock_qnx,
            sleep_fn=lambda _: None,
        )

    # Fail-closed guarantee: execution job MUST NEVER be started when compiled ISA hash drifts
    assert len(mock_qnx.compile_calls) == 1
    assert len(mock_qnx.execute_calls) == 0


def test_mock_qnexus_non_retryable_auth_error_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QNEXUS_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_API_TOKEN", raising=False)

    isa_circ = _frozen_isa_circuit()
    manifest = load_manifest(MANIFEST_V1_1)
    mock_qnx = MockQNexusModule(auth_error=True)
    delays: List[float] = []

    with pytest.raises(QNexusAPIError, match="401 Unauthorized|Invalid or expired"):
        execute_h2_qnexus(
            isa_circuit=isa_circ,
            manifest=manifest,
            shots=1000,
            qnx_module=mock_qnx,
            max_retries=3,
            sleep_fn=delays.append,
        )

    assert mock_qnx.login_calls == 1
    assert delays == []  # Zero retries on 401 auth errors


def test_cli_h2_dispatch_records_write_ahead_ledger_on_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QNEXUS_TOKEN", "ephemeral-test-token")
    isa_circ = _frozen_isa_circuit()
    drifted_circ = isa_circ.copy()
    drifted_circ.Rz(0.25, drifted_circ.qubits[1])
    mock_qnx = MockQNexusModule(compiled_circuit_override=drifted_circ)

    parser = build_parser()
    ledger_dir = tmp_path / "ledger_abort"
    args = parser.parse_args(
        ["qec", "run", "--target", "h2-1", "--shots", "5000", "--manifest", MANIFEST_V1_1, "--ledger", str(ledger_dir)]
    )
    setattr(args, "_qnx_module", mock_qnx)

    with pytest.raises(HashMismatchError):
        args.func(args)

    ledger_files = list(ledger_dir.glob("run-*.json"))
    assert len(ledger_files) == 1
    verify_ledger_file(ledger_files[0])
    rows = read_ledger(ledger_files[0])
    assert [r["stage"] for r in rows] == ["pre_submit", "aborted_hash_mismatch"]
    assert len(mock_qnx.execute_calls) == 0
