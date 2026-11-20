# Clean Regression Run (final gate record)

- **Command:** `cd /home/osiris/qec && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /tmp/qcheck/bin/python -m pytest tests/ -q --tb=short`
- **Date (UTC):** 2026-11-20T18:12:49Z
- **Result:** 33 passed, 0 failed — `PYTEST_EXIT=0` (raw log: /tmp/review/pytest_clean2.log)
- **Environment:** Python 3.14.6, pytket 2.18.5, pytket-qiskit 0.79.0, pytket-quantinuum 0.59.3,
  qnexus 0.51.4, qiskit 2.6.2, qiskit-aer 0.18.4, numpy 2.5.5, pytest 9.2.0 (venv /tmp/qcheck)
- **Test inventory:** 9 compiler-contract + 3 pre-prep error injection + 3 post-prep injection
  + 18 behavior (incl. 7 parametrized LUT syndromes, dual-basis Aer cross-checks) = 33

## Post-preparation error classification (reports/POST_PREP_INJECTION.json, 23 records)
| Injection | Classification | Count |
|---|---|---|
| Z on data qubit AFTER prep | detected by X-syndrome, NOT corrected (no post-prep syndrome round) | 16 |
| Z on data qubit BEFORE prep (contrast) | corrected by feed-forward (fidelity 1.0) | 1 |
| X on data qubit AFTER prep | UNDETECTED (X-syndrome zero; Z-syndrome nonzero but never measured) | 3 |
| Y on data qubit AFTER prep | partially detected (X-syndrome nonzero), NOT corrected; Z-syndrome unmeasured | 3 |

Successful state preparation is NOT equated with post-preparation error correction anywhere
in the package; the circuit is a preparation circuit, not a QEC memory.

## Acceptance thresholds for hardware gate (verified numerically, z=1.959964)
95% Wilson lower bound > 0.99 requires, per basis run:
n=512 -> 512/512; n=1000 -> 997; n=2000 -> 1989; n=5000 -> 4964; n=10000 -> 9920.

## Status
HARDWARE-UNVALIDATED. Next gate: qnexus syntax check on H2-1SC after authorization
(circuit hashes frozen in hardware/experiment_manifest.json). No jobs submitted; no
credentials used.
