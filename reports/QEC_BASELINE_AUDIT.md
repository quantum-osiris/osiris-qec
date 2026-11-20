# QEC Baseline Audit (Phase 0)

## 0. Repository ground truth
- repo: /home/osiris
- HEAD: HEAD
- branch: main
- git status tally (code: count): {'AM': 296, 'A': 113802, 'AD': 29, 'Am': 1, '??': 1468} (115596 entries; full listing intentionally not embedded)

## 0.1 Environment versions
- pytket 2.18.5
- pytket-qiskit 0.79.0
- pytket-quantinuum 0.59.3
- qiskit 2.6.2
- qiskit-aer 0.18.4
- numpy 2.5.5
- pytest 9.2.0

## 0.2 Implementation under review
- The `WenPlaquetteFeedForwardPass` / `dnalang_wen_plaquette_pass.py` implementation does NOT
  exist anywhere in the local git repository or its 171 mirrored legacy repos; the only copy was
  the pasted source, vendored verbatim as `qec/dnalang_wen_plaquette_pass.py` (baseline, untouched).
- Corrected module: `qec/wen_plaquette_pass.py` (adds the enforced preparation-only contract).

## 1. Mathematical specification (independently derived from the lattice)
- Lattice: 4x4 periodic (toroidal); qubit (r,c) -> index 4r+c; 16 data qubits.
- Plaquettes: checkerboard, Z-type on (r+c) even, X-type on (r+c) odd; all weight 4 (no boundary plaquettes -> toric-type boundaries).
- Generators listed in module: 16 (8 X-type, 8 Z-type); ALL pure X or Z type: True.
- Module's WEN_STABILIZERS == independent checkerboard derivation: True (derived=16 listed=16 equal=True).
- Pairwise commutation of all 16 generators: True (verified by symplectic inner product).
- Independent stabilizer rank (GF(2)): 14 -> encoded logical qubits k = 16 - 14 = **2**.
- Logical operators of weight <= 3 (exhaustive enumeration): 0 found -> d=4 (no nontrivial logical of weight <= 3; row/col strings have weight 4).
- Logical representatives (row/column strings, weight 4, commute with all, not in stabilizer group):
  X_L_row0, X_L_col0, Z_L_row0, Z_L_col0.

## 2. Classification
This is a **Wen-plaquette (checkerboard) CSS code on a 4x4 torus**, k=2, distance d=4.
It is NOT a boundary surface code (all stabilizers weight 4, periodic boundaries) and not
qubit-count-equivalent to the 32-qubit toric code; it is the vertex-qubit checkerboard model.

## 3. Implemented protocol (what the pass actually does)
- 20 qubits total: 16 data + 4 ancilla (q[16..19]), ancillas reused across rounds via Reset.
- Measures ONLY the 8 X-type generators, in 2 rounds of 4 (round 1: plaquettes [4, 6, 12, 14],
  round 2: [1, 3, 9, 11]); the 8 Z-type generators are NEVER measured.
- Round-1 feed-forward: single conditional Z per plaquette (see table below).
- Round-2 feed-forward: 4-bit LUT over (A1,A3,A9,A11), big-endian string -> reversed-int condition_value (little-endian TKET).
- Final: barrier + destructive X-basis measurement of the 16 data qubits into c5_end.
- Initial-state assumption: input must be |0>^16 on data qubits (all Z generators already +1);
  the pass enforces an empty input circuit but the |0> assumption is implicit in the physics.

## 4. Independent LUT verification (syndrome of each correction computed from supports)
| syndrome_be | Z correction on | computed syndrome | matches | disturbs round-1 plaquettes |
|---|---|---|---|---|
| 0011 | [10, 11] | 0011 | True | [] |
| 0101 | [4, 8] | 0101 | True | [] |
| 0110 | [0, 13] | 0110 | True | [] |
| 1001 | [2, 15] | 1001 | True | [] |
| 1010 | [5, 9] | 1010 | True | [] |
| 1100 | [6, 7] | 1100 | True | [] |
| 1111 | [2, 3, 14, 15] | 1111 | True | [] |
All LUT entries independently consistent (syndrome matches key, round-1 plaquettes undisturbed): **True**.

## 5. Round-1 correction audit
[
 {
  "stab_idx": 4,
  "stab": "X(4, 5, 8, 9)",
  "correction_Z_on": 5,
  "ancilla": 16,
  "c_bit": 0,
  "target_in_support": true,
  "flips_X_plaquettes": [
   1,
   4
  ]
 },
 {
  "stab_idx": 6,
  "stab": "X(6, 7, 10, 11)",
  "correction_Z_on": 7,
  "ancilla": 17,
  "c_bit": 1,
  "target_in_support": true,
  "flips_X_plaquettes": [
   3,
   6
  ]
 },
 {
  "stab_idx": 12,
  "stab": "X(12, 13, 0, 1)",
  "correction_Z_on": 13,
  "ancilla": 18,
  "c_bit": 2,
  "target_in_support": true,
  "flips_X_plaquettes": [
   9,
   12
  ]
 },
 {
  "stab_idx": 14,
  "stab": "X(14, 15, 2, 3)",
  "correction_Z_on": 15,
  "ancilla": 19,
  "c_bit": 3,
  "target_in_support": true,
  "flips_X_plaquettes": [
   11,
   14
  ]
 }
]

## 6. Syndrome-to-correction mapping summary
- Round 1: syndrome bit "1" on a c*_1st register -> conditional Z; mapping: {'c0_1st': 5, 'c1_1st': 7, 'c2_1st': 13, 'c3_1st': 15} (each correction flips its own plaquette back and exactly one round-2 plaquette, which the round-2 LUT then accounts for).
- Round 2: 7-entry even-parity LUT (all weight-2 syndromes + 1111). Odd-parity round-2 syndromes receive NO correction; by the torus parity argument (product of all 8 X generators = identity) the round-2 syndrome is always even when starting from a state with even total X-parity, so all reachable branches are covered.

## 7. Known limitations recorded at baseline
- X/Y errors on data qubits flip Z-type generators, which are never measured -> undetectable by this circuit (tested in Phase 3).
- This is a state-PREPARATION circuit, not a QEC memory: there are no repeated syndrome rounds after preparation.
- DD options in the capsule are inert metadata, not applied by the pass.
