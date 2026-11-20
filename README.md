# OSIRIS Quantum QEC — Wen-Plaquette Feed-Forward Preparation Package

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24406733.svg)](https://doi.org/10.5281/zenodo.24406733) [![Release](https://img.shields.io/badge/release-v1.0.0-blue)](https://github.com/quantum-osiris/osiris-qec/releases/tag/v1.0.0) ![Status](https://img.shields.io/badge/status-HARDWARE--UNVALIDATED-amber)

- **Preprint & Evidence Archive (Zenodo):** <https://doi.org/10.5281/zenodo.24406733>
- **Standalone Manuscript:** [`paper/wen_plaquette_feedforward_qec_v1.pdf`](paper/wen_plaquette_feedforward_qec_v1.pdf) ([LaTeX source](paper/wen_plaquette_feedforward_qec_v1.tex), [`SHA256SUMS.txt`](paper/SHA256SUMS.txt))
- **Scope & Provenance:** Prior-art 4x4 Wen-plaquette 2-round LUT protocol credited to Iqbal et al. (`arXiv:2302.01917`) and Quantinuum's feed-forward tutorial; this package provides the contract-enforced `pytket` `CustomPass`, exact 256-branch statevector verification, pre/post-preparation error taxonomy (`33/33` tests passing), reproducible noise benchmarks, and frozen Quantinuum H2 / `qnexus` 0.51.4 protocol (**HARDWARE-UNVALIDATED** — no provider jobs submitted).

Rigorously tested, reproducible package built around a 20-qubit Wen-plaquette
syndrome-measurement + lookup-table feed-forward preparation circuit, implemented
as a pytket `CustomPass`.

## Layout

```
qec/
├── dnalang_wen_plaquette_pass.py   # vendored ORIGINAL baseline (untouched, for comparison)
├── wen_plaquette_pass.py           # corrected pass: enforced preparation-only contract
├── qec_math.py                     # independent lattice derivation: stabilizers, rank, distance
├── qec_sim.py                      # exact 20-qubit statevector simulator (mid-circuit meas., FF)
├── qec_verify.py                   # branch enumeration, Aer cross-check, shot runners
├── audit_baseline.py               # Phase 0 -> reports/QEC_BASELINE_AUDIT.md
├── logical_validation.py           # Phase 4 -> reports/LOGICAL_VALIDATION.md
├── verify_independent.py           # Phase 7 -> reports/INDEPENDENT_VERIFICATION.md
├── tests/
│   ├── test_compiler_pass.py       # Phase 1: transformation contract regression tests
│   ├── test_qec_behavior.py        # Phase 2: behavioral verification (exact branch enumeration)
│   └── test_error_injection.py     # Phase 3 -> reports/ERROR_CORRECTION_MATRIX.json
├── benchmarks/qec_noise_benchmark.py  # Phase 5 -> reports/QEC_BENCHMARK_RESULTS.json/.png
├── hardware/quantinuum_h2.py       # Phase 6: local H2-1 compile (offline) + manifest
│   └── experiment_manifest.json    #   hardware execution manifest (NOT submitted)
├── reports/                        # audit, benchmark, verification reports
└── submission/                     # Phase 8: technical report, protocol, reproducibility, claims
```

## Environment (recorded)

- Python 3.14.6, pytket 2.18.5, pytket-qiskit 0.79.0, pytket-quantinuum 0.59.3,
  qiskit 2.6.2, qiskit-aer 0.18.4, qnexus 0.51.4, numpy 2.5.5, pytest 9.2.0, matplotlib 3.11.2
- venv: `/tmp/qcheck` (uv-created)

## Run

```bash
cd qec
/tmp/qcheck/bin/python -m pytest tests/ -q          # full test suite
/tmp/qcheck/bin/python audit_baseline.py             # Phase 0 report
/tmp/qcheck/bin/python logical_validation.py         # Phase 4 report
/tmp/qcheck/bin/python benchmarks/qec_noise_benchmark.py   # Phase 5 (background, ~10 min)
/tmp/qcheck/bin/python hardware/quantinuum_h2.py     # Phase 6 local H2 compile + manifest
/tmp/qcheck/bin/python verify_independent.py         # Phase 7 verifier + negative tests
```

No credentials are used anywhere; no jobs are submitted. Hardware execution requires
explicit authorization and runtime-supplied credentials (see hardware/experiment_manifest.json).
