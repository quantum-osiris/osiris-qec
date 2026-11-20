# Reproducibility

## Environment (exact)
- Python 3.14.6 (uv-managed), venv at /tmp/qcheck
- pytket 2.18.5, pytket-qiskit 0.79.0, pytket-quantinuum 0.59.3,
  qiskit 2.6.2, qiskit-aer 0.18.4, numpy 2.5.5, pytest 9.2.0, matplotlib 3.11.2
- Install: `uv venv /tmp/qcheck && uv pip install --python /tmp/qcheck/bin/python \
  pytket pytket-qiskit pytket-quantinuum qiskit qiskit-aer numpy pytest matplotlib`

## Commands (from qec/)
```bash
/tmp/qcheck/bin/python -m pytest tests/ -q                 # 28 tests
/tmp/qcheck/bin/python audit_baseline.py                    # reports/QEC_BASELINE_AUDIT.md
/tmp/qcheck/bin/python logical_validation.py                # reports/LOGICAL_VALIDATION.md
/tmp/qcheck/bin/python benchmarks/qec_noise_benchmark.py   # reports/QEC_BENCHMARK_RESULTS.{json,png}
/tmp/qcheck/bin/python hardware/quantinuum_h2.py            # reports/H2_COMPATIBILITY.md + manifest
/tmp/qcheck/bin/python verify_independent.py                # reports/INDEPENDENT_VERIFICATION.md
```

## Seeds
- tests/test_qec_behavior.py: run_shots seed=101; branch enumeration is exhaustive (no seed).
- tests/test_error_injection.py: seeds 1000+q (single-qubit), 2000+.. (weight-2), 3000/3001 (ancilla); 16 shots per case.
- benchmarks/qec_noise_benchmark.py: seeds 11, 22, 33; 60 shots per (p, seed, mode); p in {0, 1e-4, 1e-3, 5e-3, 1e-2}.
- Aer cross-check: AerBackend, 512 shots, no seed needed (distribution check).

## Determinism
- Circuit generation is deterministic: identical SHA-256 across builds (tested).
- Capsule hash includes a UTC timestamp by design; circuit hashes do not.
- Simulator is an exact statevector method with explicit branch control;
  sampled tests use the seeds above.

## Hardware
- No jobs submitted. Offline compile only (QuantinuumAPIOffline). Credentials are
  never stored, printed, or committed.
