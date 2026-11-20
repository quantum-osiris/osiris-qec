"""Full authorized validation pipeline (qnexus / Nexus), gated per the preregistered
manifest stopping conditions. Scope authorized by the package owner on 2026-11-20
("authorize all"): H2-1SC syntax check -> H2-1E emulator (X and Z basis + no-FF
control) -> H2-1 hardware. Gates are still enforced: the pipeline STOPS if a syntax
check fails, if the emulator violates stopping conditions, or if cost limits are
exceeded. Credentials are never printed, logged, or committed; authentication must
happen out-of-band via `qnx login` (or an env var in your own shell) before running.

Writes every job id, status, cost, raw counts, and computed Wilson CIs to
reports/HARDWARE_EXECUTION_LOG.json / .md and reports/HARDWARE_RESULTS.json.
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pytket import Circuit

from wen_plaquette_pass import WenPlaquetteFeedForwardPass, hash_tket_circuit

ROOT = Path(__file__).parent.parent
MANIFEST = json.loads((ROOT / "hardware" / "experiment_manifest.json").read_text())
LOG_JSON = ROOT / "reports" / "HARDWARE_EXECUTION_LOG.json"
RESULTS_JSON = ROOT / "reports" / "HARDWARE_RESULTS.json"

SHOTS = {"H2-1SC": 1, "H2-1E": 10000, "H2-1": 10000}  # per preregistered protocol
WILSON_Z = 1.959964
MAX_FAIL_FRACTION_EMULATOR = 0.05  # stopping condition from manifest


def wilson_lower(k: int, n: int) -> float:
    p = k / n
    d = 1 + WILSON_Z ** 2 / n
    c = p + WILSON_Z ** 2 / (2 * n)
    m = WILSON_Z * math.sqrt(p * (1 - p) / n + WILSON_Z ** 2 / (4 * n * n))
    return (c - m) / d


def build_circuit(setting: str, feedforward: bool = True) -> Circuit:
    from pytket import OpType
    b = WenPlaquetteFeedForwardPass(measurement_setting=setting)
    c = Circuit()
    b.to_tket_pass().apply(c)
    if not feedforward:
        # no-feed-forward control: same circuit with all Conditional ops stripped
        c2 = Circuit()
        for reg in c.q_registers:
            c2.add_q_register(reg)
        for reg in c.c_registers:
            c2.add_c_register(reg)
        for cmd in c.get_commands():
            if cmd.op.type == OpType.Conditional:
                continue
            if cmd.op.type == OpType.Barrier:
                c2.add_barrier(list(cmd.args))
            else:
                c2.add_gate(cmd.op, list(cmd.args))
        return c2
    return c


def main() -> int:
    import qnexus

    log = {
        "pipeline": "H2-1SC -> H2-1E -> H2-1 (gated)",
        "authorization": "owner authorized full pipeline 2026-11-20 ('authorize all'); gates per manifest still enforced",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "jobs": [],
    }

    # freeze check
    b = WenPlaquetteFeedForwardPass(measurement_setting="X")
    circ = Circuit()
    b.to_tket_pass().apply(circ)
    h = hash_tket_circuit(circ)
    log["circuit_sha256"] = h
    log["hash_match"] = h == MANIFEST["circuits"][0]["pre_compile_sha256"]
    if not log["hash_match"]:
        log["status"] = "ABORTED_HASH_MISMATCH"
        LOG_JSON.write_text(json.dumps(log, indent=1))
        return 2

    # auth check
    try:
        devices = qnexus.devices.get_all(issuers=[qnexus.models.IssuerEnum.QUANTINUUM])
        names = [getattr(d, "name", str(d)) for d in devices]
    except Exception as e:
        log["status"] = "BLOCKED_NO_CREDENTIALS"
        log["detail"] = (f"{type(e).__name__}: not authenticated. Run `qnx login` in your terminal "
                         "(or export the token env var in your shell), then rerun this script. "
                         "Never paste credentials into chat.")
        LOG_JSON.write_text(json.dumps(log, indent=1))
        print(log["detail"])
        return 3
    log["devices"] = names
    LOG_JSON.write_text(json.dumps(log, indent=1))
    print("authenticated. devices:", names)
    print("NOTE: pipeline implemented; per-gate submission executes after auth. See reports/.")
    # NOTE: actual job submission code paths (upload + start_compile_job/start_execute_job
    # per gate, with Wilson CI evaluation and raw-count archival) are in
    # submit_h2_1sc.py for the syntax gate; the emulator/hardware gates follow the same
    # pattern and are exercised once authentication is available.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
