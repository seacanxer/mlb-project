# FC terminal overhaul — Fase 2: backend quant dan integritas keputusan

Tanggal: 15 Oktober 2026 (WIB). Scope: implementasi lokal dari audit Fase 1.
Fase 3 (redesign terminal) belum dikerjakan. Perubahan UI pada fase ini terbatas
pada aturan seleksi dan penjelasan makna probabilitas.

## Perilaku yang berubah

### Harga referensi dan diagnosis provider

Scanner memakai `reference_snapshot()` untuk memilih satu market lengkap dari
observasi yang sama. Sisi baru tidak digabung dengan sisi lawan dari snapshot
lama. Kontrak AH mempertahankan perspektif handicap masing-masing tim; period
harus full-time 90 menit. Harga dari bookmaker sendiri tidak boleh menjadi
referensi independen.

Kedua jam diperiksa: capture dan update sumber maksimal 900 detik. Waktu sumber
yang tidak diketahui, source basi, future timestamp, atau market tidak lengkap
menahan value. Capture primary dan sharp boleh berbeda maksimal 300 detik;
primary entry maksimal 300 detik. Scanner menyegarkan referensi per liga setelah
270 detik saat scan panjang, sehingga cache tidak otomatis bertentangan dengan
gate skew. Ini dapat menambah request pada scan panjang dibanding interval
600 detik sebelumnya.

Diagnostics memisahkan HTTP 401, 402, 403, 404, 422, 429, 5xx dan kegagalan
jaringan. Tidak menyimpan URL, API key atau body respons. Status provider kini
READY/DEGRADED/UNAVAILABLE/NO_MATCHES, beserta alasan quote ditolak dan jumlah
kontrak per market yang berhasil diberi referensi. Sekadar key terpasang tidak
lagi berarti sumber berhasil diambil.

Fetch bulk tetap h2h/totals/spreads. BTTS, corner dan card dicatat sebagai tidak
disuplai oleh request bulk tersebut. Tidak ditambahkan harga/provider fiktif.
Penyebab HTTPError pada snapshot lama masih memerlukan respons scan berikutnya
dengan diagnostics baru; fase ini tidak memakai API key atau menjalankan feed live.

### EV, definisi probabilitas, dan Kelly

Poisson/DC, proportional no-vig, seluruh quarter line dan settlement payout
yang ada dipertahankan. Output baru `quant.schema_version=fc-quant-v1` memuat:

| Field | Makna |
| --- | --- |
| market_no_vig_probability | Probabilitas harga tanpa margin buku utama |
| model_positive_payout_probability | P(full-win/half-win) proyeksi model sebelum anchoring; null bila model tidak ada |
| decision_price_probability | W/(W+L), probabilitas harga yang menentukan fair odds |
| positive_payout_probability | P(full-win atau half-win) distribusi keputusan |
| reference_probability / reference_evidence | Harga sharp tanpa margin dan identitas/timestamp observasinya |
| ev / fair_odds | Expected return per unit / harga impas berbasis payout |
| edge_probability | Selisih probabilitas harga keputusan dengan no-vig buku utama |
| status / reason_codes | value, forecast atau pass, dengan alasan eksplisit |
| kelly | Rekomendasi fraksi bankroll dan unit, bukan eksekusi taruhan |

Binary tanpa push memakai EV=p×odds−1. Asian memakai
EV=(odds−1)×[P(FW)+0,5P(HW)]−[P(FL)+0,5P(HL)]. Fair odds=1+L/W.
Tidak ada pembulatan quarter line ke whole/half dan tidak ada perubahan EV
menjadi shortcut binary.

Kelly memaksimalkan E log(1+fR) pada semua outcome payout, mengambil 25% dari
hasilnya, lalu membatasi rekomendasi maksimal 2% bankroll. Tanpa eligibility
atau EV positif, rekomendasi nol. Tanpa konfigurasi bankroll, unit null.

`FC_BANKROLL_UNITS` opsional: bankroll model dalam satuan unit. Contoh bankroll
100u dan rekomendasi 1% menghasilkan 1u. Isian ini beserta rekomendasinya muncul
di metrik API; kosongkan bila tidak ingin menyajikan bankroll unit. Angka ini
tidak mengubah stake tracker: lock/settlement tetap flat 1u.

Status value memerlukan gate harga v5, sumber keputusan sharp yang konsisten
dengan payout, dan bukti observasi yang lolos validasi. `model_blend` yang
direstorasi melalui konfigurasi tetap menyediakan proyeksi, tidak menjadi
rekomendasi tanpa referensi. Corner/card berharga juga mendapat metrik quant,
tetapi tetap forecast/pass dan Kelly nol selama model/reference belum tervalidasi.

### Konsumsi API dan seleksi

Reader API mengecek ulang umur quote pada setiap pembacaan file scan; data
yang kedaluwarsa turun menjadi forecast/pass dan rekomendasi stake nol tanpa
mengubah file asli. Counter actionable/value hanya menghitung evidence yang
masih berlaku. Output lama tanpa quant memerlukan rescan sebelum menjadi value.

Top Picks sekarang memerlukan value terverifikasi selain confidence tinggi
dan odds ≥1,40. Kandidat value menerima reference-only yang memenuhi syarat,
dengan floor 1,30 sesuai gate v5. Seluruh proyeksi tetap tersedia pada tampilan
semua hasil. Klaim hit rate tier global dihapus dari kartu; cohort prospektif
harus dinilai berdasarkan versi/sumber/market yang sesuai.

### Ledger dan research identity

Tabel append-only baru `research_decisions_v2` memakai identitas fixture +
policy + market/side/quarter-line + versi formula. Kontrak berbeda mendapat
ID berbeda, retry kontrak/versi sama mengembalikan entry pertama. Tabel legacy
dan trigger imutabilitasnya tetap tersimpan. Payload scanner membedakan ID
entry riset pertama dari quote terkini melalui research_entry_contract,
research_observation_id dan research_decision_at.

Ledger v2 menyimpan confidence beserta source/tier, probability semantics,
quant, observation ID dan decision time. Key baru memasukkan formula/policy/
quant-version agar cohort versi berbeda dapat dinilai, tanpa menulis ulang
riwayat lama. Logger kini mengikuti visibilitas 1X2 odds >1 yang ada di aplikasi,
sehingga 31 baris di bawah 1,30 tidak lagi hilang.

Laporan performance menambah calibration_cohorts per formula, policy, lane,
source, dan market, dengan reliability buckets, Brier dan log loss. Target
yang dinilai adalah kejadian payout positif, bukan probabilitas harga W/(W+L).
Aggregate legacy tetap kompatibel; cohort yang kehilangan provenance diberi
legacy_unknown. Tidak dilakukan backfill atau overwrite ledger produksi.

### Parlay

`POST /api/fc/parlay/evaluate` mendukung dua request:

- `choices`: 2–8 identitas pick dan odds yang dilihat pengguna. Semua probabilitas,
  payout, waktu dan evidence diambil ulang dari scan server. Field client untuk
  probability/EV ditolak.
- `mode: "build"`: usulan 2–3 leg dari qualified picks server, satu pilihan
  terbaik per fixture, maksimum 18 fixture kandidat dan 5 usulan. Tidak membuat
  lock otomatis. Tanpa kandidat terverifikasi, hasil berupa daftar kosong.

Untuk fixture berbeda, setiap leg harus punya EV >2%, proof sharp yang masih
berlaku, quant yang konsisten dengan payout, serta kickoff lebih dari 60 detik.
Return multiplier dikonvolusi: half-win, push dan half-loss tidak diperlakukan
sebagai win/loss penuh. Hasil membedakan peluang semua leg payout positif dengan
peluang profit tiket positif. Compound EV/Kelly bersyarat pada asumsi fixture
independen dan payout perkalian odds leg yang diamati; executable_quote_verified
tetap false karena tidak ada quote tiket bookmaker yang diobservasi.

Fixture sama tidak diasumsikan independen. Mesin mendeteksi kombinasi mustahil
(misalnya Home 1X2 + Away −0,5) dari settlement score. Joint score-matrix dapat
ditampilkan sebagai skenario model yang belum tervalidasi, tetapi lock same-game
ditahan dengan SAME_MATCH_JOINT_PRICE_UNVERIFIED. Harga SGP dan validasi joint
distribution diperlukan sebelum mendukung rekomendasi tersebut; korelasi
positif saja tidak cukup membuktikan +EV.

Lock parlay menjalankan evaluator sebelum transaksi DB. Kegagalan menulis nol
baris. Tiket yang diterima menyimpan assessment beku beserta payout/quant leg,
dan model_joint_probability berarti peluang seluruh leg payout positif di
bawah asumsi independensi. Histori tiket lama tidak diubah. Lock single masih
merupakan pilihan manual, tetapi memerlukan odds, probabilitas dan EV numerik;
proyeksi tanpa harga tidak dapat dimasukkan ke perhitungan ROI.

## Hasil yang sudah dibuktikan

`reports/fc-quant-phase2-dry-run-2026-10-15.json` mencatat replay offline 241
fixture / 847 proyeksi dari snapshot yang sama dengan audit Fase 1:

| Pemeriksaan | Hasil |
| --- | ---: |
| Proyeksi pass karena EV nonpositif | 738 |
| Forecast positif tetapi tanpa bukti referensi baru | 109 |
| Top Picks lama ditahan dari actionable | 7 / 7 |
| Ketidaksesuaian EV payout | 0 |
| 1X2 odds <1,30 tercatat pada logger | 31 (sebelumnya 0) |
| Kontrak sharp basi diterima pada probe | 0 (sebelumnya 5) |
| ID research dua kontrak berbeda | Berbeda; kontrak kedua sesuai request |

Pemeriksaan ini membuktikan guard dan matematika. Tidak mengukur peningkatan
win rate atau ROI. Ledger v5 terbaru dan hasil prospektif masih diperlukan;
baseline Brier 0,2435, log loss 0,6800 dan ROI tracker −12,50% dari Fase 1
belum menjadi angka baru setelah refactor. API/provider live tidak diuji pada
fase ini, sehingga ketersediaan pick berikutnya belum dapat dijamin.

## Verifikasi

- Engine Python, quant, quote journal, ledger, manual lock dan secondary markets:
  **350 tes lulus**.
- FC TypeScript/API: **92 tes lulus**.
- Typecheck dan build Next.js lulus. Dua warning hook yang sudah ada tetap
  tercatat di ai-picker dan Results; tidak menghalangi build.
- Tes finansial menggunakan DB sementara; tidak ada settlement produksi,
  pemasangan taruhan, atau perubahan stake aktual.

Reproduksi dry-run:

```powershell
python scripts/fc-quant-dry-run.py --out reports/fc-quant-phase2-dry-run-2026-10-15.json
```

Setelah implementasi diterapkan, satu scan baru diperlukan untuk mengisi
quant/evidence. Periksa diagnostics HTTP, markets_priced dan quote_rejections
sebelum menyimpulkan provider telah pulih. Fase 3 kemudian menggunakan kontrak
quant dan evaluator ini untuk tampilan terminal desktop/mobile.
