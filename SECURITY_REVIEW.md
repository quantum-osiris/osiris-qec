# OSIRIS-QEC v1.1.0 Security & Integrity Review

## 1. Threat Model & Provenance Objectives

OSIRIS-QEC v1.1.0 transitions the verified v1.0.0 simulation package (`10.5281/zenodo.24406733`) to a hardware-dispatch-capable toolkit while guaranteeing that:
1. **No unverified or silently mutated quantum circuit can be submitted to Quantinuum Nexus (`H2-1`).**
2. **No API credentials (`QNEXUS_TOKEN`, `NEXUS_API_TOKEN`, `ZENODO_API_TOKEN`) are ever persisted, logged, or committed.**
3. **Every local validation or remote hardware dispatch leaves a tamper-evident RFC 8785 write-ahead audit trail even if execution is interrupted.**

## 2. Control Summary

| Control Domain | Implementation | Failure Mode | Verification Test |
| :--- | :--- | :--- | :--- |
| **Input & Register Isolation** | `WenPlaquetteFeedForwardPass._check_input_contract` & `build_wen_plaquette` | `ValueError` before transformation on non-empty circuits or `q`/`qr`/`quantum`/`c`/`creg`/`cl`/`classical` collisions | `tests/test_hash_lock.py` |
| **Metadata Drift Immunity** | `normalize_circuit_metadata` & `canonical_circuit_dict` | Strips mutable `name`/`metadata` and normalizes `phase` mod 2 prior to SHA-256 | `test_metadata_normalization` |
| **Pre-Upload Hash Lock** | `build_and_verify_frozen_artifacts` | `HashMismatchError` (CLI exit `1`) if pre-compile != `b86aeabd...` or ISA != `02d5cb72...` | `test_hash_gate_rejects_tampered_*` |
| **Compilation Lock** | `qnx.compile(..., optimisation_level=0, QuantinuumConfig(no_opt=True))` | `ManifestError` if `optimisation_level != 0`, `hash_lock != true`, or `compiler_lock != true` | `test_hash_gate_rejects_unlocked_*` |
| **Post-Compile ISA Drift Gate** | `verify_compiled_program_hash` | Inspects compiled circuit returned by QNexus **before** `start_execute_job`; aborts with `HashMismatchError` on any gate/angle drift | `test_mock_qnexus_aborts_before_execute_on_compiled_isa_drift` |
| **Write-Ahead Forensic Ledger** | `osiris_cli/ledger.py` (RFC 8785 + `os.fsync`) | `pre_submit` hash-chained record flushed before network calls; tampering breaks `entry_sha256` / `prev_sha256` | `test_ledger_append_and_tamper_detection`, `test_cli_h2_dispatch_records_write_ahead_ledger_on_abort` |
| **Retry Isolation** | `with_qnexus_retries` | Retries only transient `429`/`502`/`503`/`504`/network timeouts; **never** retries `HashMismatchError`, `ManifestError`, or `401`/`403` auth errors | `test_mock_qnexus_non_retryable_auth_error_fails_immediately` |

## 3. Secret & Credential Hygiene

- Static grep and repository audit confirm zero embedded tokens, keys, or `.env` files across all tracked files.
- `.gitignore` excludes `.env`, `.env.*`, `ledger/`, and build artifacts.
- Authentication tokens (`QNEXUS_TOKEN`, `NEXUS_API_TOKEN`, `ZENODO_API_TOKEN`) are read exclusively from runtime environment variables or out-of-repo user configuration and are never echoed to stdout, stderr, or ledger entries.
