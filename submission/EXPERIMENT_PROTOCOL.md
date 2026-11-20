# Experiment Protocol — Wen-Plaquette Feed-Forward Preparation on Quantinuum H2

**Status: HARDWARE-UNVALIDATED.** All results so far are local simulation + offline
compilation. No syntax-checker, emulator, or hardware job has been submitted.

**Provenance:** the preparation protocol itself is prior art — arXiv:2302.01917
(Iqbal et al., Quantinuum H1) and Quantinuum's tutorial "Topological Order from
Measurements and Feed-Forward". This package contributes the pytket CustomPass
integration, independent verification, regression tests, and benchmarking.

## Objective
Demonstrate, on Quantinuum System Model H2, that the 20-qubit Wen-plaquette
feed-forward preparation circuit (pytket CustomPass, this package) prepares the
codespace of the 4x4 toroidal Wen-plaquette code (16 data qubits, k=2, d=4),
using 2 rounds of mid-circuit X-stabilizer measurement with 4 reused ancillas
and classical feed-forward (4 single-bit conditional Z + 7-entry 4-bit LUT).

## Preconditions (all verified locally before any submission)
1. H2-1SC syntax check passes on the compiled circuit (free, no HQC).
2. Local offline compile to H2 ISA succeeds (hardware/quantinuum_h2.py):
   depth 19, 32 ZZPhase, 72 PhasedX, 20 Rz, 20 Conditional, 24 Measure, 8 Reset,
   20/56 qubits, 28/4000 clbits.
3. Noiseless simulation (exact, all 128 reachable branches + AerBackend
   cross-check) confirms codespace preparation — see reports/.

## Circuit
- Source: `wen_plaquette_pass.py` -> `WenPlaquetteFeedForwardPass(measurement_setting="X")`.
- SHA-256 of pre-compile circuit and H2-compiled circuit: see
  `hardware/experiment_manifest.json`.

## Procedure (current submission path: qnexus / Quantinuum Nexus)
The legacy Quantinuum API is sunset and pytket-quantinuum's submission API is
retired (docs.quantinuum.com/product-updates). Use qnexus 0.51.4:
`qnexus.login_with_credentials()` -> `qnexus.devices.get_all()` ->
`qnexus.QuantinuumConfig(device_name="H2-1SC" / "H2-1E" / "H2-1")` ->
`qnexus.start_compile_job` / `qnexus.start_execute_job`. pytket-quantinuum is used
only for offline local compilation.

1. Syntax-check on H2-1SC (1 shot) via qnexus. Abort on failure.
2. Emulator H2-1E: >= 1,000 shots (recommend 10,000). Validate:
   a. X-basis run (measurement_setting="X"): c5_end outcomes satisfy even parity on
      all 8 X-plaquette supports;
   b. Z-basis run (measurement_setting="Z"): c5_end outcomes satisfy even parity on
      all 8 Z-plaquette supports (a single destructive readout verifies only one
      basis, so both settings are run);
   c. round-2 syndrome (c4_2nd) distribution consistent with ideal;
   d. compare observed fidelity against the noisy-simulation prediction in
      reports/QEC_BENCHMARK_RESULTS.json at the device's quoted physical error rate;
   e. run a no-feed-forward control circuit on the emulator as well.
3. Hardware H2-1 (ONLY with separate explicit human authorization): same criteria.

## Acceptance criteria (statistically strict)
- H2-1SC passes via qnexus.
- For each basis run (X and Z independently): the **95% Wilson lower confidence bound**
  on the parity-success fraction exceeds 0.99. Minimum passing successes per shot count
  (verified numerically, z = 1.959964):

  | Shots per basis | Minimum successes | Maximum failures |
  | --------------- | ----------------- | ---------------- |
  | 512             | 512               | 0                |
  | 1,000           | 997               | 3                |
  | 2,000           | 1,989             | 11               |
  | 5,000           | 4,964             | 36               |
  | 10,000          | 9,920             | 80               |

- Feed-forward conditionals present and exercised (multiple distinct c4_2nd values).

## Stopping conditions
- Syntax check failure -> fix locally, do not submit.
- Emulator parity-violation rate > 5% at 1,000 shots -> stop, investigate.
- No hardware submission without explicit authorization; no credentials are
  stored in this package.

## Result retrieval
Via qnexus / Quantinuum API by the authorized user; counts keyed by c5_end;
compare to local simulation artifacts in reports/.
