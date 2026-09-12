# FC Phase 3 — Deterministic four-market mathematics

## Status

Phase 3A–3C selesai secara lokal sebagai pure Python library dan projection-only CLI. Tidak ada fitter Dixon–Coles, kalibrasi, uncertainty estimate, selection policy, pick publisher, staking, atau UI integration. Lambda dan rho pada CLI adalah input; memasukkannya secara manual tidak menjadikan output official.

Implementasi:

- [Ratio benchmark](E:/MLB-Project/betting-machine-fc/football_formula_engine/baseline.py): baseline preparation yang wajib menerima UTC cutoff dan hanya memakai result yang telah available. Bukan model utama/approved.
- [Score distribution](E:/MLB-Project/betting-machine-fc/football_formula_engine/score_matrix.py): independent Poisson + supplied Dixon–Coles rho, adaptive grid, tail tolerance, tau/rho validity, truncation diagnostics.
- [Four market and settlement](E:/MLB-Project/betting-machine-fc/football_formula_engine/markets.py): 1X2, BTTS, O/U dan AH dengan satu distribusi serta payout FW/HW/P/HL/FL.
- [Fair odds/value](E:/MLB-Project/betting-machine-fc/football_formula_engine/value.py): payout-aware fair odds dan EV, optional win commission, proportional no-vig baseline.
- [Projection CLI](E:/MLB-Project/betting-machine-fc/football_formula_engine/math_cli.py): read-only JSON, selalu `projection_only` dan `official_enabled=false`.

## Frozen mathematical behavior

- Matrix grid membesar sampai upper bound gabungan tail mass ≤1e-8, dengan hard limit fail-closed. Normalisasi hanya terhadap truncation residual setelah semua tau valid; rho yang membuat sel negatif ditolak.
- Semua market dihitung dari matriks yang sama. BTTS tidak memakai perkalian marginal setelah DC. O/U half-line menggunakan complement yang tepat; Under 2.5 memasukkan total tepat dua gol.
- Signed AH menggunakan perspektif selection: home -0.75 adalah -3 quarter-units; lawannya away +0.75 adalah +3. Total 2.25 adalah 9 quarter-units.
- Quarter lines dipecah 50/50 ke dua component lines dan menghasilkan full/half/push/loss categories. Fungsi settlement memakai fungsi market yang sama dengan projection.
- `W=FW+0.5×HW`, `L=FL+0.5×HL`, `EV=(odds−1)(1−commission)W−L`, dan fair odds `1+L/((1−commission)W)`. W=0 menghasilkan fair odds null; all-push EV nol.
- Proportional no-vig menerima complete price vector yang diberikan, tetapi tidak mengubah Asian effective shares menjadi full-win probabilities. Quote grouping/completeness enforcement ada di data/policy phase berikutnya.

## Golden evidence

- Home -0.75, score 1–0 → half win.
- Home -1.5, score 3–1 → full win.
- Over 2.25 dengan total dua → half loss; Under 2.25 → half win.
- Under 2.5 dengan total dua → full win.
- AH home line q dan away line -q mempunyai payout complement untuk seluruh q dari -3.0 sampai +3.0 pada property tests.
- O/U sides mempunyai payout complement untuk line 0 sampai 4.0 per quarter.
- Pada lambda 1.5/1.2, perubahan rho tidak mengubah O/U 2.5 pada lambda tetap, tetapi mengubah BTTS.
- Synthetic payout FW=.55/HW=.10/P=.05/HL=.05/FL=.25 memberi fair odds 1.458333 dan EV +0.295 pada odds 1.95.

Run projection dari `betting-machine-fc`:

```powershell
python -m football_formula_engine.math_cli --lambda-home 1.5 --lambda-away 1.2 --rho -0.1 --ou-line 2.25 --ah-line -0.75
```

Optional `--odds-json` hanya menghitung EV pada quote input; hasil tetap projection-only. Contoh ini sintetis dan tidak boleh masuk tracker.

## Gate dan batas

Probability mass, complements, adaptive tail, rho boundaries, all Asian outcomes, fair-price zero EV, nonfinite input, CLI status dan baseline cutoff telah diuji. Performa prediksi belum diuji. Phase 4 harus mengestimasi strengths/rho secara terregularisasi dan menghasilkan versioned artifacts; Phase 5 baru menilai OOS calibration/ROI. Tidak ada alasan untuk mengaktifkan Today's Pick dari hasil Phase 3 saja.

Rollback runtime tidak diperlukan: library dan CLI belum dipakai reader/scheduler/UI. Existing Formula Final config tetap default-off.
