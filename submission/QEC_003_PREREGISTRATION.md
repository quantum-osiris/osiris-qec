# Preregistration Protocol — `OSIRIS-QEC-003`: Full $X+Z$ Toroidal Memory Cycles & Checkerboard Twist-Defect Anyon Braiding on Quantinuum H2

- **Protocol Identifier:** `OSIRIS-QEC-003` (`osiris_qec.qec003_memory_twists`, `v1.2.0`)
- **Predecessor Baseline:** `OSIRIS-QEC-002` (`osiris-qec v1.1.1`, Zenodo DOI `10.5281/zenodo.24424726`)
- **Evidence Status:** `SIMULATED` (20-qubit exact statevector & seeded Monte Carlo) + `OFFLINE_COMPILED` (`pytket-quantinuum` `QuantinuumAPIOffline` targeting `H2-1` / `H2-1E`); **`provider_job_id: null`** (`hardware_attested: false`; zero live provider jobs submitted).
- **Normative Verification Artifact:** `reports/qec003_verification_report.json` (IETF RFC 8785 JCS canonical JSON via `rfc8785==0.1.4`).

---

## 1. Scientific Motivation & Scope Upgrade Beyond `OSIRIS-QEC-002`

`OSIRIS-QEC-002` rigorously established a critical operational boundary: **fault-tolerant state preparation $\neq$ quantum error-correcting memory**. Because the 2-round Wen-plaquette preparation circuit measures only the eight $X$-type plaquettes (electric $e$-anyons) during state preparation and performs zero post-preparation syndrome rounds:
1. Magnetic $m$-anyons (created by Pauli-$X$ faults) flip only $Z$-plaquettes and remain **100% invisible (`0/16` detected)**.
2. Post-preparation $Y$ and $Z$ faults flip $X$-plaquettes (`32/32` detected), yet **`0/48` (`0.0%`) post-preparation weight-1 Pauli faults preserve the encoded logical state**.
3. On a closed CSS torus without lattice dislocations, electric ($e$) and magnetic ($m$) excitations remain strictly decoupled Abelian sectors ($\prod X_p = +I$, $\prod Z_p = +I$).

`OSIRIS-QEC-003` resolves both boundaries within the exact same **20-ion budget (`16` data + `4` recycled ancillas $\le 56$ ions on Quantinuum System Model H2)** with **zero routing `SWAP` overhead**:
- **Experiment Track 3A (Full $X+Z$ Toroidal Memory Cycles):** Multi-round non-destructive extraction of **all 8 $X$-plaquettes AND all 8 $Z$-plaquettes** across $R \in \{1, 2, 3\}$ memory cycles using 4 vertex-disjoint parallel sub-batches per round on recycled ancillas `q[16..19]`, decoded via CSS log-LLR Belief Propagation + Ordered Statistics Decoding (`BP+OSD-CS`, order 2) over $(H_X, H_Z)$ ($\operatorname{rank}_{\mathbb{F}_2}(H_X) = \operatorname{rank}_{\mathbb{F}_2}(H_Z) = 7$).
- **Experiment Track 3B (Checkerboard Twist Defects & $e \leftrightarrow m$ Anyon Braiding):** Explicit Bombin lattice dislocation on the 16-qubit periodic checkerboard lattice introducing two non-local **weight-5 mixed-parity Ising twist stabilizers** (`T1 = +X4.Y5.Z6.X8.X9`, `T2 = -Z4.Z7.Z8.X10.Y11`) and a mixed `XXZZ` branch-cut plaquette (`B1 = +X6.X7.Z9.Z10`), demonstrating deterministic twist-vacuum feed-forward preparation, electric-to-magnetic anyon transmutation ($e \mapsto m$), and twist-defect condensation with **0 routing SWAPs** on `H2-1`.

---

## 2. Preregistered Artifact Hashes, `H2-1` ISA Gate Counts & HQC Budgets

All circuits are compiled offline via `QuantinuumBackend("H2-1", api_handler=QuantinuumAPIOffline())` and verified as **exact zero-drift fixed points** under Nexus `optimisation_level=0` (`QuantinuumConfig(device_name=..., no_opt=True)`).

HQC budgets are computed deterministically from Quantinuum's System Model H2 cost formula:
$$\mathrm{HQC}(C) = 5 + \frac{C \cdot (N_{1q} + 10 N_{2q} + 5 N_m)}{5000}$$
where $N_{1q} = N_{\mathrm{PhasedX}}$ (virtual `Rz` and `Conditional(Rz)` incur $0$ HQC), $N_{2q} = N_{\mathrm{ZZPhase}}$, and $N_m = N_{\mathrm{Measure}} + N_{\mathrm{Reset}}$.

| Circuit Variant | Qubits / Clbits | Pre-Compile SHA-256 | `H2-1` ISA SHA-256 (`opt0` Fixed-Point) | Depth | `ZZPhase` | `PhasedX` | `Measure` + `Reset` | `SWAP` | HQC @ `512` | HQC @ `1,000` | HQC @ `2,000` |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`QEC-002` Prep (`X` basis)** | `20 / 28` | `b86aeabd70eecb7f...` | `02d5cb72849f9b47...` | `19` | `32` | `72` | `24 + 8 = 32` | `0` | `61.5248` | `115.40` | `225.80` |
| **`QEC-002` Prep (`Z` basis)** | `20 / 28` | `d994f2db4bc877e2...` | `b0b7a9778ad7660d...` | `18` | `32` | `56` | `24 + 8 = 32` | `0` | `59.8864` | `112.20` | `219.40` |
| **`QEC-003` Memory `R = 1`** | `20 / 40` | `663e7e5020ab287c...` | `200180d6bd490098...` | `50` | `96` | `120` | `40 + 24 = 64` | `0` | `148.3600` | `285.00` | `565.00` |
| **`QEC-003` Memory `R = 2`** | `20 / 56` | `7f1d743995426055...` | `1d8094230ebee8cb...` | `82` | `160` | `184` | `56 + 40 = 96` | `0` | `236.8336` | `457.80` | `910.60` |
| **`QEC-003` Memory `R = 3`** | `20 / 72` | `d4f2a9aefa0001b3...` | `0d037e0dddd4a51f...` | `114` | `224` | `248` | `72 + 56 = 128` | `0` | `325.3072` | `630.60` | `1256.20` |
| **`QEC-003` Twist `e -> m` (`Step 3`)** | `20 / 42` | `ded8e23650863ea2...` | `e3586fbd73e18db8...` | `74` | `108` | `183`* | `42 + 26 = 68` | `0` | `169.1472` | `325.60` | `646.20` |

*\*Includes `179` outer `PhasedX` + `4` conditional `PhasedX` operations from weight-2 `X` twist-vacuum feed-forward destabilizers.*

### Full 64-Hex Preregistered Digests (`OSIRIS-QEC-003`)
- **`Memory R=1`:**
  - Pre-compile: `663e7e5020ab287cb222e54abb00528627442b38241c1554c167d70d93a3b49c`
  - `H2-1` ISA: `200180d6bd4900985bc5ac665e786c468a9c02405ce8c8957d8b14eec3b7e8ea`
- **`Memory R=2`:**
  - Pre-compile: `7f1d74399542605501523f9603e56a2cabdaa5eb16d7e6d82001fe62f1f6f6de`
  - `H2-1` ISA: `1d8094230ebee8cb1b0513500ef1a4ec8d61278cebca0d81c759ed2efd997009`
- **`Memory R=3`:**
  - Pre-compile: `d4f2a9aefa0001b34354965399885d939b8a5156979af25915864b7116104fad`
  - `H2-1` ISA: `0d037e0dddd4a51fc20b95876855f477d224cc52d73048dd5f101d7b3eccc369`
- **`Twist Braiding (Step 3: e -> m Transmutation)`:**
  - Pre-compile: `ded8e23650863ea24e6db10e33af8bb971500b8eb215fe242c6da556bc18ae40`
  - `H2-1` ISA: `e3586fbd73e18db8f46cb3801db16431a51febddaaa8ab86406d5143d9fb987e`

---

## 3. Preregistered Theoretical Baselines (`SIMULATED`)

### 3.1 Post-Preparation Fault Taxonomy (`OSIRIS-QEC-002` vs `OSIRIS-QEC-003`)

| Fault Ensemble (`[[16,2,4]]` Data Qubits `q[0..15]`) | Total Faults | `QEC-002` Detected | `QEC-002` Logically Preserved | `QEC-003` Detected | `QEC-003` Logically Preserved (`BP+OSD`) | `QEC-003` Residual Logical Error |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Weight-1 `X` (post-prep)** | `16` | `0 / 16` (`0.0%`) | `0 / 16` (`0.0%`) | `16 / 16` (`100%`) | **`16 / 16` (`100.0%`)** | **`0.0%`** |
| **Weight-1 `Y` (post-prep)** | `16` | `16 / 16` (partial $X$) | `0 / 16` (`0.0%`) | `16 / 16` (`100%`) | **`16 / 16` (`100.0%`)** | **`0.0%`** |
| **Weight-1 `Z` (post-prep)** | `16` | `16 / 16` (`100%`) | `0 / 16` (`0.0%`) | `16 / 16` (`100%`) | **`16 / 16` (`100.0%`)** | **`0.0%`** |
| **All Weight-1 Post-Prep (`X,Y,Z`)** | **`48`** | `32 / 48` (`66.7%`) | **`0 / 48` (`0.0%`)** | **`48 / 48` (`100%`)** | **`48 / 48` (`100.0%`)** | **`0.0%`** |
| **All Weight-2 Post-Prep (`{X,Y,Z}^2`)** | **`1,080`** | — | `0 / 1,080` (`0.0%`) | **`1,080 / 1,080` (`100%`)** | `672 / 1,080` (`62.22%`: `560` exact + `112` stab-deg) | `408 / 1,080` (`37.78%` $d=4$ torus coset ties) |

### 3.2 Checkerboard Twist-Defect Group & $e \leftrightarrow m$ Transmutation Signatures

- **15 Stabilizer Generators:** 12 outer checkerboard weight-4 $X/Z$ plaquettes (`P_0_Z..P_3_X`, `P_8_Z..P_15_Z`), left weight-5 pentagon twist `T1 = +X4.Y5.Z6.X8.X9`, mixed branch-cut plaquette `B1 = +X6.X7.Z9.Z10`, and right weight-5 pentagon twist `T2 = -Z4.Z7.Z8.X10.Y11`.
- **Algebraic Invariants:** `105/105` commuting pairs; exact signed product $\prod_{j=1}^{15} G_j = +I_{2^{16}}$ (unified $\mathbb{Z}_2$ fermion parity conservation); $\operatorname{rank}_{\mathbb{F}_2} = 14 \implies k = 2$; exhaustive Pauli enumeration finds `0` logicals of weight $\le 3$ and `44` logicals of weight `4` $\implies$ exact **$[[16, 2, 4]]$** code.
- **Preregistered 5-Step Syndrome Signature (`c_tw_syn[0..14]`):**
  - `Step 0` (`I`, twist vacuum): `000000000000000` (`0` $e$, `0` $m$, `0` twist/cut)
  - `Step 1` (`Z2`, create $e$-pair): `010000000010000` (`P_1_X`, `P_14_X` $\implies$ `2` $e$-anyons, `0` $m$-anyons)
  - `Step 2` (`Z2.Z6`, enter branch cut): `000000000010010` (`P_14_X`, `B1_branch_cut`)
  - `Step 3` (`Z2.Z6.X10`, cross branch cut): `000000100010000` (`P_14_X` electric $e$-anyon + `P_10_Z` magnetic $m$-anyon — **direct experimental signature of $e \leftrightarrow m$ transmutation: odd $e$-count $= 1$ and odd $m$-count $= 1$ simultaneously!**)
  - `Step 4` (`Z2.Z6.X10.X11`, twist fusion): `000000000010001` (`P_14_X` + `T2_twist_right` — transmuted $m$-anyon absorbed into weight-5 Ising twist defect)

---

## 4. Hardware / Emulator Execution Gates & Stopping Conditions

1. **Gate 1 (`H2-1SC` Syntax Check, `0` HQC):** Compile all locked `OSIRIS-QEC-003` circuits under `optimisation_level=0` (`no_opt=True`) and verify zero SHA-256 drift against Section 2 before any `H2-1E` or `H2-1` execution.
2. **Gate 2 (`H2-1E` Emulator, `1,000` shots per circuit):**
   - Track 3A (`R=1, 2, 3`): `BP+OSD-CS` decoded logical survival rate exceeds bare 2-qubit physical baseline with 95% Wilson lower confidence bound above unencoded break-even; syndrome parity rejection confirms global torus parity detection of measurement faults.
   - Track 3B (`Step 0..4`): Target 15-bit anyon-transmutation syndrome (`000000100010000` at `Step 3`) is the unique modal outcome with statistically significant odd-$e$/odd-$m$ correlation ($> 5\sigma$ over independent readout flip noise).
3. **Fail-Closed Stopping Conditions:**
   - Abort immediately (`EXIT 1`, zero jobs executed) on any pre-compile or post-compile `H2-1` ISA SHA-256 mismatch.
   - Never promote `evidence_class` to `HARDWARE_ATTESTED` without physical `H2-1` QPU Nexus `COMPLETED` status confirmation and write-ahead RFC 8785 JCS ledger verification (`H2-1E` runs remain `EMULATOR_ATTESTED`).
