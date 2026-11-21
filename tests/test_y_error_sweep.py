"""
Phase 3B (v1.1.0): Full 16/16 post-preparation Pauli-Y fault-taxonomy sweep.

Upgrades post-preparation Y-error validation from 3 representative qubits
`(0, 5, 15)` to all 16 data qubits `0..15`, recording deterministic X/Z
syndrome strings, partial X-syndrome detection, unmeasured Z-syndrome defects,
and non-preservation of the prepared logical state (`logical_fidelity == 0.0`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from osiris_qec.wen_plaquette_pass import (
    N_DATA,
    inject_y_error_after_prep,
    run_postprep_y_error_sweep,
)

REPORT_V1_1 = Path(__file__).resolve().parent.parent / "reports" / "POST_PREP_Y_SWEEP_V1_1.json"


@pytest.mark.parametrize("qubit", range(N_DATA))
def test_postprep_y_error_sweep(qubit: int) -> None:
    result = inject_y_error_after_prep(qubit=qubit)

    assert result.qubit == qubit
    assert result.syndrome_recorded is True
    assert result.syndrome_detected is True
    assert result.logical_state_preserved is False
    # Every vertex on the 4x4 checkerboard torus touches exactly 2 X-plaquettes and 2 Z-plaquettes
    assert len(result.x_syndrome) == 8 and result.x_syndrome.count("1") == 2
    assert len(result.z_syndrome) == 8 and result.z_syndrome.count("1") == 2
    assert len(result.x_syndrome_plaquettes) == 2
    assert len(result.z_syndrome_plaquettes) == 2
    assert result.logical_fidelity < 1e-12


def test_postprep_y_error_sweep_aggregate_and_determinism() -> None:
    sweep_a = run_postprep_y_error_sweep()
    sweep_b = run_postprep_y_error_sweep()

    assert sweep_a == sweep_b
    assert sweep_a["total_qubits"] == 16
    assert sweep_a["detected_count"] == 16
    assert sweep_a["undetected_count"] == 0
    assert sweep_a["all_preserved"] is False
    assert sweep_a["logical_fidelity"] == 0.0
    assert len(sweep_a["records"]) == 16

    REPORT_V1_1.parent.mkdir(parents=True, exist_ok=True)
    REPORT_V1_1.write_text(json.dumps(sweep_a, indent=2) + "\n", encoding="utf-8")
