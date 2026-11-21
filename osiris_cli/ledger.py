"""
osiris_cli.ledger — RFC 8785 (JSON Canonicalization Scheme) write-ahead execution
ledger with SHA-256 hash chaining and Wilson 95% lower-confidence-bound scoring.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

GENESIS_PREV_SHA256 = "0" * 64
WILSON_Z_95 = 1.959963984540054


class LedgerError(RuntimeError):
    """Raised when ledger serialization, hash integrity, or chain verification fails."""


def _utf16_sort_key(s: str) -> bytes:
    """RFC 8785 Section 3.2.3: sort object member names by UTF-16BE code units."""
    return s.encode("utf-16-be")


def _rfc8785_escape_string(s: str) -> str:
    """RFC 8785 Section 3.2.2.2: minimal JSON string escaping."""
    out: List[str] = ['"']
    for ch in s:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif code == 0x08:
            out.append("\\b")
        elif code == 0x09:
            out.append("\\t")
        elif code == 0x0A:
            out.append("\\n")
        elif code == 0x0C:
            out.append("\\f")
        elif code == 0x0D:
            out.append("\\r")
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _rfc8785_format_number(val: int | float) -> str:
    """RFC 8785 Section 3.2.2.3: IEEE-754 / ECMAScript NumberToString serialization."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if not math.isfinite(val):
        raise LedgerError(f"RFC 8785 forbids non-finite IEEE-754 number: {val!r}")
    if val == 0.0:
        return "0"

    sign = "-" if val < 0 else ""
    aval = abs(val)

    # Shortest round-trip decimal representation via Python's Ryū/David-Gay repr
    s = repr(aval)
    if "e" in s or "E" in s:
        mant, exp_str = s.lower().split("e")
        exp = int(exp_str)
        digits = mant.replace(".", "")
        dot_pos = mant.index(".") if "." in mant else len(mant)
        k = len(digits)
        n = exp + dot_pos
    else:
        if "." in s:
            int_part, frac_part = s.split(".")
            raw_digits = (int_part + frac_part).lstrip("0")
            digits = raw_digits.rstrip("0") or "0"
            if int_part != "0":
                n = len(int_part)
            else:
                leading_zeros = len(frac_part) - len(frac_part.lstrip("0"))
                n = -leading_zeros
            k = len(digits)
        else:
            digits = s.rstrip("0") or "0"
            n = len(s)
            k = len(digits)

    # ECMAScript 7.1.12.1 formatting branches
    if k <= n <= 21:
        return sign + digits + ("0" * (n - k))
    if 0 < n < k and n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + ("0" * (-n)) + digits
    exp_out = n - 1
    exp_sign = "+" if exp_out >= 0 else "-"
    if k == 1:
        return f"{sign}{digits}e{exp_sign}{abs(exp_out)}"
    return f"{sign}{digits[0]}.{digits[1:]}e{exp_sign}{abs(exp_out)}"


def _rfc8785_serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _rfc8785_format_number(value)
    if isinstance(value, str):
        return _rfc8785_escape_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_rfc8785_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        for k in value.keys():
            if not isinstance(k, str):
                raise LedgerError(f"RFC 8785 requires string object keys, got {type(k).__name__}")
        sorted_items = sorted(value.items(), key=lambda kv: _utf16_sort_key(kv[0]))
        return "{" + ",".join(
            f"{_rfc8785_escape_string(k)}:{_rfc8785_serialize(v)}" for k, v in sorted_items
        ) + "}"
    raise LedgerError(f"Unsupported type for RFC 8785 canonicalization: {type(value).__name__}")


def canonical_json(payload: Dict[str, Any]) -> str:
    """Serialize `payload` to strict RFC 8785 (JCS) canonical JSON text."""
    if not isinstance(payload, dict):
        raise LedgerError("Ledger payload must be a JSON object (dict).")
    return _rfc8785_serialize(payload)


def canonicalize(payload: Dict[str, Any]) -> bytes:
    """Return UTF-8 encoded RFC 8785 canonical JSON bytes for `payload`."""
    return canonical_json(payload).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    """Compute SHA-256 over an entry's RFC 8785 representation excluding `entry_sha256`."""
    body = {k: v for k, v in entry.items() if k != "entry_sha256"}
    return sha256_hex(canonicalize(body))


def compute_wilson_lower_bound(successes: int, shots: int, z: float = WILSON_Z_95) -> float:
    """95% Wilson score lower confidence bound (z = 1.959964) matching frozen protocol."""
    if shots <= 0:
        raise ValueError(f"shots must be positive, got {shots}")
    if not (0 <= successes <= shots):
        raise ValueError(f"successes ({successes}) must be in 0..{shots}")
    p_hat = successes / float(shots)
    z2 = z * z
    denom = 1.0 + z2 / shots
    center = p_hat + z2 / (2.0 * shots)
    half_width = z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * shots)) / shots)
    return max(0.0, (center - half_width) / denom)


def _last_entry_hash(ledger_file: Path) -> str:
    if not ledger_file.exists() or ledger_file.stat().st_size == 0:
        return GENESIS_PREV_SHA256
    lines = [ln.strip() for ln in ledger_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return GENESIS_PREV_SHA256
    last_obj = json.loads(lines[-1])
    prev = last_obj.get("entry_sha256")
    if not isinstance(prev, str) or len(prev) != 64:
        raise LedgerError(f"Previous ledger entry missing valid 64-hex entry_sha256 in {ledger_file}")
    return prev


def append_ledger(ledger_file: Path | str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonicalize `payload` under RFC 8785, bind `prev_sha256` and `entry_sha256`,
    and append atomically (with fsync) to `ledger_file` as a single canonical JSON line.
    """
    path = Path(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = dict(payload)
    record.pop("entry_sha256", None)
    if "prev_sha256" not in record:
        record["prev_sha256"] = _last_entry_hash(path)

    record["entry_sha256"] = compute_entry_hash(record)
    line = canonical_json(record) + "\n"

    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    return record


def create_pre_submit_entry(
    manifest: Dict[str, Any],
    shots: int,
    target: str,
    *,
    execution_id: str | None = None,
) -> Dict[str, Any]:
    """Create a write-ahead `pre_submit` record prior to local or QNexus execution."""
    return {
        "execution_id": execution_id or uuid.uuid4().hex[:8],
        "stage": "pre_submit",
        "target": target,
        "shots": int(shots),
        "precompile_sha256": manifest["precompile_sha256"],
        "isa_sha256": manifest["isa_sha256"],
        "manifest_version": str(manifest.get("manifest_version", "1.1.0")),
        "optimisation_level": int(manifest.get("optimisation_level", 0)),
        "qnexus_version": str(manifest.get("qnexus_version", "0.51.4")),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def create_completed_entry(
    pre_entry: Dict[str, Any],
    *,
    stage: str = "completed",
    raw_bitstrings: List[str] | None = None,
    syndrome_trajectories: List[str] | None = None,
    raw_fidelity: float,
    postselected_fidelity: float,
    wilson_lower_bound: float,
    passed: bool,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a post-execution record chained to `pre_entry`."""
    rec: Dict[str, Any] = {
        "execution_id": pre_entry["execution_id"],
        "stage": stage,
        "target": pre_entry["target"],
        "shots": int(pre_entry["shots"]),
        "precompile_sha256": pre_entry["precompile_sha256"],
        "isa_sha256": pre_entry["isa_sha256"],
        "manifest_version": pre_entry.get("manifest_version", "1.1.0"),
        "optimisation_level": int(pre_entry.get("optimisation_level", 0)),
        "qnexus_version": pre_entry.get("qnexus_version", "0.51.4"),
        "raw_bitstrings": list(raw_bitstrings or []),
        "syndrome_trajectories": list(syndrome_trajectories or []),
        "raw_fidelity": round(float(raw_fidelity), 6),
        "postselected_fidelity": round(float(postselected_fidelity), 6),
        "wilson_lower_bound": round(float(wilson_lower_bound), 6),
        "pass": bool(passed),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        rec.update(extra)
    return rec


def read_ledger(ledger_file: Path | str) -> List[Dict[str, Any]]:
    path = Path(ledger_file)
    if not path.exists():
        raise LedgerError(f"Ledger not found: {path}")
    rows: List[Dict[str, Any]] = []
    for idx, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"Malformed JSON on line {idx} of {path}: {exc}") from exc
        if not isinstance(obj, dict):
            raise LedgerError(f"Line {idx} of {path} is not a JSON object.")
        rows.append(obj)
    if not rows:
        raise LedgerError(f"Ledger file is empty: {path}")
    return rows


def verify_ledger_file(ledger_file: Path | str) -> Dict[str, Any]:
    """
    Verify every line in `ledger_file` for:
      1. Byte-exact RFC 8785 canonical JSON form
      2. Valid `entry_sha256` over payload
      3. Unbroken `prev_sha256` hash chain starting from `GENESIS_PREV_SHA256`
    """
    path = Path(ledger_file)
    if not path.exists():
        raise LedgerError(f"Ledger not found: {path}")

    raw_lines = [ln.rstrip("\r\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not raw_lines:
        raise LedgerError(f"Ledger file is empty: {path}")

    expected_prev = GENESIS_PREV_SHA256
    entries: List[Dict[str, Any]] = []

    for idx, line in enumerate(raw_lines, start=1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"Invalid JSON at line {idx}: {exc}") from exc
        if not isinstance(obj, dict):
            raise LedgerError(f"Entry {idx} is not a JSON object.")

        canon = canonical_json(obj)
        if line != canon:
            raise LedgerError(f"RFC 8785 canonicalization mismatch at line {idx}.")

        observed_prev = obj.get("prev_sha256")
        if observed_prev != expected_prev:
            raise LedgerError(
                f"Broken ledger hash chain at line {idx}: expected prev_sha256={expected_prev}, "
                f"observed={observed_prev}."
            )

        observed_hash = obj.get("entry_sha256")
        recomputed_hash = compute_entry_hash(obj)
        if observed_hash != recomputed_hash:
            raise LedgerError(
                f"Entry SHA-256 mismatch at line {idx}: expected={recomputed_hash}, "
                f"observed={observed_hash}."
            )

        expected_prev = observed_hash
        entries.append(obj)

    return {
        "ledger_file": str(path),
        "entry_count": len(entries),
        "head_sha256": expected_prev,
        "rfc8785_valid": True,
        "sha256_valid": True,
        "chain_valid": True,
    }
