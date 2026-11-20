"""Phase 5: reproducible noisy benchmark (Monte Carlo trajectories on the exact
statevector simulator). Writes reports/QEC_BENCHMARK_RESULTS.json and a figure.

Noise model (documented, applied per op in qec_sim.run_ops):
  p_1q    depolarizing on H / Z / conditional-Z applications (random X/Y/Z on a random qubit)
  p_2q    depolarizing on each CX
  p_meas  bit-flip of the RECORDED classical bit after each stabilizer measurement
  p_reset depolarizing after each ancilla reset
All channels share the same physical error probability p in the sweep.
Baseline: identical circuit with feed-forward corrections DISABLED (no CZ ops),
plus the raw physical error rate as reference. No advantage is claimed without it.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import qec_sim as qs
import qec_verify as qv

ROOT = Path(__file__).parent.parent
OUT = ROOT / "reports" / "QEC_BENCHMARK_RESULTS.json"

P_SWEEP = [0.0, 1e-4, 1e-3, 5e-3, 1e-2]
SEEDS = [11, 22, 33]
SHOTS = 60


def resource_counts() -> dict:
    ops = qv.build_ops()
    from collections import Counter
    kinds = Counter(op[0] for op in ops if op[0] != "BARRIER")
    # depth: count layers naively by op order (single-qubit ops on distinct qubits
    # still counted serially here; true depth via pytket below)
    from pytket import Circuit
    from wen_plaquette_pass import WenPlaquetteFeedForwardPass
    b = WenPlaquetteFeedForwardPass()
    c = Circuit()
    b.to_tket_pass().apply(c)
    return {
        "total_ops_before_barrier": sum(kinds.values()),
        "cx_count": kinds["CX"],
        "h_count": kinds["H"],
        "measure_count": kinds["MEASURE"],
        "reset_count": kinds["RESET"],
        "conditional_z_count": kinds["CZ"],
        "circuit_depth": c.depth(),
        "n_qubits": c.n_qubits,
        "n_clbits": c.n_bits,
    }


def strip_feedforward(ops: list) -> list:
    return [op for op in ops if op[0] != "CZ"]


def _bench_worker(args):
    p, seed, use_ff = args
    noise = None
    if p > 0:
        noise = {"p_1q": p, "p_2q": p, "p_meas": p, "p_reset": p}
    ops = qv.get_ops() if use_ff else strip_feedforward(qv.get_ops())
    rng = np.random.default_rng(seed)
    # target state for logical fidelity: noiseless all-zero branch
    target, _ = qs.run_ops(qv.get_ops(), outcomes={bk: 0 for bk in qv.MEAS_BITKEYS})
    fids, corr = [], []
    for _ in range(SHOTS):
        st, _ = qs.run_ops(ops, rng=rng, noise=noise)
        xexps = [qs.expectation(st, "X", sup) for _, sup in qv.X_STABS]
        corr.append(all(e > 0.999 for e in xexps))
        fids.append(qs.state_fidelity(st, target))
    fids = np.array(fids)
    corr = np.array(corr, dtype=float)
    return {
        "p": p, "seed": seed, "feedforward": use_ff,
        "mean_logical_fidelity": float(fids.mean()),
        "ci95_logical_fidelity": float(1.96 * fids.std(ddof=1) / np.sqrt(len(fids))),
        "correction_success_rate": float(corr.mean()),
        "ci95_correction": float(1.96 * corr.std(ddof=1) / np.sqrt(len(corr))),
        "shots": SHOTS,
    }


def main() -> None:
    jobs = [(p, s, ff) for p in P_SWEEP for s in SEEDS for ff in (True, False)]
    with mp.Pool(16, initializer=qv._pool_init) as pool:
        results = pool.map(_bench_worker, jobs)
    res = {
        "noise_model": {
            "p_1q": "depolarizing after each 1q gate", "p_2q": "depolarizing after each CX",
            "p_meas": "bit-flip of recorded classical bit", "p_reset": "depolarizing after reset",
            "note": "all channels set to the same p; Monte Carlo trajectories on exact statevector sim",
        },
        "p_sweep": P_SWEEP, "seeds": SEEDS, "shots_per_cell": SHOTS,
        "resources": resource_counts(),
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(f"wrote {OUT}")
    for p in P_SWEEP:
        ff = [r for r in results if r["p"] == p and r["feedforward"]]
        nf = [r for r in results if r["p"] == p and not r["feedforward"]]
        mf = np.mean([r["mean_logical_fidelity"] for r in ff])
        mn = np.mean([r["mean_logical_fidelity"] for r in nf])
        print(f"p={p:g}  logical_fid with FF={mf:.4f}  without FF={mn:.4f}")

    # figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 4))
        for ff, label in [(True, "with feed-forward"), (False, "no feed-forward (baseline)")]:
            xs = [r["p"] for r in results if r["feedforward"] == ff]
            ys = [np.mean([r["mean_logical_fidelity"] for r in results
                           if r["p"] == p and r["feedforward"] == ff]) for p in P_SWEEP]
            ax.plot(P_SWEEP, ys, "o-", label=label)
        ax.set_xscale("log")
        ax.set_xlabel("physical error probability p per op")
        ax.set_ylabel("mean fidelity to prepared logical state")
        ax.set_title("Wen-plaquette prep: noisy trajectories (60 shots x 3 seeds per point)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(ROOT / "reports" / "QEC_BENCHMARK_RESULTS.png", dpi=120)
        print("wrote figure")
    except ImportError:
        print("matplotlib unavailable; JSON only")


if __name__ == "__main__":
    main()
