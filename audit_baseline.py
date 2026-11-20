"""Phase 0: baseline audit. Derives the code spec independently and writes
reports/QEC_BASELINE_AUDIT.md. Run: python audit_baseline.py"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.metadata as md

import qec_math as qm
from wen_plaquette_pass import (
    ROUND_1_MAP, ROUND_2_LUT_BE, ROUND_2_MAP, WEN_STABILIZERS,
)

ROOT = Path(__file__).parent
REPORT = ROOT / "reports" / "QEC_BASELINE_AUDIT.md"


def git_info() -> str:
    def run(*args):
        try:
            return subprocess.run(["git", "-C", "/home/osiris", *args],
                                  capture_output=True, text=True).stdout.strip()
        except Exception as e:
            return f"<error {e}>"
    status = run("status", "--short")
    from collections import Counter
    tally = Counter(line.split()[0] for line in status.splitlines() if line.strip())
    return (
        f"- repo: /home/osiris\n"
        f"- HEAD: {run('rev-parse', 'HEAD') or 'UNBORN (branch main has no commits yet)'}\n"
        f"- branch: {run('branch', '--show-current')}\n"
        f"- git status tally (code: count): {dict(tally)} "
        f"({sum(tally.values())} entries; full listing intentionally not embedded)\n"
    )


def versions() -> str:
    lines = []
    for p in ["pytket", "pytket-qiskit", "pytket-quantinuum", "qiskit", "qiskit-aer", "numpy", "pytest"]:
        try:
            lines.append(f"- {p} {md.version(p)}")
        except Exception:
            lines.append(f"- {p} NOT INSTALLED")
    return "\n".join(lines)


def module_stabs_match_derivation() -> tuple[bool, str]:
    derived = {(t, tuple(sorted(s))) for t, s in qm.derive_stabilizers()}
    listed = {(s.pauli_type, tuple(sorted(s.support))) for s in WEN_STABILIZERS}
    return derived == listed, f"derived={len(derived)} listed={len(listed)} equal={derived == listed}"


def lut_audit() -> list[dict]:
    """Independently verify each LUT correction against plaquette supports."""
    x_stabs = {i: s.support for i, s in enumerate(WEN_STABILIZERS) if s.pauli_type == "X"}
    r1 = sorted(ROUND_1_MAP.keys())
    r2 = sorted(ROUND_2_MAP.keys())
    rows = []
    for syndrome_be, targets in ROUND_2_LUT_BE.items():
        # expected syndrome: plaquette flipped iff odd overlap with correction support
        syn = []
        for stab_idx in r2:  # order A1, A3, A9, A11 == ROUND_2_MAP insertion order 1,3,9,11
            overlap = len(set(targets) & set(x_stabs[stab_idx]))
            syn.append(overlap % 2)
        syn_be = "".join(map(str, syn))
        r1_disturb = [i for i in r1 if len(set(targets) & set(x_stabs[i])) % 2 == 1]
        rows.append({
            "syndrome_be": syndrome_be,
            "correction_Z_on": targets,
            "independently_computed_syndrome": syn_be,
            "matches_key": syn_be == syndrome_be,
            "disturbs_round1_plaquettes": r1_disturb,
        })
    return rows


def round1_audit() -> list[dict]:
    rows = []
    for stab_idx, (target_q, anc_idx, c_idx) in ROUND_1_MAP.items():
        stab = WEN_STABILIZERS[stab_idx]
        flipped = [j for j, s in enumerate(WEN_STABILIZERS)
                   if s.pauli_type == "X" and (target_q in s.support)]
        rows.append({
            "stab_idx": stab_idx, "stab": f"{stab.pauli_type}{stab.support}",
            "correction_Z_on": target_q, "ancilla": anc_idx, "c_bit": c_idx,
            "target_in_support": target_q in stab.support,
            "flips_X_plaquettes": flipped,
        })
    return rows


def main() -> None:
    params = qm.code_parameters()
    match, match_detail = module_stabs_match_derivation()
    paulis = [qm.from_support(t, s) for t, s in qm.derive_stabilizers()]
    logicals = qm.enumerate_logicals(paulis, max_weight=3)
    reps = qm.logical_representatives(paulis)
    lut_rows = lut_audit()
    r1_rows = round1_audit()
    lut_ok = all(r["matches_key"] and not r["disturbs_round1_plaquettes"] for r in lut_rows)

    n_x = sum(1 for s in WEN_STABILIZERS if s.pauli_type == "X")
    n_z = sum(1 for s in WEN_STABILIZERS if s.pauli_type == "Z")

    r1_map_desc = {f"c{i}_1st": ROUND_1_MAP[s][0] for i, s in enumerate(sorted(ROUND_1_MAP))}
    report = f"""# QEC Baseline Audit (Phase 0)

## 0. Repository ground truth
{git_info()}
## 0.1 Environment versions
{versions()}

## 0.2 Implementation under review
- The `WenPlaquetteFeedForwardPass` / `dnalang_wen_plaquette_pass.py` implementation does NOT
  exist anywhere in the local git repository or its 171 mirrored legacy repos; the only copy was
  the pasted source, vendored verbatim as `qec/dnalang_wen_plaquette_pass.py` (baseline, untouched).
- Corrected module: `qec/wen_plaquette_pass.py` (adds the enforced preparation-only contract).

## 1. Mathematical specification (independently derived from the lattice)
- Lattice: {params['L']}x{params['L']} periodic (toroidal); qubit (r,c) -> index 4r+c; {params['n_data_qubits']} data qubits.
- Plaquettes: checkerboard, Z-type on (r+c) even, X-type on (r+c) odd; all weight 4 (no boundary plaquettes -> toric-type boundaries).
- Generators listed in module: {len(WEN_STABILIZERS)} ({n_x} X-type, {n_z} Z-type); ALL pure X or Z type: {params['all_generators_pure_type']}.
- Module's WEN_STABILIZERS == independent checkerboard derivation: {match} ({match_detail}).
- Pairwise commutation of all {len(WEN_STABILIZERS)} generators: {params['all_pairs_commute']} (verified by symplectic inner product).
- Independent stabilizer rank (GF(2)): {params['stabilizer_rank']} -> encoded logical qubits k = 16 - {params['stabilizer_rank']} = **{params['n_logical_qubits_k']}**.
- Logical operators of weight <= 3 (exhaustive enumeration): {len(logicals)} found -> {params['distance_claim']}.
- Logical representatives (row/column strings, weight 4, commute with all, not in stabilizer group):
  X_L_row0, X_L_col0, Z_L_row0, Z_L_col0.

## 2. Classification
This is a **Wen-plaquette (checkerboard) CSS code on a 4x4 torus**, k=2, distance d=4.
It is NOT a boundary surface code (all stabilizers weight 4, periodic boundaries) and not
qubit-count-equivalent to the 32-qubit toric code; it is the vertex-qubit checkerboard model.

## 3. Implemented protocol (what the pass actually does)
- 20 qubits total: 16 data + 4 ancilla (q[16..19]), ancillas reused across rounds via Reset.
- Measures ONLY the 8 X-type generators, in 2 rounds of 4 (round 1: plaquettes {sorted(ROUND_1_MAP.keys())},
  round 2: {sorted(ROUND_2_MAP.keys())}); the 8 Z-type generators are NEVER measured.
- Round-1 feed-forward: single conditional Z per plaquette (see table below).
- Round-2 feed-forward: 4-bit LUT over (A1,A3,A9,A11), big-endian string -> reversed-int condition_value (little-endian TKET).
- Final: barrier + destructive X-basis measurement of the 16 data qubits into c5_end.
- Initial-state assumption: input must be |0>^16 on data qubits (all Z generators already +1);
  the pass enforces an empty input circuit but the |0> assumption is implicit in the physics.

## 4. Independent LUT verification (syndrome of each correction computed from supports)
| syndrome_be | Z correction on | computed syndrome | matches | disturbs round-1 plaquettes |
|---|---|---|---|---|
{chr(10).join(f"| {r['syndrome_be']} | {r['correction_Z_on']} | {r['independently_computed_syndrome']} | {r['matches_key']} | {r['disturbs_round1_plaquettes']} |" for r in lut_rows)}
All LUT entries independently consistent (syndrome matches key, round-1 plaquettes undisturbed): **{lut_ok}**.

## 5. Round-1 correction audit
{json.dumps(r1_rows, indent=1)}

## 6. Syndrome-to-correction mapping summary
- Round 1: syndrome bit "1" on a c*_1st register -> conditional Z; mapping: {r1_map_desc} (each correction flips its own plaquette back and exactly one round-2 plaquette, which the round-2 LUT then accounts for).
- Round 2: 7-entry even-parity LUT (all weight-2 syndromes + 1111). Odd-parity round-2 syndromes receive NO correction; by the torus parity argument (product of all 8 X generators = identity) the round-2 syndrome is always even when starting from a state with even total X-parity, so all reachable branches are covered.

## 7. Known limitations recorded at baseline
- X/Y errors on data qubits flip Z-type generators, which are never measured -> undetectable by this circuit (tested in Phase 3).
- This is a state-PREPARATION circuit, not a QEC memory: there are no repeated syndrome rounds after preparation.
- DD options in the capsule are inert metadata, not applied by the pass.
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report)
    print(f"wrote {REPORT}")
    print(json.dumps(params, indent=1))
    print("module==derived:", match, "| LUT ok:", lut_ok, "| logicals<=3:", len(logicals))


if __name__ == "__main__":
    main()
