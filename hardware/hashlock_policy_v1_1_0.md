# OSIRIS-QEC v1.1.0 Fail-Closed Hash-Lock & Compilation-Lock Policy

## 1. Immutable Artifact Baseline

All compilation, validation, and hardware dispatch paths in OSIRIS-QEC v1.1.0 are cryptographically bound to the preregistered v1.0.0 baseline (`ac668e4`, Zenodo DOI [`10.5281/zenodo.24406733`](https://doi.org/10.5281/zenodo.24406733)):

| Artifact | Frozen SHA-256 Digest | Structural Invariants |
| :--- | :--- | :--- |
| **Pre-compile circuit** (`WenPlaquetteFeedForwardPass`) | `b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b` | 20 qubits (16 data + 4 ancilla), 28 clbits, depth 16, 20 `Conditional`, 8 `Reset`, 24 `Measure` |
| **Quantinuum H2-1 ISA circuit** (`QuantinuumAPIOffline`) | `02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062` | Depth 19, 32 `ZZPhase`, 72 `PhasedX`, 20 `Rz`, 20 `Conditional`, 24 `Measure`, 8 `Reset`, 1 `Barrier` |

## 2. Two-Stage Pre-Flight & Post-Compile Verification

1. **Pre-Upload Gate (`build_and_verify_frozen_artifacts`):**
   - Rebuilds the preparation circuit via `WenPlaquetteFeedForwardPass` after metadata normalization (`name`, `phase`, `metadata`) and verifies exact equality with `b86aeabd...`.
   - Compiles offline to the H2-1 native gate set and verifies exact equality with `02d5cb72...`, `depth == 19`, and `ZZPhase == 32`.
   - Verifies manifest lock flags (`hash_lock == true`, `compiler_lock == true`, `optimisation_level == 0`).
2. **QNexus Transport & Post-Compile Gate (`execute_h2_qnexus`):**
   - Uploads the verified H2-1 ISA circuit to Quantinuum Nexus (`qnexus 0.51.4`) and invokes `qnx.compile(..., optimisation_level=0, backend_config=QuantinuumConfig(device_name="H2-1", no_opt=True))`.
   - Downloads/inspects the compiled program returned by Nexus and verifies `hash_tket_circuit(compiled_program) == 02d5cb72...` **before** calling `qnx.start_execute_job(...)`.

## 3. Fail-Closed Enforcement

- Any mismatch at manifest load, pre-compile generation, offline ISA compilation, or QNexus post-compile verification raises `HashMismatchError`, records an `aborted_hash_mismatch` forensic entry in the RFC 8785 write-ahead ledger, prints `[FAIL]`, and terminates with **exit code `1`**.
- There is **no bypass flag** and **no warning-only mode** for hash or compilation-lock violations (`--force` never overrides `HashMismatchError` or `ManifestError`).
- Any future modification to circuit topology, shot accounting, post-selection, or Wilson confidence bounds requires a new manifest version and new preregistered hashes without altering `hardware/experiment_manifest_v1_0_0.json`.
