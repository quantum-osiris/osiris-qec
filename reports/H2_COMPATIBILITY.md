# H2 Compatibility (Phase 6) — local validation, no submission

## Environment
- pytket 2.18.5, pytket-quantinuum 0.59.3, qnexus 0.51.4 (installed locally; versions recorded).
- H2 backend data (from installed package): 56 qubits, 4000 clbits,
  gate set {Rz, PhasedX, ZZMax, ZZPhase, TK2}.
- Docs checked (docs.quantinuum.com, 2026-11): current devices H1-1 and H2-1
  (H2-2 announced Dec 2024); H2-1SC free syntax checker; H2-1E emulator;
  submission moved to qnexus as of pytket-quantinuum 0.56.

## Local compilation result
- Pre-compile circuit sha256: `b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`
- After local rebase to H2 gate subset + squash: sha256 `02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`, depth 19
- Gate counts after compile: {"Barrier": 1, "Conditional": 20, "Measure": 24, "PhasedX": 72, "Reset": 8, "Rz": 20, "ZZPhase": 32}
- Checks: {
 "n_qubits_20_le_56": true,
 "n_clbits_28_le_4000": true,
 "midcircuit_measure_present": true,
 "reset_present": true,
 "conditional_feedforward_present": true,
 "rebased_to_h2_gate_set": true
}
- ALL LOCAL CHECKS PASS: True

## Feature support on H2
- Mid-circuit measurement: 24 Measure ops (supported on H-series).
- Ancilla reset/reuse: 8 Reset ops (supported).
- Classical feed-forward: 20 Conditional ops (supported via TKET conditional / transport layer).
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

## Gate execution status (2026-11-20)
- H2-1SC syntax-check script `hardware/submit_h2_1sc.py` prepared and run: circuit hash freeze check PASSED (matches manifest), submission BLOCKED on authentication (no credentials in this environment; `qnx login` required out-of-band). See reports/HARDWARE_EXECUTION_LOG.json. No emulator or hardware jobs submitted.
