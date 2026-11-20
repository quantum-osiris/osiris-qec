"""Authorized gate: H2-1SC syntax check via qnexus (Nexus). Scope: SYNTAX CHECK ONLY.
H2-1E (emulator, consumes HQC) and H2-1 (hardware) are NOT submitted by this script;
they require separate explicit authorization.

Prerequisites (out-of-band, never in chat/transcripts):
  - run `qnx login` in a terminal (interactive Nexus auth), or
  - export the token env var in your shell before running this script.
Credentials are never printed, logged, or committed by this script.

Steps: verify frozen circuit hash -> upload circuit -> compile job on H2-1SC ->
record job id, status, cost, result into reports/HARDWARE_EXECUTION_LOG.{json,md}.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pytket import Circuit

from wen_plaquette_pass import WenPlaquetteFeedForwardPass, hash_tket_circuit

ROOT = Path(__file__).parent.parent
MANIFEST = json.loads((ROOT / "hardware" / "experiment_manifest.json").read_text())
LOG_JSON = ROOT / "reports" / "HARDWARE_EXECUTION_LOG.json"
LOG_MD = ROOT / "reports" / "HARDWARE_EXECUTION_LOG.md"

TARGET = "H2-1SC"


def main() -> int:
    # 1. freeze check: rebuild circuit and compare hash to the manifest
    b = WenPlaquetteFeedForwardPass(measurement_setting="X", target_device="H2-1")
    circ = Circuit()
    b.to_tket_pass().apply(circ)
    h = hash_tket_circuit(circ)
    frozen = MANIFEST["circuits"][0]["pre_compile_sha256"]
    log = {
        "gate": "H2-1SC syntax check via qnexus",
        "timestamp_utc": datetime.now(timezone.utc).isohtml if False else datetime.now(timezone.utc).isoformat(),
        "circuit_sha256": h,
        "frozen_sha256": frozen,
        "hash_match": h == frozen,
        "target": TARGET,
        "status": "STARTED",
    }
    if h != frozen:
        log["status"] = "ABORTED_HASH_MISMATCH"
        LOG_JSON.write_text(json.dumps(log, indent=1))
        print("ABORTED: rebuilt circuit hash does not match frozen manifest hash.")
        return 2

    # 2. auth check (presence only; never print secrets)
    import qnexus
    try:
        devices = qnexus.devices.get_all(issuers=[qnexus.models.IssuerEnum.QUANTINUUM])
        names = [getattr(d, "name", str(d)) for d in devices]
    except Exception as e:
        log["status"] = "BLOCKED_NO_CREDENTIALS"
        log["detail"] = (f"{type(e).__name__}: not authenticated. Run `qnx login` in a terminal "
                         f"(or export the token env var in your shell), then rerun this script. "
                         f"Credentials must never be pasted into chat.")
        LOG_JSON.write_text(json.dumps(log, indent=1))
        print(log["detail"])
        return 3
    log["available_quantinuum_devices"] = names
    log["target_available"] = TARGET in names
    if TARGET not in names:
        log["status"] = "ABORTED_TARGET_UNAVAILABLE"
        LOG_JSON.write_text(json.dumps(log, indent=1))
        print(f"{TARGET} not in available devices: {names}")
        return 4

    # 3. upload circuit
    ref = qnexus.circuits.upload(
        circuit=circ,
        name="wen_plaquette_prep_v1",
        description="20-qubit Wen-plaquette feed-forward preparation; frozen hash " + h[:16],
    )
    log["circuit_ref"] = str(ref.id) if hasattr(ref, "id") else str(ref)

    # 4. compile job against the syntax checker (no HQC consumed)
    cfg = qnexus.QuantinuumConfig(device_name=TARGET)
    job = qnexus.start_compile_job(
        programs=[ref],
        backend_config=cfg,
        name="wen-plaquette-prep-H2-1SC-syntax-check",
        description="Syntax validation only. No emulator/hardware execution.",
        optimisation_level=2,
    )
    log["compile_job_id"] = str(job.id)
    log["status"] = "SUBMITTED"
    LOG_JSON.write_text(json.dumps(log, indent=1))
    print(f"submitted compile job {job.id} to {TARGET}; waiting...")

    # 5. wait and record outcome
    import time
    final = None
    for _ in range(120):
        time.sleep(15)
        final = job.get_status() if hasattr(job, "get_status") else None
        s = str(final)
        if any(k in s.upper() for k in ("COMPLETED", "FAILED", "CANCELED", "ERROR")):
            break
    log["final_status"] = s
    try:
        log["cost"] = getattr(job, "cost", None) or "n/a (syntax check consumes no HQC)"
    except Exception:
        pass
    log["status"] = "COMPLETED" if "COMPLETED" in s.upper() else s
    LOG_JSON.write_text(json.dumps(log, indent=1))

    LOG_MD.write_text(
        "# Hardware Execution Log\n\n"
        f"- Gate: {log['gate']}\n- Time (UTC): {log['timestamp_utc']}\n"
        f"- Circuit sha256: `{h}` (matches frozen manifest: {log['hash_match']})\n"
        f"- Target: {TARGET}; available devices: {names}\n"
        f"- Compile job id: `{log.get('compile_job_id')}`\n"
        f"- Final status: {s}\n- Cost: {log.get('cost')}\n\n"
        "No emulator (H2-1E) or hardware (H2-1) jobs were submitted; they require separate "
        "explicit authorization. No credentials were printed or stored.\n"
        f"\nFull JSON: reports/HARDWARE_EXECUTION_LOG.json\n"
    )
    print("final status:", s)
    print("wrote", LOG_JSON, "and", LOG_MD)
    return 0 if "COMPLETED" in s.upper() else 5


if __name__ == "__main__":
    raise SystemExit(main())
