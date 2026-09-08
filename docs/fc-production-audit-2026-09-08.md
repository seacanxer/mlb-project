# Audit FC production dan patch seleksi — 8 September 2026

Status: audit API produksi dan patch lokal selesai; belum deploy/push. Pengambilan data sekitar 15:13–15:25 WIB. Tidak menjalankan mutation pada server produksi.

## Temuan utama

Filter lebih ketat belum memperbaiki kualitas probabilitas. Kandidat juga berkurang karena coverage rating sangat kecil pada slate saat audit. Di sisi lain, API memasukkan kembali kandidat yang ditolak ke daftar watch, sehingga aturan seleksi dan tampilan tidak konsisten.

### Hasil produksi yang terukur

Sumber: [tracker publik](https://fc.texasdrill.me/api/tracker), [health/config](https://fc.texasdrill.me/api/health), [picks](https://fc.texasdrill.me/api/picks), dan [matches](https://fc.texasdrill.me/api/matches?limit=200). Angka adalah snapshot, bukan hasil permanen.

| Metrik | Snapshot |
|---|---:|
| Settled picks | 653 |
| Wins / losses / pushes | 321 / 328 / 4 |
| Hit rate non-push | 49,46% |
| Profit flat-unit | -57,41u |
| ROI | -8,79% |
| Pending | 202 |
| Overdue | 197 |

| Market | Settled | Win rate non-push | ROI |
|---|---:|---:|---:|
| O/U | 388 | 52,20% | -4,10% |
| AH | 22 | 36,84% | -26,80% |
| BTTS | 233 | 47,21% | -13,40% |
| 1X2 | 10 | 20,00% | -43,85% |

Histori mencampur formula dan kebijakan lama. BTTS/1X2 masih ikut ROI kumulatif meskipun config aktif hanya AH/O/U. Tidak tersedia provenance formula/selection status pada response settled sehingga angka ini tidak dapat diatribusikan secara bersih ke Formula v4 atau official versus shadow. Sampel AH dan 1X2 kecil. Overdue menimbulkan potensi bias terhadap subset yang berhasil diselesaikan.

### Mengapa menaikkan filter probabilitas gagal

Audit kalibrasi terbatas pada O/U half-goal (tanpa push/half outcomes), karena `1 / fair_odds` pada Asian lines bukan probabilitas kemenangan penuh.

| Prediksi tersimpan | n | Rata-rata prediksi | Aktual menang | Profit |
|---|---:|---:|---:|---:|
| <55% | 17 | 52,23% | 47,06% | +0,25u |
| 55–60% | 96 | 57,84% | 54,17% | +5,97u |
| 60–65% | 123 | 62,78% | 48,78% | -11,72u |
| ≥65% | 127 | 68,84% | 55,12% | -7,29u |

Ini bukti deskriptif overconfidence pada histori gabungan, bukan alasan menetapkan 55–60% sebagai filter baru berdasarkan hasil yang sudah diketahui. Memotong raw EV dengan penalti tetap 0,02/0,04 belum sama dengan kalibrasi statistik. Menggunakan harga bookmaker untuk membentuk lambda lalu menghitung edge terhadap bookmaker yang sama juga membatasi independensi sinyal.

### Mengapa volume menurun

- Config produksi sudah memiliki limit 50, per-market 25, per-match 2; limit daftar bukan penyebab utama snapshot 5 picks.
- Window saat audit adalah 40 jam. Perubahan yang diminta ke 24 jam mempersempit waktu, bukan memperluasnya.
- Semua 262 cached matches: 5 full, 250 shadow, 7 market-only. Ini menjelaskan sedikitnya official picks pada slate tersebut; tidak membuktikan rasio yang sama setiap hari.
- Projection utama mewajibkan tiga harga 1X2 dan pasangan O/U. Fixture tanpa 1X2 dibuang meskipun pasangan AH/O/U cukup untuk proyeksi pasar.
- Shadow membutuhkan conservative EV ≥6% dan probability ≥56%; setelah penalti 4%, raw EV harus ≥10%. Filter ini sangat ketat untuk prior liga yang hanya berbobot lemah.
- Menyimpan Settings memaksa per-match menjadi 1, meskipun config awal 2. Ini menciptakan perubahan volume yang tidak terlihat.

### Mengapa watch terlihat noise

- API menambahkan semua kandidat dari `matches_detailed.json` yang tidak berada di selected list sebagai watch hanya dengan batas odds.
- Jalur itu melewati conservative EV, coverage, diversification dan selection cap.
- `conservative_ev or ev` memakai raw EV saat conservative EV tepat nol.
- API menandai semua baris `locked=True`, termasuk watch tambahan yang tidak pernah masuk tahap penyimpanan lock.
- Shadow bisa mengambil slot `is_top_pick` meskipun tier-nya watch: snapshot API menghitung 5 top picks, tetapi hanya 3 bertier top_pick dan 24 watch dari total 27 baris.
- Kandidat yang kickoff-nya sudah lewat tidak disaring di pembacaan cache.

### Settlement dan freshness

- Ada 197 overdue. Kode settlement memakai hasil FlashScore 7 hari dan fallback 3 hari dengan nama/date matching; sebagian lama dapat keluar dari jangkauan feed. Penyebab tiap overdue belum terbukti tanpa hasil resmi dan log provider server.
- Jangan otomatis mengubah overdue menjadi loss/void atau melakukan fuzzy matching lebih longgar.
- `scan_state` web process tertinggal dibanding timestamp config worker. Snapshot health menampilkan scan 7 September sementara config menyatakan sukses 8 September. Ini bukan bukti worker berhenti: state antarprocess terpisah.

## Patch yang diterapkan

| File | Perubahan |
|---|---|
| config.json | window 24 jam, odds cap 2,75 |
| prediction.py | `build_projection_fallback` memakai pasangan O/U dan AH ketika projection utama gagal validasi; output selalu shadow; liga blocked tetap ditolak |
| main.py | CLI memakai paginated/window scan; fallback yang sama; missing 1X2 dapat dianalisis; shadow conservative EV ≥2%, probability ≥50%, wajib dua market lengkap, odds maksimal 2,50; official cap 2,75 |
| main.py | Top Pick hanya full/official; selector tidak mengarang status locked; tolak nilai non-finite |
| server.py | fallback hanya pada ValueError, diagnostics funnel, final-detail league check untuk semua source, perbaikan FlashScore→1xbit fallback |
| server.py | hapus watch bypass; sembunyikan cached fixture yang sudah kickoff; count official mencakup top; lock flag mengikuti cache yang benar-benar dipersist |
| server.py | simpan diagnostic scan dan baca timestamp worker dari config; Settings mempertahankan per-match dalam rentang 1–2 |
| league_profiles.py | tutup celah friendlies, Primavera, MLS Next Pro, team-vs-player, dan trophy |

Routing senior unrated sudah shadow sebelum patch. Tidak perlu melonggarkan larangan youth atau nonstandard untuk menambah volume. Fallback tidak membuat rating tim atau harga draw buatan; `fair_1x2` fallback merupakan output distribusi pasar, bukan quote 1X2 yang diamati.

Shadow tetap memakai mekanisme pencatatan existing, sehingga tracker historis masih bercampur. Pemisahan cohort official/shadow/formula pada database adalah pekerjaan berikutnya dan diperlukan untuk evaluasi bersih. Patch ini tidak mengubah settlement historis atau mengkalibrasi model secara otomatis.

## Verifikasi

- 72 pytest tests lulus, termasuk API, projection, payout, tracker, parlay dan scanner fallback.
- Test memakai database temporary; config endpoint test diisolasi agar tidak menimpa config lokal.
- Regression cases: missing 1X2, missing paired market, blocked competitions, official-only top slots, shadow noise gates, widened official cap, API rejection bypass, expired cache, scanner diagnostics.
- `git diff --check` lulus.
- Tidak ada perubahan Next.js; build/test Node tidak diperlukan untuk patch Python ini.
- Ada warning deprecation dari dependency Starlette/httpx; tidak menyebabkan kegagalan.

### Replay kandidat produksi

Script `betting-machine-fc/audit_public.py` hanya GET API. Ia membandingkan seleksi dari cached candidates yang sama dalam 24 jam dan memeriksa pasangan market dari detailed data:

- 29 candidates dalam window;
- gate lama: 3 selected;
- gate baru: 4 selected, yaitu 1 official dan 3 shadow.

Replay tidak mencakup fixture yang dulu gagal projection karena tidak tersimpan, tidak mengambil quote baru, dan bukan backtest profit. Karena itu belum dapat mengklaim 30–40 picks/hari atau kenaikan win rate. Peningkatan hanya 1 kandidat pada snapshot ini; pengaruh fallback perlu diukur dari diagnostic scan setelah deployment.

## Tahap untuk membuktikan ketajaman

1. Simpan formula version, policy version, official/shadow, reference odds, target odds, dan waktu quote pada setiap lock baru.
2. Audit overdue per fixture dengan identitas dan skor resmi; laporkan unresolved secara terpisah.
3. Rekonstruksi evaluasi berdasarkan waktu lock, gunakan ratings yang tersedia sebelum match, dan uji walk-forward pada hari yang belum dipakai menyetel threshold.
4. Bandingkan reference no-vig baseline, market-only dan hybrid. Evaluasi O/U binary terpisah dari payout distribusi Asian lines.
5. Ukur calibration/Brier, log loss, flat-unit ROI, CLV, coverage dan uncertainty per market/liga; laporkan official dan shadow terpisah.
6. Pilih perubahan formula hanya bila perbaikan bertahan di forward cohorts. Menaikkan odds cap bisa menambah variance dan menurunkan hit rate, sehingga profit dan hit rate harus dinilai bersama.

## Delivery

Patch berada di working tree lokal. Belum commit, push, atau deploy ke `fc.texasdrill.me`; endpoint produksi yang diaudit masih menjalankan versi sebelum patch. Keberhasilan tests membuktikan perilaku implementasi yang diuji, bukan peningkatan kemenangan di masa depan.
