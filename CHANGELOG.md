# Changelog

All notable changes to `osiris-qec` are documented in this file.

## [1.1.0] - 2026-11-21

### Preserved Immutable Baseline (`v1.0.0`)
- Frozen pre-compile circuit SHA-256 (`b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`) and Quantinuum H2-1 ISA SHA-256 (`02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`, depth `19`, `32 ZZPhase`) remain bit-for-bit unchanged.
- Archived immutable v1.0.0 manifest in `hardware/experiment_manifest_v1_0_0.json` linked to Zenodo DOI `10.5281/zenodo.24406733` (`ac668e4`).

### Added
- **Compiler Pass Hardening (`wen_plaquette_pass.py`, `osiris_qec/`):**
  - Extended register-collision protection rejecting `qr`, `quantum`, `c`, `creg`, `cl`, `classical`, and conflicting `q` / stage registers with `ValueError` prior to transformation; added `build_wen_plaquette()` functional builder with strict register isolation.
  - Added `normalize_circuit_metadata()` normalizing `circuit.name`, `circuit.phase`, and `circuit.metadata` before SHA-256 hashing while attaching `{"osiris_qec_version": "1.1.0", "compiler_lock": true, "hash_locked": true}`.
- **Full 16/16 Post-Preparation Y-Error Sweep (`tests/test_y_error_sweep.py`, `reports/POST_PREP_Y_SWEEP_V1_1.json`):**
  - Expanded post-preparation Pauli-Y fault injection from 3 representative qubits `(0, 5, 15)` to all `16/16` data qubits `0..15`, recording deterministic X/Z syndromes and `0.0` logical state preservation.
- **OSIRIS-CLI QEC Command Family (`osiris_cli/qec_runner.py`):**
  - Implemented `osiris qec verify`, `osiris qec run --target {selene,h2-1}`, `osiris qec manifest`, and `osiris qec ledger {verify,show}` (plus `pyproject.toml` `osiris` console entrypoint).
- **RFC 8785 Write-Ahead Execution Ledger (`osiris_cli/ledger.py`, `hardware/ledger_schema_v1_1_0.json`):**
  - Strict RFC 8785 (JCS) canonical JSON serializer with IEEE-754 number formatting, UTF-16BE key sorting, atomic `fsync` write-ahead `pre_submit` logging, and `prev_sha256` -> `entry_sha256` hash chaining.
- **Provenance-Locked QNexus 0.51.4 Client (`osiris_cli/qnexus_client.py`, `hardware/hashlock_policy_v1_1_0.md`):**
  - Enforces `optimisation_level=0`, pre-upload SHA-256 verification, post-compile ISA SHA-256 verification prior to `start_execute_job` (fail-closed exit `1`), and bounded exponential backoff retries on transient HTTP `429`/`502`/`503`/`504` and transport errors.
- **Documentation, Security Review & CI:**
  - Added `SECURITY_REVIEW.md`, `hardware/experiment_manifest_v1_1_0.json`, `.github/workflows/ci.yml`, synchronized `README.md`, `submission/EXPERIMENT_PROTOCOL.md`, and updated `paper/` v1.1.0 manuscript & figures.

## [1.0.0] - 2026-11-20

- Initial public release and Zenodo publication (`10.5281/zenodo.24406733`) of the 20-qubit toroidal Wen-plaquette feed-forward preparation `pytket` `CustomPass`, independent GF(2) symplectic verifier (`[[16, 2, 4]]`), exact 256-branch statevector enumerator, dual-basis Qiskit Aer cross-checks, pre/post-prep fault taxonomy (`33/33` tests), noise benchmark, and frozen H2-1 ISA manifest (**HARDWARE-UNVALIDATED**).
