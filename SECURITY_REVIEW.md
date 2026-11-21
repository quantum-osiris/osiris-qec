# OSIRIS-QEC v1.1.1 Security & Integrity Review (`OSIRIS-QEC-002`)

## 1. Threat Model & Provenance Objectives

OSIRIS-QEC `v1.1.1` (`osiris-qec`, protocol `OSIRIS-QEC-002`) preserves the immutable `v1.0.0` (`10.5281/zenodo.24406733`) and `v1.1.0` (`10.5281/zenodo.24421051`) artifacts while enforcing four security and provenance invariants:
1. **Fail-Closed Artifact Lock:** Compilation and execution enforce a preregistered artifact lock—no unverified or mutated quantum circuit can be submitted to Quantinuum Nexus (`H2-1`).
2. **Third-Party Verifiable RFC 8785 Ledger:** Execution records are serialized exclusively through the pinned `rfc8785==0.1.4` JCS reference library with **zero `json.dumps` fallback**, eliminating cross-language IEEE-754 float canonicalization drift.
3. **Gateway Congestion & Auth Hygiene:** Transient transport retries honor HTTP `Retry-After` headers and apply ±25% randomized jitter to prevent thundering-herd retries while never retrying `401`/`403` auth errors or integrity failures; all timestamps use timezone-aware UTC (`datetime.now(timezone.utc)`).
4. **Zero Credential Persistence:** API tokens (`QNEXUS_TOKEN`, `NEXUS_API_TOKEN`, `ZENODO_API_TOKEN`) are read exclusively from runtime environment variables and never logged or committed.

## 2. Control Summary

| Control Domain | Implementation | Failure Mode | Verification Test |
| :--- | :--- | :--- | :--- |
| **Input & Register Isolation** | `WenPlaquetteFeedForwardPass._check_input_contract` & `build_wen_plaquette` | `ValueError` before transformation on non-empty circuits or `q`/`qr`/`quantum`/`c`/`creg`/`cl`/`classical` collisions | `tests/test_hash_lock.py` |
| **Metadata Drift Immunity** | `normalize_circuit_metadata` & `canonical_circuit_dict` | Strips mutable `name`/`metadata` and normalizes `phase` mod 2 prior to SHA-256 | `test_metadata_normalization` |
| **Pre-Upload Hash Lock** | `build_and_verify_frozen_artifacts` | `HashMismatchError` (CLI exit `1`) if pre-compile != `b86aeabd...` or ISA != `02d5cb72...` | `test_hash_gate_rejects_tampered_*` |
| **Compilation Lock** | `qnx.compile(..., optimisation_level=0, QuantinuumConfig(no_opt=True))` | `ManifestError` if `optimisation_level != 0`, `hash_lock != true`, or `compiler_lock != true` | `test_hash_gate_rejects_unlocked_*` |
| **Post-Compile ISA Drift Gate** | `verify_compiled_program_hash` | Inspects compiled circuit returned by QNexus **before** `start_execute_job`; aborts with `HashMismatchError` on any gate/angle drift | `test_mock_qnexus_aborts_before_execute_on_compiled_isa_drift` |
| **Pinned RFC 8785 WAL** | `osiris_cli/ledger.py` (`rfc8785.dumps` + `os.fsync`) | Fails closed (`LedgerError`) on `NaN`/`Inf`/`>=2^53` or canonical/hash-chain mismatch; no stdlib JSON fallback | `test_rfc8785_canonicalization_is_stable_and_compliant` |
| **Retry-After & Jitter Isolation** | `with_qnexus_retries` | Honors `Retry-After` + ±25% jitter on `429`/`502`/`503`/`504`; **never** retries `HashMismatchError`, `ManifestError`, or `401`/`403` | `test_retry_after_header_and_jitter_prevent_thundering_herd` |
| **UTC Timestamp Hygiene** | `datetime.now(timezone.utc)` | Static repository scan blocks deprecated naive `datetime.utcnow()` | `test_no_deprecated_utcnow_in_repository` |
