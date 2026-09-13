# FC Historical Data — Status & Provenance

## Tujuan

Melengkapi data historis untuk membuka gate Phase 5
(`docs/fc-phase5-evaluation.md`): target 3 season per liga top-5 Eropa agar
evaluation spec baru bisa punya **multiple outer test periods**.

## Sumber data (dua jalur, tanpa fabrikasi)

| Jalur | Sumber | Kolom | Status |
|---|---|---|---|
| Primer | football-data.co.uk (`scraper_historical.download`) | Skor + odds B365/AH lengkap | **GAGAL dari mesin ini** — TLS handshake ditolak (sama seperti catatan Phase 5; bukan fabrikasi, dicatat jujur). Odds 2526 yang sudah ada tetap dari sumber ini. |
| Mirror | `datasets/football-datasets` (GitHub raw, PDDL) | **Skor + statistik saja — TANPA kolom odds** | Berhasil. File dinamai `<LEAGUE>_<SEASON>_mirror.csv`. |

Aturan kejujuran data: mirror tidak menggantikan file football-data.co.uk
secara diam-diam. Suffix `_mirror` + tabel ini menjaga provenance tetap
teraudit. Jangan pernah rename `_mirror.csv` jadi file polos.

## Isi direktori `betting-machine-fc/data/`

**Football-data.co.uk asli (ada odds, baris 2526/2425):**
`E0_2425, E0_2526` + liga lain 2526 (E1–EC, SP1/SP2, D1/D2, I1/I2, F1/F2,
N1, P1, B1, T1, G1, SC1–SC3).

**Mirror GitHub (skor saja, 3 season top-5):**
`{E0,SP1,D1,I1,F1}_{2223,2324,2425}_mirror.csv` — 15 file, skor lengkat
(FTHG/FTAG tervalidasi lengkap semua baris).

## Integritas

- `python3 scripts/fc-fetch-historical.py --verify` — laporan integritas file lokal.
- `F2_2526.csv` ada 1 baris tanpa skor final (Bastia vs Red Star 05/12/2025,
  di-upstream-kosong) — engine harus skip baris skor-null (sudah ditangani
  loader engine: baris tanpa FTHG/FTAG di-skip).

## Pemakaian untuk Phase 5 baru

- Spec baru boleh memakai mirror 2223/2324/2425 untuk **fit + evaluasi
  probabilitas** (skor/log-loss/Brier — tidak butuh odds).
- ROI/CLV historis **tetap tidak bisa** dari mirror (tanpa odds) — gate
  `timed_executable_quotes_for_roi` hanya terbuka lewat logging quote live
  (roadmap #5) atau football-data.co.uk asli berhasil di-fetch dari VPS.
- Boundary train/test harus tetap mengikuti protokol freeze Phase 5:
  periode test bekas tidak boleh dipakai retune.
