# OSIRIS Quantum QEC — Wen-Plaquette Feed-Forward Preparation & Hash-Locked H2 Dispatch (`v1.1.0`)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24421051.svg)](https://doi.org/10.5281/zenodo.24421051) [![Baseline v1.0.0 DOI](https://img.shields.io/badge/v1.0.0_baseline-10.5281%2Fzenodo.24406733-blue)](https://doi.org/10.5281/zenodo.24406733) [![Release](https://img.shields.io/badge/release-v1.1.0-blue)](https://github.com/quantum-osiris/osiris-qec/releases/tag/v1.1.0) ![Status](https://img.shields.io/badge/status-HARDWARE--UNVALIDATED-amber)

Rigorously tested, provenance-locked package built around a 20-qubit toroidal Wen-plaquette syndrome-measurement + lookup-table (LUT) feed-forward state-preparation circuit, implemented as a hardened `pytket` `CustomPass` with an RFC 8785 write-ahead execution ledger and fail-closed `osiris qec` CLI for local Selene validation and Quantinuum H2-1 dispatch.

- **Zenodo `v1.1.0` Preprint & Archive:** <https://doi.org/10.5281/zenodo.24421051> (Concept DOI: <https://doi.org/10.5281/zenodo.24406732>; immutable `v1.0.0` baseline: <https://doi.org/10.5281/zenodo.24406733>)
- **Standalone `v1.1.0` Manuscript:** [`paper/wen_plaquette_feedforward_qec_v1_1.pdf`](paper/wen_plaquette_feedforward_qec_v1_1.pdf) ([LaTeX source](paper/wen_plaquette_feedforward_qec_v1_1.tex), [`SHA256SUMS.txt`](paper/SHA256SUMS.txt))
- **Provenance:** Prior-art 4x4 Wen-plaquette 2-round LUT protocol credited to Iqbal *et al.* (`arXiv:2302.01917`) and Quantinuum's feed-forward tutorial; this package provides the contract-hardened `pytket` `CustomPass`, independent GF(2) symplectic derivation, exact 256-branch verification, complete 16/16 pre/post-prep fault taxonomy, RFC 8785 write-ahead ledger, and hash-locked Quantinuum H2 / `qnexus 0.51.4` dispatch (**`HARDWARE-UNVALIDATED`** — no live provider jobs submitted).

## Hardware Allocation & Preregistered Artifact Lock

- **Logical Lattice (`16` data qubits):** `q[0..15]` implement the `[[16, 2, 4]]` periodic checkerboard Wen-plaquette encoding (`k = 2` logical qubits, exact distance `d = 4`).
- **Syndrome Resources (`4` ancilla qubits):** `q[16..19]` are reused across two X-stabilizer extraction rounds via mid-circuit recycle (observed operations across full circuit: **`24 Measure`**, **`8 Reset`**, **`20 Conditional`**). **Ancilla qubits do not contribute to logical code distance.**
- **Preregistered Artifact Lock:** Compilation and execution use a preregistered artifact lock. The pre-compile circuit SHA-256 (`b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`) and Quantinuum H2-1 ISA SHA-256 (`02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`, depth `19`, `32 ZZPhase`) are verified immediately prior to execution and re-verified post-compile under `optimisation_level=0`. Any mismatch invalidates the run and aborts submission (`EXIT 1`, fail closed).

## Layout

```
qec/
├── wen_plaquette_pass.py               # v1.1.0 hardened pass (register collision & metadata lock)
├── dnalang_wen_plaquette_pass.py       # vendored ORIGINAL baseline (untouched, for comparison)
├── osiris_qec/                         # canonical package namespace + 16/16 post-prep Y-sweep
├── osiris_cli/
│   ├── qec_runner.py                   # `osiris qec {verify,run,manifest,ledger}` CLI
│   ├── ledger.py                       # RFC 8785 canonical JSON + SHA-256 hash-chained WAL
│   └── qnexus_client.py                # hash-locked qnexus 0.51.4 transport + backoff retries
├── qec_math.py                         # independent lattice derivation: stabilizers, rank, distance
├── qec_sim.py                          # exact 20-qubit statevector simulator (mid-circuit meas., FF)
├── qec_verify.py                       # 256-branch enumeration, dual-basis Aer cross-check
├── hardware/
│   ├── experiment_manifest_v1_0_0.json # immutable v1.0.0 baseline manifest
│   ├── experiment_manifest_v1_1_0.json # v1.1.0 hash-locked & compiler-locked manifest
│   ├── ledger_schema_v1_1_0.json       # JSON Schema for RFC 8785 execution ledger entries
│   └── hashlock_policy_v1_1_0.md       # fail-closed pre/post-compile hash-lock specification
├── tests/                              # 33 baseline tests + 16/16 Y-sweep + hash-lock + mock QNexus
├── reports/                            # audit, benchmark, 16/16 fault-taxonomy & verification JSON/MD
├── paper/                              # standalone 4-page preprint PDF, LaTeX, SVG/PDF figures & sums
└── submission/                         # technical report, protocol, reproducibility & Zenodo receipts
```

## Reference CLI Usage (`osiris qec`)

```bash
# 1. Validate frozen v1.0.0 and v1.1.0 artifact hashes (fail-closed exit 1 on mismatch)
osiris qec verify --manifest hardware/experiment_manifest_v1_0_0.json
osiris qec verify --manifest hardware/experiment_manifest_v1_1_0.json --strict

# 2. Inspect manifest hashes
osiris qec manifest --file hardware/experiment_manifest_v1_1_0.json --show-hashes

# 3. Local Selene validation (verifies Reset, LUT branches, syndromes & RFC 8785 WAL; zero hardware calls)
osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_0.json

# 4. Verify & summarize RFC 8785 hash-chained execution ledger
osiris qec ledger verify ledger/run-*.json
osiris qec ledger show ledger/run-*.json --summary

# 5. Authorized Quantinuum H2-1 submission (requires out-of-band QNEXUS_TOKEN / `qnx login`)
osiris qec run --target h2-1 --shots 5000 --manifest hardware/experiment_manifest_v1_1_0.json

# 6. Full automated regression & verification suite
pytest -q
```

No credentials are stored or committed anywhere in this repository; see [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) and [`CHANGELOG.md`](CHANGELOG.md).
