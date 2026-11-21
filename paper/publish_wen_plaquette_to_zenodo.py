#!/usr/bin/env python3
"""
publish_wen_plaquette_to_zenodo.py (v1.1.1 / OSIRIS-QEC-002) — Uploads and
publishes OSIRIS-QEC v1.1.1 (manuscript, vector figures, arXiv `quant-ph`
submission tarball, manifests, strict `rfc8785` schema, 16/16 Y-sweep report,
and full reproducibility archive) as a linked Zenodo version preserving both
v1.0.0 (`10.5281/zenodo.24406733`) and v1.1.0 (`10.5281/zenodo.24421051`).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple

API_BASE = "https://zenodo.org/api/deposit/depositions"
V100_DOI = "10.5281/zenodo.24406733"
V110_DOI = "10.5281/zenodo.24421051"


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


def build_metadata(repo_url: str, manifest_v111: Dict[str, Any]) -> Dict[str, Any]:
    pre_sha = manifest_v111["precompile_sha256"]
    h2_sha = manifest_v111["isa_sha256"]
    return {
        "upload_type": "publication",
        "publication_type": "preprint",
        "publication_date": "2026-11-21",
        "title": (
            "State Preparation Is Not Quantum Memory: Exact 256-Branch Verification, 16/16 "
            "Post-Preparation Fault Taxonomy, Strict RFC 8785 Provenance, and Hash-Locked "
            "Quantinuum H2 Dispatch for [[16, 2, 4]] Wen-Plaquette Codes (OSIRIS-QEC-002, osiris-qec v1.1.1)"
        ),
        "creators": [
            {
                "name": "Davis, Devin Phillip",
                "affiliation": "Agile Defense Systems LLC",
            }
        ],
        "description": (
            "<p><strong>Status: HARDWARE-UNVALIDATED</strong> (benchmark <code>OSIRIS-QEC-002</code>, package "
            "<code>osiris-qec v1.1.1</code>; exact 20-qubit statevector enumeration, dual-basis Qiskit Aer C++ "
            "simulation, Selene local dry-run validation, 16/16 pre/post-preparation fault taxonomy, and offline "
            "<code>pytket-quantinuum</code> H2-1 ISA compilation; zero provider jobs submitted).</p>"
            "<p><strong>Headline Scope Result (State Preparation &ne; QEC Memory):</strong> While weight-1 Pauli-"
            "<code>Z</code> faults injected <em>before</em> preparation on the <code>[[16, 2, 4]]</code> periodic "
            "Wen-plaquette circuit (16 data qubits + 4 recycled ancillas; prior art Iqbal <em>et al.</em>, "
            "<code>arXiv:2302.01917</code>) are corrected 16/16 times (fidelity <code>1.0</code>), complete 16/16 "
            "<em>post</em>-preparation Pauli-<code>Y</code> and Pauli-<code>Z</code> sweeps across all data qubits "
            "<code>q[0..15]</code> excite nonzero X-syndromes (16/16 detected) yet preserve the encoded logical "
            "state in <strong>0/16</strong> cases (<code>F_L = 0.0</code> for <code>Y</code>; <code>&lt; 10^-3</code> "
            "for <code>Z</code>), and <code>X</code> faults escape detection because <code>Z</code> stabilizers are "
            "never measured.</p>"
            "<ul>"
            "<li><strong>v1.1.1 Normative RFC 8785 Pin:</strong> Write-ahead execution ledgering is pinned "
            "exclusively to Trail of Bits' <code>rfc8785==0.1.4</code> JCS serializer with zero stdlib "
            "<code>json.dumps</code> fallback, guaranteeing byte-exact IEEE-754 float canonicalization across "
            "third-party verifiers.</li>"
            "<li><strong>Gateway Congestion &amp; UTC Hygiene:</strong> <code>qnexus 0.51.4</code> transport honors "
            "HTTP <code>Retry-After</code> headers and applies &plusmn;25% randomized backoff jitter while failing "
            "closed immediately on integrity or <code>401</code>/<code>403</code> errors; all timestamps use "
            "timezone-aware UTC.</li>"
            "<li><strong>Preregistered Artifact Lock &amp; arXiv Bundle:</strong> Compilation and execution enforce "
            f"pre-compile SHA-256 (<code>{pre_sha}</code>) and H2-1 ISA SHA-256 (<code>{h2_sha}</code>, depth 19, "
            "32 <code>ZZPhase</code>) both pre-flight and post-compile under <code>optimisation_level=0</code>, "
            "shipped alongside a ready-to-upload <code>arXiv</code> <code>quant-ph</code> TeX bundle "
            "(<code>osiris-qec-v1.1.1-arxiv-quant-ph.tar.gz</code>).</li>"
            "</ul>"
        ),
        "access_right": "open",
        "license": "cc-by-4.0",
        "version": "1.1.1",
        "keywords": [
            "quantum error correction",
            "Wen-plaquette code",
            "toric code",
            "mid-circuit measurement",
            "classical feed-forward",
            "pytket",
            "Quantinuum H2",
            "RFC 8785",
            "OSIRIS-QEC-002",
        ],
        "related_identifiers": [
            {"identifier": f"{repo_url}/tree/v1.1.1", "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": V110_DOI, "relation": "isNewVersionOf", "scheme": "doi"},
            {"identifier": V100_DOI, "relation": "references", "scheme": "doi"},
            {"identifier": "arXiv:2302.01917", "relation": "cites", "scheme": "arxiv"},
            {"identifier": "10.5281/zenodo.24293756", "relation": "references", "scheme": "doi"},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/home/osiris/qec"))
    parser.add_argument("--deposition-id", type=int, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--arxiv-bundle", type=Path, default=Path("/tmp/osiris-qec-v1.1.1-arxiv-quant-ph.tar.gz"))
    parser.add_argument("--repo-url", default="https://github.com/quantum-osiris/osiris-qec")
    parser.add_argument("--draft-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.draft_only and not args.publish:
        parser.error("Specify --draft-only or --publish")

    root = args.root.resolve()
    paper_dir = root / "paper"
    manifest_v111 = json.loads((root / "hardware" / "experiment_manifest_v1_1_1.json").read_text(encoding="utf-8"))

    files = [
        paper_dir / "wen_plaquette_feedforward_qec_v1_1_1.pdf",
        paper_dir / "wen_plaquette_feedforward_qec_v1_1_1.tex",
        paper_dir / "fig1_torus_checkerboard_lut.pdf",
        paper_dir / "fig2_noisy_fidelity_benchmark.pdf",
        paper_dir / "fig3_error_taxonomy_and_wilson_gate.pdf",
        paper_dir / "SHA256SUMS.txt",
        args.arxiv_bundle.resolve(),
        args.bundle.resolve(),
        root / "hardware" / "experiment_manifest_v1_0_0.json",
        root / "hardware" / "experiment_manifest_v1_1_0.json",
        root / "hardware" / "experiment_manifest_v1_1_1.json",
        root / "hardware" / "ledger_schema_v1_1_0.json",
        root / "hardware" / "hashlock_policy_v1_1_0.md",
        root / "reports" / "POST_PREP_Y_SWEEP_V1_1.json",
        root / "reports" / "POST_PREP_INJECTION.json",
        root / "reports" / "ERROR_CORRECTION_MATRIX.json",
        root / "reports" / "QEC_BENCHMARK_RESULTS.json",
        root / "submission" / "EXPERIMENT_PROTOCOL.md",
        root / "submission" / "ARXIV_SUBMISSION.md",
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
    st, meta_res = _call("PUT", f"{API_BASE}/{did}", token, data={"metadata": build_metadata(args.repo_url, manifest_v111)})
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
        "protocol": "OSIRIS-QEC-002",
        "version": "1.1.1",
        "status": "HARDWARE-UNVALIDATED",
        "baseline_v1_0_0_doi": V100_DOI,
        "previous_v1_1_0_doi": V110_DOI,
        "record_id": pub.get("id"),
        "doi": pub.get("doi"),
        "conceptdoi": pub.get("conceptdoi"),
        "doi_url": pub.get("doi_url"),
        "record_html": (pub.get("links") or {}).get("record_html", f"https://zenodo.org/records/{pub.get('id')}"),
        "github_release_url": f"{args.repo_url}/releases/tag/v1.1.1",
        "precompile_sha256": manifest_v111["precompile_sha256"],
        "isa_sha256": manifest_v111["isa_sha256"],
        "jcs_serializer": "rfc8785==0.1.4",
        "optimisation_level": 0,
        "state": pub.get("state"),
        "submitted": pub.get("submitted"),
        "created": pub.get("created"),
        "uploaded_files": uploaded,
    }
    receipt_out = root / "submission" / "zenodo_publication_receipt_v1_1_1.json"
    receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
