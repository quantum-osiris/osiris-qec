"""
v1.1.0 Compiler Hardening, Metadata Determinism, Hash-Lock Gate, and RFC 8785
Canonical JSON Ledger Tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytket import Circuit

from osiris_cli.ledger import (
    LedgerError,
    append_ledger,
    canonical_json,
    canonicalize,
    compute_wilson_lower_bound,
    sha256_hex,
    verify_ledger_file,
)
from osiris_cli.qec_runner import load_manifest
from osiris_cli.qnexus_client import (
    EXPECTED_ISA,
    EXPECTED_PRECOMPILE,
    HashMismatchError,
    ManifestError,
    build_and_verify_frozen_artifacts,
    verify_manifest_lock,
)
from osiris_qec.wen_plaquette_pass import (
    LOCKED_COMPILER_METADATA,
    WenPlaquetteFeedForwardPass,
    build_wen_plaquette,
    compute_sha256,
    get_circuit_metadata,
    hash_tket_circuit,
    normalize_circuit_metadata,
    set_circuit_metadata,
)

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Section 2.1: Register-Collision & Non-Empty Input Rejection
# ---------------------------------------------------------------------------

def test_reject_existing_q_register() -> None:
    circ = Circuit()
    circ.add_q_register("q", 4)
    with pytest.raises(ValueError):
        build_wen_plaquette(circ)

    circ_exact = Circuit()
    circ_exact.add_q_register("q", 20)
    with pytest.raises(ValueError):
        build_wen_plaquette(circ_exact)


@pytest.mark.parametrize("qreg_name", ["qr", "quantum"])
def test_reject_reserved_quantum_registers(qreg_name: str) -> None:
    circ = Circuit()
    circ.add_q_register(qreg_name, 4)
    with pytest.raises(ValueError, match="colliding quantum register"):
        WenPlaquetteFeedForwardPass().to_tket_pass().apply(circ)


def test_reject_existing_c_register() -> None:
    circ = Circuit()
    circ.add_c_register("c", 1)
    with pytest.raises(ValueError, match="colliding classical register"):
        build_wen_plaquette(circ)


@pytest.mark.parametrize("creg_name", ["creg", "cl", "classical", "c0_1st", "c4_2nd", "c5_end"])
def test_reject_existing_creg_variants(creg_name: str) -> None:
    circ = Circuit()
    circ.add_c_register(creg_name, 8)
    with pytest.raises(ValueError, match="colliding classical register"):
        WenPlaquetteFeedForwardPass().to_tket_pass().apply(circ)


def test_reject_nonempty_circuit() -> None:
    circ = Circuit(2)
    circ.H(0)
    with pytest.raises(ValueError, match="preparation-only"):
        build_wen_plaquette(circ)


# ---------------------------------------------------------------------------
# Section 2.2: Metadata Determinism & Frozen v1.0.0 Parity
# ---------------------------------------------------------------------------

def test_hash_stability() -> None:
    a = build_wen_plaquette(Circuit())
    b = build_wen_plaquette(Circuit())
    assert compute_sha256(a) == compute_sha256(b) == EXPECTED_PRECOMPILE


def test_metadata_normalization() -> None:
    clean = build_wen_plaquette(Circuit())
    drifted = build_wen_plaquette(Circuit())

    # Simulate metadata drift during upstream/downstream pass handling
    drifted.name = "transient_user_circuit_name"
    drifted.add_phase(2.0)  # +2pi global phase (trivial mod 2 half-turns)
    set_circuit_metadata(drifted, {"arbitrary": "drift", "timestamp": "2099-01-01"})

    # Hash function is invariant to name/trivial-phase/metadata drift
    assert hash_tket_circuit(drifted) == hash_tket_circuit(clean) == EXPECTED_PRECOMPILE

    # In-place normalization restores locked v1.1.0 metadata dictionary
    normalize_circuit_metadata(drifted, compiler_lock=True)
    assert drifted.name in (None, "")
    assert get_circuit_metadata(drifted) == LOCKED_COMPILER_METADATA
    assert hash_tket_circuit(drifted) == EXPECTED_PRECOMPILE


def test_frozen_manifest_parity() -> None:
    m_v10 = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_0_0.json")
    m_v11 = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_1_0.json")

    assert m_v10["precompile_sha256"] == m_v11["precompile_sha256"] == EXPECTED_PRECOMPILE
    assert m_v10["isa_sha256"] == m_v11["isa_sha256"] == EXPECTED_ISA

    _, _, stats = build_and_verify_frozen_artifacts(m_v11)
    assert stats["precompile_sha256"] == EXPECTED_PRECOMPILE
    assert stats["isa_sha256"] == EXPECTED_ISA
    assert stats["depth"] == 19
    assert stats["zzphase_count"] == 32


# ---------------------------------------------------------------------------
# Section 6 & 7: Fail-Closed Hash Gate & Compilation Lock Enforcement
# ---------------------------------------------------------------------------

def test_hash_gate_rejects_tampered_isa() -> None:
    manifest = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_1_0.json")
    manifest["isa_sha256"] = "deadbeef" * 8
    with pytest.raises(HashMismatchError, match="ISA hash mismatch"):
        verify_manifest_lock(manifest)


def test_hash_gate_rejects_tampered_precompile() -> None:
    manifest = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_1_0.json")
    manifest["precompile_sha256"] = "00" * 32
    with pytest.raises(HashMismatchError, match="Pre-compile hash mismatch"):
        verify_manifest_lock(manifest)


def test_hash_gate_rejects_unlocked_or_nonzero_opt_manifest() -> None:
    base = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_1_0.json")

    m_no_hash = {**base, "hash_lock": False}
    with pytest.raises(ManifestError, match="Hash lock disabled"):
        verify_manifest_lock(m_no_hash)

    m_no_comp = {**base, "compiler_lock": False}
    with pytest.raises(ManifestError, match="Compiler lock disabled"):
        verify_manifest_lock(m_no_comp)

    m_bad_opt = {**base, "optimisation_level": 2}
    with pytest.raises(ManifestError, match="optimisation_level=0"):
        verify_manifest_lock(m_bad_opt)


# ---------------------------------------------------------------------------
# Section 8 & 12: RFC 8785 Canonicalization, Hash Chain & Wilson Bounds
# ---------------------------------------------------------------------------

def test_rfc8785_canonicalization_is_stable_and_compliant() -> None:
    payload_a = {
        "z_key": [1, 1.0, -0.0, 0.0, 0.9964, 1e-6, 1e-7, 1e30, 333333333.33333329],
        "a_key": "line\nbreak\tand\"quote\"",
        "nested": {"b": True, "a": None, "c": False},
    }
    payload_b = {
        "nested": {"c": False, "b": True, "a": None},
        "a_key": "line\nbreak\tand\"quote\"",
        "z_key": [1, 1, 0, 0, 0.9964, 0.000001, 1e-7, 1e30, 333333333.3333333],
    }
    canon_a = canonicalize(payload_a)
    canon_b = canonicalize(payload_b)
    assert canon_a == canon_b
    assert sha256_hex(canon_a) == sha256_hex(canon_b)
    # Normative RFC 8785 Section 3.2.2.3 IEEE-754 checks (`1.0 -> 1`, `-0.0 -> 0`)
    assert canonical_json({"one_float": 1.0, "neg_zero": -0.0, "fid": 0.9964}) == '{"fid":0.9964,"neg_zero":0,"one_float":1}'

    # Normative RFC 8785 Section 3.2.3 UTF-16 code-unit sorting (surrogate pair U+1F600 sorts BEFORE U+FB33!)
    utf16_sorted = canonical_json({"\ufb33": "hebrew", "😀": "emoji", "\u20ac": "euro", "\n": "nl"})
    assert list(utf16_sorted.split('":'))[0].startswith('{"\\n')
    assert utf16_sorted.index("emoji") < utf16_sorted.index("hebrew")

    with pytest.raises(LedgerError):
        canonical_json({"bad": float("nan")})
    with pytest.raises(LedgerError):
        canonical_json({"unsafe_int": 2**53})


def test_no_deprecated_utcnow_in_repository() -> None:
    bad_token = "datetime." + "utcnow"
    for py_file in ROOT.rglob("*.py"):
        if any(
            p in py_file.parts
            for p in (".git", "__pycache__", "tests", ".venv", "venv", "build", "dist")
        ):
            continue
        text = py_file.read_text(encoding="utf-8")
        assert bad_token not in text, f"Deprecated {bad_token}() found in {py_file}"


def test_v1_1_1_manifest_protocol_naming_consistency() -> None:
    m_v111 = load_manifest(ROOT / "hardware" / "experiment_manifest_v1_1_1.json")
    assert m_v111["manifest_version"] == "1.1.1"
    assert m_v111["package"] == "osiris-qec"
    assert m_v111["protocol"] == "OSIRIS-QEC-002"
    assert m_v111["precompile_sha256"] == EXPECTED_PRECOMPILE
    assert m_v111["isa_sha256"] == EXPECTED_ISA


def test_ledger_append_and_tamper_detection(tmp_path: Path) -> None:
    ledger_path = tmp_path / "run-test.json"
    e1 = append_ledger(ledger_path, {"execution_id": "abc12345", "stage": "pre_submit", "target": "selene", "shots": 512})
    e2 = append_ledger(ledger_path, {"execution_id": "abc12345", "stage": "completed", "target": "selene", "pass": True})

    assert e2["prev_sha256"] == e1["entry_sha256"]
    summary = verify_ledger_file(ledger_path)
    assert summary["entry_count"] == 2
    assert summary["chain_valid"] is True

    # Tamper with line 2 payload without updating entry_sha256
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"pass":true', '"pass":false')
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LedgerError, match="SHA-256 mismatch"):
        verify_ledger_file(ledger_path)


def test_frozen_wilson_threshold_table_exact() -> None:
    expected_min_pass = {512: 512, 1000: 997, 2000: 1989, 5000: 4964, 10000: 9920}
    for shots, min_k in expected_min_pass.items():
        assert compute_wilson_lower_bound(min_k, shots) > 0.99
        if min_k > 0:
            assert compute_wilson_lower_bound(min_k - 1, shots) <= 0.99
