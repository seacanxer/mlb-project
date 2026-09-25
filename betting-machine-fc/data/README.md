# FC Historical Data — Status & Provenance

## Tujuan

Melengkapi data historis untuk membuka gate Phase 5
(`docs/fc-phase5-evaluation.md`): target 3 season per liga top-5 Eropa agar
evaluation spec baru bisa punya **multiple outer test periods**.

## Sumber data (tiga jalur, tanpa fabrikasi)

| Jalur | Sumber | Kolom | Status |
|---|---|---|---|
| Primer | football-data.co.uk (`scraper_historical.download`) | Skor + odds B365/AH lengkap | **GAGAL dari mesin ini** — TLS handshake ditolak (sama seperti catatan Phase 5; bukan fabrikasi, dicatat jujur). Odds 2526 yang sudah ada tetap dari sumber ini. |
| Mirror | `datasets/football-datasets` (GitHub raw, PDDL) | **Skor + statistik saja — TANPA kolom odds** | Berhasil. File dinamai `<LEAGUE>_<SEASON>_mirror.csv`. |
| Score feed | FotMob day feed (`apigw.fotmob.com/matches?date=`) dan ESPN scoreboard (opt-in `--espn`) | **Skor + waktu mulai saja — TANPA kolom odds** | Dijalankan lewat `scripts/fc-fetch-dayfeed.py`. File memakai suffix jujur `<CODE>_<SEASON>_dayfeed.csv` / `<CODE>_<SEASON>_espn.csv` + sidecar `.source.json`. |

Aturan kejujuran data: mirror tidak menggantikan file football-data.co.uk
secara diam-diam. Suffix `_mirror` + tabel ini menjaga provenance tetap
teraudit. Jangan pernah rename `_mirror.csv` jadi file polos.

Untuk jalur score feed berlaku aturan yang sama, ditambah:

- Suffix `_dayfeed` / `_espn` menyatakan file ini **tidak pernah berisi odds**;
  loader engine (`load_football_data_csv(..., source=...)`) karena itu tidak
  mengeluarkan quote apa pun dari file ini (provider quote tetap
  `football-data.co.uk`).
- Season football-data yang sudah ada file-nya **tidak pernah ditimpa** oleh
  score feed (`REGISTERED_FOOTBALL_DATA_FILE_EXISTS`).
- Prioritas lane per season di `training_files()`: `_live_scores` >
  `<CODE>_<SEASON>.csv` > `_dayfeed` > `_espn`.
- Hanya kode dengan `LEAGUES[code].source == 'football-data'` yang boleh
  dipanggil `refresh_scores()`; kode score-feed di-refresh lewat
  `fc-fetch-dayfeed.py`.
- Kalender season per liga diatur `season_start_month` (default Juli);
  liga kalender (Brasil, Argentina, Jepang, dll) memakai bulan sendiri supaya
  label season cocok dengan data.
- Cache raw response ada di `data/.feed_cache/` dan di-**gitignore**
  (regenerable); CSV + sidecar tetap di-track.
- **Nama tim di-canonicalize per team-id** (`hId`/`aId` FotMob): semua
  varian ejaan satu klub (`Ceara`/`Ceará`, `America MG`/`América-MG`,
  `Arsenal Academy`/`Arsenal U21`) ditulis memakai ejaan paling sering
  muncul per id (tie-break alfabet, deterministik). Laporan jumlah id
  unik + kolisi ada di field `canonical_teams` / `canonical_collisions`
  JSON hasil `fc-fetch-dayfeed.py`. Kolisi yang diketahui & diterima:
  `I2` → `Reggiana` (id `6500` dan `959006`).
- Liga yang **tidak di-mapping** ke kode model (dokumentasi di
  `football_formula_engine/leagues.py`): Ghana Division 1 dan Croatia
  2. NL dihapus karena FotMob hanya punya divisi utama mereka — klub
  yang dicari (`Dinamo Zagreb II`, `Accra Lions`, dll) tidak ada di
  cache manapun, jadi lane-nya akan selalu kosong/salah. Liga bawah
  Meksiko/Jepang/Swedia/Ceko/Romania/Mesir/Austria/Wales, U2/PRI, dan
  laga klub persahabatan sengaja tidak di-map.
- Gap yang diketahui & diterima: `EPL2` (FotMob `Premier League 2`
  memakai klub akademi Premier League; klub PDL Football-data seperti
  `Barnsley U21`/`Sheffield Wednesday U21` tidak ada → fixture itu
  gagal team-match dan di-gate, bukan diprediksi salah) dan `DEN2`
  (`Hellerup IK` tidak ada di cache FotMob).

Jalankan:

```bash
python scripts/fc-fetch-dayfeed.py                # ambil + tulis semua liga
python scripts/fc-fetch-dayfeed.py --no-fetch     # tulis ulang dari cache
python scripts/fc-fetch-dayfeed.py --codes J2,SC1 # subset liga
python scripts/fc-fetch-dayfeed.py --espn         # tambah lane ESPN (opt-in)
```

## Isi direktori `betting-machine-fc/data/`

**Football-data.co.uk asli (ada odds, baris 2526/2425):**
`E0_2425, E0_2526` + liga lain 2526 (E1–EC, SP1/SP2, D1/D2, I1/I2, F1/F2,
N1, P1, B1, T1, G1, SC1–SC3).

**Mirror GitHub (skor saja, 3 season top-5):**
`{E0,SP1,D1,I1,F1}_{2223,2324,2425}_mirror.csv` — 15 file, skor lengkat
(FTHG/FTAG tervalidasi lengkap semua baris).

## Integritas

### Tim nasional senior putra

`international_results.csv` berasal dari
`martj42/international_results` (CC0; hash dan tanggal ada di
`international_results.source.json`). Dataset mencakup hasil tim nasional
senior putra, termasuk pertandingan netral. Jalankan
`python scripts/fc-refresh-national.py` untuk memperbarui snapshot; updater
memvalidasi format, skor, tanggal, dan tidak menerima sumber yang mundur.

Scanner memakai hasil sejak 2023 dan model ratio baseline terpisah (`INT_MEN`).
Pertandingan historis netral dikeluarkan dari fitting karena baseline ini
memerlukan observasi home/away yang jelas.
Hasil pertandingan baru masuk ke model paling cepat hari UTC berikutnya.
Kompetisi yang didukung secara eksplisit: UEFA Nations League, Africa Cup of
Nations senior, CONCACAF Nations League, persahabatan tim nasional senior, dan
Arabian Gulf Cup. Nama liga seperti `UEFA Nations League. Team vs Player`,
turnamen junior, tim cadangan, klub, dan wanita tidak digabung ke model ini.

Hasil `INT_MEN` adalah proyeksi riset: venue netral pada fixture live belum
terverifikasi dan model belum lulus evaluasi prospektif. Selisih probabilitas
1X2 di atas 20 poin persentase dari pasar menahan seluruh proyeksi fixture.
Jalur ini tidak menerbitkan value atau Official pick. Audit cakupan sebelum
scan dengan `python scripts/fc-preflight-24h.py`.

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
