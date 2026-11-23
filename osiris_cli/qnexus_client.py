"""
osiris_cli.qnexus_client — Provenance-locked Quantinuum Nexus (qnexus 0.51.4)
client with fail-closed pre/post-compile SHA-256 verification and exponential
backoff retries for transient transport errors.
"""

from __future__ import annotations

import email.utils
import importlib.metadata
import os
import random
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pytket import Circuit

from hardware.quantinuum_h2 import local_h2_compile
from osiris_cli.ledger import compute_wilson_lower_bound
from wen_plaquette_pass import (
    FROZEN_H2_ISA_SHA256,
    FROZEN_PRECOMPILE_SHA256,
    WEN_STABILIZERS,
    WenPlaquetteFeedForwardPass,
    hash_tket_circuit,
)

QNEXUS_VERSION = "0.51.4"
EXPECTED_PRECOMPILE = FROZEN_PRECOMPILE_SHA256
EXPECTED_ISA = FROZEN_H2_ISA_SHA256
EXPECTED_DEPTH = 19
EXPECTED_ZZPHASE_COUNT = 32

T = TypeVar("T")


class HashMismatchError(RuntimeError):
    """Raised when any pre-compile or compiled ISA hash deviates from the frozen manifest."""


class ManifestError(RuntimeError):
    """Raised when an experiment manifest is missing, malformed, or unlocked."""


class QNexusAPIError(RuntimeError):
    """Raised when QNexus API calls fail after exhausting allowed retries or hit auth errors."""


TRANSIENT_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504})
NON_RETRYABLE_HTTP_CODES = frozenset({400, 401, 403, 404, 422})


def get_installed_qnexus_version() -> str:
    try:
        return importlib.metadata.version("qnexus")
    except importlib.metadata.PackageNotFoundError:
        try:
            import qnexus as qnx  # type: ignore
            return getattr(qnx, "__version__", "unknown")
        except ImportError:
            return "unknown"


def verify_hash(observed: str, expected: str, label: str) -> None:
    if observed != expected:
        raise HashMismatchError(
            f"{label} hash mismatch\n"
            f"Expected:\n{expected}\n\n"
            f"Observed:\n{observed}"
        )


def verify_manifest_lock(manifest: dict[str, Any], *, require_v1_1_locks: bool = True) -> None:
    if require_v1_1_locks:
        if not manifest.get("hash_lock", False):
            raise ManifestError("Hash lock disabled in manifest (`hash_lock` must be true).")
        if not manifest.get("compiler_lock", False):
            raise ManifestError("Compiler lock disabled in manifest (`compiler_lock` must be true).")
        if int(manifest.get("optimisation_level", -1)) != 0:
            raise ManifestError(
                f"Quantinuum compilation lock requires optimisation_level=0, "
                f"got {manifest.get('optimisation_level')!r}."
            )
    verify_hash(manifest["precompile_sha256"], EXPECTED_PRECOMPILE, "Pre-compile")
    verify_hash(manifest["isa_sha256"], EXPECTED_ISA, "H2-1 ISA")


def build_and_verify_frozen_artifacts(manifest: dict[str, Any]) -> tuple[Circuit, Circuit, dict[str, Any]]:
    """
    Deterministically build the pre-compile circuit and offline H2-1 ISA circuit,
    verifying both SHA-256 digests, depth=19, and ZZPhase=32 against the frozen baseline.
    """
    verify_hash(manifest["precompile_sha256"], EXPECTED_PRECOMPILE, "Manifest pre-compile")
    verify_hash(manifest["isa_sha256"], EXPECTED_ISA, "Manifest H2-1 ISA")

    builder = WenPlaquetteFeedForwardPass(measurement_setting="X", target_device="H2-1")
    pre_circ = Circuit()
    builder.to_tket_pass().apply(pre_circ)
    pre_hash = hash_tket_circuit(pre_circ)
    verify_hash(pre_hash, manifest["precompile_sha256"], "Pre-compile")

    isa_circ = local_h2_compile(pre_circ, optimisation_level=2)
    isa_hash = hash_tket_circuit(isa_circ)
    verify_hash(isa_hash, manifest["isa_sha256"], "H2-1 ISA")

    counts = Counter(cmd.op.type.name for cmd in isa_circ.get_commands())
    depth = isa_circ.depth()
    zzphase = counts.get("ZZPhase", 0)
    if depth != EXPECTED_DEPTH or zzphase != EXPECTED_ZZPHASE_COUNT:
        raise HashMismatchError(
            f"H2-1 structural drift: expected depth={EXPECTED_DEPTH}, ZZPhase={EXPECTED_ZZPHASE_COUNT}; "
            f"observed depth={depth}, ZZPhase={zzphase}."
        )

    return pre_circ, isa_circ, {
        "precompile_sha256": pre_hash,
        "isa_sha256": isa_hash,
        "depth": depth,
        "zzphase_count": zzphase,
        "gate_counts": dict(sorted(counts.items())),
    }


def _is_transient_exception(exc: BaseException) -> bool:
    """Classify whether `exc` is a transient network/gateway error eligible for retry."""
    if isinstance(exc, (HashMismatchError, ManifestError, ValueError, TypeError, KeyError)):
        return False

    status_code = getattr(exc, "status_code", None)
    if status_code is None and hasattr(exc, "response"):
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status_code, int):
        if status_code in NON_RETRYABLE_HTTP_CODES:
            return False
        if status_code in TRANSIENT_HTTP_CODES:
            return True

    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    msg = f"{type(exc).__name__}: {exc}".lower()
    non_retry_tokens = ("unauthorized", "forbidden", "401", "403", "not authenticated", "login")
    if any(tok in msg for tok in non_retry_tokens):
        return False
    retry_tokens = ("timeout", "timed out", "temporarily unavailable", "502", "503", "504", "429", "connection", "reset by peer")
    return any(tok in msg for tok in retry_tokens)


def _extract_retry_after_seconds(exc: BaseException, max_delay: float = 60.0) -> float | None:
    """Extract HTTP `Retry-After` delay (delta-seconds or RFC 7231 HTTP-date) if present."""
    headers = getattr(exc, "headers", None)
    if headers is None and hasattr(exc, "response"):
        headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers or not hasattr(headers, "items"):
        return None

    raw_val: str | None = None
    for k, v in headers.items():
        if str(k).lower() == "retry-after":
            raw_val = str(v).strip()
            break
    if not raw_val:
        return None

    try:
        secs = float(raw_val)
        return max(0.0, min(max_delay, secs))
    except ValueError:
        pass

    try:
        dt = email.utils.parsedate_to_datetime(raw_val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = (dt - datetime.now(UTC)).total_seconds()
        return max(0.0, min(max_delay, delta))
    except (TypeError, ValueError, OverflowError):
        return None


def with_qnexus_retries(
    operation_name: str,
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    jitter_ratio: float = 0.25,
    rng_fn: Callable[[], float] = random.random,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """
    Execute `fn()` with bounded exponential backoff, `Retry-After` header support,
    and randomized jitter to prevent thundering-herd retries on congested gateways.
    Fail-closed integrity errors (`HashMismatchError`, `ManifestError`) and auth
    errors (`401`/`403`) abort immediately without retry.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except (HashMismatchError, ManifestError):
            raise
        except Exception as exc:
            if not _is_transient_exception(exc) or attempt >= max_retries:
                raise QNexusAPIError(
                    f"QNexus {operation_name} failed after {attempt + 1} attempt(s): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            retry_after = _extract_retry_after_seconds(exc, max_delay=max_delay)
            if retry_after is not None:
                # Respect server Retry-After plus a small positive desynchronization jitter (0..10%)
                delay = min(max_delay, retry_after * (1.0 + 0.10 * max(0.0, min(1.0, rng_fn()))))
            else:
                exp_delay = min(max_delay, base_delay * (backoff_factor ** attempt))
                jitter_mult = 1.0 + jitter_ratio * (2.0 * max(0.0, min(1.0, rng_fn())) - 1.0)
                delay = max(0.0, exp_delay * jitter_mult)

            sleep_fn(delay)
            attempt += 1


def build_qnexus_config() -> dict[str, Any]:
    return {
        "optimisation_level": 0,
        "compiler_lock": True,
        "qnexus_version": QNEXUS_VERSION,
        "depth": EXPECTED_DEPTH,
        "zzphase_count": EXPECTED_ZZPHASE_COUNT,
    }


def extract_circuit_from_ref(program_ref: Any) -> Circuit:
    """Extract a `pytket.Circuit` from a QNexus `CircuitRef` or mock program wrapper."""
    if isinstance(program_ref, Circuit):
        return program_ref
    if hasattr(program_ref, "download_circuit") and callable(program_ref.download_circuit):
        return program_ref.download_circuit()
    if hasattr(program_ref, "circuit") and isinstance(program_ref.circuit, Circuit):
        return program_ref.circuit
    raise QNexusAPIError(
        f"Unable to extract compiled pytket Circuit for post-compile hash verification "
        f"from {type(program_ref).__name__}; refusing unverified execution."
    )


def verify_compiled_program_hash(compiled_program: Any, expected_isa_sha256: str = EXPECTED_ISA) -> str:
    """Mandatory post-compile provenance gate: abort before execution if QNexus drifted ISA."""
    compiled_circ = extract_circuit_from_ref(compiled_program)
    observed = hash_tket_circuit(compiled_circ)
    if observed != expected_isa_sha256:
        raise HashMismatchError(
            f"Compiled ISA hash drift detected\n"
            f"Expected:\n{expected_isa_sha256}\n\n"
            f"Observed:\n{observed}"
        )
    return observed


def _score_qnexus_results(results: Any, requested_shots: int) -> dict[str, Any]:
    """Extract bitstrings, syndrome trajectories, parity fidelity, and Wilson LCB from QNexus results."""
    x_supports = [s.support for s in WEN_STABILIZERS if s.pauli_type == "X"]
    raw_bitstrings: list[str] = []
    syndrome_trajectories: list[str] = []

    res_item = results[0] if isinstance(results, (list, tuple)) and results else results
    if isinstance(res_item, dict) and "c5_end_bitstrings" in res_item:
        raw_bitstrings = list(res_item["c5_end_bitstrings"])
        syndrome_trajectories = list(res_item.get("syndrome_trajectories", []))
    elif hasattr(res_item, "get_counts"):
        counts = res_item.get_counts()
        for bits_tuple, count in counts.items():
            bstr = "".join(str(int(b)) for b in bits_tuple)
            raw_bitstrings.extend([bstr] * int(count))

    if not raw_bitstrings:
        return {
            "shots": requested_shots,
            "raw_bitstrings": [],
            "syndrome_trajectories": syndrome_trajectories,
            "raw_fidelity": 0.0,
            "postselected_fidelity": 0.0,
            "wilson_lower_bound": 0.0,
            "pass": False,
        }

    total = len(raw_bitstrings)
    passing = 0
    for bstr in raw_bitstrings:
        data_bits = [int(ch) for ch in bstr[:16]]
        if all(sum(data_bits[q] for q in sup) % 2 == 0 for sup in x_supports):
            passing += 1

    raw_fid = passing / float(total)
    wilson_lb = compute_wilson_lower_bound(passing, total)
    return {
        "shots": total,
        "raw_bitstrings": raw_bitstrings[:64],
        "syndrome_trajectories": syndrome_trajectories[:64],
        "raw_fidelity": raw_fid,
        "postselected_fidelity": raw_fid,
        "wilson_lower_bound": wilson_lb,
        "pass": wilson_lb > 0.99,
    }


def login(qnx_mod: Any) -> None:
    if os.getenv("QNEXUS_TOKEN") or os.getenv("NEXUS_API_TOKEN"):
        return
    qnx_mod.login()


def execute_h2_qnexus(
    isa_circuit: Circuit,
    manifest: dict[str, Any],
    shots: int,
    *,
    device_name: str = "H2-1",
    qnx_module: Any = None,
    max_retries: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """
    Two-phase provenance-locked Quantinuum Nexus execution:
      1. Verify manifest locks and local ISA circuit SHA-256 (`02d5cb72...`).
      2. Authenticate, upload ISA circuit, lock-compile with `optimisation_level=0`,
         verify compiled ISA SHA-256 == `02d5cb72...` BEFORE execution, then submit
         and retrieve results with bounded exponential backoff retries.
    """
    verify_manifest_lock(manifest, require_v1_1_locks=True)
    verify_hash(hash_tket_circuit(isa_circuit), manifest["isa_sha256"], "Pre-upload H2-1 ISA")

    qnx = qnx_module
    if qnx is None:
        import qnexus as qnx  # type: ignore

    installed_ver = get_installed_qnexus_version() if qnx_module is None else getattr(qnx, "__version__", QNEXUS_VERSION)
    if installed_ver not in (QNEXUS_VERSION, "unknown") and installed_ver != manifest.get("qnexus_version", QNEXUS_VERSION):
        raise ManifestError(
            f"qnexus version mismatch: expected {manifest.get('qnexus_version', QNEXUS_VERSION)}, "
            f"installed {installed_ver}"
        )

    with_qnexus_retries("login", lambda: login(qnx), max_retries=max_retries, sleep_fn=sleep_fn)

    project = with_qnexus_retries(
        "projects.get_or_create",
        lambda: qnx.projects.get_or_create(name="OSIRIS-QEC"),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    circuit_ref = with_qnexus_retries(
        "circuits.upload",
        lambda: qnx.circuits.upload(
            name=f"osiris-qec-{ts}",
            circuit=isa_circuit,
            project=project,
        ),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    backend_cfg = qnx.QuantinuumConfig(device_name=device_name, no_opt=True)

    compiled_list = with_qnexus_retries(
        "compile",
        lambda: qnx.compile(
            programs=[circuit_ref],
            name="osiris_locked_compile",
            project=project,
            optimisation_level=0,
            backend_config=backend_cfg,
        ),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )
    compiled_program = compiled_list[0]

    # Mandatory post-compile provenance gate BEFORE submitting execution job
    verified_compiled_hash = with_qnexus_retries(
        "verify_compiled_program_hash",
        lambda: verify_compiled_program_hash(compiled_program, manifest["isa_sha256"]),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    job_ref = with_qnexus_retries(
        "start_execute_job",
        lambda: qnx.start_execute_job(
            programs=[compiled_program],
            n_shots=[int(shots)],
            backend_config=backend_cfg,
            name="osiris-qec-h2",
            project=project,
        ),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    with_qnexus_retries(
        "jobs.wait_for",
        lambda: qnx.jobs.wait_for(job_ref),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    raw_results = with_qnexus_retries(
        "jobs.results",
        lambda: qnx.jobs.results(job_ref),
        max_retries=max_retries,
        sleep_fn=sleep_fn,
    )

    scored = _score_qnexus_results(raw_results, int(shots))
    return {
        "job_id": str(getattr(job_ref, "id", job_ref)),
        "target": device_name.lower(),
        "optimisation_level": 0,
        "qnexus_version": QNEXUS_VERSION,
        "depth": EXPECTED_DEPTH,
        "zzphase_count": EXPECTED_ZZPHASE_COUNT,
        "verified_compiled_isa_sha256": verified_compiled_hash,
        **scored,
    }
