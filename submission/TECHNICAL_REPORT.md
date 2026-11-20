# Technical Report — 20-Qubit Wen-Plaquette Feed-Forward Preparation (pytket CustomPass)

**Status: HARDWARE-UNVALIDATED.** All evidence is local simulation + offline
compilation; no provider job has been submitted.

**Provenance:** the 4×4 Wen-plaquette preparation protocol (16 data + 4 ancilla qubits,
two rounds of X-stabilizer measurement, 7-entry LUT, conditional Z) is prior art:
arXiv:2302.01917 (Iqbal et al., Quantinuum H1) and Quantinuum's official tutorial
"Topological Order from Measurements and Feed-Forward". This package's contribution
is the pytket `CustomPass` integration, independent verification, regression tests,
and reproducible benchmarking — not invention of the protocol.

## 1. Scientific objective and hypothesis
Demonstrate a rigorously verified, reproducible preparation of the codespace of the
4x4 toroidal Wen-plaquette CSS code (16 data qubits, stabilizer rank 14, k=2 logical
qubits, distance d=4) via 2 rounds of mid-circuit X-stabilizer measurement on 4 reused
ancillas with classical feed-forward (4 single-bit conditional Z corrections + a 7-entry
4-bit LUT), packaged as a pytket `CustomPass`, and validate H2 compatibility locally.

## 2. Mathematical code specification (independently derived)
- Lattice: 4x4 periodic; qubit (r,c) -> 4r+c; checkerboard plaquettes (Z on r+c even,
  X on r+c odd), all weight 4. Module tables match the lattice derivation exactly.
- All 16 generators pairwise commute; GF(2) rank 14 -> k=2; exhaustive enumeration of
  all Paulis of weight <= 3 finds no nontrivial logical -> d=4.
- Logical representatives: row/column strings (weight 4).

## 3. Circuit architecture
20 qubits (16 data + 4 ancilla), 28 clbits. Round 1: measure X plaquettes (4,6,12,14),
conditional Z on one support qubit each. Round 2: measure X plaquettes (1,3,9,11),
4-bit LUT conditional Z corrections. Final: X-basis measurement of 16 data qubits.
Resources pre-compile: 132 ops before barrier (64 H, 32 CX, 8 Measure, 8 Reset,
20 Conditional-Z), depth 16.

## 4. Syndrome extraction & feed-forward
- Endianness contract: big-endian syndrome string -> reversed-string integer for
  pytket's little-endian condition_bits. Verified at unit level, in the emitted
  circuit, and behaviorally (branch enumeration).
- LUT: 7 even-weight syndromes; each correction's syndrome recomputed independently
  from stabilizer supports matches its key and does not disturb round-1 plaquettes.

## 5. Compiler-pass implementation & contract
- Original baseline vendored untouched (`dnalang_wen_plaquette_pass.py`).
- Corrected pass (`wen_plaquette_pass.py`): preparation-only contract enforced —
  nonempty input or conflicting q-register raises ValueError; nothing silently
  discarded. Output circuit identical to baseline on empty input (regression test).

## 6-7. Verification methodology & test coverage
- 28/28 automated tests pass (pytest): contract regression (9), behavior (16),
  error injection (3).
- Exact branch enumeration: all 256 measurement-outcome combos; 128 reachable
  (others exactly zero-probability), ALL 128 reachable branches land in the codespace
  (worst stabilizer expectation 0.9999999999999942). No sampling.
- Independent cross-check on qiskit AerBackend (C++): 512 shots of the full dynamic
  circuit, 0 X-plaquette parity violations in the final X-basis readout.
- Independent verifier (`verify_independent.py`) derives everything from the lattice,
  not the LUTs; negative tests confirm it detects a corrupted LUT entry, an invalid
  stabilizer, and an endianness mismatch.

## 8-10. Results (executed)
- Noiseless prep: codespace on all 128 reachable branches; branch-independent final
  state (fidelity 0.9999999999999885 across 5 distinct reachable branches).
- Error injection, PRE-preparation (16 shots/case): weight-1 Z on any data qubit
  corrected 16/16; weight-1 X/Y NOT detected 0/32; weight-2 Z pairs tested corrected
  4/4 (not guaranteed by d=4); ancilla Z corrected, ancilla X undetected.
- Error injection, POST-preparation (reviewer check 1, tests/test_post_prep_injection.py,
  reports/POST_PREP_INJECTION.json): a Z error applied after preparation produces a
  nonzero X-syndrome on all 16 data qubits (detectable) but is NOT corrected —
  the circuit has no syndrome round after preparation (pre-prep Z: fidelity 1.0;
  post-prep Z: fidelity < 0.001). Post-prep X errors flip Z stabilizers, which are
  never measured: undetected. Reported separately from pre-prep results.
- Measurement basis (reviewer check 2): structural test confirms c5_end is X-basis
  (H before each Measure) for setting "X" and Z-basis for setting "Z"; AerBackend
  cross-checks pass in both bases (X: 512 shots 0 violations; Z: 256 shots 0
  violations of the respective plaquette parities). A single destructive readout
  verifies only one basis; both settings are required.
- Logical validation: prepared state is a FIXED logical computational-basis state
  (Z_L row/col = +1, X_L = 0); arbitrary logical states/superpositions are NOT
  encodable by this circuit; it is NOT a fault-tolerant memory. Z-error correction
  preserves the logical state (fidelity 1.0); X-error does not (fidelity 0.0).
- Noise benchmark (Monte Carlo trajectories, documented per-op depolarizing /
  measurement bit-flip / reset noise, seeds 11/22/33, 60 shots per cell):
  mean fidelity to the prepared logical state with feed-forward:
  p=0 -> 1.0000, 1e-4 -> 0.9889, 1e-3 -> 0.9056, 5e-3 -> 0.6389, 1e-2 -> 0.3833;
  no-feed-forward baseline ~0.00-0.01. Figure: reports/QEC_BENCHMARK_RESULTS.png.
  No quantum advantage or fault tolerance is claimed.

## 11-13. Hardware compatibility, resources, cost
- Local offline compile to H2-1 ISA (pytket-quantinuum 0.59.3, QuantinuumAPIOffline):
  depth 19, 32 ZZPhase + 72 PhasedX + 20 Rz + 20 Conditional + 24 Measure + 8 Reset;
  20/56 qubits, 28/4000 clbits. Circuit hashes in hardware/experiment_manifest.json.
- Submission path (reviewer check 3, verified against current docs 2026-11): the
  legacy Quantinuum API is SUNSET and pytket-quantinuum's submission API is retired;
  current path is qnexus 0.51.4 / Quantinuum Nexus (`login_with_credentials`,
  `devices.get_all()`, `QuantinuumConfig(device_name=...)`, `start_compile_job` /
  `start_execute_job`) — API inspected locally, not logged in. pytket-quantinuum is
  used only for offline compilation.
- Cost: H2-1SC syntax check consumes no HQC; H2-1E/H2-1 consume HQC (exact cost TBD
  via qnexus at submission). NO jobs submitted; no credentials used.
- Acceptance criteria upgraded to statistical form: 95% Wilson lower confidence bound
  on parity-success fraction > 0.99 per basis run (see EXPERIMENT_PROTOCOL.md).

## 14-15. Limitations & unresolved defects
- X/Y errors undetected (single syndrome type only); not a QEC memory; fixed logical
  state only; DD options in the capsule are inert metadata; benchmark is simulation,
  not hardware.

## 16. Evidence-based conclusions
Preparation: VERIFIED. Error detection/correction for weight-1 Z: VERIFIED.
Arbitrary logical encoding / fault-tolerant memory: REFUTED (not supported).
H2 hardware execution: BLOCKED on credentials/authorization (local compile VERIFIED).
Full claim table: reports/INDEPENDENT_VERIFICATION.md and CLAIMS_AND_EVIDENCE.json.
