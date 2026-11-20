#!/usr/bin/env python3
"""
publish_wen_plaquette_to_zenodo.py — Uploads and publishes the standalone
Wen-plaquette feed-forward QEC manuscript, vector figures, frozen H2 manifest,
verification reports, and complete reproducibility bundle to Zenodo.

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
    req = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            txt = resp.read().decode("utf-8")
            return resp.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as exc:
        txt = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(txt)
        except Exception:
            return exc.code, {"raw": txt[:500]}


def build_metadata(repo_url: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    pre_sha = manifest["circuits"][0]["pre_compile_sha256"]
    h2_sha = manifest["circuits"][0]["h2_compiled_sha256"]
    return {
        "upload_type": "publication",
        "publication_type": "preprint",
        "publication_date": "2026-11-20",
        "title": (
            "Compiler-Contract Enforcement, Exact 256-Branch Verification, Pre/Post-Preparation "
            "Error Taxonomy, and Pre-Registered Quantinuum H2 Protocol for 20-Qubit Toroidal "
            "Wen-Plaquette Feed-Forward Preparation"
        ),
        "creators": [
            {
                "name": "Davis, Devin Phillip",
                "affiliation": "Agile Defense Systems LLC",
            }
        ],
        "description": (
            "<p><strong>Status: HARDWARE-UNVALIDATED</strong> (local exact 20-qubit statevector enumeration, "
            "dual-basis Qiskit Aer C++ simulation, reproducible Monte Carlo depolarizing benchmarks, and offline "
            "<code>pytket-quantinuum</code> H2-1 ISA compilation; zero provider jobs have been submitted).</p>"
            "<p>Complete standalone manuscript (<code>wen_plaquette_feedforward_qec_v1.pdf</code>), LaTeX source, "
            "vector figures, contract-enforced <code>pytket</code> <code>CustomPass</code> "
            "(<code>wen_plaquette_pass.py</code>), independent GF(2) symplectic verifier (<code>qec_math.py</code>, "
            "<code>verify_independent.py</code>), 33-test regression suite, frozen Quantinuum H2 execution manifest "
            f"(pre-compile SHA-256 <code>{pre_sha}</code>; H2-1 compiled SHA-256 <code>{h2_sha}</code>), and full "
            "reproducibility archive (<code>osiris-qec-v1.0.0-reproducibility-bundle.tar.gz</code>).</p>"
            "<ul>"
            "<li><strong>Provenance &amp; Contribution Boundary:</strong> The underlying 4&times;4 toroidal "
            "Wen-plaquette two-round measurement and 7-entry lookup-table (LUT) feed-forward preparation protocol is "
            "prior art (Iqbal <em>et al.</em>, <code>arXiv:2302.01917</code>, and Quantinuum's official tutorial "
            "<em>Topological Order from Measurements and Feed-Forward</em>). This package contributes the enforced "
            "preparation-only <code>pytket</code> compiler contract, independent symplectic distance proof "
            "(<code>[[16, 2, 4]]</code>), exhaustive 256-branch verification, pre/post-preparation fault taxonomy, "
            "and pre-registered Quantinuum H2 statistical acceptance protocol.</li>"
            "<li><strong>Exact 256-Branch Verification &amp; Dual-Basis Aer Cross-Checks:</strong> Exhaustive "
            "non-sampled enumeration of all 2<sup>8</sup> = 256 mid-circuit syndrome trajectories confirms 128 "
            "reachable even-parity branches landing in the +1 stabilizer codespace (worst stabilizer expectation "
            "<code>0.9999999999999942</code>; branch-to-branch fidelity <code>0.9999999999999885</code> to fixed "
            "<code>|00&gt;_L</code>) and 128 zero-amplitude odd-parity branches, cross-checked on Qiskit "
            "<code>AerBackend</code> in both <code>X</code> (512 shots, 0 violations) and <code>Z</code> (256 shots, "
            "0 violations) readout bases.</li>"
            "<li><strong>Pre- vs. Post-Preparation Fault Taxonomy (Preparation &ne; Memory):</strong> Single-qubit "
            "<code>Z</code> errors injected <em>before</em> preparation are corrected 16/16 times (fidelity "
            "<code>1.0000</code>), whereas <code>Z</code> errors injected <em>after</em> preparation produce nonzero "
            "<code>X</code>-syndromes (16/16 detectable) but are <em>not</em> corrected (0/16, fidelity "
            "<code>&lt; 0.001</code>), and <code>X</code> errors remain undetected because <code>Z</code> stabilizers "
            "are never measured.</li>"
            "<li><strong>Frozen Quantinuum H2-1 ISA &amp; Statistical Wilson Gate:</strong> Offline compilation to "
            "H2-1 native gates yields depth 19 (<code>32 ZZPhase</code>, <code>72 PhasedX</code>, <code>20 Rz</code>, "
            "<code>20 Conditional</code>, <code>24 Measure</code>, <code>8 Reset</code>; 20/56 qubits, 28/4000 clbits) "
            "for execution via <code>qnexus</code> 0.51.4 (<code>H2-1SC &rarr; H2-1E &rarr; H2-1</code>) governed by a "
            "per-basis 95% Wilson lower confidence bound <code>&gt; 0.99</code> (512/512, 997/1000, 1989/2000, "
            "4964/5000, 9920/10000).</li>"
            "</ul>"
        ),
        "access_right": "open",
        "license": "cc-by-4.0",
        "version": "1.0.0",
        "keywords": [
            "quantum error correction",
            "Wen-plaquette code",
            "toric code",
            "mid-circuit measurement",
            "classical feed-forward",
            "pytket",
            "Quantinuum H2",
            "pre-registered quantum experiment",
            "OSIRIS-QEC",
        ],
        "related_identifiers": [
            {
                "identifier": f"{repo_url}/tree/v1.0.0",
                "relation": "isSupplementTo",
                "scheme": "url",
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
    parser.add_argument("--deposition-id", type=int, default=0)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-url", default="https://github.com/quantum-osiris/osiris-qec")
    parser.add_argument("--draft-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.draft_only and not args.publish:
        parser.error("Specify --draft-only or --publish")

    root = args.root.resolve()
    paper_dir = root / "paper"
    manifest = json.loads((root / "hardware" / "experiment_manifest.json").read_text(encoding="utf-8"))

    files = [
        paper_dir / "wen_plaquette_feedforward_qec_v1.pdf",
        paper_dir / "wen_plaquette_feedforward_qec_v1.tex",
        paper_dir / "fig1_torus_checkerboard_lut.pdf",
        paper_dir / "fig2_noisy_fidelity_benchmark.pdf",
        paper_dir / "fig3_error_taxonomy_and_wilson_gate.pdf",
        paper_dir / "SHA256SUMS.txt",
        args.bundle.resolve(),
        root / "hardware" / "experiment_manifest.json",
        root / "submission" / "CLAIMS_AND_EVIDENCE.json",
        root / "submission" / "EXPERIMENT_PROTOCOL.md",
        root / "submission" / "TECHNICAL_REPORT.md",
        root / "submission" / "REPRODUCIBILITY.md",
        root / "reports" / "QEC_BENCHMARK_RESULTS.json",
        root / "reports" / "QEC_BENCHMARK_RESULTS.png",
        root / "reports" / "ERROR_CORRECTION_MATRIX.json",
        root / "reports" / "POST_PREP_INJECTION.json",
    ]
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f"Missing required artifact file: {f}")

    token = _get_token()
    if args.deposition_id:
        did = args.deposition_id
        st, dep = _call("GET", f"{API_BASE}/{did}", token, ctype=None)
        if st != 200:
            raise RuntimeError(f"Failed to fetch Zenodo deposition {did} (HTTP {st}): {dep}")
    else:
        st, dep = _call("POST", API_BASE, token, data={})
        if st not in (200, 201):
            raise RuntimeError(f"Failed to create Zenodo deposition (HTTP {st}): {dep}")
        did = dep["id"]

    bucket = dep["links"]["bucket"]
    st, meta_res = _call("PUT", f"{API_BASE}/{did}", token, data={"metadata": build_metadata(args.repo_url, manifest)})
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
        "version": "1.0.0",
        "status": "HARDWARE-UNVALIDATED",
        "record_id": pub.get("id"),
        "doi": pub.get("doi"),
        "conceptdoi": pub.get("conceptdoi"),
        "doi_url": pub.get("doi_url"),
        "record_html": (pub.get("links") or {}).get("record_html", f"https://zenodo.org/records/{pub.get('id')}"),
        "github_release_url": f"{args.repo_url}/releases/tag/v1.0.0",
        "pre_compile_sha256": manifest["circuits"][0]["pre_compile_sha256"],
        "h2_compiled_sha256": manifest["circuits"][0]["h2_compiled_sha256"],
        "state": pub.get("state"),
        "submitted": pub.get("submitted"),
        "created": pub.get("created"),
        "uploaded_files": uploaded,
    }
    receipt_out = root / "submission" / "zenodo_publication_receipt.json"
    receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
