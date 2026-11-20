"""Phase 6: Quantinuum H2 compatibility — LOCAL validation only. No credentials,
no submission, no paid jobs. Writes hardware/experiment_manifest.json and
reports/H2_COMPATIBILITY.md.

Local facts used (pytket-quantinuum 0.59.3, installed):
  H2 gate set: {Rz, PhasedX, ZZMax, ZZPhase, TK2}; 56 qubits; 4000 clbits.
Docs (docs.quantinuum.com, checked 2026-11): devices H1-1 and H2-1 (56 qubits,
all-to-all); H2-2 announced Dec 2024; H2-1SC syntax checker (no HQC consumed);
H2-1E emulator and H2-1LE local emulator; submission via qnexus since
pytket-quantinuum 0.56. H-series supports mid-circuit measurement, reset and
classical feed-forward (TKET Conditional).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pytket import Circuit, OpType

sys.path.insert(0, str(Path(__file__).parent.parent))
from wen_plaquette_pass import WenPlaquetteFeedForwardPass, hash_tket_circuit

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "hardware" / "experiment_manifest.json"
REPORT = ROOT / "reports" / "H2_COMPATIBILITY.md"

H2_GATE_SET = {OpType.Rz, OpType.PhasedX, OpType.ZZMax, OpType.ZZPhase, OpType.TK2}


def local_h2_backend():
    """Quantinuum H2-1 backend in OFFLINE mode: no credentials, no network.
    Used only for local compilation to the H2 ISA (default_compilation_pass)."""
    from pytket.extensions.quantinuum import QuantinuumBackend
    from pytket.extensions.quantinuum.backends.api_wrappers import QuantinuumAPIOffline
    return QuantinuumBackend("H2-1", api_handler=QuantinuumAPIOffline())


def local_h2_compile(circ: Circuit, optimisation_level: int = 2) -> Circuit:
    """Compile to the H2-1 native gate set locally via the offline backend."""
    be = local_h2_backend()
    return be.get_compiled_circuit(circ.copy(), optimisation_level=optimisation_level)


def gate_counts(circ: Circuit) -> dict:
    from collections import Counter
    kinds = Counter(cmd.op.type.name for cmd in circ.get_commands())
    return dict(sorted(kinds.items()))


def main() -> None:
    b = WenPlaquetteFeedForwardPass(measurement_setting="X", target_device="H2-1")
    circ = Circuit()
    b.to_tket_pass().apply(circ)
    circ_hash = hash_tket_circuit(circ)

    compiled = local_h2_compile(circ, optimisation_level=2)
    compiled_hash = hash_tket_circuit(compiled)
    gc = gate_counts(compiled)
    n_cond = sum(1 for cmd in compiled.get_commands() if cmd.op.type == OpType.Conditional)
    n_meas = sum(1 for cmd in compiled.get_commands() if cmd.op.type == OpType.Measure)
    n_reset = sum(1 for cmd in compiled.get_commands() if cmd.op.type == OpType.Reset)
    n_bits = compiled.n_bits

    checks = {
        "n_qubits_20_le_56": compiled.n_qubits <= 56,
        "n_clbits_28_le_4000": n_bits <= 4000,
        "midcircuit_measure_present": n_meas == 24,
        "reset_present": n_reset == 8,
        "conditional_feedforward_present": n_cond == 20,
        "rebased_to_h2_gate_set": set(gc) - {"Conditional", "Measure", "Reset", "Barrier"} <= {str(g).split(".")[-1] for g in H2_GATE_SET},
    }

    manifest = {
        "manifest_version": "1.0",
        "status": "PREPARED_LOCALLY__NOT_SUBMITTED",
        "target_backends": [
            {"name": "H2-1SC", "role": "syntax checker (free, no HQC consumed)", "requires_api": True},
            {"name": "H2-1E", "role": "device emulator (consumes HQC)", "requires_api": True},
            {"name": "H2-1", "role": "hardware (subscription / Azure Quantum / ORNL QCUP)", "requires_api": True},
        ],
        "circuits": [{
            "id": "wen_plaquette_prep_v1",
            "pre_compile_sha256": circ_hash,
            "h2_compiled_sha256": compiled_hash,
            "n_qubits": compiled.n_qubits,
            "n_clbits": n_bits,
            "depth_after_compile": compiled.depth(),
            "gate_counts_after_compile": gc,
        }],
        "shot_allocation": {"H2-1SC": "syntax check only, 1 shot", "H2-1E": "1000-10000 shots (emulator)", "H2-1": "1000-10000 shots proposed"},
        "estimated_cost": "H2-1SC: no HQC. H2-1E / H2-1: consumes HQC; exact cost TBD via qnexus at submission time. No job has been submitted.",
        "scientific_hypothesis": "The 20-qubit Wen-plaquette feed-forward preparation circuit compiles to the H2 ISA and, on H2-1, the final X-basis readout of the 16 data qubits satisfies all 8 Z-plaquette even-parity constraints in every shot (codespace preparation), with feed-forward corrections visible in the classical register.",
        "expected_observations": [
            "All 24 mid-circuit measurements execute; 20 conditional Z corrections present.",
            "Every c5_end outcome string has even parity on each Z-plaquette support.",
            "Syndrome distribution over c4_2nd matches the ideal uniform-over-even-parity distribution.",
        ],
        "submission_path": {
            "status": "legacy Quantinuum API SUNSET; pytket-quantinuum job-submission API retired (docs.quantinuum.com/product-updates).",
            "current_path": "qnexus 0.51.4 (installed, API inspected, NOT logged in): qnexus.login_with_credentials() / Nexus portal auth -> qnexus.devices.get_all() -> qnexus.QuantinuumConfig(device_name='H2-1SC'|'H2-1E'|'H2-1') -> qnexus.start_compile_job / qnexus.start_execute_job. pytket-quantinuum 0.59.3 used here ONLY for offline local compilation (QuantinuumAPIOffline), which remains valid.",
            "note": "No submission attempted; credentials required and supplied at runtime by an authorized user only.",
        },
        "acceptance_criteria": [
            "H2-1SC syntax check passes via qnexus.",
            "X-basis run: 95% Wilson LOWER confidence bound on the fraction of shots satisfying all X-plaquette parity constraints exceeds 0.99 (stronger than observing >=99% at n=1000).",
            "Z-basis run: same criterion on Z-plaquette parity.",
            "Round-2 syndrome parity always even in simulation-derived expectation; on hardware, report raw distribution.",
        ],
        "stopping_conditions": [
            "Stop after syntax check if it fails (fix compilation, do not submit).",
            "Stop emulator run if >5% parity violations at low shot count.",
            "Never submit to H2-1 hardware without explicit human authorization.",
        ],
        "result_retrieval": "qnexus / Quantinuum API job results; counts keyed by c5_end; compare against reports/QEC_BENCHMARK_RESULTS.json noise predictions.",
        "credentials": "NONE stored, printed, or committed. API tokens are supplied at runtime via environment variables by an authorized user only.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))

    report = f"""# H2 Compatibility (Phase 6) — local validation, no submission

## Environment
- pytket 2.18.5, pytket-quantinuum 0.59.3, qnexus 0.51.4 (installed locally; versions recorded).
- H2 backend data (from installed package): 56 qubits, 4000 clbits,
  gate set {{Rz, PhasedX, ZZMax, ZZPhase, TK2}}.
- Docs checked (docs.quantinuum.com, 2026-11): current devices H1-1 and H2-1
  (H2-2 announced Dec 2024); H2-1SC free syntax checker; H2-1E emulator;
  submission moved to qnexus as of pytket-quantinuum 0.56.

## Local compilation result
- Pre-compile circuit sha256: `{circ_hash}`
- After local rebase to H2 gate subset + squash: sha256 `{compiled_hash}`, depth {compiled.depth()}
- Gate counts after compile: {json.dumps(gc)}
- Checks: {json.dumps(checks, indent=1)}
- ALL LOCAL CHECKS PASS: {all(checks.values())}

## Feature support on H2
- Mid-circuit measurement: {n_meas} Measure ops (supported on H-series).
- Ancilla reset/reuse: {n_reset} Reset ops (supported).
- Classical feed-forward: {n_cond} Conditional ops (supported via TKET conditional / transport layer).
- Qubit/clbit budget: 20/56 qubits, 28/4000 clbits used.
- Offline H2-1 compilation (QuantinuumAPIOffline, optimisation_level=2) succeeds:
  see manifest for hashes and gate counts.

## Submission path (validated against current docs, 2026-11)
- The legacy Quantinuum API is **sunset**; pytket-quantinuum's job-submission API is
  retired (docs.quantinuum.com/product-updates). Submission now goes through
  **qnexus / Quantinuum Nexus**: `qnexus.login_with_credentials()` (portal auth),
  `qnexus.devices.get_all()`, `qnexus.QuantinuumConfig(device_name="H2-1SC" /
  "H2-1E" / "H2-1")`, `qnexus.start_compile_job` / `qnexus.start_execute_job`.
  qnexus 0.51.4 installed locally and API inspected; **not logged in**.
- pytket-quantinuum 0.59.3 is used here ONLY for offline local compilation
  (`QuantinuumAPIOffline`), which remains valid for producing the H2-ISA circuit.

## Provenance
- The underlying preparation protocol (4x4 Wen-plaquette/toric ground state via
  2 rounds of mid-circuit X-measurement + LUT feed-forward) is prior art:
  arXiv:2302.01917 (Iqbal et al., Quantinuum H1) and Quantinuum's official tutorial
  "Topological Order from Measurements and Feed-Forward". This package's
  contribution is the pytket CustomPass integration, independent verification,
  regression tests, and reproducible benchmarking — not the protocol itself.

## What was NOT done (authorization boundary)
- No API login, no credentials read/printed/committed, no syntax-checker call,
  no emulator job, no hardware job, no payment. Submission requires explicit
  human authorization and qnexus credentials supplied at runtime.

## Manifest
See hardware/experiment_manifest.json (hashes, shots, cost TBD, hypothesis,
acceptance criteria, stopping conditions, retrieval procedure).
"""
    REPORT.write_text(report)
    print(f"wrote {MANIFEST} and {REPORT}")
    print("checks:", checks, "all pass:", all(checks.values()))
    print("gate counts after H2 rebase:", gc, "depth:", compiled.depth())


if __name__ == "__main__":
    main()
