# Independent Verification (Phase 7)

Expected results were derived from the lattice definition (qec_math.py), not from the
lookup tables under test. Versions: pytket 2.18.5, numpy 2.5.5, pytest 9.2.0; seeds recorded in test files.

| Claim | Status | Evidence |
|---|---|---|
| WEN_STABILIZERS match the independent 4x4 checkerboard derivation | VERIFIED | 16 generators compared |
| All 16 stabilizer generators pairwise commute (valid stabilizer group) | VERIFIED | symplectic inner product over all 120 pairs |
| Stabilizer rank = 14, encoded logical qubits k = 2 | VERIFIED | GF(2) rank of symplectic matrix |
| Code distance d = 4 (no nontrivial logical Pauli of weight <= 3) | VERIFIED | exhaustive enumeration over all Paulis of weight 1..3; 0 found |
| Every ROUND_2_LUT entry's correction produces exactly its syndrome key and does not disturb round-1 plaquettes | VERIFIED | syndrome recomputed from stabilizer supports for all 7 entries |
| Emitted 4-bit conditional values equal the little-endian integer of the independently computed syndrome (endianness contract holds in the circuit) | VERIFIED | checked all width-4 Conditional ops |
| Noiseless preparation lands in the codespace (all 16 stabilizers +1) on ALL reachable measurement branches — exact enumeration of all 256 outcome combos, no sampling; the 128 zero-probability combos are detected as unreachable | VERIFIED | 128/128 reachable branches, 128 unreachable, worst exp 1.000000 |
| Preparation-only contract: nonempty input rejected with ValueError | VERIFIED | ValueError raised on 1-command input |
| Negative tests: verifier detects corrupted LUT, invalid stabilizer, and endianness mismatch | VERIFIED | {"corrupted_LUT_detected": true, "invalid_stabilizer_detected": true, "endianness_mismatch_detected": true} |
| Circuit generation is deterministic (identical SHA-256 across builds) | VERIFIED | b86aeabd70eecb7f... |
| X/Y errors on data qubits are detected and corrected | REFUTED | tests/test_error_injection.py: Z-type generators are never measured; X/Y errors leave the codespace and are undetected by the X-syndrome |
| The circuit is a fault-tolerant quantum memory | REFUTED | single preparation round only; no repeated syndrome extraction after prep |
| Weight-1 Z errors on data qubits are corrected (d=4 => t=1) | VERIFIED | tests/test_error_injection.py: 16/16 qubits, corrected_fraction = 1.0 |
| Noisy performance / logical error rates vs physical error rate | VERIFIED | benchmarks/qec_noise_benchmark.py -> reports/QEC_BENCHMARK_RESULTS.json (Monte Carlo trajectories, documented noise model, with no-feed-forward baseline) |
| H2 hardware execution | BLOCKED | requires API credentials + HQC; local H2-ISA compilation and manifest only (hardware/quantinuum_h2.py, reports/H2_COMPATIBILITY.md) |

Status legend: VERIFIED = executed evidence; REFUTED = contradicted by executed evidence; BLOCKED = cannot test without credentials/authorization.
