# `osiris-qec` (`OSIRIS-QEC-002`) — 20-Qubit Toroidal Wen-Plaquette Feed-Forward Preparation & Hash-Locked H2 Dispatch (`v1.1.1`)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24424726.svg)](https://doi.org/10.5281/zenodo.24424726) [![Baseline v1.0.0 DOI](https://img.shields.io/badge/v1.0.0_baseline-10.5281%2Fzenodo.24406733-blue)](https://doi.org/10.5281/zenodo.24406733) [![Release](https://img.shields.io/badge/release-v1.1.1-blue)](https://github.com/quantum-osiris/osiris-qec/releases/tag/v1.1.1) ![Status](https://img.shields.io/badge/status-HARDWARE--UNVALIDATED-amber)

Rigorously tested, provenance-locked compiler, verification, and hardware-dispatch package (**benchmark `OSIRIS-QEC-002`**, repository `osiris-qec`; companion to the 1D superconducting repetition-code hardware study **`OSIRIS-QEC-001`** at [`10.5281/zenodo.24293756`](https://doi.org/10.5281/zenodo.24293756)).

## Headline Scientific Scope Boundary: State Preparation != QEC Memory

Fault-tolerant preparation of a stabilizer codespace is operationally distinct from a quantum error-correcting memory:
- **Pre-preparation weight-1 `Z` faults (`q[0..15]`):** **`16/16` corrected** (`logical_fidelity = 1.0`).
- **Post-preparation weight-1 `Y` (`16/16` sweep) & `Z` (`16/16` sweep) faults:** **`16/16` detected** via nonzero X-syndrome, yet **`0/16` preserve the encoded logical state** (`F_L = 0.0` for `Y`; `< 10^-3` for `Z`) because no syndrome round follows preparation.
- **Pre- and post-preparation `X` faults:** **Undetected** (`Z` stabilizers are never measured).

## Archive & Provenance Chain

- **Zenodo `v1.1.1` Preprint & Archive:** <https://doi.org/10.5281/zenodo.24424726> (Concept DOI: <https://doi.org/10.5281/zenodo.24406732>; `v1.1.0`: <https://doi.org/10.5281/zenodo.24421051>; immutable `v1.0.0` baseline: <https://doi.org/10.5281/zenodo.24406733>)
- **Standalone `v1.1.1` Manuscript & `arXiv` Guide:** [`paper/wen_plaquette_feedforward_qec_v1_1_1.pdf`](paper/wen_plaquette_feedforward_qec_v1_1_1.pdf) ([LaTeX](paper/wen_plaquette_feedforward_qec_v1_1_1.tex), [`ARXIV_SUBMISSION.md`](submission/ARXIV_SUBMISSION.md), [`SHA256SUMS.txt`](paper/SHA256SUMS.txt))
- **Prior Art:** Underlying 4×4 Wen-plaquette 2-round LUT protocol credited to Iqbal *et al.* (`arXiv:2302.01917`) and Quantinuum's feed-forward tutorial (**`HARDWARE-UNVALIDATED`** — zero live provider jobs submitted).

## Hardware Allocation & Preregistered Artifact Lock

- **Logical Lattice (`16` data qubits):** `q[0..15]` implement the `[[16, 2, 4]]` periodic checkerboard Wen-plaquette encoding (`k = 2` logical qubits, exact distance `d = 4`).
- **Syndrome Resources (`4` ancilla qubits):** `q[16..19]` are recycled across two X-stabilizer rounds via mid-circuit `Reset` (full circuit: **`24 Measure`**, **`8 Reset`**, **`20 Conditional`**). **Ancilla qubits do not contribute to logical code distance.**
- **Preregistered Artifact Lock:** Compilation and execution enforce a preregistered artifact lock. The pre-compile circuit SHA-256 (`b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`) and Quantinuum H2-1 ISA SHA-256 (`02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`, depth `19`, `32 ZZPhase`) are verified immediately prior to execution and re-verified post-compile under `optimisation_level=0`. Any mismatch invalidates the run and aborts submission (`EXIT 1`, fail closed).
- **Pinned Normative RFC 8785 Ledger:** Execution records are serialized exclusively through `rfc8785==0.1.4` (no stdlib `json.dumps` fallback), guaranteeing third-party IEEE-754 float canonicalization parity.

## Reference CLI Usage (`osiris qec`)

```bash
# 1. Validate frozen v1.0.0, v1.1.0, and v1.1.1 artifact hashes (fail-closed exit 1 on mismatch)
osiris qec verify --manifest hardware/experiment_manifest_v1_0_0.json
osiris qec verify --manifest hardware/experiment_manifest_v1_1_1.json --strict

# 2. Local Selene validation (verifies Reset, LUT branches, syndromes & strict rfc8785 WAL)
osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_1.json

# 3. Verify & summarize RFC 8785 hash-chained execution ledger
osiris qec ledger verify ledger/run-*.json
osiris qec ledger show ledger/run-*.json --summary

# 4. Authorized Quantinuum H2-1 submission (requires out-of-band QNEXUS_TOKEN / `qnx login`)
osiris qec run --target h2-1 --shots 5000 --manifest hardware/experiment_manifest_v1_1_1.json

# 5. Full automated regression & verification suite (85 tests)
pytest -q
```

No credentials are stored or committed anywhere in this repository; see [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) and [`CHANGELOG.md`](CHANGELOG.md).
