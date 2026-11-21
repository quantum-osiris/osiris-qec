# arXiv (`quant-ph`) Submission Metadata & Checklist — `OSIRIS-QEC-002` (`osiris-qec v1.1.1`)

- **Upload Archive:** `osiris-qec-v1.1.1-arxiv-quant-ph.tar.gz` (contains `ms.tex` + 3 vector PDF figures; zero external `.bib` dependencies)
- **Primary Category:** `quant-ph` (Quantum Physics)
- **Suggested Cross-Lists:** `cs.SE` (Software Engineering), `cs.ET` (Emerging Technologies)
- **License:** CC BY 4.0 (`http://creativecommons.org/licenses/by/4.0/`)

## Form Fields (Ready to Paste)

**Title:**
```text
State Preparation Is Not Quantum Memory: Exact 256-Branch Verification, 16/16 Post-Preparation Fault Taxonomy, Strict RFC 8785 Provenance, and Hash-Locked Quantinuum H2 Dispatch for [[16, 2, 4]] Wen-Plaquette Codes
```

**Authors:**
```text
Devin Phillip Davis (Agile Defense Systems LLC)
```

**Abstract (1582 / 1,920 characters):**
```text
Fault-tolerant state preparation in a topological stabilizer codespace is operationally distinct from a quantum error-correcting (QEC) memory. Studying the 20-qubit [[16, 2, 4]] periodic Wen-plaquette two-round measurement and 7-entry lookup-table (LUT) feed-forward preparation circuit (16 data qubits plus 4 recycled ancillas; prior art Iqbal et al., arXiv:2302.01917), we demonstrate that while weight-1 Pauli-Z faults injected before preparation are corrected 16/16 times (logical fidelity 1.0), complete 16/16 post-preparation Pauli-Y and Pauli-Z sweeps across all data qubits q[0..15] excite nonzero X-syndromes (16/16 detected) yet preserve the encoded logical state in 0/16 cases (F_L = 0.0 for Y; < 10^{-3} for Z), and X faults escape detection entirely because Z stabilizers are never measured. Around this scope boundary (benchmark OSIRIS-QEC-002, package osiris-qec v1.1.1; status HARDWARE-UNVALIDATED), compilation and execution enforce a preregistered artifact lock verifying both pre-compile and Quantinuum H2-1 ISA SHA-256 digests pre-flight and post-compile under optimisation_level=0. We contribute hardened pytket CustomPass register-collision and metadata-normalization contracts, exact non-sampled enumeration of all 256 syndrome branches (128 reachable even-parity branches landing in +1 codespace), dual-basis Qiskit Aer cross-checks, an atomic write-ahead execution ledger pinned exclusively to IETF RFC 8785 (rfc8785==0.1.4), and qnexus 0.51.4 transport with Retry-After and jittered backoff governed by a per-basis 95% Wilson lower confidence bound > 0.99.
```

**Comments:**
```text
4 pages, 3 vector figures, 3 tables. Benchmark OSIRIS-QEC-002 (package osiris-qec v1.1.1). Status: HARDWARE-UNVALIDATED (exact 256-branch simulation, 16/16 fault taxonomy, offline Quantinuum H2-1 ISA compilation, and preregistered execution protocol; zero provider jobs submitted). Source and verification harness: https://github.com/quantum-osiris/osiris-qec (tag v1.1.1)
```

**Report-no:**
```text
OSIRIS-QEC-002
```

**DOI:**
```text
10.5281/zenodo.24424726
```
