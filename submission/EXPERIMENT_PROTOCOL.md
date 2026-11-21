# Experiment Protocol — Wen-Plaquette Feed-Forward Preparation on Quantinuum H2 (`OSIRIS-QEC-002`, `osiris-qec v1.1.1`)

**Status: HARDWARE-UNVALIDATED.** All results so far are local exact simulation + offline
ISA compilation. No syntax-checker, emulator, or hardware job has been submitted.

> **Preregistered Artifact Lock (Mandatory Gate):**
> Compilation and execution enforce a preregistered artifact lock. The pre-compile circuit SHA-256 (`b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`) and Quantinuum H2-1 ISA SHA-256 (`02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`) are verified immediately prior to execution and re-verified post-compile on Quantinuum Nexus under `optimisation_level=0`. Any mismatch invalidates the run and aborts submission (`EXIT 1`, fail closed). Any protocol modification affecting compilation, shot accounting, post-selection, or confidence estimation requires a new manifest version and new artifact hashes.

**Provenance & Naming:**
- **Package / Repository:** `osiris-qec` (`v1.1.1`)
- **Protocol Identifier:** **`OSIRIS-QEC-002`** (*20-Qubit Toroidal Wen-Plaquette Feed-Forward State Preparation*; distinct from companion study **`OSIRIS-QEC-001`** on 1D heavy-hex superconducting repetition codes, `10.5281/zenodo.24293756`).
- **Prior Art:** The underlying 4×4 Wen-plaquette 2-round LUT preparation protocol is prior art — `arXiv:2302.01917` (Iqbal *et al.*, Quantinuum H1) and Quantinuum's tutorial *"Topological Order from Measurements and Feed-Forward"*. This package contributes the contract-hardened `pytket` `CustomPass`, independent symplectic derivation, exact 256-branch verification, complete 16/16 pre/post-prep fault taxonomy, strict IETF RFC 8785 (`rfc8785==0.1.4`) write-ahead execution ledgering, and hash-locked `osiris qec` dispatch. Immutable prior versions: `v1.0.0` (`10.5281/zenodo.24406733`, `ac668e4`) and `v1.1.0` (`10.5281/zenodo.24421051`, `58ca7b1`).

## Objective & Scope Boundary (State Preparation != QEC Memory)
Demonstrate, on Quantinuum System Model H2, that the 20-qubit Wen-plaquette
feed-forward preparation circuit (`WenPlaquetteFeedForwardPass`, `osiris-qec`)
prepares the fixed `+1` codespace logical state `|00>_L` of the 4×4 toroidal
Wen-plaquette CSS code (`[[16, 2, 4]]`: 16 data qubits, `k=2`, `d=4`), using
2 rounds of mid-circuit X-stabilizer measurement with 4 recycled ancillas
(`24 Measure`, `8 Reset`; ancillas do not contribute to logical code distance)
and classical feed-forward (4 single-bit conditional Z + 7-entry 4-bit LUT).
This single-shot preparation circuit is **not** a quantum error-correcting memory:
16/16 post-preparation `Y` and `Z` faults excite nonzero X-syndromes yet **0/16**
preserve the logical state (`F_L = 0.0` for `Y`, `< 10^{-3}` for `Z`).

## Preconditions (all verified locally before any submission)
1. Pre-flight hash gate passes (`osiris qec verify --manifest hardware/experiment_manifest_v1_1_1.json --strict`):
   - Pre-compile SHA-256: `b86aeabd70eecb7f5fbca5d0e1688e06d71dc358fd9fbaaab7fd8e4f9634230b`
   - H2-1 ISA SHA-256: `02d5cb72849f9b473c022e68023486fdecc8c9f7fc3da9a9a9299c3482f31062`
2. Local offline compile to H2 ISA (`hardware/quantinuum_h2.py`):
   depth 19, 32 `ZZPhase`, 72 `PhasedX`, 20 `Rz`, 20 `Conditional`, 24 `Measure`, 8 `Reset`,
   20/56 qubits, 28/4000 clbits.
3. Noiseless simulation (exact enumeration of all 256 syndrome branches, dual-basis
   `AerBackend` cross-check, 16/16 pre-prep Z & post-prep Z/Y sweeps, and Selene
   dry-run `osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_1.json`)
   confirms codespace preparation and write-ahead RFC 8785 (`rfc8785==0.1.4`) ledger integrity.

## Procedure (current submission path: `osiris qec` / `qnexus 0.51.4`)
The legacy Quantinuum API is sunset and `pytket-quantinuum`'s submission API is
retired (`docs.quantinuum.com/product-updates`). All submissions use `qnexus 0.51.4`
via `osiris_cli/qnexus_client.py` with `optimisation_level=0`, `QuantinuumConfig(device_name=..., no_opt=True)`,
post-compile SHA-256 verification before `start_execute_job`, `Retry-After` + jittered
exponential backoff for transient gateway congestion, and strict `rfc8785` write-ahead
ledger entries (`ledger/run-<id>.json`):

1. Local Selene validation (zero hardware submission):
   `osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_1.json`
2. Syntax-check on `H2-1SC` (1 shot, 0 HQC) via `qnexus`. Abort on failure or hash drift.
3. Emulator `H2-1E`: >= 1,000 shots (recommend 10,000) across both `X` and `Z` destructive readout settings plus no-feed-forward control.
4. Hardware `H2-1` (ONLY with separate explicit human authorization):
   `osiris qec run --target h2-1 --shots 5000 --manifest hardware/experiment_manifest_v1_1_1.json`
   followed by `osiris qec ledger verify ledger/run-*.json`.

## Acceptance criteria (statistically strict, frozen)
- `H2-1SC` passes via `qnexus` with zero ISA hash drift.
- For each basis run (X and Z independently): the **95% Wilson lower confidence bound**
  on the parity-success fraction exceeds `0.99` (`z = 1.959964`):

  | Shots per basis | Minimum successes | Maximum failures |
  | --------------- | ----------------- | ---------------- |
  | 512             | 512               | 0                |
  | 1,000           | 997               | 3                |
  | 2,000           | 1,989             | 11               |
  | 5,000           | 4,964             | 36               |
  | 10,000          | 9,920             | 80               |

- Feed-forward conditionals present and exercised (multiple distinct `c4_2nd` values).
- Write-ahead and completion entries pass `osiris qec ledger verify` under `rfc8785`.

## Stopping conditions
- Any pre-compile or H2-1 ISA SHA-256 mismatch -> immediate abort (`EXIT 1`), forensic ledger entry written, zero jobs submitted.
- Syntax check failure -> fix under a new manifest version, never overwrite frozen hashes.
- Emulator parity-violation rate > 5% at 1,000 shots -> stop, investigate.
- No hardware submission without explicit authorization; no credentials are stored in this package.
