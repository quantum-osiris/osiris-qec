#!/usr/bin/env python3
"""
generate_paper_assets.py (v1.1.0) — Deterministic vector SVG + PDF 1.4 generator
for OSIRIS-QEC v1.1.0 (Hardened Compiler Passes, 16/16 Post-Prep Y-Sweep, RFC 8785
Write-Ahead Ledger, and Provenance-Locked Quantinuum H2 Execution Protocol).

Reads exact computed values from:
  - `reports/QEC_BENCHMARK_RESULTS.json`
  - `reports/ERROR_CORRECTION_MATRIX.json`
  - `reports/POST_PREP_INJECTION.json`
  - `reports/POST_PREP_Y_SWEEP_V1_1.json`
  - `hardware/experiment_manifest_v1_0_0.json`
  - `hardware/experiment_manifest_v1_1_0.json`
  - `submission/CLAIMS_AND_EVIDENCE.json`
Preserves `HARDWARE-UNVALIDATED` status and immutable v1.0.0 hashes verbatim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

V100_DOI = "10.5281/zenodo.24406733"
CONCEPT_DOI = "10.5281/zenodo.24406732"


def _pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("`", "")
        .replace("±", "+/-")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("×", "x")
        .replace("—", "--")
        .replace("–", "-")
        .replace("−", "-")
        .replace("≠", "!=")
        .replace("→", "->")
        .replace("σ", " sigma")
        .replace("μ", "u")
        .replace("µ", "u")
    )


class VectorCanvas:
    """Dual SVG + PDF 1.4 vector graphics builder (top-left origin `(0, 0)` in points)."""

    def __init__(self, width: float, height: float):
        self.w = float(width)
        self.h = float(height)
        self.svg: List[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.0f}" height="{self.h:.0f}" viewBox="0 0 {self.w:.0f} {self.h:.0f}">',
            f'<rect x="0" y="0" width="{self.w:.0f}" height="{self.h:.0f}" fill="#ffffff"/>',
        ]
        self.pdf: List[str] = ["1 1 1 rg", f"0 0 {self.w:.2f} {self.h:.2f} re f"]

    def _py(self, y: float) -> float:
        return self.h - y

    @staticmethod
    def _rgb(hex_color: str) -> Tuple[float, float, float]:
        c = hex_color.lstrip("#")
        return int(c[0:2], 16) / 255.0, int(c[2:4], 16) / 255.0, int(c[4:6], 16) / 255.0

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str | None = None,
        stroke: str | None = None,
        lw: float = 1.0,
    ) -> None:
        s_fill = fill if fill else "none"
        s_stroke = f' stroke="{stroke}" stroke-width="{lw:.2f}"' if stroke else ""
        self.svg.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{s_fill}"{s_stroke}/>'
        )
        py = self._py(y + h)
        if fill and stroke:
            fr, fg, fb = self._rgb(fill)
            sr, sg, sb = self._rgb(stroke)
            self.pdf.append(
                f"{lw:.2f} w {fr:.3f} {fg:.3f} {fb:.3f} rg {sr:.3f} {sg:.3f} {sb:.3f} RG {x:.2f} {py:.2f} {w:.2f} {h:.2f} re B"
            )
        elif fill:
            fr, fg, fb = self._rgb(fill)
            self.pdf.append(f"{fr:.3f} {fg:.3f} {fb:.3f} rg {x:.2f} {py:.2f} {w:.2f} {h:.2f} re f")
        elif stroke:
            sr, sg, sb = self._rgb(stroke)
            self.pdf.append(f"{lw:.2f} w {sr:.3f} {sg:.3f} RG {x:.2f} {py:.2f} {w:.2f} {h:.2f} re S")

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "#111827",
        lw: float = 1.0,
        dashed: bool = False,
    ) -> None:
        dash_svg = ' stroke-dasharray="5,3"' if dashed else ""
        self.svg.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{lw:.2f}"{dash_svg}/>'
        )
        r, g, b = self._rgb(color)
        dash_pdf = "[5 3] 0 d" if dashed else "[] 0 d"
        self.pdf.append(
            f"q {dash_pdf} {lw:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {x1:.2f} {self._py(y1):.2f} m {x2:.2f} {self._py(y2):.2f} l S Q"
        )

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: str = "#ffffff",
        stroke: str = "#111827",
        lw: float = 1.4,
    ) -> None:
        self.svg.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{lw:.2f}"/>'
        )
        fr, fg, fb = self._rgb(fill)
        sr, sg, sb = self._rgb(stroke)
        py = self._py(cy)
        k = 0.55228475 * r
        self.pdf.append(
            f"q {lw:.2f} w {fr:.3f} {fg:.3f} {fb:.3f} rg {sr:.3f} {sg:.3f} {sb:.3f} RG "
            f"{cx + r:.2f} {py:.2f} m "
            f"{cx + r:.2f} {py + k:.2f} {cx + k:.2f} {py + r:.2f} {cx:.2f} {py + r:.2f} c "
            f"{cx - k:.2f} {py + r:.2f} {cx - r:.2f} {py + k:.2f} {cx - r:.2f} {py:.2f} c "
            f"{cx - r:.2f} {py - k:.2f} {cx - k:.2f} {py - r:.2f} {cx:.2f} {py - r:.2f} c "
            f"{cx + k:.2f} {py - r:.2f} {cx + r:.2f} {py - k:.2f} {cx + r:.2f} {py:.2f} c B Q"
        )

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 10.0,
        color: str = "#111827",
        bold: bool = False,
        anchor: str = "start",
        mono: bool = False,
    ) -> None:
        fam_svg = "monospace" if mono else "Helvetica, Arial, sans-serif"
        wt_svg = "bold" if bold else "normal"
        esc_svg = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.svg.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-family="{fam_svg}" font-size="{size:.1f}" '
            f'font-weight="{wt_svg}" fill="{color}" text-anchor="{anchor}">{esc_svg}</text>'
        )
        esc_pdf = _pdf_escape(s)
        font_tag = "/F3" if mono else ("/F2" if bold else "/F1")
        char_w = 0.60 if mono else (0.53 if bold else 0.50)
        approx_w = len(esc_pdf) * size * char_w
        px = x if anchor == "start" else (x - 0.5 * approx_w if anchor == "middle" else x - approx_w)
        r, g, b = self._rgb(color)
        self.pdf.append(
            f"BT {font_tag} {size:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg {px:.2f} {self._py(y):.2f} Td ({esc_pdf}) Tj ET"
        )

    def to_svg(self) -> str:
        return "\n".join(self.svg + ["</svg>"]) + "\n"

    def pdf_stream(self) -> bytes:
        return ("\n".join(self.pdf) + "\n").encode("latin-1", errors="replace")

    def save(self, stem_path: Path) -> None:
        stem_path.with_suffix(".svg").write_text(self.to_svg(), encoding="utf-8")
        stem_path.with_suffix(".pdf").write_bytes(build_pdf_document([(self.w, self.h, self.pdf_stream())]))


def build_pdf_document(pages: Sequence[Tuple[float, float, bytes]]) -> bytes:
    objects: List[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    f1 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    f3 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    f4 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>")
    f5 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold >>")
    f6 = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic >>")

    pages_placeholder_idx = add_obj(b"")
    page_ids: List[int] = []

    for w, h, stream in pages:
        c_id = add_obj(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream")
        p_id = add_obj(
            f"<< /Type /Page /Parent {pages_placeholder_idx} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] "
            f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R /F3 {f3} 0 R /F4 {f4} 0 R /F5 {f5} 0 R /F6 {f6} 0 R >> >> "
            f"/Contents {c_id} 0 R >>".encode("ascii")
        )
        page_ids.append(p_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_placeholder_idx - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_placeholder_idx} 0 R >>".encode("ascii"))

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = []
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf.extend(f"{idx} 0 obj\n".encode("ascii"))
        buf.extend(obj)
        buf.extend(b"\nendobj\n")

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        buf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(buf)


def make_fig1_torus_and_lut() -> VectorCanvas:
    c = VectorCanvas(540, 206)
    c.text(
        270,
        15,
        "4x4 Toroidal Wen-Plaquette CSS Code ([[16, 2, 4]]: 16 Data + 4 Recycled Ancillas) & LUT",
        size=9.3,
        bold=True,
        anchor="middle",
    )

    gx, gy, cell = 34.0, 36.0, 34.0
    c.text(gx + 2 * cell, 28, "(a) Checkerboard Torus (q_{4r+c})", size=8.2, bold=True, anchor="middle")
    r1_plaq = {4, 6, 12, 14}
    r2_plaq = {1, 3, 9, 11}
    r1_targets = {5, 7, 13, 15}

    for r in range(4):
        for col in range(4):
            idx = 4 * r + col
            x0 = gx + col * cell
            y0 = gy + r * cell
            is_x = ((r + col) % 2 == 1)
            if idx in r1_plaq:
                fill, lbl, tcol = "#dbeafe", f"X{idx} (R1)", "#1d4ed8"
            elif idx in r2_plaq:
                fill, lbl, tcol = "#dcfce7", f"X{idx} (R2)", "#047857"
            else:
                fill, lbl, tcol = "#f3f4f6", f"Z{idx}", "#4b5563"
            is_wrap = (r == 3 or col == 3)
            c.rect(x0, y0, cell, cell, fill=fill, stroke="#64748b", lw=0.7 if not is_wrap else 0.9)
            c.text(x0 + 0.5 * cell, y0 + 0.56 * cell, lbl, size=5.9 if is_x else 6.2, bold=is_x, color=tcol, anchor="middle", mono=True)

    for r in range(4):
        for col in range(4):
            q = 4 * r + col
            vx = gx + col * cell
            vy = gy + r * cell
            is_r1_z = q in r1_targets
            c.circle(vx, vy, 6.2, fill="#fef3c7" if is_r1_z else "#ffffff", stroke="#b45309" if is_r1_z else "#111827", lw=1.2)
            c.text(vx, vy + 2.2, str(q), size=5.8, bold=True, color="#92400e" if is_r1_z else "#111827", anchor="middle", mono=True)

    c.rect(gx, 180, 9, 7, fill="#dbeafe", stroke="#1d4ed8", lw=0.7)
    c.text(gx + 12, 186, "R1 X-plaq", size=6.5)
    c.rect(gx + 58, 180, 9, 7, fill="#dcfce7", stroke="#047857", lw=0.7)
    c.text(gx + 70, 186, "R2 X-plaq", size=6.5)
    c.circle(gx + 124, 183.5, 4.0, fill="#fef3c7", stroke="#b45309", lw=1.0)
    c.text(gx + 131, 186, "R1 cond-Z", size=6.5)

    tx, ty, tw, th = 208.0, 34.0, 316.0, 154.0
    c.text(tx + 0.5 * tw, 28, "(b) Round-2 Syndrome LUT (Ancillas A1, A3, A9, A11 -> c4_2nd)", size=8.2, bold=True, anchor="middle")
    c.rect(tx, ty, tw, th, fill="#fafafa", stroke="#334155", lw=0.9)
    c.rect(tx, ty, tw, 17.0, fill="#e2e8f0", stroke="#334155", lw=0.8)
    headers = [
        (tx + 8, "BE Synd."),
        (tx + 58, "LE Int"),
        (tx + 124, "Conditional Z Support"),
        (tx + 236, "R1 Disturb."),
    ]
    for hx, htxt in headers:
        c.text(hx, ty + 11.5, htxt, size=6.8, bold=True, mono=True)

    lut_rows = [
        ("0011", "12 (0b1100)", "Z on q[10], q[11]", "None (0/4)"),
        ("0101", "10 (0b1010)", "Z on q[4], q[8]", "None (0/4)"),
        ("0110", " 6 (0b0110)", "Z on q[0], q[13]", "None (0/4)"),
        ("1001", " 9 (0b1001)", "Z on q[2], q[15]", "None (0/4)"),
        ("1010", " 5 (0b0101)", "Z on q[5], q[9]", "None (0/4)"),
        ("1100", " 3 (0b0011)", "Z on q[6], q[7]", "None (0/4)"),
        ("1111", "15 (0b1111)", "Z on q[2, 3, 14, 15]", "None (0/4)"),
    ]
    for i, (be, le_str, z_sup, dist) in enumerate(lut_rows):
        ry = ty + 17.0 + i * 16.5
        if i % 2 == 1:
            c.rect(tx + 0.5, ry, tw - 1.0, 16.5, fill="#f1f5f9")
        c.text(tx + 12, ry + 11.2, be, size=6.8, bold=True, color="#0f172a", mono=True)
        c.text(tx + 58, ry + 11.2, le_str, size=6.4, color="#1e40af", mono=True)
        c.text(tx + 124, ry + 11.2, z_sup, size=6.5, color="#047857", mono=True)
        c.text(tx + 238, ry + 11.2, dist, size=6.5, color="#374151", mono=True)

    c.text(
        tx + 8,
        ty + th - 6,
        "4 recycled ancillas (24 Meas, 8 Reset) do not add logical distance.",
        size=6.3,
        color="#334155",
        mono=True,
    )
    return c


def summarize_benchmark(bench: Dict[str, Any]) -> List[Dict[str, float]]:
    rows = bench["results"]
    ps = sorted({float(r["p"]) for r in rows})
    summary: List[Dict[str, float]] = []
    for p in ps:
        ff_rows = [r for r in rows if abs(float(r["p"]) - p) < 1e-12 and r["feedforward"] is True]
        noff_rows = [r for r in rows if abs(float(r["p"]) - p) < 1e-12 and r["feedforward"] is False]
        ff_fid = sum(float(r["mean_logical_fidelity"]) for r in ff_rows) / len(ff_rows)
        ff_corr = sum(float(r["correction_success_rate"]) for r in ff_rows) / len(ff_rows)
        noff_fid = sum(float(r["mean_logical_fidelity"]) for r in noff_rows) / len(noff_rows)
        noff_corr = sum(float(r["correction_success_rate"]) for r in noff_rows) / len(noff_rows)
        total_shots = sum(int(r["shots"]) for r in ff_rows)
        se_fid = math.sqrt(max(ff_fid * (1.0 - ff_fid), 0.0) / max(total_shots, 1))
        se_corr = math.sqrt(max(ff_corr * (1.0 - ff_corr), 0.0) / max(total_shots, 1))
        summary.append(
            {
                "p": p,
                "shots": float(total_shots),
                "ff_fid": ff_fid,
                "ff_fid_ci95": 1.96 * se_fid,
                "ff_corr": ff_corr,
                "ff_corr_ci95": 1.96 * se_corr,
                "noff_fid": noff_fid,
                "noff_corr": noff_corr,
            }
        )
    return summary


def make_fig2_benchmark(summary: Sequence[Dict[str, float]]) -> VectorCanvas:
    c = VectorCanvas(540, 208)
    c.text(
        270,
        15,
        "Simulated Depolarizing + Readout/Reset Noise Benchmark (Seeds 11, 22, 33; 180 Shots/Point)",
        size=9.5,
        bold=True,
        anchor="middle",
    )

    panels = [
        ("ff_fid", "noff_fid", "ff_fid_ci95", "(a) Logical State Fidelity vs. Physical Error Rate p", 46.0, "#2563eb"),
        ("ff_corr", "noff_corr", "ff_corr_ci95", "(b) Codespace Correction Rate vs. Physical Error Rate p", 304.0, "#059669"),
    ]
    pw, ph, y0 = 216.0, 142.0, 36.0
    x_slots = [22.0, 68.0, 114.0, 160.0, 198.0]
    p_labels = ["0", "1e-4", "1e-3", "5e-3", "1e-2"]

    for ff_key, noff_key, ci_key, title, x0, col in panels:
        c.text(x0 + 0.5 * pw, 29, title, size=7.8, bold=True, anchor="middle")
        c.rect(x0, y0, pw, ph, fill="#fafafa", stroke="#374151", lw=0.9)
        for tv in (0.0, 0.25, 0.50, 0.75, 1.00):
            yy = y0 + ph * (1.0 - tv)
            c.line(x0, yy, x0 + pw, yy, color="#e5e7eb", lw=0.7, dashed=True)
            c.text(x0 - 4, yy + 2.5, f"{tv:.2f}", size=6.4, color="#374151", anchor="end", mono=True)

        ff_pts: List[Tuple[float, float]] = []
        noff_pts: List[Tuple[float, float]] = []
        for idx, row in enumerate(summary):
            xx = x0 + x_slots[idx]
            c.text(xx, y0 + ph + 11, p_labels[idx], size=6.5, bold=True, anchor="middle", mono=True)
            vf = max(0.0, min(1.0, row[ff_key]))
            vn = max(0.0, min(1.0, row[noff_key]))
            ci = row[ci_key]
            yf = y0 + ph * (1.0 - vf)
            yn = y0 + ph * (1.0 - vn)
            y_hi = y0 + ph * (1.0 - min(1.0, vf + ci))
            y_lo = y0 + ph * (1.0 - max(0.0, vf - ci))
            c.line(xx, y_hi, xx, y_lo, color=col, lw=1.0)
            c.line(xx - 3, y_hi, xx + 3, y_hi, color=col, lw=1.0)
            c.line(xx - 3, y_lo, xx + 3, y_lo, color=col, lw=1.0)
            ff_pts.append((xx, yf))
            noff_pts.append((xx, yn))

        for (x1, y1), (x2, y2) in zip(noff_pts[:-1], noff_pts[1:]):
            c.line(x1, y1, x2, y2, color="#9ca3af", lw=1.2, dashed=True)
        for (x1, y1), (x2, y2) in zip(ff_pts[:-1], ff_pts[1:]):
            c.line(x1, y1, x2, y2, color=col, lw=1.6)
        for px, py in noff_pts:
            c.circle(px, py, 2.3, fill="#9ca3af", stroke="#ffffff", lw=0.5)
        for px, py in ff_pts:
            c.circle(px, py, 2.8, fill=col, stroke="#ffffff", lw=0.6)

        leg_y1 = y0 + ph - 32.0
        leg_y2 = y0 + ph - 20.0
        c.rect(x0 + 8, leg_y1 - 7, 136, 23, fill="#ffffff", stroke="#cbd5e1", lw=0.6)
        c.line(x0 + 13, leg_y1, x0 + 25, leg_y1, color=col, lw=1.6)
        c.text(x0 + 29, leg_y1 + 2.3, "With LUT feed-forward", size=6.3, bold=True, color=col)
        c.line(x0 + 13, leg_y2, x0 + 25, leg_y2, color="#6b7280", lw=1.2, dashed=True)
        c.text(x0 + 29, leg_y2 + 2.3, "No feed-forward (~0.00-0.01)", size=6.2, color="#4b5563")

    c.text(
        270,
        200,
        "Physical error rate p (1Q/2Q depolarizing + measurement bit-flip + reset depolarizing; HARDWARE-UNVALIDATED)",
        size=6.8,
        color="#374151",
        anchor="middle",
    )
    return c


def make_fig3_taxonomy_and_gate(
    err_matrix: Sequence[Dict[str, Any]],
    post_prep: Sequence[Dict[str, Any]],
    y_sweep_v11: Dict[str, Any],
    manifest_v10: Dict[str, Any],
) -> VectorCanvas:
    c = VectorCanvas(540, 208)
    c.text(
        270,
        15,
        "Pre/Post-Prep Fault Taxonomy (Incl. 16/16 Y Sweep) & Hash-Locked H2 Gate (opt_level=0)",
        size=9.2,
        bold=True,
        anchor="middle",
    )

    w1_pre = {
        p: [r for r in err_matrix if r.get("pauli") == p and len(r.get("qubits", [])) == 1 and max(r["qubits"]) < 16]
        for p in ("Z", "X", "Y")
    }
    pre_z_corr = sum(float(r["corrected_fraction"]) for r in w1_pre["Z"]) / max(len(w1_pre["Z"]), 1)
    pre_x_corr = sum(float(r["corrected_fraction"]) for r in w1_pre["X"]) / max(len(w1_pre["X"]), 1)
    pre_y_corr = sum(float(r["corrected_fraction"]) for r in w1_pre["Y"]) / max(len(w1_pre["Y"]), 1)

    post_z = [r for r in post_prep if r["error"].startswith("Z on data") and "AFTER" in r["error"]]
    post_x = [r for r in post_prep if r["error"].startswith("X on data") and "AFTER" in r["error"]]

    post_z_det = sum(1.0 for r in post_z if r["detected"]) / max(len(post_z), 1)
    post_z_cor = sum(1.0 for r in post_z if r["corrected"]) / max(len(post_z), 1)
    post_x_det = sum(1.0 for r in post_x if r["detected"]) / max(len(post_x), 1)
    post_y_det = float(y_sweep_v11["detected_count"]) / float(y_sweep_v11["total_qubits"])
    post_y_cor = 1.0 if y_sweep_v11["all_preserved"] else 0.0

    ax0, ay0, aw, ah = 42.0, 36.0, 224.0, 138.0
    c.text(ax0 + 0.5 * aw, 29, "(a) Pauli Injection (Pre vs. Post, 16/16 Y Sweep)", size=7.6, bold=True, anchor="middle")
    c.rect(ax0, ay0, aw, ah, fill="#fafafa", stroke="#374151", lw=0.9)
    for tv in (0.0, 0.5, 1.0):
        yy = ay0 + ah * (1.0 - tv)
        c.line(ax0, yy, ax0 + aw, yy, color="#e5e7eb", lw=0.7, dashed=True)
        c.text(ax0 - 4, yy + 2.5, f"{int(tv*100)}%", size=6.4, anchor="end", mono=True)

    bars = [
        ("Pre Z", pre_z_corr, pre_z_corr),
        ("Pre X", pre_x_corr, pre_x_corr),
        ("Pre Y", pre_y_corr, pre_y_corr),
        ("Post Z", post_z_det, post_z_cor),
        ("Post X", post_x_det, 0.0),
        ("Post Y", post_y_det, post_y_cor),
    ]
    slot = aw / len(bars)
    for idx, (lbl, det_v, cor_v) in enumerate(bars):
        cx = ax0 + slot * (idx + 0.5)
        yd = ay0 + ah * (1.0 - det_v)
        yc = ay0 + ah * (1.0 - cor_v)
        c.rect(cx - 11, yd, 10, (ay0 + ah) - yd, fill="#f59e0b", stroke="#92400e", lw=0.7)
        c.rect(cx + 1, yc, 10, (ay0 + ah) - yc, fill="#059669", stroke="#065f46", lw=0.7)
        c.text(cx, ay0 + ah + 11, lbl, size=6.1, bold=True, anchor="middle", mono=True)

    c.rect(ax0 + 40, ay0 + 7, 82, 21, fill="#ffffff", stroke="#cbd5e1", lw=0.6)
    c.rect(ax0 + 44, ay0 + 10, 7, 5.5, fill="#f59e0b", stroke="#92400e", lw=0.6)
    c.text(ax0 + 54, ay0 + 15.0, "X-Syndrome Detected", size=5.9)
    c.rect(ax0 + 44, ay0 + 19, 7, 5.5, fill="#059669", stroke="#065f46", lw=0.6)
    c.text(ax0 + 54, ay0 + 24.0, "Codespace Corrected", size=5.9)
    c.text(ax0 + 0.5 * aw, 198, "Post-prep Z (16/16) & Y (16/16) detected, 0/32 corrected.", size=6.3, color="#374151", anchor="middle")

    bx0, by0, bw, bh = 284.0, 36.0, 240.0, 152.0
    c.text(bx0 + 0.5 * bw, 29, "(b) Hash-Locked H2-1 ISA & 95% Wilson Gate", size=7.8, bold=True, anchor="middle")
    c.rect(bx0, by0, bw, bh, fill="#f8fafc", stroke="#334155", lw=0.9)

    gates = manifest_v10["circuits"][0]["gate_counts_after_compile"]
    c.text(bx0 + 8, by0 + 13, f"Frozen H2-1 ISA (depth {manifest_v10['circuits'][0]['depth_after_compile']}, opt_level=0 lock):", size=6.5, bold=True, color="#0f172a", mono=True)
    c.text(
        bx0 + 8,
        by0 + 24,
        f"ZZPhase:{gates['ZZPhase']} PhasedX:{gates['PhasedX']} Rz:{gates['Rz']} Cond:{gates['Conditional']} Meas:{gates['Measure']} Rst:{gates['Reset']}",
        size=6.2,
        color="#1e40af",
        mono=True,
    )
    c.line(bx0 + 6, by0 + 30, bx0 + bw - 6, by0 + 30, color="#cbd5e1", lw=0.8)
    c.text(bx0 + 8, by0 + 41, "Shots/Basis   Min Pass (k)   Max Fail   Wilson LCB", size=6.3, bold=True, mono=True)
    wilson_rows = [
        (512, 512, 0, "0.9925"),
        (1000, 997, 3, "0.9912"),
        (2000, 1989, 11, "0.9902"),
        (5000, 4964, 36, "0.9900"),
        (10000, 9920, 80, "0.9900"),
    ]
    for idx, (n, k_min, f_max, lcb) in enumerate(wilson_rows):
        ry = by0 + 53 + idx * 14.5
        c.text(bx0 + 8, ry, f"{n:<11d}   {k_min:<12d}   {f_max:<8d}   {lcb}", size=6.3, color="#047857", mono=True)

    c.line(bx0 + 6, by0 + 126, bx0 + bw - 6, by0 + 126, color="#cbd5e1", lw=0.8)
    c.text(bx0 + 8, by0 + 137, "osiris qec: SHA-256 pre/post lock + RFC8785 WAL", size=6.1, bold=True, color="#92400e", mono=True)
    c.text(bx0 + 8, by0 + 147, "Status: HARDWARE-UNVALIDATED (fail-closed gate)", size=6.1, color="#b91c1c", mono=True)
    return c


def embed_canvas(cmds: List[str], fig: VectorCanvas, x: float, y_top: float, target_w: float, page_h: float) -> float:
    scale = target_w / fig.w
    target_h = fig.h * scale
    ty = page_h - y_top - target_h
    cmds.append(f"q {scale:.5f} 0 0 {scale:.5f} {x:.2f} {ty:.2f} cm")
    cmds.extend(fig.pdf)
    cmds.append("Q")
    return y_top + target_h


def build_preprint_pdf(
    doi_v110: str,
    repo_url: str,
    manifest_v11: Dict[str, Any],
    bench_summary: Sequence[Dict[str, Any]],
    claims_doc: Dict[str, Any],
    fig1: VectorCanvas,
    fig2: VectorCanvas,
    fig3: VectorCanvas,
) -> bytes:
    W, H = 612.0, 792.0
    pre_sha = manifest_v11["precompile_sha256"]
    h2_sha = manifest_v11["isa_sha256"]

    def wrap_paragraph(text: str, max_chars: int = 98) -> List[str]:
        words = text.split()
        lines: List[str] = []
        cur = ""
        for w in words:
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= max_chars:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_lines(
        cmds: List[str],
        x: float,
        y: float,
        lines: Sequence[str],
        font: str = "/F4",
        size: float = 9.0,
        leading: float = 11.4,
        rgb: Tuple[float, float, float] = (0.07, 0.09, 0.15),
    ) -> float:
        r, g, b = rgb
        for ln in lines:
            esc = _pdf_escape(ln)
            cmds.append(f"BT {font} {size:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {H - y:.2f} Td ({esc}) Tj ET")
            y += leading
        return y

    def draw_footer(cmds: List[str], page_no: int) -> None:
        cmds.append("0.82 0.85 0.89 RG 0.6 w 50 32 m 562 32 l S")
        footer = f"OSIRIS-QEC v1.1.0  |  DOI: {doi_v110} (v1.0.0: {V100_DOI})  |  HARDWARE-UNVALIDATED  |  Page {page_no} of 4"
        cmds.append(f"BT /F3 6.5 Tf 0.35 0.39 0.45 rg 50 21 Td ({_pdf_escape(footer)}) Tj ET")

    # ---------------- PAGE 1 ----------------
    p1: List[str] = ["1 1 1 rg 0 0 612 792 re f"]
    y = 38.0
    y = draw_lines(
        p1,
        50,
        y,
        [
            "Hardened Compiler Passes, Exact 256-Branch & 16/16 Fault-Taxonomy",
            "Verification, RFC 8785 Execution Ledger, and Hash-Locked Quantinuum H2",
            "Dispatch for 20-Qubit Toroidal Wen-Plaquette Feed-Forward Preparation",
        ],
        font="/F5",
        size=12.1,
        leading=15.0,
    )
    y += 3
    short_repo = repo_url.replace("https://", "")
    y = draw_lines(
        p1,
        50,
        y,
        [
            "Devin Phillip Davis  |  Agile Defense Systems LLC  |  November 21, 2026  |  Release v1.1.0",
            f"v1.1.0 DOI: {doi_v110}  |  v1.0.0 Baseline: {V100_DOI}  |  {short_repo}",
            f"Locked Pre-Compile SHA-256: {pre_sha[:28]}...  |  H2-1 ISA SHA-256: {h2_sha[:28]}...",
        ],
        font="/F3",
        size=6.6,
        leading=9.6,
        rgb=(0.18, 0.22, 0.30),
    )
    y += 3
    box_top = y
    box_h = 39.0
    p1.append(f"0.99 0.97 0.92 rg 0.72 0.33 0.04 RG 0.9 w 50 {H - box_top - box_h:.2f} 512 {box_h:.2f} re B")
    draw_lines(
        p1,
        57,
        box_top + 10,
        [
            "STATUS: HARDWARE-UNVALIDATED. Preregistered artifact lock enforced: pre-compile and H2-1 ISA SHA-256 hashes are verified",
            "pre-flight and post-compile (optimisation_level=0); any mismatch invalidates the run and aborts submission (EXIT 1).",
            "PROVENANCE: 4x4 Wen-plaquette 2-round LUT protocol is prior art (Iqbal et al., arXiv:2302.01917 & Quantinuum tutorial).",
        ],
        font="/F2",
        size=6.7,
        leading=9.6,
        rgb=(0.55, 0.18, 0.04),
    )
    y = box_top + box_h + 10

    y = draw_lines(p1, 50, y, ["Abstract"], font="/F5", size=10.0, leading=12.4)
    abstract_txt = (
        "We present OSIRIS-QEC v1.1.0, a provenance-locked compiler, verification, and hardware-dispatch package for "
        "preparing a fixed logical state of the [[16, 2, 4]] four-by-four periodic Wen-plaquette CSS code on 20 qubits "
        "(16 logical-lattice data qubits + 4 recycled syndrome ancillas executing 24 mid-circuit Measure and 8 Reset "
        "operations; ancillas do not contribute to code distance). Preserving the frozen v1.0.0 circuit artifacts "
        "(DOI 10.5281/zenodo.24406733) bit-for-bit, v1.1.0 introduces: (i) hardened register-collision rejection across "
        "{q, qr, quantum, c, creg, cl, classical} and metadata normalization (name, phase, metadata) guaranteeing zero "
        "hash drift; (ii) expansion of post-preparation Pauli-Y fault injection to all 16/16 data qubits alongside "
        "exhaustive 256-branch enumeration and dual-basis Qiskit Aer cross-checks; (iii) the osiris qec CLI supporting "
        "local Selene validation and fail-closed Quantinuum H2-1 dispatch via qnexus 0.51.4 (optimisation_level=0, "
        "pre-upload and post-compile SHA-256 verification, bounded exponential backoff retries); and (iv) an atomic "
        "RFC 8785 canonical JSON write-ahead execution ledger enforcing the 95% Wilson lower bound > 0.99 per basis."
    )
    y = draw_lines(p1, 50, y, wrap_paragraph(abstract_txt, 98), font="/F4", size=9.0, leading=11.3)
    y += 6

    y = draw_lines(p1, 50, y, ["1. Hardware Allocation, Hardened Pass Contract, and Metadata Determinism"], font="/F5", size=9.9, leading=12.4)
    sec1_txt = (
        "Sixteen vertex data qubits q[0..15] on a 4x4 torus encode [[16, 2, 4]] (checkerboard Z plaquettes on even r+c, "
        "X plaquettes on odd r+c; Fig. 1a), while four ancillas q[16..19] are recycled across Round 1 {4, 6, 12, 14} and "
        "Round 2 {1, 3, 9, 11} via mid-circuit Reset without increasing code distance. WenPlaquetteFeedForwardPass and "
        "build_wen_plaquette() reject non-empty circuits and colliding quantum/classical register names with ValueError "
        "before transformation, normalize circuit.name, circuit.phase, and circuit.metadata prior to SHA-256 hashing, "
        "and preserve exact bit-for-bit hash equality between v1.0.0 and v1.1.0 on empty inputs."
    )
    y = draw_lines(p1, 50, y, wrap_paragraph(sec1_txt, 98), font="/F4", size=9.0, leading=11.3)
    y += 5

    y = embed_canvas(p1, fig1, 61.0, y, 490.0, H)
    y += 8
    y = draw_lines(
        p1,
        50,
        y,
        [
            "Figure 1: (a) [[16, 2, 4]] toroidal Wen-plaquette lattice (16 data qubits + 4 recycled ancillas, 24 Measure, 8 Reset).",
            "(b) Audited 7-entry Round-2 LUT with BE->LE pytket condition encoding and zero Round-1 plaquette disturbance.",
        ],
        font="/F6",
        size=8.0,
        leading=9.8,
    )
    assert y <= 752, f"Page 1 overflow: {y}"
    draw_footer(p1, 1)

    # ---------------- PAGE 2 ----------------
    p2: List[str] = ["1 1 1 rg 0 0 612 792 re f"]
    y2 = 46.0
    y2 = draw_lines(
        p2,
        50,
        y2,
        ["2. Exact 256-Branch Statevector Verification and Dual-Basis Aer Cross-Checks"],
        font="/F5",
        size=10.0,
        leading=13.0,
    )
    sec2_txt = (
        "Independent lattice derivation (qec_math.py, qec_verify.py) confirms pairwise commutation across all 120 "
        "generator pairs, GF(2) rank 14 (k = 2), and zero nontrivial centralizer operators of weight <= 3 (exact d = 4). "
        "Negative tests verify detection of corrupted LUT entries, invalid stabilizer supports, and BE/LE endianness "
        "mismatches. Exhaustive non-sampled enumeration of all 2^8 = 256 mid-circuit outcome trajectories proves 128 "
        "reachable even-parity branches (1/128 probability each) land in the +1 codespace (worst stabilizer expectation "
        "0.9999999999999942, branch-to-branch fidelity 0.9999999999999885 to fixed |00>_L) while 128 odd-parity branches "
        "have exact zero amplitude. Dual destructive readout runs on C++ Qiskit AerBackend confirm 0/512 X-basis and "
        "0/256 Z-basis plaquette parity violations, complemented in v1.1.0 by deterministic Selene local dry-run "
        "validation (`osiris qec run --target selene`) exercising Reset semantics and all 8 even Round-2 LUT branches."
    )
    y2 = draw_lines(p2, 50, y2, wrap_paragraph(sec2_txt, 98), font="/F4", size=9.0, leading=11.4)
    y2 += 7

    y2 = draw_lines(
        p2,
        50,
        y2,
        ["3. Reproducible Monte Carlo Depolarizing Noise Benchmark"],
        font="/F5",
        size=10.0,
        leading=13.0,
    )
    sec3_txt = (
        "benchmarks/qec_noise_benchmark.py evaluates circuit-level noise injecting single-qubit depolarizing error p "
        "after every 1Q gate, two-qubit depolarizing error p after every CX, classical bit-flip p on each recorded "
        "measurement bit, and depolarizing error p after each ancilla Reset across seeds {11, 22, 33} (60 trajectories "
        "per seed = 180 trajectories per (p, mode) cell). Figure 2 and Table I contrast LUT feed-forward against the "
        "no-feed-forward baseline: at p = 1e-3, LUT feed-forward achieves mean logical fidelity 0.9056 (codespace rate "
        "0.9333) versus 0.0056 without feed-forward."
    )
    y2 = draw_lines(p2, 50, y2, wrap_paragraph(sec3_txt, 98), font="/F4", size=9.0, leading=11.4)
    y2 += 5

    y2 = embed_canvas(p2, fig2, 61.0, y2, 490.0, H)
    y2 += 8
    y2 = draw_lines(
        p2,
        50,
        y2,
        [
            "Figure 2: Monte Carlo statevector trajectory benchmark across p in {0, 1e-4, 1e-3, 5e-3, 1e-2} (seeds 11, 22, 33; 180 shots",
            "per point) comparing LUT feed-forward against no-feed-forward control for (a) logical state fidelity and (b) codespace rate.",
        ],
        font="/F6",
        size=8.0,
        leading=9.8,
    )
    y2 += 7

    table1 = [
        "Table I: Pooled Noisy State-Preparation Benchmark (Seeds 11, 22, 33; 180 Trajectories/Cell; Simulation Only)",
        "------------------------------------------------------------------------------------------------------------",
        "Noise Rate p    Shots   FF Logical Fidelity (95% CI)   FF Codespace Rate (95% CI)   No-FF Logical Fidelity",
        "------------------------------------------------------------------------------------------------------------",
    ]
    for r in bench_summary:
        table1.append(
            f"{r['p']:<13.4g}   {int(r['shots']):<5d}   "
            f"{r['ff_fid']:.4f} +/- {r['ff_fid_ci95']:.4f}              "
            f"{r['ff_corr']:.4f} +/- {r['ff_corr_ci95']:.4f}            "
            f"{r['noff_fid']:.4f}"
        )
    table1.append("------------------------------------------------------------------------------------------------------------")
    y2 = draw_lines(p2, 50, y2, table1, font="/F3", size=7.2, leading=9.6)
    assert y2 <= 752, f"Page 2 overflow: {y2}"
    draw_footer(p2, 2)

    # ---------------- PAGE 3 ----------------
    p3: List[str] = ["1 1 1 rg 0 0 612 792 re f"]
    y3 = 44.0
    y3 = draw_lines(
        p3,
        50,
        y3,
        ["4. Complete 16/16 Pre- & Post-Preparation Fault Taxonomy (Preparation != Memory)"],
        font="/F5",
        size=10.0,
        leading=13.0,
    )
    sec4_txt = (
        "OSIRIS-QEC strictly separates pre-preparation fault tolerance from post-preparation memory claims. Weight-1 Z "
        "faults injected before Round 1 on any of the 16 data qubits are corrected 16/16 times (fidelity 1.0000), whereas "
        "pre-preparation X and Y faults flip unmeasured Z stabilizers (0/32 corrected). In v1.1.0, post-preparation Y-fault "
        "validation is expanded from 3 representative qubits to a complete 16/16 sweep across q[0..15] "
        "(tests/test_y_error_sweep.py, reports/POST_PREP_Y_SWEEP_V1_1.json): every post-preparation Y fault excites "
        "exactly two X-plaquettes and two unmeasured Z-plaquettes (16/16 partially detected via X readout, 0/16 corrected, "
        "logical fidelity 0.0000), matching post-preparation Z faults (16/16 detected, 0/16 corrected; Fig. 3a, Table II)."
    )
    y3 = draw_lines(p3, 50, y3, wrap_paragraph(sec4_txt, 98), font="/F4", size=9.0, leading=11.4)
    y3 += 5

    y3 = embed_canvas(p3, fig3, 61.0, y3, 490.0, H)
    y3 += 8
    y3 = draw_lines(
        p3,
        50,
        y3,
        [
            "Figure 3: (a) Single-qubit Z/X/Y injection before vs. after preparation including the complete 16/16 post-prep Y sweep.",
            "(b) Hash-locked H2-1 ISA compilation profile (optimisation_level=0) and frozen 95% Wilson (>0.99) acceptance thresholds.",
        ],
        font="/F6",
        size=8.0,
        leading=9.8,
    )
    y3 += 7

    table2 = [
        "Table II: Pre- vs. Post-Preparation Fault Classification (POST_PREP_INJECTION.json & POST_PREP_Y_SWEEP_V1_1.json)",
        "------------------------------------------------------------------------------------------------------------",
        "Fault Class & Timing          Cases   X-Syndrome Detected   Codespace Corrected   Operational Classification",
        "------------------------------------------------------------------------------------------------------------",
        "Weight-1 Z BEFORE prep         16     16 / 16 (100%)        16 / 16 (fid = 1.0)   Corrected by 2-round LUT",
        "Weight-1 X or Y BEFORE prep    32      0 / 32 (Z unmeas.)    0 / 32 (fid = 0.0)   Undetected / uncorrected",
        "Weight-1 Z AFTER prep          16     16 / 16 (2 X-plaq)     0 / 16 (fid < 1e-3)  Detectable, NOT corrected",
        "Weight-1 X AFTER prep           3      0 / 3  (X synd = 0)   0 / 3  (2 Z-plaq)    Undetected (Z unmeasured)",
        "Weight-1 Y AFTER prep (v1.1)   16     16 / 16 (2 X-plaq)     0 / 16 (fid = 0.0)   Partially detected, 0% corr",
        "------------------------------------------------------------------------------------------------------------",
    ]
    y3 = draw_lines(p3, 50, y3, table2, font="/F3", size=7.2, leading=9.6)
    y3 += 8

    y3 = draw_lines(
        p3,
        50,
        y3,
        ["5. Fail-Closed Hash Gate, QNexus opt_level=0 Lock, and RFC 8785 Write-Ahead Ledger"],
        font="/F5",
        size=10.0,
        leading=12.8,
    )
    sec5_txt = (
        "Before any QNexus upload (`osiris qec run --target h2-1`), osiris_cli verifies both the pre-compile SHA-256 "
        f"({pre_sha[:20]}...) and offline H2-1 ISA SHA-256 ({h2_sha[:20]}..., depth 19, 32 ZZPhase), flushes an RFC 8785 "
        "canonical JSON `pre_submit` entry (with SHA-256 hash chaining and fsync) to `ledger/run-<id>.json`, compiles on "
        "Quantinuum Nexus (`qnexus 0.51.4`) under `optimisation_level=0` (`no_opt=True`), and re-verifies the returned "
        "compiled circuit SHA-256 prior to `start_execute_job`—aborting fail-closed (`EXIT 1`) on any drift."
    )
    y3 = draw_lines(p3, 50, y3, wrap_paragraph(sec5_txt, 98), font="/F4", size=9.0, leading=11.3)
    assert y3 <= 752, f"Page 3 overflow: {y3}"
    draw_footer(p3, 3)

    # ---------------- PAGE 4 ----------------
    p4: List[str] = ["1 1 1 rg 0 0 612 792 re f"]
    y4 = 46.0
    table3 = [
        "Table III: Frozen Statistical Acceptance Gate (95% Wilson Lower Bound > 0.99, z = 1.959964, Per Basis)",
        "------------------------------------------------------------------------------------------------------------",
        "Target Stage      Device   Shots / Basis (X & Z indep.)   Min Passing Shots   Max Parity Violations   Cost",
        "------------------------------------------------------------------------------------------------------------",
        "Local Dry-Run     Selene   1,000 (deterministic local)    1,000 (LB=0.9962)   0 (Reset + LUT check)   0 HQC",
        "Gate 1 (Syntax)   H2-1SC   1 (compile + ISA hash check)   ISA SHA-256 exact   0 syntax/hash errors    0 HQC",
        "Gate 2 (Emul.)    H2-1E    1,000 / 2,000 / 5,000 / 10k    997 / 1989 / 4964   3 / 11 / 36 (80 @ 10k)  HQC",
        "Gate 3 (QPU)      H2-1     512 / 1,000 / 5,000 / 10,000   512 / 997 / 4,964   0 / 3 / 36 (80 @ 10k)   HQC",
        "------------------------------------------------------------------------------------------------------------",
    ]
    y4 = draw_lines(p4, 50, y4, table3, font="/F3", size=7.1, leading=9.9)
    y4 += 9

    n_ver = sum(1 for c_item in claims_doc["claims"] if c_item["status"] == "VERIFIED")
    n_ref = sum(1 for c_item in claims_doc["claims"] if c_item["status"] == "REFUTED")
    n_blk = sum(1 for c_item in claims_doc["claims"] if c_item["status"] in ("BLOCKED", "UNVERIFIED"))

    y4 = draw_lines(
        p4,
        50,
        y4,
        [f"6. Audited Claim Matrix ({len(claims_doc['claims'])} Claims: {n_ver} VERIFIED, {n_ref} REFUTED, {n_blk} BLOCKED/UNVERIFIED)"],
        font="/F5",
        size=10.0,
        leading=13.0,
    )
    sec6_bullets = [
        "* VERIFIED: Preparation-only & register-collision pass contract; metadata normalization & v1.0.0==v1.1.0 SHA-256",
        "  parity; independent 4x4 checkerboard symplectic derivation ([[16, 2, 4]]); 7-entry LUT & BE->LE condition_bits;",
        "  exact 128/128 reachable codespace landing (worst <S> = 0.9999999999999942); dual-basis Aer C++ cross-checks;",
        "  16/16 pre-prep Z correction; 16/16 post-prep Z & 16/16 post-prep Y fault taxonomy; Selene local runner; RFC 8785",
        "  hash-chained write-ahead ledger; fail-closed QNexus opt_level=0 pre/post-compile hash gate & mock API retry suite.",
        "* EXPLICITLY REFUTED OVERCLAIMS: Novelty of the underlying 2-round LUT protocol (prior art: arXiv:2302.01917);",
        "  X/Y data error correction (0/32); post-preparation error correction (0/16 Z, 0/16 Y); fault-tolerant QEC memory;",
        "  arbitrary logical state encoding (prepares fixed |00>_L only; DD capsule fields are inert metadata).",
        "* UNVERIFIED / BLOCKED: Quantum advantage (none claimed); live Quantinuum H2-1SC/H2-1E/H2-1 QPU execution",
        "  (hash-locked CLI & manifests verified; blocked solely on out-of-band QNexus credentials & HQC allocation).",
    ]
    y4 = draw_lines(p4, 50, y4, sec6_bullets, font="/F4", size=8.9, leading=11.6)
    y4 += 9

    y4 = draw_lines(
        p4,
        50,
        y4,
        ["7. Reference CLI Verification & Reproducibility Workflow (v1.1.0)"],
        font="/F5",
        size=10.0,
        leading=13.0,
    )
    repro_lines = [
        "  osiris qec verify --manifest hardware/experiment_manifest_v1_0_0.json",
        "  osiris qec verify --manifest hardware/experiment_manifest_v1_1_0.json --strict",
        "  pytest -q                                          # full regression + 16/16 Y-sweep + hash-lock + mock QNexus",
        "  osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_0.json",
        "  osiris qec ledger verify ledger/run-*.json && sha256sum -c paper/SHA256SUMS.txt",
    ]
    y4 = draw_lines(p4, 50, y4, repro_lines, font="/F3", size=7.2, leading=10.4)
    y4 += 9

    y4 = draw_lines(p4, 50, y4, ["References"], font="/F5", size=9.9, leading=12.6)
    refs = [
        "[1] M. Iqbal et al., 'Topological Order from Measurements and Feed-Forward on a Trapped Ion Quantum Computer,'",
        "    Commun. Phys. 7, 205 (2024); arXiv:2302.01917.",
        "[2] Quantinuum, 'Topological Order from Measurements and Feed-Forward' (Official H-Series Documentation Tutorial).",
        "[3] X.-G. Wen, Phys. Rev. Lett. 90, 016803 (2003); A. Yu. Kitaev, Ann. Phys. 303, 2-30 (2003).",
        "[4] S. Sivarajah et al., 't|ket>: a retargetable compiler for NISQ devices,' Quantum Sci. Technol. 6, 014003 (2020).",
        "[5] A. Rundgren, B. Jordan, and S. Erdtman, 'JSON Canonicalization Scheme (JCS),' IETF RFC 8785 (2020).",
        "[6] E. B. Wilson, J. Am. Stat. Assoc. 22, 209 (1927).",
        f"[7] D. P. Davis, OSIRIS-QEC v1.0.0 Baseline Archive, Zenodo doi:{V100_DOI} (2026); OSIRIS-QEC-001,",
        "    Zenodo doi:10.5281/zenodo.24293756 (2026).",
    ]
    y4 = draw_lines(p4, 50, y4, refs, font="/F4", size=8.3, leading=10.7)
    assert y4 <= 752, f"Page 4 overflow: {y4}"
    draw_footer(p4, 4)

    return build_pdf_document(
        [
            (W, H, ("\n".join(p1) + "\n").encode("latin-1", errors="replace")),
            (W, H, ("\n".join(p2) + "\n").encode("latin-1", errors="replace")),
            (W, H, ("\n".join(p3) + "\n").encode("latin-1", errors="replace")),
            (W, H, ("\n".join(p4) + "\n").encode("latin-1", errors="replace")),
        ]
    )


def build_latex_source(doi_v110: str, repo_url: str, manifest_v11: Dict[str, Any], bench_summary: Sequence[Dict[str, Any]]) -> str:
    pre_sha = manifest_v11["precompile_sha256"]
    h2_sha = manifest_v11["isa_sha256"]
    rows_tex = "\n".join(
        f"{r['p']:.4g} & {int(r['shots'])} & ${r['ff_fid']:.4f} \\pm {r['ff_fid_ci95']:.4f}$ & "
        f"${r['ff_corr']:.4f} \\pm {r['ff_corr_ci95']:.4f}$ & ${r['noff_fid']:.4f}$ \\\\"
        for r in bench_summary
    )
    return f"""\\documentclass[10pt,twocolumn]{{article}}
\\usepackage[margin=0.72in]{{geometry}}
\\usepackage{{amsmath,amssymb,booktabs,graphicx,hyperref}}
\\title{{\\textbf{{Hardened Compiler Passes, Exact 256-Branch \\& 16/16 Fault-Taxonomy Verification, RFC 8785 Execution Ledger, and Hash-Locked Quantinuum H2 Dispatch for 20-Qubit Toroidal Wen-Plaquette Feed-Forward Preparation}}}}
\\author{{Devin Phillip Davis\\\\Agile Defense Systems LLC\\\\\\texttt{{v1.1.0 DOI: {doi_v110}}} \\quad \\texttt{{v1.0.0 DOI: {V100_DOI}}} \\quad \\texttt{{{repo_url}}}}}
\\date{{November 21, 2026 --- Version 1.1.0 (\\textbf{{STATUS: HARDWARE-UNVALIDATED}})}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}
\\noindent\\textbf{{Status: HARDWARE-UNVALIDATED.}} Compilation and execution use a preregistered artifact lock: the pre-compile SHA-256 (\\texttt{{{pre_sha[:20]}...}}) and Quantinuum H2-1 ISA SHA-256 (\\texttt{{{h2_sha[:20]}...}}) are verified immediately prior to execution and post-compile under \\texttt{{optimisation\\_level=0}}; any mismatch invalidates the run and aborts submission. Building upon the prior-art $4\\times 4$ toroidal Wen-plaquette two-round LUT protocol of Iqbal \\emph{{et al.}} (arXiv:2302.01917), OSIRIS-QEC v1.1.0 preserves the immutable v1.0.0 baseline (\\texttt{{{V100_DOI}}}) while adding strict register-collision protection, metadata normalization, a complete $16/16$ post-preparation Pauli-$Y$ sweep, an IETF RFC~8785 hash-chained write-ahead execution ledger, and the \\texttt{{osiris qec}} CLI for Selene validation and hash-locked Quantinuum H2-1 dispatch.
\\end{{abstract}}

\\section{{Hardware Allocation and Pass Hardening}}
Sixteen data qubits $q[0..15]$ implement the $[[16,2,4]]$ toroidal Wen-plaquette encoding, while $4$ ancilla qubits $q[16..19]$ are recycled via mid-circuit \\texttt{{Reset}} ($24$ \\texttt{{Measure}}, $8$ \\texttt{{Reset}} total; ancillas do not contribute to logical code distance; Fig.~\\ref{{fig:torus}}). \\texttt{{WenPlaquetteFeedForwardPass}} and \\texttt{{build\\_wen\\_plaquette}} reject non-empty inputs and colliding \\texttt{{q/qr/quantum/c/creg/cl/classical}} registers while normalizing mutable metadata so v1.0.0 and v1.1.0 circuit hashes match bit-for-bit.

\\begin{{figure}}[t]
\\centering
\\includegraphics[width=\\columnwidth]{{fig1_torus_checkerboard_lut.pdf}}
\\caption{{$[[16,2,4]]$ toroidal layout ($16$ data + $4$ recycled ancillas) and $7$-entry Round-2 LUT.}}
\\label{{fig:torus}}
\\end{{figure}}

\\section{{Exact Verification and Noise Benchmark}}
Exhaustive $256$-branch enumeration confirms $128/128$ reachable even-parity branches land in $+1$ codespace (worst $\\langle S\\rangle = 0.9999999999999942$), cross-checked in $X$ ($512/512$) and $Z$ ($256/256$) bases on Qiskit Aer and via \\texttt{{osiris qec run --target selene}}. Table~\\ref{{tab:bench}} and Fig.~\\ref{{fig:bench}} report noisy trajectories.

\\begin{{figure}}[t]
\\centering
\\includegraphics[width=\\columnwidth]{{fig2_noisy_fidelity_benchmark.pdf}}
\\caption{{Simulated depolarizing + readout/reset noise benchmark ($180$ shots/point).}}
\\label{{fig:bench}}
\\end{{figure}}

\\begin{{table}}[t]
\\centering
\\caption{{Pooled noisy preparation benchmark (simulation only).}}
\\label{{tab:bench}}
\\footnotesize
\\begin{{tabular}}{{ccccc}}
\\toprule
$p$ & Shots & FF Fidelity & FF Codespace & No-FF Fid. \\\\
\\midrule
{rows_tex}
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\section{{16/16 Post-Prep Fault Taxonomy \\& Hash-Locked H2 Gate}}
Expanding post-preparation $Y$-fault injection to all $16/16$ data qubits confirms $16/16$ partial $X$-syndrome detection with $0/16$ preservation ($F_L=0.0$; Fig.~\\ref{{fig:gate}}). \\texttt{{osiris qec}} enforces RFC~8785 write-ahead ledgering, \\texttt{{optimisation\\_level=0}}, post-compile ISA hash verification, and the $95\\%$ Wilson lower bound $>0.99$.

\\begin{{figure}}[t]
\\centering
\\includegraphics[width=\\columnwidth]{{fig3_error_taxonomy_and_wilson_gate.pdf}}
\\caption{{$16/16$ pre/post-prep Pauli taxonomy and hash-locked Quantinuum H2 Wilson ($>0.99$) gate.}}
\\label{{fig:gate}}
\\end{{figure}}

\\begin{{thebibliography}}{{9}}
\\bibitem{{Iqbal2024}} M. Iqbal \\emph{{et al.}}, Commun.\\ Phys.\\ \\textbf{{7}}, 205 (2024); arXiv:2302.01917.
\\bibitem{{Wen2003}} X.-G. Wen, Phys.\\ Rev.\\ Lett.\\ \\textbf{{90}}, 016803 (2003).
\\bibitem{{RFC8785}} A. Rundgren \\emph{{et al.}}, IETF RFC 8785 (2020).
\\bibitem{{Wilson1927}} E. B. Wilson, J.\\ Am.\\ Stat.\\ Assoc.\\ \\textbf{{22}}, 209--212 (1927).
\\bibitem{{DavisV100}} D. P. Davis, OSIRIS-QEC v1.0.0, Zenodo \\texttt{{{V100_DOI}}} (2026).
\\end{{thebibliography}}
\\end{{document}}
"""


def write_synchronized_docs(root: Path, doi_v110: str, repo_url: str, manifest_v11: Dict[str, Any]) -> None:
    pre_sha = manifest_v11["precompile_sha256"]
    h2_sha = manifest_v11["isa_sha256"]

    (root / ".gitignore").write_text(
        "__pycache__/\n*.py[cod]\n.pytest_cache/\n.coverage\nhtmlcov/\n*.egg-info/\nbuild/\ndist/\nledger/\n.env\n.env.*\n*.tar.gz\n",
        encoding="utf-8",
    )

    (root / "CITATION.cff").write_text(
        f"""cff-version: 1.2.0
message: "If you use OSIRIS-QEC, its verification suite, or preprint, please cite it as below."
authors:
  - family-names: "Davis"
    given-names: "Devin Phillip"
    affiliation: "Agile Defense Systems LLC"
title: "Hardened Compiler Passes, Exact 256-Branch & 16/16 Fault-Taxonomy Verification, RFC 8785 Execution Ledger, and Hash-Locked Quantinuum H2 Dispatch for 20-Qubit Toroidal Wen-Plaquette Feed-Forward Preparation"
version: 1.1.0
doi: "{doi_v110}"
date-released: 2026-11-21
url: "{repo_url}"
repository-code: "{repo_url}"
license: Apache-2.0
type: software
identifiers:
  - type: doi
    value: "{doi_v110}"
    description: "Zenodo v1.1.0 Version DOI"
  - type: doi
    value: "{V100_DOI}"
    description: "Frozen v1.0.0 Baseline Evidence DOI"
  - type: doi
    value: "{CONCEPT_DOI}"
    description: "Zenodo Concept DOI (all versions)"
keywords:
  - quantum error correction
  - Wen-plaquette code
  - topological order
  - mid-circuit measurement
  - classical feed-forward
  - pytket
  - Quantinuum H2
  - RFC 8785 canonical JSON
  - pre-registered quantum experiment
""",
        encoding="utf-8",
    )

    zenodo_meta = {
        "title": (
            "Hardened Compiler Passes, Exact 256-Branch & 16/16 Fault-Taxonomy Verification, "
            "RFC 8785 Execution Ledger, and Hash-Locked Quantinuum H2 Dispatch for 20-Qubit "
            "Toroidal Wen-Plaquette Feed-Forward Preparation (OSIRIS-QEC v1.1.0)"
        ),
        "upload_type": "publication",
        "publication_type": "preprint",
        "publication_date": "2026-11-21",
        "version": "1.1.0",
        "license": "cc-by-4.0",
        "access_right": "open",
        "creators": [{"name": "Davis, Devin Phillip", "affiliation": "Agile Defense Systems LLC"}],
        "keywords": [
            "quantum error correction",
            "Wen-plaquette code",
            "toric code",
            "mid-circuit measurement",
            "classical feed-forward",
            "pytket CustomPass",
            "Quantinuum H2",
            "RFC 8785",
            "pre-registered quantum protocol",
            "OSIRIS-QEC",
        ],
        "related_identifiers": [
            {"identifier": f"{repo_url}/tree/v1.1.0", "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": V100_DOI, "relation": "isNewVersionOf", "scheme": "doi"},
            {"identifier": "arXiv:2302.01917", "relation": "cites", "scheme": "arxiv"},
            {"identifier": "10.5281/zenodo.24293756", "relation": "references", "scheme": "doi"},
        ],
        "notes": (
            f"STATUS: HARDWARE-UNVALIDATED. Preserves frozen v1.0.0 hashes verbatim "
            f"(pre-compile SHA-256: {pre_sha}; H2-1 ISA SHA-256: {h2_sha}; v1.0.0 DOI: {V100_DOI})."
        ),
    }
    (root / ".zenodo.json").write_text(json.dumps(zenodo_meta, indent=2) + "\n", encoding="utf-8")

    readme_content = f"""# OSIRIS Quantum QEC — Wen-Plaquette Feed-Forward Preparation & Hash-Locked H2 Dispatch (`v1.1.0`)

[![DOI](https://zenodo.org/badge/DOI/{doi_v110}.svg)](https://doi.org/{doi_v110}) [![Baseline v1.0.0 DOI](https://img.shields.io/badge/v1.0.0_baseline-{V100_DOI.replace('/', '%2F')}-blue)](https://doi.org/{V100_DOI}) [![Release](https://img.shields.io/badge/release-v1.1.0-blue)]({repo_url}/releases/tag/v1.1.0) ![Status](https://img.shields.io/badge/status-HARDWARE--UNVALIDATED-amber)

Rigorously tested, provenance-locked package built around a 20-qubit toroidal Wen-plaquette syndrome-measurement + lookup-table (LUT) feed-forward state-preparation circuit, implemented as a hardened `pytket` `CustomPass` with an RFC 8785 write-ahead execution ledger and fail-closed `osiris qec` CLI for local Selene validation and Quantinuum H2-1 dispatch.

- **Zenodo `v1.1.0` Preprint & Archive:** <https://doi.org/{doi_v110}> (Concept DOI: <https://doi.org/{CONCEPT_DOI}>; immutable `v1.0.0` baseline: <https://doi.org/{V100_DOI}>)
- **Standalone `v1.1.0` Manuscript:** [`paper/wen_plaquette_feedforward_qec_v1_1.pdf`](paper/wen_plaquette_feedforward_qec_v1_1.pdf) ([LaTeX source](paper/wen_plaquette_feedforward_qec_v1_1.tex), [`SHA256SUMS.txt`](paper/SHA256SUMS.txt))
- **Provenance:** Prior-art 4x4 Wen-plaquette 2-round LUT protocol credited to Iqbal *et al.* (`arXiv:2302.01917`) and Quantinuum's feed-forward tutorial; this package provides the contract-hardened `pytket` `CustomPass`, independent GF(2) symplectic derivation, exact 256-branch verification, complete 16/16 pre/post-prep fault taxonomy, RFC 8785 write-ahead ledger, and hash-locked Quantinuum H2 / `qnexus 0.51.4` dispatch (**`HARDWARE-UNVALIDATED`** — no live provider jobs submitted).

## Hardware Allocation & Preregistered Artifact Lock

- **Logical Lattice (`16` data qubits):** `q[0..15]` implement the `[[16, 2, 4]]` periodic checkerboard Wen-plaquette encoding (`k = 2` logical qubits, exact distance `d = 4`).
- **Syndrome Resources (`4` ancilla qubits):** `q[16..19]` are reused across two X-stabilizer extraction rounds via mid-circuit recycle (observed operations across full circuit: **`24 Measure`**, **`8 Reset`**, **`20 Conditional`**). **Ancilla qubits do not contribute to logical code distance.**
- **Preregistered Artifact Lock:** Compilation and execution use a preregistered artifact lock. The pre-compile circuit SHA-256 (`{pre_sha}`) and Quantinuum H2-1 ISA SHA-256 (`{h2_sha}`, depth `19`, `32 ZZPhase`) are verified immediately prior to execution and re-verified post-compile under `optimisation_level=0`. Any mismatch invalidates the run and aborts submission (`EXIT 1`, fail closed).

## Layout

```
qec/
├── wen_plaquette_pass.py               # v1.1.0 hardened pass (register collision & metadata lock)
├── dnalang_wen_plaquette_pass.py       # vendored ORIGINAL baseline (untouched, for comparison)
├── osiris_qec/                         # canonical package namespace + 16/16 post-prep Y-sweep
├── osiris_cli/
│   ├── qec_runner.py                   # `osiris qec {{verify,run,manifest,ledger}}` CLI
│   ├── ledger.py                       # RFC 8785 canonical JSON + SHA-256 hash-chained WAL
│   └── qnexus_client.py                # hash-locked qnexus 0.51.4 transport + backoff retries
├── qec_math.py                         # independent lattice derivation: stabilizers, rank, distance
├── qec_sim.py                          # exact 20-qubit statevector simulator (mid-circuit meas., FF)
├── qec_verify.py                       # 256-branch enumeration, dual-basis Aer cross-check
├── hardware/
│   ├── experiment_manifest_v1_0_0.json # immutable v1.0.0 baseline manifest
│   ├── experiment_manifest_v1_1_0.json # v1.1.0 hash-locked & compiler-locked manifest
│   ├── ledger_schema_v1_1_0.json       # JSON Schema for RFC 8785 execution ledger entries
│   └── hashlock_policy_v1_1_0.md       # fail-closed pre/post-compile hash-lock specification
├── tests/                              # 33 baseline tests + 16/16 Y-sweep + hash-lock + mock QNexus
├── reports/                            # audit, benchmark, 16/16 fault-taxonomy & verification JSON/MD
├── paper/                              # standalone 4-page preprint PDF, LaTeX, SVG/PDF figures & sums
└── submission/                         # technical report, protocol, reproducibility & Zenodo receipts
```

## Reference CLI Usage (`osiris qec`)

```bash
# 1. Validate frozen v1.0.0 and v1.1.0 artifact hashes (fail-closed exit 1 on mismatch)
osiris qec verify --manifest hardware/experiment_manifest_v1_0_0.json
osiris qec verify --manifest hardware/experiment_manifest_v1_1_0.json --strict

# 2. Inspect manifest hashes
osiris qec manifest --file hardware/experiment_manifest_v1_1_0.json --show-hashes

# 3. Local Selene validation (verifies Reset, LUT branches, syndromes & RFC 8785 WAL; zero hardware calls)
osiris qec run --target selene --shots 1000 --manifest hardware/experiment_manifest_v1_1_0.json

# 4. Verify & summarize RFC 8785 hash-chained execution ledger
osiris qec ledger verify ledger/run-*.json
osiris qec ledger show ledger/run-*.json --summary

# 5. Authorized Quantinuum H2-1 submission (requires out-of-band QNEXUS_TOKEN / `qnx login`)
osiris qec run --target h2-1 --shots 5000 --manifest hardware/experiment_manifest_v1_1_0.json

# 6. Full automated regression & verification suite
pytest -q
```

No credentials are stored or committed anywhere in this repository; see [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) and [`CHANGELOG.md`](CHANGELOG.md).
"""
    (root / "README.md").write_text(readme_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/home/osiris/qec"))
    parser.add_argument("--doi", required=True, help="v1.1.0 Zenodo DOI")
    parser.add_argument("--repo-url", default="https://github.com/quantum-osiris/osiris-qec")
    args = parser.parse_args()

    root = args.root.resolve()
    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)

    bench = json.loads((root / "reports" / "QEC_BENCHMARK_RESULTS.json").read_text(encoding="utf-8"))
    err_matrix = json.loads((root / "reports" / "ERROR_CORRECTION_MATRIX.json").read_text(encoding="utf-8"))
    post_prep = json.loads((root / "reports" / "POST_PREP_INJECTION.json").read_text(encoding="utf-8"))
    y_sweep_v11 = json.loads((root / "reports" / "POST_PREP_Y_SWEEP_V1_1.json").read_text(encoding="utf-8"))
    manifest_v10 = json.loads((root / "hardware" / "experiment_manifest_v1_0_0.json").read_text(encoding="utf-8"))
    manifest_v11 = json.loads((root / "hardware" / "experiment_manifest_v1_1_0.json").read_text(encoding="utf-8"))
    claims_doc = json.loads((root / "submission" / "CLAIMS_AND_EVIDENCE.json").read_text(encoding="utf-8"))

    bench_summary = summarize_benchmark(bench)
    fig1 = make_fig1_torus_and_lut()
    fig2 = make_fig2_benchmark(bench_summary)
    fig3 = make_fig3_taxonomy_and_gate(err_matrix, post_prep, y_sweep_v11, manifest_v10)

    fig1.save(paper_dir / "fig1_torus_checkerboard_lut")
    fig2.save(paper_dir / "fig2_noisy_fidelity_benchmark")
    fig3.save(paper_dir / "fig3_error_taxonomy_and_wilson_gate")

    pdf_bytes = build_preprint_pdf(
        doi_v110=args.doi,
        repo_url=args.repo_url,
        manifest_v11=manifest_v11,
        bench_summary=bench_summary,
        claims_doc=claims_doc,
        fig1=fig1,
        fig2=fig2,
        fig3=fig3,
    )
    pdf_v11_path = paper_dir / "wen_plaquette_feedforward_qec_v1_1.pdf"
    pdf_v11_path.write_bytes(pdf_bytes)

    tex_v11_path = paper_dir / "wen_plaquette_feedforward_qec_v1_1.tex"
    tex_v11_path.write_text(build_latex_source(args.doi, args.repo_url, manifest_v11, bench_summary), encoding="utf-8")

    write_synchronized_docs(root, args.doi, args.repo_url, manifest_v11)

    tracked_for_sums = [
        pdf_v11_path,
        tex_v11_path,
        paper_dir / "fig1_torus_checkerboard_lut.pdf",
        paper_dir / "fig2_noisy_fidelity_benchmark.pdf",
        paper_dir / "fig3_error_taxonomy_and_wilson_gate.pdf",
        root / "wen_plaquette_pass.py",
        root / "dnalang_wen_plaquette_pass.py",
        root / "osiris_qec" / "wen_plaquette_pass.py",
        root / "osiris_cli" / "qec_runner.py",
        root / "osiris_cli" / "ledger.py",
        root / "osiris_cli" / "qnexus_client.py",
        root / "qec_math.py",
        root / "qec_sim.py",
        root / "qec_verify.py",
        root / "hardware" / "experiment_manifest_v1_0_0.json",
        root / "hardware" / "experiment_manifest_v1_1_0.json",
        root / "hardware" / "ledger_schema_v1_1_0.json",
        root / "hardware" / "hashlock_policy_v1_1_0.md",
        root / "reports" / "QEC_BENCHMARK_RESULTS.json",
        root / "reports" / "ERROR_CORRECTION_MATRIX.json",
        root / "reports" / "POST_PREP_INJECTION.json",
        root / "reports" / "POST_PREP_Y_SWEEP_V1_1.json",
        root / "submission" / "CLAIMS_AND_EVIDENCE.json",
        root / "submission" / "EXPERIMENT_PROTOCOL.md",
        root / "CHANGELOG.md",
        root / "SECURITY_REVIEW.md",
    ]
    sums_lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}"
        for p in tracked_for_sums
    ]
    (paper_dir / "SHA256SUMS.txt").write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    print(
        f"Built v1.1.0 4-page PDF ({len(pdf_bytes):,} bytes), LaTeX, 3 SVG+PDF figures, "
        f"synchronized docs, and SHA256SUMS.txt ({len(tracked_for_sums)} entries)."
    )


if __name__ == "__main__":
    main()
