# Changelog

All notable changes to `osiris-qec` (`OSIRIS-QEC-002`) are documented in this file.

## [1.1.1] - 2026-11-21

### Fixed & Hardened (Post-v1.1.0 Engineering Review)
- **Strict Normative RFC 8785 Serializer (`osiris_cli/ledger.py`, `pyproject.toml`):**
  - Pinned Trail of Bits' `rfc8785>=0.1.4` as a mandatory core dependency and removed any custom/stdlib JSON fallback so every ledger entry canonicalizes identically across compliant third-party JCS verifiers (`1.0 -> 1`, `-0.0 -> 0`, IEEE-754 shortest round-trip floats, UTF-16 code-unit key ordering, and safe-integer `±(2^53-1)` domain enforcement).
  - Added normative IETF RFC 8785 Section 3.2.2.3 & Section 3.2.3 test vectors (`test_hash_lock.py`).
- **Gateway Congestion Resilience & Timestamp Hygiene (`osiris_cli/qnexus_client.py`):**
  - Added HTTP `Retry-After` header parsing (both delta-seconds and RFC 7231 HTTP-date) plus bounded randomized jitter (`jitter_ratio=0.25`) to `with_qnexus_retries` to prevent thundering-herd collisions on rate-limited or congested gateways.
  - Added an automated AST/source regression test (`test_no_deprecated_utcnow_in_repository`) guaranteeing zero deprecated naive `datetime.utcnow()` calls across the codebase.
- **Abstract Framing & Naming Unification (`OSIRIS-QEC-002` inside `osiris-qec`):**
  - Elevated the `16/16` post-preparation Pauli-Y/Z negative result (`16/16` detected via X-syndrome, **`0/16` preserve logical state**; *state preparation != QEC memory*) to the opening sentences of the Abstract across the PDF manuscript, LaTeX source, `README.md`, and `arXiv` cover package.
  - Unified protocol naming to **`OSIRIS-QEC-002`** within package `osiris-qec` (`hardware/experiment_manifest_v1_1_1.json`), explicitly distinguishing it from companion study **`OSIRIS-QEC-001`** (1D heavy-hex superconducting repetition codes, `10.5281/zenodo.24293756`), and corrected phrasing drift (`"Compilation and execution enforce a preregistered artifact lock"`).
- **`arXiv` (`quant-ph`) Submission Package:**
  - Added `submission/ARXIV_SUBMISSION.md` and self-contained `osiris-qec-v1.1.1-arxiv-quant-ph.tar.gz` (`ms.tex` + vector PDF figures).
  - Frozen circuit hashes (`b86aeabd...` and `02d5cb72...`) and prior Zenodo DOIs (`v1.0.0`: `10.5281/zenodo.24406733`; `v1.1.0`: `10.5281/zenodo.24421051`) remain 100% immutable.

## [1.1.0] - 2026-11-21

- Added register-collision hardening (`q`, `qr`, `quantum`, `c`, `creg`, `cl`, `classical`), metadata normalization, full `16/16` post-preparation Y-error sweep (`reports/POST_PREP_Y_SWEEP_V1_1.json`), `osiris qec` CLI (`verify`, `run`, `manifest`, `ledger`), write-ahead ledgering, and `qnexus 0.51.4` `optimisation_level=0` pre/post-compile hash-lock enforcement (`10.5281/zenodo.24421051`).

## [1.0.0] - 2026-11-20

- Initial public release and Zenodo publication (`10.5281/zenodo.24406733`, `ac668e4`) of the 20-qubit toroidal Wen-plaquette feed-forward preparation `pytket` `CustomPass`, independent GF(2) symplectic verifier (`[[16, 2, 4]]`), exact 256-branch enumerator, dual-basis Qiskit Aer cross-checks, noise benchmark, and frozen H2-1 ISA manifest (**HARDWARE-UNVALIDATED**).
