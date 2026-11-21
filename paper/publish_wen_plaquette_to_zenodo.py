#!/usr/bin/env python3
"""
publish_wen_plaquette_to_zenodo.py (v1.1.0) — Uploads and publishes OSIRIS-QEC
v1.1.0 (manuscript, vector figures, immutable v1.0.0 + hash-locked v1.1.0
manifests, RFC 8785 ledger schema, 16/16 Y-sweep report, and full reproducibility
bundle) as a linked Zenodo version preserving v1.0.0 (`10.5281/zenodo.24406733`).

Reads `ZENODO_API_TOKEN` from `/home/osiris/osiris-ide/.env` or environment
without ever printing or logging credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

API_BASE = "https://zenodo.org/api/deposit/depositions"
V100_DOI = "10.5281/zenodo.24406733"


def _get_token() -> str:
    for key in ("ZENODO_API_TOKEN", "OSIRIS_ZENODO_TOKEN", "ZENODO_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    for p in (Path("/home/osiris/osiris-ide/.env"), Path.home() / ".env"):
        if p.is_file():
            for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if line.startswith(("ZENODO_API_TOKEN=", "OSIRIS_ZENODO_TOKEN=", "ZENODO_TOKEN=")):
                    tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if tok:
                        return tok
    raise RuntimeError("Zenodo token not found in environment or /home/osiris/osiris-ide/.env")


def _call(
    method: str,
    url: str,
    token: str,
    data: Dict[str, Any] | None = None,
    raw: bytes | None = None,
    ctype: str | None = "application/json",
) -> Tuple[int, Dict[str, Any]]:
    import time
    body = raw if raw is not None else (json.dumps(data).encode("utf-8") if data is not None else None)
    headers = {"Authorization": f"Bearer {token}"}
    if ctype and body is not None:
        headers["Content-Type"] = ctype
    for attempt in range(5):
        req = urllib.request.Request(url, method=method, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                txt = resp.read().decode("utf-8")
                return resp.status, (json.loads(txt) if txt else {})
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2.5 * (attempt + 1))
                continue
            txt = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(txt)
            except Exception:
                return exc.code, {"raw": txt[:500]}
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                time.sleep(2.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"Unreachable retry loop for {url}")


def build_metadata(repo_url: str, manifest_v11: Dict[str, Any]) -> Dict[str, Any]:
    pre_sha = manifest_v11["precompile_sha256"]
    h2_sha = manifest_v11["isa_sha256"]
    return {
        "upload_type": "publication",
        "publication_type": "preprint",
        "publication_date": "2026-11-21",
        "title": (
            "Hardened Compiler Passes, Exact 256-Branch & 16/16 Fault-Taxonomy Verification, "
            "RFC 8785 Execution Ledger, and Hash-Locked Quantinuum H2 Dispatch for 20-Qubit "
            "Toroidal Wen-Plaquette Feed-Forward Preparation (OSIRIS-QEC v1.1.0)"
        ),
        "creators": [
            {
                "name": "Davis, Devin Phillip",
                "affiliation": "Agile Defense Systems LLC",
            }
        ],
        "description": (
            "<p><strong>Status: HARDWARE-UNVALIDATED</strong> (exact local 20-qubit statevector enumeration, "
            "dual-basis Qiskit Aer C++ simulation, Selene local dry-run validation, 16/16 pre/post-preparation "
            "fault taxonomy, and offline <code>pytket-quantinuum</code> H2-1 ISA compilation; zero provider jobs "
            "have been submitted).</p>"
            "<p><strong>Preregistered Artifact Lock:</strong> Compilation and execution enforce a fail-closed "
            f"cryptographic lock verifying pre-compile SHA-256 (<code>{pre_sha}</code>) and Quantinuum H2-1 ISA "
            f"SHA-256 (<code>{h2_sha}</code>, depth <code>19</code>, <code>32 ZZPhase</code>) both pre-flight and "
            "post-compile under <code>optimisation_level=0</code>, preserving the immutable v1.0.0 baseline "
            f"(<code>{V100_DOI}</code>) bit-for-bit.</p>"
            "<ul>"
            "<li><strong>Provenance &amp; Hardware Allocation:</strong> Underlying 4&times;4 toroidal Wen-plaquette "
            "2-round LUT protocol credited to Iqbal <em>et al.</em> (<code>arXiv:2302.01917</code>) and Quantinuum's "
            "official tutorial. Sixteen vertex qubits encode <code>[[16, 2, 4]]</code> while 4 recycled ancillas "
            "execute mid-circuit syndrome checks (<code>24 Measure</code>, <code>8 Reset</code>; ancillas do not "
            "contribute to logical code distance).</li>"
            "<li><strong>v1.1.0 Compiler Hardening &amp; Metadata Determinism:</strong> Rejects colliding registers "
            "(<code>q</code>, <code>qr</code>, <code>quantum</code>, <code>c</code>, <code>creg</code>, "
            "<code>cl</code>, <code>classical</code>) and non-empty circuits with <code>ValueError</code>, and "
            "normalizes <code>name</code>, <code>phase</code>, and <code>metadata</code> prior to hashing.</li>"
            "<li><strong>Complete 16/16 Post-Preparation Y-Fault Sweep:</strong> Expands post-preparation Pauli-Y "
            "injection across all 16 data qubits (<code>16/16</code> partially detected via X-syndrome, "
            "<code>0/16</code> preserved, <code>F_L = 0.0</code>), confirming state preparation &ne; QEC memory.</li>"
            "<li><strong><code>osiris qec</code> CLI, QNexus Retries &amp; RFC 8785 Write-Ahead Ledger:</strong> "
            "Adds <code>osiris qec verify|run|manifest|ledger</code>, atomic IETF RFC 8785 hash-chained write-ahead "
            "logging, bounded exponential backoff for transient gateway errors, and mock QNexus integration tests.</li>"
            "</ul>"
        ),
        "access_right": "open",
        "license": "cc-by-4.0",
        "version": "1.1.0",
        "keywords": [
            "quantum error correction",
            "Wen-plaquette code",
            "toric code",
            "mid-circuit measurement",
            "classical feed-forward",
            "pytket",
            "Quantinuum H2",
            "RFC 8785",
            "pre-registered quantum experiment",
            "OSIRIS-QEC",
        ],
        "related_identifiers": [
            {
                "identifier": f"{repo_url}/tree/v1.1.0",
                "relation": "isSupplementTo",
                "scheme": "url",
            },
            {
                "identifier": V100_DOI,
                "relation": "isNewVersionOf",
                "scheme": "doi",
            },
            {
                "identifier": "arXiv:2302.01917",
                "relation": "cites",
                "scheme": "arxiv",
            },
            {
                "identifier": "10.5281/zenodo.24293756",
                "relation": "references",
                "scheme": "doi",
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/home/osiris/qec"))
    parser.add_argument("--deposition-id", type=int, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-url", default="https://github.com/quantum-osiris/osiris-qec")
    parser.add_argument("--draft-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.draft_only and not args.publish:
        parser.error("Specify --draft-only or --publish")

    root = args.root.resolve()
    paper_dir = root / "paper"
    manifest_v11 = json.loads((root / "hardware" / "experiment_manifest_v1_1_0.json").read_text(encoding="utf-8"))

    files = [
        paper_dir / "wen_plaquette_feedforward_qec_v1_1.pdf",
        paper_dir / "wen_plaquette_feedforward_qec_v1_1.tex",
        paper_dir / "fig1_torus_checkerboard_lut.pdf",
        paper_dir / "fig2_noisy_fidelity_benchmark.pdf",
        paper_dir / "fig3_error_taxonomy_and_wilson_gate.pdf",
        paper_dir / "SHA256SUMS.txt",
        args.bundle.resolve(),
        root / "hardware" / "experiment_manifest_v1_0_0.json",
        root / "hardware" / "experiment_manifest_v1_1_0.json",
        root / "hardware" / "ledger_schema_v1_1_0.json",
        root / "hardware" / "hashlock_policy_v1_1_0.md",
        root / "reports" / "POST_PREP_Y_SWEEP_V1_1.json",
        root / "reports" / "POST_PREP_INJECTION.json",
        root / "reports" / "ERROR_CORRECTION_MATRIX.json",
        root / "reports" / "QEC_BENCHMARK_RESULTS.json",
        root / "submission" / "EXPERIMENT_PROTOCOL.md",
        root / "CHANGELOG.md",
        root / "SECURITY_REVIEW.md",
    ]
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f"Missing required artifact file: {f}")

    token = _get_token()
    did = args.deposition_id
    st, dep = _call("GET", f"{API_BASE}/{did}", token, ctype=None)
    if st != 200:
        raise RuntimeError(f"Failed to fetch Zenodo deposition {did} (HTTP {st}): {dep}")

    bucket = dep["links"]["bucket"]
    st, meta_res = _call("PUT", f"{API_BASE}/{did}", token, data={"metadata": build_metadata(args.repo_url, manifest_v11)})
    if st not in (200, 201):
        raise RuntimeError(f"Failed to set Zenodo metadata (HTTP {st}): {meta_res}")

    uploaded = []
    for f in files:
        raw = f.read_bytes()
        st, up_res = _call("PUT", f"{bucket}/{f.name}", token, raw=raw, ctype="application/octet-stream")
        if st not in (200, 201):
            raise RuntimeError(f"Upload failed for {f.name} (HTTP {st}): {up_res}")
        uploaded.append({"name": f.name, "bytes": len(raw), "checksum": up_res.get("checksum")})

    if args.draft_only:
        prereserve = (meta_res.get("metadata") or {}).get("prereserve_doi") or {}
        print(
            json.dumps(
                {
                    "state": "draft",
                    "deposition_id": did,
                    "prereserved_doi": prereserve.get("doi"),
                    "draft_url": f"https://zenodo.org/deposit/{did}",
                    "uploaded_files_count": len(uploaded),
                },
                indent=2,
            )
        )
        return 0

    st, pub = _call("POST", f"{API_BASE}/{did}/actions/publish", token, ctype=None)
    if st not in (200, 201, 202):
        raise RuntimeError(f"Zenodo publish failed (HTTP {st}): {pub}")

    receipt = {
        "package": "osiris-qec",
        "version": "1.1.0",
        "status": "HARDWARE-UNVALIDATED",
        "baseline_v1_0_0_doi": V100_DOI,
        "record_id": pub.get("id"),
        "doi": pub.get("doi"),
        "conceptdoi": pub.get("conceptdoi"),
        "doi_url": pub.get("doi_url"),
        "record_html": (pub.get("links") or {}).get("record_html", f"https://zenodo.org/records/{pub.get('id')}"),
        "github_release_url": f"{args.repo_url}/releases/tag/v1.1.0",
        "precompile_sha256": manifest_v11["precompile_sha256"],
        "isa_sha256": manifest_v11["isa_sha256"],
        "optimisation_level": 0,
        "state": pub.get("state"),
        "submitted": pub.get("submitted"),
        "created": pub.get("created"),
        "uploaded_files": uploaded,
    }
    receipt_out = root / "submission" / "zenodo_publication_receipt_v1_1_0.json"
    receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
