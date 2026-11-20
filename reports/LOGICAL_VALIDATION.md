# Logical Validation (Phase 4)

## Code
4x4 toroidal Wen-plaquette (checkerboard) CSS code: 16 data qubits, stabilizer rank 14,
k = 2 logical qubits, distance d = 4 (verified by exhaustive enumeration up to weight 3).

## What the circuit prepares
The preparation circuit fixes all 16 stabilizers to +1 (Z-type from |0>^16 input,
X-type by measurement + feed-forward). Since k=2, fixing all stabilizers still leaves a
4-dimensional codespace; the LUT corrections select ONE specific state in it.

- All-256-branch codespace membership: see tests/test_qec_behavior.py (exact enumeration).
- Branch-to-branch state fidelity (measurement outcomes (1,0,1,1,0,1,1,0), (0,1,0,1,1,0,1,1),
  (1,1,1,1,1,1,1,1) vs all-zero branch): [((0, 0, 0, 0, 0, 0, 1, 1), 0.9999999999999885), ((0, 0, 0, 0, 0, 1, 0, 1), 0.9999999999999885), ((0, 0, 0, 0, 0, 1, 1, 0), 0.9999999999999885), ((0, 0, 0, 0, 1, 0, 0, 1), 0.9999999999999885), ((0, 0, 0, 0, 1, 0, 1, 0), 0.9999999999999885)] -> the prepared state is
  INDEPENDENT of the measurement branch (feed-forward works as designed).

## Logical observables of the prepared state
{
 "X_L_row0": 0.0,
 "X_L_col0": 0.0,
 "Z_L_row0": 0.9999999999999942,
 "Z_L_col0": 0.9999999999999942
}
The prepared state is a fixed logical state (all logical Z-type representatives +1,
i.e. a computational-basis logical state in the Z_L basis; X_L expectations are 0
because no logical-X preparation is performed).

## Logical-state preservation
- Weight-1 Z error injected before preparation, then feed-forward: fidelity to prepared
  logical state = 1.000000 -> PRESERVED (corrected).
- Weight-1 X error injected before preparation: fidelity = 0.000000 -> NOT preserved;
  X errors flip Z-type stabilizers which this circuit never measures -> UNDETECTED.

## Honest limitation
This circuit prepares ONE fixed logical state. It does NOT encode arbitrary logical
states or superpositions, and it is NOT a fault-tolerant quantum memory (no repeated
syndrome rounds after preparation; post-preparation errors are unprotected).
To encode arbitrary logical states you would need logical-state injection (e.g. prepare
logical X eigenstates via transversal/lattice-surgery methods or by measuring logical
operators), plus full X- and Z-syndrome rounds for error correction. Those are engineering
extensions, not present in the baseline implementation.
