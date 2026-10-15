# FC terminal overhaul — Fase 1: audit diagnostik

Tanggal: 15 Oktober 2026 (WIB). Baseline: `main`, commit `5ae7091`.

## Status dan cakupan

Fase 1 selesai: inspeksi source, rekalkulasi snapshot, reproduksi bug secara
offline, dan baseline test. Fase 2 (backend) serta Fase 3 (frontend) merupakan
checkpoint berikutnya. Belum ada perubahan formula produksi, staking riil,
lock, settlement, deployment, commit atau push pada fase ini.

Target adalah aplikasi FC yang dibicarakan dalam thread: Next.js 14 / React 18 /
TypeScript, scanner Python, model Poisson/Dixon–Coles dan SQLite. MLB tidak
termasuk refactor ini. Audit UI berbasis source lokal, bukan hasil pemeriksaan
browser deployment terbaru. Desain Figma lama bukan acuan visual untuk brief baru.

## Kesimpulan utama

Mesin sudah mempunyai fondasi matematika deterministik. Tidak ditemukan LLM
memilih pemenang pada jalur `fc-scan-live.py` dan `football_formula_engine` yang
diaudit. Poisson/Dixon–Coles, proportional de-vig, score-matrix, quarter-line
settlement, dan EV berbasis payout sudah ada. Menggantinya secara membabi buta
berisiko menghilangkan penanganan Asian line yang sudah benar.

Masalah pertama adalah data dan definisi output: snapshot terbaru tidak memakai
model liga maupun harga sharp, Top Picks menerima EV negatif, dan laporan tidak
mengukur angka confidence yang sama dengan yang ditampilkan. Ada pula bug
freshness harga referensi dan pengaitan research decision yang dapat direproduksi.

## Angka yang diverifikasi

### Snapshot scanner yang tersimpan di repo

| Ukuran | Hasil |
| --- | ---: |
| Fixture | 241 |
| Fixture berproyeksi dengan `market_only` | 217 |
| Proyeksi market utama | 847 |
| Proyeksi dengan confidence dari harga pasar | 847 / 847 |
| Qualified/value picks | 0 |
| Lolos aturan Top Picks saat ini (confidence tinggi, odds ≥1,40) | 7 |
| Top Picks dengan EV nonpositif | 7 / 7 |
| Rentang EV tujuh pick tersebut | −5,92% sampai −2,66% |
| 1X2 odds <1,30 yang dapat tampil, tetapi tidak dicatat logger | 31 |
| Proyeksi dengan selisih confidence vs probability >1 percentage point | 635 / 847 |
| Selisih maksimum kedua angka tersebut | 20,02 percentage points |
| Kesalahan EV tersimpan vs rekalkulasi payout (toleransi pembulatan) | 0 |

`config.json:last_scan_diagnostics` mengonfirmasi model_lane=0,
reference_only_lane=0 dan fixtures_priced=0. Keenam request liga sharp
berstatus `FETCH_FAILED / HTTPError`. Ada 42 fixture yang kehilangan referensi.
Penyebab HTTP belum dapat dipastikan: kode sekarang tidak menyimpan status HTTP
yang membedakan autentikasi, kuota, entitlement, endpoint, dan gangguan provider.
Tidak ada percobaan memakai API key atau menghabiskan kuota provider dalam audit.

Counter coverage market_only=218 menghitung masuk jalur sebelum analisis selesai;
217 fixture akhirnya mendapat hasil, satu `COMPLETE_MARKET_UNAVAILABLE`, dan 23
duplikat dikeluarkan. Angka ini bukan 218 model statistik aktif.

### Ringkasan model-performance yang tersimpan (15 Oktober, 13:00 WIB)

| Market | N dinilai (termasuk push) | Hit rate tanpa push | Brier | Log loss | Gap kalibrasi |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1X2 | 415 | 55,42% | 0,2336 | 0,6587 | +3,11 pp |
| Asian HDP | 439 | 48,56% | 0,2399 | 0,6722 | −3,05 pp |
| O/U | 480 | 47,69% | 0,2486 | 0,6913 | −5,67 pp |
| BTTS | 396 | 53,28% | 0,2516 | 0,6976 | −4,60 pp |
| Gabungan | 1.730 | 51,13% | 0,2435 | 0,6800 | −2,65 pp |

Laporan menyatakan 4.915 entri, 1.730 ter-grade, 3.185 pending. Pending tidak
boleh disamakan dengan overdue. Gap membandingkan prediksi probabilitas payout
positif dengan kejadian win/half-win, termasuk push sebagai non-win; denominator
berbeda dari hit rate. Ini ringkasan berbagai versi, bukan validasi v5 terpisah.

Full ledger terbaru tidak ada di direktori engine; report hanya menyertakan 100
detail terakhir. Salinan Downloads yang pernah diberikan pengguna masih tersedia:
12.458 baris ledger sampai 9 Oktober 2026 dan 10.321 grade sampai 9 Oktober.
Versinya blend-v2, secondary-v1, ratio baseline, DC, blend-v3, serta sebagian
tanpa versi. Salinan tersebut tidak berisi cohort sharp-reference-v5 sehingga
tidak dapat digunakan untuk mengklaim kalibrasi versi terbaru.

### Rekalkulasi tracker historis (cohort berbeda)

197 single settled: 74 profit positif, 111 negatif, 12 push; hit rate 40,00%,
ROI hasil rekalkulasi −9,824%, Brier 0,23967, log loss 0,67153. Semua payout
konsisten dengan skor yang tersimpan, tetapi skor tidak diverifikasi ulang ke
sumber independen. Seluruh 203 baris single termasuk pending kehilangan timestamp
quote dan formula_version pada snapshot; interpretasi probabilitas legacy masih
provisional. Ada 6 single overdue. Tracker gabungan melaporkan 203 tiket settled,
ROI −12,50%, profit −25,37u, termasuk 6 parlay kalah (−6u).

| Bucket probabilitas single legacy | N | Rata-rata prediksi | Payout positif aktual | Gap |
| --- | ---: | ---: | ---: | ---: |
| 20–30% | 12 | 28,42% | 16,67% | −11,76 pp |
| 30–40% | 35 | 35,05% | 25,71% | −9,34 pp |
| 40–50% | 56 | 45,17% | 33,93% | −11,24 pp |
| 50–60% | 70 | 54,77% | 48,57% | −6,20 pp |
| 60–70% | 21 | 63,23% | 38,10% | −25,14 pp |
| 70–80% | 3 | 73,04% | 66,67% | −6,37 pp |

Bucket terakhir terlalu kecil untuk kesimpulan kuat. Tabel ini tidak mewakili
847 proyeksi market-only saat ini atau validasi strategi baru.

## Temuan source dan reproduksi

1. **P1 — harga sharp basi dapat lolos freshness gate.**
   `live_quotes.py:103` membatasi `captured_at`, sedangkan
   `sharp_reference.py:41` membawa `source_updated_at` tanpa memeriksa umurnya.
   Reproduksi memakai quote ditangkap 5 detik lalu tetapi sumber diperbarui 3.600
   detik lalu: 5 kontrak tetap diterima dalam jendela 900 detik. Home fair 50%
   pada odds 2,10 menghasilkan EV 5% dan gate kosong. Ini bug terkonfirmasi
   secara sintetis; tidak ada bukti bahwa quote tersebut benar-benar dipakai live.
   Perbaikan: cek kedua timestamp, skew antar sisi, identitas kontrak, dan
   provenance quote; sumber waktu tak diketahui diberi status eksplisit.

2. **P1 — Top Picks tidak menguji edge.**
   `PredictionBoard.tsx:28` hanya memeriksa confidence dan odds. Ketujuh hasil
   snapshot memenuhi filter meskipun EV negatif. EV tidak tampak di sel utama,
   sehingga pengguna harus membuka detail. Perbaikan: satu status server yang
   konsisten (`value`, `forecast`, `pass`, `unavailable`) dan EV selalu terlihat;
   rekomendasi actionable harus memenuhi gate harga, kualitas dan freshness.

3. **P1 — confidence kartu dan target evaluasi berbeda.**
   Scanner memberi `confidence` sebagai probabilitas harga W/(W+L), sedangkan
   `probability` adalah P(full-win atau half-win). Keduanya tidak sama pada Asian
   line; pada market-only, fit score matrix dapat berbeda dari harga asli pula.
   Kartu menggunakan confidence; logger menyimpan probability tetapi tidak
   confidence/source/tier yang dipakai pemilihan. Perbaikan: kontrak terpisah
   `market_no_vig`, `model_probability`, `decision_price_probability`,
   `positive_payout_probability` dan lima probabilitas payout; evaluasi harus
   menggunakan target yang tepat dan dipisah per versi/sumber/market.

4. **P1 — ledger tidak mengikuti aturan visibilitas terbaru.**
   `predictions.ts:53` menampilkan 1X2 odds >1; `fc-log-projections.py:119`
   tetap melewatkan odds <1,30. Reproduksi pada snapshot: 31 terlihat secara
   aturan kartu, 0 tercatat. Perbaikan: satu kebijakan visibilitas yang disepakati,
   diuji lintas Python/TypeScript; perubahan filter pengguna tidak boleh diam-diam
   mengubah populasi evaluasi.

5. **P1 — research ID mengacu kontrak pertama untuk kontrak kedua.**
   `live_quotes.py:50,112` memakai primary key fixture+policy. Scanner dapat
   menerbitkan dua pick dengan policy sama. Reproduksi: permintaan kedua O/U
   Over 2,5 mengembalikan artifact/contract Home 1X2 pertama. Snapshot saat ini
   punya 0 value pick, jadi tidak ada kasus nyata yang bisa dihitung di snapshot.
   Perbaikan: identitas per fixture+policy+kontrak+versi keputusan, migrasi
   kompatibel, serta tes idempotensi dan pencocokan payload.

6. **P1 — parlay saat ini adalah pencatatan manual, belum smart builder.**
   `fc-manual-lock.py:170–291` memeriksa kickoff/harga dan menggandakan odds,
   tetapi tidak mensyaratkan edge leg dan tidak mengisi model_joint_probability.
   Market berbeda pada fixture yang sama diperbolehkan. Contoh sintetis Home
   1X2 + Away AH −0,5 mempunyai joint probability 0%, sedangkan perkalian
   probabilitas marginal menghasilkan 12,91%. Perbaikan: evaluator parlay
   sebelum lock; kontradiksi ditolak, korelasi dihitung dari joint distribution
   yang tersedia, harga SGP nyata wajib untuk menyatakan EV aktual.

7. **P2 — sumber sharp BTTS belum diminta oleh fetch utama.**
   `reference_odds.py:23` hanya meminta h2h, totals dan spreads. Adapter mampu
   membaca BTTS, tetapi itu tidak membuat fetch utama mendapatkannya. Corner
   dan card juga membutuhkan sumber kontrak tersendiri. Perbaikan: laporkan
   coverage market/provider, gunakan endpoint yang benar bila tersedia, dan
   jangan menciptakan reference probability untuk market yang tidak disuplai.

8. **P2 — Kelly tidak terhubung ke scanner/UI utama.**
   `types.ts:80` mendefinisikan `kelly_pct` opsional, tetapi jalur scanner yang
   diaudit tidak menghasilkannya. Tracker memakai flat 1u. Implementasi berikutnya
   harus menghasilkan rekomendasi yang terpisah dari taruhan nyata; unit hanya
   dapat dihitung setelah bankroll dan definisi 1u tersedia.

9. **P2 — UI belum memenuhi brief terminal.**
   `fc.css:53,63,105` memakai kartu radius 15px, gradient hijau, teks probabilitas
   kecil tanpa monospace, dan ruang vertikal berulang per fixture. Warna hijau
   juga dipakai untuk navigasi/status, sehingga tidak khusus berarti +EV.
   `PredictionBoard.tsx:93–101,127–134` menyembunyikan EV pada disclosure;
   pipeline lengkap dan Kelly tidak dapat dibandingkan per baris. Perbaikan:
   tabel padat dengan kolom angka rata kanan, monospace/tabular-nums, matriks
   data desktop dan baris market bertumpuk di mobile, keyboard/focus yang jelas,
   palette carbon/slate dan warna semantik hanya untuk hasil analitik.

## Koreksi penting terhadap formula dalam brief

Untuk binary tanpa push: EV = p × decimal_odds − 1. Untuk Asian settlement:

`W = P(full_win) + 0.5 P(half_win)`

`L = P(full_loss) + 0.5 P(half_loss)`

`EV = (odds − 1) W − L`; `fair_odds = 1 + L/W`.

Contoh uji: payout=(0,4; 0,2; 0,1; 0,1; 0,2), odds=2,0 memberi EV=25%.
Shortcut binary memakai P(payout positif)=60% memberi 20%, sehingga salah 5pp.
Pada snapshot Asian, kesalahan maksimum shortcut ini mencapai 26,41pp.
EV engine sekarang cocok dengan rekalkulasi; bagian ini harus dipertahankan.

Quarter Kelly pada binary mengikuti rumus brief. Untuk split/push, cari f yang
memaksimalkan E[log(1+fR)] atas lima outcome, lalu kalikan 0,25 dan cap 2%
bankroll sebagai rekomendasi. Jangan menempelkan rumus binary ke probability
yang semantiknya berbeda. Korelasi positif saja juga tidak membuktikan +EV
parlay; joint payout dan harga bookmaker tetap harus dibandingkan.

## Urutan fase berikut dan kriteria selesai

**Fase 2 — backend:** perbaiki freshness dan error HTTP yang tersanitasi;
pastikan asal data/coverage terlihat; benahi identitas ledger dan definisi
probabilitas; tambahkan evaluator Kelly dan parlay; satu kontrak API untuk UI.
Pertahankan model Poisson/DC dan payout math yang lulus pengujian. De-vig
multiplicative sudah memenuhi brief; alternatif Power hanya diaktifkan setelah
evaluasi. Bila LLM kelak digunakan, pisahkan schema evidence dan delta maksimal
±0,03, validasi numerik di kode, normalisasi outcome dan hitung ulang EV; tanpa
evidence output harus abstain. Jalur FC sekarang tidak memerlukannya.

Gate selesai: tes stale/unknown timestamps, line quarter/push, kontradiksi
parlay, invalid inputs, exact contract identity dan cap Kelly; laporan cohort
versi baru secara terpisah. Full ledger terbaru diperlukan untuk mengukur
perubahan akurasi; jangan menebak peningkatan win rate dari tes unit atau replay
yang mencampur versi. Staking riil dan produksi tetap perlu persetujuan eksplisit.

**Fase 3 — frontend:** implementasikan terminal FC pada komponen produksi,
bukan memperpanjang mock Figma: matchup/waktu, market/line, odds, no-vig,
probabilitas model/decision yang diberi sumber, EV, rekomendasi stake dan alasan
pass/unavailable. Projection goals, corner/card, watchlist, operator di ROI,
lock serta hasil parlay tetap terwakili. Gate selesai: typecheck, build,
integration tests yang relevan, review browser desktop/mobile dan aksesibilitas.

## Bukti dan reproduksi

- `reports/fc-terminal-phase1-audit-2026-10-15.json`: hitungan snapshot, SHA-256
  sumber, diagnostics dan probe sintetis.
- `reports/fc-terminal-phase1-settlement-2026-10-15.json`: rekalkulasi 197 single
  dan reliability buckets provisional dari skor tersimpan.
- `scripts/fc-terminal-audit.py`: audit offline yang dapat diulang, tanpa akses
  API atau mutasi tracker.
- Baseline Python: **120 passed** (markets, market catalog, sharp reference,
  projection ledger). Baseline TypeScript: **13 passed** (predictions, pick
  class, parlay labels, model performance). Tes existing ini belum mencakup
  semua reproduksi bug di atas. Error awal Windows temp/realpath diselesaikan
  dengan izin runtime dan direktori temp workspace khusus.

```powershell
python scripts/fc-terminal-audit.py --out reports/fc-terminal-phase1-audit-2026-10-15.json
python scripts/fc-p0-audit.py --out reports/fc-terminal-phase1-settlement-2026-10-15.json
```
