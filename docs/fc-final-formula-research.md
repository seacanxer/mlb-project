# Formula Final FC: 1X2, O/U, Asian Handicap, dan BTTS

## Keputusan utama

Desain yang direkomendasikan adalah **regularized, time-weighted Dixon–Coles dengan penyesuaian liga, satu distribusi skor bersama, kalibrasi koheren, dan seleksi berdasarkan expected return setelah memperhitungkan ketidakpastian**. Nama spesifikasi: `fc-coherent-dc-v1`. Keempat market termasuk dalam cakupan, tetapi izin menerbitkan pick diberikan secara terpisah per liga–market setelah validasi.

Ini adalah finalisasi desain matematika dan kontrak evaluasi, bukan klaim bahwa parameter optimal atau ROI positif sudah ditemukan. Belum ada backtest baru yang membuktikan keunggulan desain ini pada data proyek. Aktivasi official tetap tertutup sampai hasil pengujian tersedia. Target bisnis adalah peningkatan jumlah peluang yang benar-benar dapat dinilai, kualitas probabilitas, dan profit net yang terukur—bukan kewajiban menghasilkan 30–40 pick sehari.

Formula yang lebih kompleks tidak otomatis lebih baik. Dixon–Coles merupakan dasar yang dapat diaudit; penelitian lain menawarkan hierarchical Bayes, model dinamis, dan distribusi Weibull-count/copula. Tidak ada dasar untuk menyatakan bahwa semua model serius harus Poisson atau satu model akan unggul di seluruh liga.[^1][^2][^3]

Bagian bertanda **keputusan desain** adalah rekomendasi engineering untuk proyek ini, bukan hasil empiris dari paper. Ringkasan sumber, batas bukti, dan parameter yang masih harus diestimasi dicantumkan agar implementasi tidak mengubah asumsi menjadi fakta.

## 1. Koreksi terhadap preparation

Dokumen `risetv2.pdf` memberi fondasi berguna: satu matriks skor, penyesuaian kekuatan tim, de-vig, payout Asian, dan walk-forward. Namun beberapa pernyataannya perlu dibatasi sebelum menjadi kode.[^12]

| Pokok | Keputusan final | Alasan |
|---|---|---|
| Rasio gol home/away | Jadikan baseline pembanding, bukan model utama | Sampel split kecil dan kekuatan lawan tidak dikontrol secara eksplisit |
| Nilai rho universal | Estimasi dengan regularisasi; sertakan rho=0 sebagai baseline | Korelasi skor rendah tidak harus sama antar liga atau periode |
| DC memperbaiki O/U 2.5 secara langsung | Ditolak pada lambda tetap | Koreksi empat sel semuanya berada di total gol ≤2 dan jumlah koreksinya nol |
| Elo logistic = probabilitas menang | Ditolak | Dengan skor draw=0.5, expected score adalah P(win)+0.5P(draw), bukan P(win) |
| EV=p×odds−1 untuk semua market | Hanya kasus binary tanpa push | Asian membutuhkan lima kategori payout |
| CLV satu-satunya ukuran sukses | Ditolak | Harus dilengkapi proper scores, kalibrasi, return aktual, coverage, dan ketidakpastian |
| Kelly langsung 0.25–0.5 | Tidak diaktifkan pada peluncuran | Ketidakpastian probabilitas belum tervalidasi; flat-unit lebih transparan untuk audit |
| Lebih banyak pick melalui shadow | Ditolak sebagai jalur official | Coverage boleh bertambah; kelayakan taruhan tidak boleh direkayasa |

**Koreksi review terdahulu:** dugaan bahwa implementasi lama menukar pasangan lambda pada koreksi DC 0–1 dan 1–0 tidak terbukti. Pemeriksaan versi historis `83215fe:betting-machine-fc/model.py` menunjukkan pasangan yang benar. Jangan membuat patch pembalikan lambda berdasarkan dugaan tersebut.

Identitas Elo di atas mengikuti definisi nilai hasil pertandingan. Elo masih dapat menjadi fitur atau baseline 1X2 dengan model draw tambahan, tetapi tidak boleh dicampur sebagai bobot persentase seolah-olah sudah memberikan tiga probabilitas lengkap. Konsep expected score juga digunakan dalam dokumentasi rating FIDE.[^11]

## 2. Kondisi repo dan batas data

Pada checkout yang diperiksa, lapisan FC di Next.js membaca artifact JSON melalui `lib/fc/store.ts`; modul tersebut bukan mesin prediksi. `scripts/fc-scrape-fixtures.py` mengumpulkan jadwal, bukan odds atau analisa. Kontrak `lib/fc/types.ts` masih memuat istilah legacy seperti `shadow`, `watch`, dan satu angka `probability` yang ambigu untuk Asian.[^13]

Konsekuensinya, pekerjaan nanti bukan sekadar mengganti konstanta di mesin Python lama. Diperlukan engine teruji yang menghasilkan artifact ber-versi untuk adapter FC. Arsitektur aplikasi Next.js/TypeScript dipertahankan; training dan kalkulasi numerik dapat dijalankan sebagai proses Python terpisah. Jangan menghitung ulang formula di React atau menyalin logika payout ke beberapa menu.

Normalisasi historis saat ini mengambil B365 1X2, O/U 2.5, serta AH; closing columns tidak dipertahankan. Koleksi yang ada belum membuktikan tersedianya snapshot historis BTTS atau semua alternative totals. Hasil skor cukup untuk menilai probabilitas BTTS, tetapi **tidak cukup untuk membuktikan ROI BTTS tanpa harga yang tersedia saat keputusan dibuat**. Backtest closing-price juga bukan simulasi strategi scan 24 jam sebelum kickoff.

Temuan provenance penting: Football-Data menyatakan odds Pinnacle dari public API-nya sejak **23 Juli 2025** dapat sistematis tertinggal, termasuk kolom closing. Karena itu data tersebut tidak boleh otomatis dianggap benchmark CLV terpercaya. Pernyataan ini spesifik pada feed yang dijelaskan Football-Data, bukan bukti bahwa seluruh produk Pinnacle bermasalah.[^4]

Keputusan desain: tandai sumber/kolom/periode yang terdampak; keluarkan dari benchmark utama sampai freshness terverifikasi. Pertahankan closing quote sumber lain bila tersedia dan dokumentasikan keterbatasannya. `scraped_at` milik jadwal tidak boleh dipakai sebagai timestamp odds.

## 3. Pemilihan keluarga model

| Kandidat | Kegunaan | Kelemahan dan keputusan |
|---|---|---|
| League-average independent Poisson | Baseline minimum untuk mendeteksi kompleksitas yang tidak berguna | Tidak mengenali tim; wajib tersedia dalam evaluasi |
| Rasio attack/defense | Mudah dijelaskan dan menjadi pembanding preparation | Rentan sampel tipis dan schedule strength; tidak menjadi default |
| Regularized time-weighted DC | Interpretabel, hemat data, satu matriks untuk empat market | Keterbatasan tail/dependence; dipilih sebagai kandidat utama |
| Hierarchical/dynamic model | Partial pooling dan perubahan kemampuan tim | Risiko overshrinkage serta kompleksitas inference; perlu pembanding OOS |
| Weibull-count/copula atau alternatif dispersion | Menangani pola gol yang tidak cocok dengan Poisson | Kandidat challenger jika residual/holdout menunjukkan kebutuhan |
| Market-informed ensemble | Memakai informasi harga yang tidak ada pada statistik gol | Data timing dan circularity harus dikontrol; gated, bukan default |
| Elo, xG, lineup | Potensi fitur tambahan | Tidak aktif tanpa data point-in-time dan incremental improvement yang terukur |

Baio–Blangiardo juga membahas overshrinkage: pooling bukan pembenaran untuk meratakan semua tim. Boshnakov dan kolega menunjukkan alternatif distribusi count dengan copula. Temuan tersebut mendukung pengujian alternatif, bukan klaim bahwa mengganti distribusi pasti menaikkan profit.[^2][^3]

Penelitian Egidi dan kolega menggabungkan informasi historis dan odds dalam model scoring rate. Itu mendukung kelayakan pendekatan gabungan, tetapi bukan izin menggunakan closing odds yang belum tersedia ketika prediksi dibuat.[^5]

## 4. Formula inti: kekuatan tim dan liga

Untuk pertandingan m pada liga l dan musim s, home i melawan away j:

```text
log(lambda_home,m) = mu_l,s + home_l,s × home_indicator_m + attack_i + defence_j
log(lambda_away,m) = mu_l,s                            + attack_j + defence_i
```

`defence` didefinisikan sebagai kerentanan: nilai lebih tinggi berarti lebih mudah kebobolan. Dengan definisi ini kedua tandanya positif; jangan menyalin tanda dari implementasi yang mendefinisikan defence sebagai kekuatan bertahan. Untuk venue netral, `home_indicator=0`. Identitas tim, liga, musim, dan venue harus eksplisit.

Keputusan desain:

- Estimasi attack dan defence bersama-sama, sehingga jadwal lawan ikut diperhitungkan.
- Gunakan kendala sum-to-zero pada attack dan defence dalam populasi liga untuk identifiability.
- Regularisasikan kekuatan tim ke pusat liga. Regularisasikan baseline/home advantage liga–musim ke prior historis yang hanya memakai masa lalu.
- Tim promosi tidak otomatis mewarisi rating divisi lama secara setara. Gunakan prior liga baru; transfer antardivisi hanya bila koefisiennya tervalidasi.
- Kompetisi cup, venue netral, dan liga yang tidak tercakup training tidak otomatis mendapat izin official.
- Tidak ada multiplier manual “big league”, “must win”, “revenge”, atau persentase confidence dari narasi AI.

Bobot waktu dan objektif fitting:

```text
w_m = exp(-ln(2) × age_days_m / H_l)
theta_hat = argmin_theta [ -sum_m w_m log P_theta(score_m) + penalty(theta) ]
n_eff = (sum_m w_m)^2 / sum_m w_m^2
```

`H_l` adalah half-life. Untuk eksperimen awal, preregister kandidat 90, 180, dan 365 hari; ini **ruang pencarian engineering**, bukan hasil optimasi. Liga dengan data terbatas memakai half-life pooled yang dipilih pada validation, bukan tuning terpisah dengan beberapa kemenangan. Laporan menampilkan jumlah pertandingan mentah dan `n_eff` per tim/segmen; angka tersebut bukan confidence probabilitas.

Implementasi awal menggunakan penalized likelihood/MAP dengan refit berkala dan time decay, bukan mengklaim sudah membangun state-space model penuh. Prior musim dan decay diuji lewat ablation agar sejarah tidak didiskon berulang secara tidak sengaja.

## 5. Distribusi skor dan koreksi Dixon–Coles

Untuk x gol home dan y gol away:

```text
P(x,y) = Pois(x; lambda_home) × Pois(y; lambda_away) × tau(x,y)

tau(0,0) = 1 - lambda_home × lambda_away × rho
tau(1,0) = 1 + lambda_away × rho
tau(0,1) = 1 + lambda_home × rho
tau(1,1) = 1 - rho
tau(other) = 1
```

Estimasi rho per liga dengan shrinkage ke nol; rho=0 tetap kandidat sah. Formula DC dan time weighting merupakan fondasi historis model ini.[^1] Rentang tetap seperti [-0.15,0.15] bukan jaminan valid untuk semua lambda.

Syarat non-negatif pada satu fixture:

```text
max(-1/lambda_home, -1/lambda_away) <= rho
rho <= min(1, 1/(lambda_home × lambda_away))
```

Likelihood training harus valid pada seluruh observasi. Validasi ulang pada setiap prediksi dan setiap bootstrap fit. Jika parameter menghasilkan tau negatif, tandai model invalid: jangan diam-diam clip tau lalu normalize. Fallback rho=0 hanya boleh berasal dari model alternatif yang sudah terdaftar dan tervalidasi, bukan penyelamatan ad hoc terhadap pick tertentu.

Gunakan grid adaptif dengan batas massa ekor terkontrol, bukan hard-code 0..10. Target toleransi numerik awal `1e-8` adalah aturan akurasi komputasi, bukan gate taruhan. Normalisasi boleh mengoreksi truncation yang terukur; nilai `tail_mass_bound` dan ukuran grid harus disimpan.

Pada lambda tetap, delta empat sel adalah `[-c,+c,+c,-c]`, dengan `c=lambda_home×lambda_away×exp(-lambda_home-lambda_away)×rho`. Jumlahnya nol. Semua berada di total ≤2, sehingga DC tidak mengubah O/U 2.5 secara langsung. Re-estimasi model bersama dapat mengubah lambda dan dengan demikian mengubah O/U 2.5 secara tidak langsung.

## 6. Kalibrasi koheren dan ketidakpastian

Kalibrasi tidak boleh dilatih pada pertandingan yang dipakai untuk mengevaluasinya. Brier/log loss mengukur lebih dari kalibrasi; reliability curve dan ukuran sampelnya tetap diperlukan. Dokumentasi scikit-learn memperingatkan risiko overfit isotonic pada calibration set kecil.[^6]

**Keputusan desain:** baseline kalibrasi adalah identity. Challenger awal menggunakan exponential tilt pada matriks, bukan empat penyesuaian probabilitas yang saling independen:

```text
P_cal(x,y) = P_base(x,y) × exp(c · g(x,y)) / Z
g(x,y) = [ I(x+y<=2), I(x>y), I(x=y), I(x>0 and y>0) ]
Z = sum_x,y P_base(x,y) × exp(c · g(x,y))
```

Keempat koefisien dikalibrasikan lewat penalized score log loss pada prediksi out-of-sample historis. `c=0` berarti identity. Koefisien liga di-shrink ke pooled coefficients; jangan melatih empat parameter bebas pada segmen sangat kecil. Pilih kekuatan regularisasi di inner validation. Ini proposal kalibrasi khusus proyek, bukan algoritme sepak bola yang sudah terbukti menang dalam sumber penelitian.

Fitur indikator bounded dipilih agar koreksi tetap normalizable. Sesudah tilt, hitung ulang batas truncation—misalnya bound awal dikalikan `exp(max(c·g)-min(c·g))`—dan perluas grid bila perlu. Semua market diturunkan dari `P_cal`; alternatif totals tetap memerlukan evaluasi tersendiri karena fitur total ≤2 tidak menjamin kalibrasi di semua line.

Ketidakpastian berasal dari refit moving-block bootstrap pada data historis, bukan mengurangi semua probabilitas 5–10 poin. Blok disusun berdasarkan waktu/matchday, urutan dipertahankan, dan fit kalibrasi diulang tanpa memakai outer test. Distribusi mean return antar-fit mengukur ketidakpastian estimasi; variasi hasil skor dalam satu matriks adalah risiko hasil pertandingan. Keduanya berbeda.

Jika bootstrap belum andal atau gagal konvergen, statusnya `UNCERTAINTY_UNAVAILABLE`, bukan error bar nol. Quantile bootstrap bukan jaminan probabilitas profit dunia nyata, terutama saat terjadi regime shift.

## 7. Empat market dari matriks yang sama

```text
P(home) = sum_{x>y} P_cal(x,y)
P(draw) = sum_{x=y} P_cal(x,y)
P(away) = sum_{x<y} P_cal(x,y)

P(BTTS yes) = sum_{x>=1,y>=1} P_cal(x,y)
P(BTTS no) = 1 - P(BTTS yes)

P(over k.5) = sum_{x+y>k.5} P_cal(x,y)
P(under k.5) = 1 - P(over k.5)
```

BTTS menggunakan joint distribution. Perkalian marginal hanya identitas untuk model independen, bukan shortcut universal sesudah DC/kalibrasi. Jangan memaksa BTTS Yes maupun favorit home lebih sering muncul melalui aturan seleksi.

Untuk handicap, definisikan margin dari sudut tim yang dipilih: `d=x-y` untuk home, `d=y-x` untuk away. Pada component handicap h, tanda `d+h` menentukan win/push/loss. Untuk total t, gunakan tanda `x+y-t` bagi Over dan kebalikannya bagi Under.

Line seperempat dibagi rata ke dua line terdekat berjarak 0.5: -0.75 → -1.0 dan -0.5; +0.25 → 0 dan +0.5; total 2.25 → 2.0 dan 2.5. Pembagian stake dan push mengikuti aturan Asian yang dijelaskan operator.[^7] Period standar spesifikasi adalah regulation time plus injury time; aturan extra time, abandoned, postponed, dan void tetap harus mengikuti market/operator yang benar-benar digunakan, bukan asumsi global.

## 8. Satu formula expected return untuk semua market

Untuk satu unit stake pada decimal odds o, simpan peluang full win FW, half win HW, push P, half loss HL, dan full loss FL. Jumlahnya harus satu.

```text
W = P(FW) + 0.5 × P(HW)
L = P(FL) + 0.5 × P(HL)
EV_gross = (o-1) × W - L
fair_odds = 1 + L/W, jika W>0
EV_net = sum_x,y P_cal(x,y) × net_payout(x,y)
```

Jika W=0 dan L>0, tidak ada fair odds finite. Jika seluruh stake push, kontrak tidak punya peluang untung; jangan tampilkan sebagai value. `net_payout` memasukkan komisi dan aturan biaya yang benar-benar berlaku; jangan mengasumsikan biaya exchange sama dengan sportsbook.

Rumus binary muncul sebagai kasus khusus W=p dan L=1−p. Peluang profit, peluang full win, dan ekuivalen break-even tidak boleh ditampilkan dengan label tunggal “win probability” pada AH. Fair odds tanpa biaya dan fair odds net harus dibedakan bila biaya ada.

Contoh matematika, bukan hasil backtest:

| Kasus | Return net per 1 unit tanpa biaya |
|---|---:|
| Home -0.75, home menang satu gol, odds 1.95 | +0.475 |
| Over 2.25, total tepat dua gol | -0.500 |
| Under 2.25, total tepat dua gol, odds 1.95 | +0.475 |
| AH 0, pertandingan draw | 0 |

Contoh distribusi `FW=.55, HW=.10, P=.05, HL=.05, FL=.25` menghasilkan W=.60, L=.275, fair odds 1.458333 dan EV pada odds 1.95 sebesar +.295 unit. Ini fixture sintetis untuk memeriksa kode, bukan bukti edge 29.5% pada pertandingan nyata.

## 9. Market reference, de-vig, dan CLV

Untuk 1X2 atau pasangan binary tanpa push, baseline no-vig adalah `q_i=(1/o_i)/sum_j(1/o_j)`. Bandingkan dengan Shin atau power method pada validation; jangan menganggap normalisasi selalu benar atau Shin selalu unggul. Penelitian Štrumbelj menemukan perbedaan metode dan kualitas sumber odds dalam data yang ditelitinya.[^8]

Satu set de-vig harus menggunakan outcome lengkap pada bookmaker, timestamp, period, dan line yang cocok. Jangan mengambil tiga harga maksimum dari bookmaker berbeda lalu menyebut normalisasinya keyakinan satu market. Execution best price boleh digunakan terpisah bila benar-benar tersedia dan dapat diambil.

Pada Asian, reciprocal fair odds bukan probabilitas full win. De-vig dua sisi dapat memberi implied effective share, tetapi tidak mengidentifikasi kelima payout probabilities. Benchmark Asian harus memakai payout-aware reference distribution atau evaluasi langsung pada contract return dengan batas asumsi yang jelas. Satu quote cukup untuk menghitung model EV, tetapi tidak cukup untuk de-vig market secara mandiri.

Pisahkan `P_history`, `P_reference`, dan harga execution. Modul ensemble opsional boleh membentuk `P_mix=(1-w)P_history+wP_reference`, dengan bobot dari chronological OOS log score dan fallback yang telah diuji. Stacking predictive distributions memiliki dasar metodologis; penerapannya di proyek ini tetap perlu diuji.[^9] Modul ini **off** dalam baseline pertama karena data reference point-in-time belum terbukti lengkap. Jangan memilih bobot 70/30 berdasarkan intuisi.

Menggunakan target odds sebagai input bukan otomatis leakage bila sudah tersedia saat keputusan. Namun selisih model terhadap odds yang sama tidak membuktikan sinyal independen. Hasil harus dibandingkan dengan market-only baseline dan, bila layak, ablation tanpa harga target. Closing quote masa depan sama sekali tidak boleh menjadi fitur pre-match.

Ukuran CLV yang konsisten dengan payoff:

```text
closing_reference_EV = sum P_close(x,y) × R_entry(x,y)
binary special case = q_close × odds_entry - 1
```

Kontrak entry, line, dan period harus sama. Bila closing line berubah dan kontrak lama tidak dapat dipricing ulang secara defensible, tandai CLV unavailable; jangan membandingkan dua odds dari line berbeda. Selalu laporkan coverage CLV. Positive CLV adalah evidence pendukung terhadap reference yang digunakan, bukan sertifikat profit.

## 10. Seleksi berkualitas tanpa filter bertumpuk

Pipeline keputusan dipisahkan menjadi **coverage → validitas data → probabilitas → payout/EV → validasi model → exposure**. Scan horizon 24 jam memperluas kesempatan mengamati pertandingan; bukan bukti bahwa harga 24 jam sebelum kickoff masih bisa dipakai saat ini.

Untuk setiap kandidat b pada odds yang masih executable:

```text
EV_b^(r) = expected net return pada bootstrap fit r
EV_lower_b = quantile_0.10({EV_b^(r)})
eligible_b = data_valid AND model_segment_approved AND uncertainty_valid
official_candidate_b = eligible_b AND EV_lower_b > 0
rank_b = EV_lower_b
```

Quantile 0.10 merupakan **kebijakan risiko awal yang dipreregister**, bukan ambang optimum hasil penelitian. Sensitivitas terhadap 0.05 dan mean EV dilaporkan dalam development, tidak dipakai untuk memilih ulang strategi setelah melihat final test. Jangan menumpuk confidence gate, disagreement penalty, league bonus, dan probability haircut di atas ketidakpastian yang sama.

Aturan final publikasi:

- Evaluasi seluruh sisi yang memiliki quote valid: home/draw/away, Over/Under, kedua AH, Yes/No.
- Maksimum satu official pick per fixture pada peluncuran. Beberapa line/sisi tetap dicatat sebagai kandidat, bukan beberapa taruhan independen.
- Pilih EV_lower tertinggi; tie-break deterministik menggunakan quote terbaru lalu contract ID. Tidak ada random pick.
- `top_pick` adalah subset official. `watch` menjadi analisa/diagnostik tanpa saran stake dan tidak masuk official ROI.
- Tidak ada minimum jumlah pick. `NO BET` dengan alasan terstruktur adalah output normal.
- Model dengan input kurang lengkap boleh menghasilkan projection-only yang jelas labelnya, tetapi tidak melewati jalur approval.
- Batas odds adalah kebijakan produk/risk terpisah; tidak menetapkan rentang seperti 1.60–2.40 sebagai hukum optimal. Analisa ROI dan kalibrasi wajib dipecah menurut rentang odds agar longshot tidak menyamarkan kualitas.

Untuk menambah volume, perbaiki mapping liga/tim, quote coverage, tim baru dengan pooling, kedua sisi market, dan kalender. Laporkan alasan gugur per tahap. Bila coverage naik tetapi EV_lower tetap negatif, jangan mengubah angka hanya untuk mengisi halaman.

## 11. Staking, ROI, dan parlay

Peluncuran evaluasi memakai paper tracking flat satu unit per official pick. ROI didefinisikan sebagai total profit net dibagi total stake terselesaikan, termasuk stake yang push/void dengan profit nol; tampilkan pula void count dan definisi denominator. Pending tidak boleh dihitung sebagai kalah atau mengurangi denominator secara diam-diam. Half-win/half-loss masuk sesuai payout, bukan dibulatkan menjadi win/loss penuh.

Generalized Kelly, jika kelak diaktifkan:

```text
f_star = argmax_f sum_x,y P_cal(x,y) × log(1 + f × R(x,y))
```

Optimasi mensyaratkan wealth positif untuk seluruh outcome dan batas exposure yang disepakati. Kelly memaksimalkan expected log growth di bawah model probabilitasnya; ia tidak membuat probabilitas yang salah menjadi benar.[^10] Fractional factor, cap per hari, dan total exposure memerlukan kebijakan bankroll terpisah. Belum ada real-money auto-staking dalam spesifikasi peluncuran ini.

Parlay tidak digunakan sebagai alat memperbaiki ROI single yang negatif. Peluncuran formula mengevaluasi singles dahulu. Parlay hanya dari official candidates berbeda fixture, ledger dan ROI terpisah; perkalian probabilitas leg harus diberi asumsi independence, bukan dianggap pasti benar. Same-game parlay membutuhkan joint payout dari matriks dan aturan harga operator; tidak aktif di tahap pertama.

## 12. Protokol pembuktian sebelum official

Gunakan nested chronological evaluation: **training → calibration → policy validation → untouched future test**. Dalam beberapa rolling origins, hanya informasi sebelum kickoff/decision timestamp boleh masuk. Semua kandidat dari satu fixture berada pada split yang sama. Tim dan musim tidak boleh diperbarui menggunakan hasil yang belum tersedia.

Parameter half-life, regularisasi, pilihan kalibrasi, dan alternatif model dipilih di inner periods. Final test tidak boleh menjadi tuning set setelah hasilnya kurang bagus. Catat seluruh eksperimen, bukan hanya konfigurasi yang menang. Kecocokan likelihood training bukan bukti kemampuan prediksi.

Baseline wajib: league-average Poisson, ratio preparation, independent regularized Poisson, DC tanpa kalibrasi, market-only pada quote yang tersedia saat keputusan, dan kebijakan NO BET. Untuk market tanpa historical odds, laporkan probabilistic validation saja; tandai ROI dan CLV `NOT EVALUABLE` sampai snapshot terkumpul.

Metrik yang wajib dibaca bersama:

| Lapisan | Ukuran |
|---|---|
| Distribusi | Score log loss, probabilitas tail, validitas matriks |
| 1X2 | Multiclass log loss/Brier, reliability per outcome |
| BTTS & half-line O/U | Binary log loss/Brier, reliability, bias Yes/No dan Over/Under |
| AH & integer/quarter totals | Proper score kategori payout yang mungkin, calibration atas W/L, return net |
| Kebijakan | Pick count, acceptance rate, profit units, flat-unit ROI, drawdown, exposure |
| Reference | Same-contract CLV, jumlah quote cocok, freshness/provenance exclusions |
| Ketidakpastian | Confidence interval block bootstrap; hasil per fold, liga, market, odds band, versi |

Log score dipilih sebagai primary distribution metric; Brier dan reliability tetap dilaporkan. Literatur evaluasi sepak bola juga mempertanyakan menjadikan RPS satu-satunya kriteria.[^14] Jangan memilih model berdasarkan hit rate saja: win rate 55% pada odds berbeda tidak menyiratkan return yang sama.

**Release gate desain:** jalur matematika dan settlement harus lolos seluruh invariant; perbaikan prediksi harus bertahan pada beberapa outer periods, bukan hanya aggregate; segmen official memerlukan prospective executable quotes dan evidence return net positif dengan uncertainty yang memadai. Sebagai kriteria konservatif, lower 95% block-bootstrap CI net ROI pada evaluasi kebijakan yang telah dibekukan harus di atas nol. Jika tidak tercapai, tetap paper-only—bukan bukti model pasti buruk, melainkan bukti profit belum cukup.

Gate CI tidak menghapus selection bias atau multiple testing. Keluarga liga–market yang dinilai harus dipreregister, hasil negatif ikut dilaporkan, dan selective release dikonfirmasi pada forward period tambahan. Gunakan fixed evaluation horizon atau prosedur sequential yang dipreregister; jangan mengintip setiap hari lalu berhenti tepat ketika CI positif.

Tidak ada angka universal “100/500 pick sudah cukup”. Sebagai ilustrasi kasar binary independen di p≈0.5, interval normal 95% dengan half-width 3 poin persentase memerlukan sekitar 1,068 observasi. Korelasi, seleksi, serta payout Asian membuat kebutuhan aktual berbeda. Precision target dan effective sample harus dilaporkan, bukan menjanjikan profit dari jumlah sampel tertentu.

## 13. Kontrak implementasi dan lima menu

Setiap prediction artifact minimal memuat `fixture_id`, `competition_id`, `season`, `kickoff_utc`, `decision_at`, `training_cutoff`, `formula_version`, `calibration_version`, `policy_version`, `data_version/hash`, `model_segment_status`, lambda, rho, matrix/tail metadata, dan uncertainty diagnostics.

Setiap quote harus menyimpan provider/bookmaker, captured timestamp, market, side, signed line, period, decimal odds, serta status freshness. Setiap kandidat menyimpan kelima payout probabilities, W, L, fair odds, gross/net EV, EV_lower, gate reasons, dan parent prediction/quote ID. Quote entry yang sudah dikunci tidak boleh ditimpa hasil refresh.

Ledger settlement menyimpan contract yang dikunci, stake, aturan settlement, score/status sumber, profit, settled timestamp, dan revision trail. Idempotency memakai bet/contract identity, bukan nama tim. Void atau koreksi skor tidak boleh menggandakan profit.

| Menu | Perilaku yang menjadi kontrak |
|---|---|
| Top Picks | Official-only, satu fixture satu pick; daftar kosong sah; tampilkan alasan dan EV uncertainty |
| Match Prediction | Keempat market dari matriks sama; projection-only dibedakan; AH menampilkan payout probabilities |
| Market Intel | Quote execution dan reference terpisah, no-vig method, timing, line movement, CLV availability |
| Parlay Picks | Off untuk klaim edge peluncuran; nanti official legs, separate ledger, tanpa forced fill |
| Model Detail | Formula/version, lambda/rho, training cutoff, calibration status, sample/validation metrics dan limitations |

AI boleh memberi review penjelasan, agree/disagree/abstain. AI tidak mengubah probabilitas, payout, gate, atau settlement tanpa versi model yang eksplisit dan pengujian terpisah. Missing data ditampilkan, bukan diisi narasi.

## 14. Acceptance tests dan urutan patch

Pemeriksaan numerik spesifikasi telah dilakukan untuk identitas terbatas: pada lambda home 1.5 dan away 1.2, rho -0.2/0/+0.2 memberi P(Over 2.5) sama, sekitar 0.506375509. BTTS Yes berubah sekitar 0.567075125 / 0.542881141 / 0.518687156. Massa matriks 0..30 mendekati satu. Contoh fair odds dan EV pada bagian 8 juga konsisten. Ini **bukan** backtest, unit test suite engine baru, atau verifikasi produksi.

Coding agent harus menambahkan:

1. Invariant matriks: non-negatif, sum≈1, tail tolerance, rho invalid rejected, marginal dan complement konsisten.
2. Golden cases semua signed AH ±0/0.25/0.5/0.75/1.0, totals integer/half/quarter, kedua sisi, semua payout.
3. EV pada fair odds nol; binary reduction; all-push dan zero-win cases.
4. Identitas DC/O-U 2.5, BTTS dependence, kalibrasi identity, dan coherent recomputation semua market.
5. Point-in-time checks untuk hasil, quote, injury/lineup jika nanti ada, serta season/team mapping.
6. Scan failure tidak menjadi “tidak ada match”; stale/missing odds tidak menjadi official; tidak ada shadow promotion.
7. Locked quote immutable, settlement idempotent, revision ledger, pending/void/half results benar.
8. Reproducibility fixture JSON: seed, data hash, model version, ranking tie-break, offline/live inference parity.

Urutan patch yang direkomendasikan setelah persetujuan:

| Phase | Lingkup | Syarat selesai |
|---|---|---|
| 1 | Data contracts, quote provenance, immutable ledger, funnel diagnostics | Data dan settlement dapat diaudit; belum mengubah official formula |
| 2 | Engine matriks DC terregularisasi dan unified payout | Golden/invariant tests lulus; projection/paper-only |
| 3 | Chronological evaluation, uncertainty, calibration challenger | Laporan baseline dan ablation; artifact versioned |
| 4 | Selection policy dan Top Picks/Match Prediction/Market Intel/Model Detail | Tidak ada bypass; API/UI konsisten; paper tracking |
| 5 | Forward confirmation dan staged release per liga–market | Release gates lulus; rollback per versi tersedia |
| 6 | Challenger model, optional market ensemble, staking/parlay evaluation | Incremental benefit terbukti; ledger tetap terpisah |

Parameter hasil training—half-life terpilih, prior/penalty, attack/defence, rho, koefisien kalibrasi—belum memiliki nilai final yang dibuktikan data. Yang final adalah cara mengestimasi, menguji, menyimpan, dan mengizinkan penggunaannya. Parameter kosong tidak boleh diganti angka tebakan lalu diberi label calibrated.

**Rekomendasi akhir:** setujui spesifikasi ini sebagai design freeze kandidat pertama, bukan jaminan hasil taruhan. Mulai dari integritas data dan payout, lanjut model serta pembuktian. Coverage yang lebih baik memberi kesempatan menemukan lebih banyak value; tidak ada formula yang dapat menjamin jumlah pick atau kemenangan harian.

## Sources

Sumber daring diperiksa 12 September 2026. Paper lama menjelaskan metode pada populasi/periode masing-masing, bukan performa pasar saat ini. Catatan repo mengacu pada checkout lokal yang diperiksa, bukan audit ulang deployment production.

[^1]: Dixon, M. J., dan Coles, S. G. (1997). *Modelling Association Football Scores and Inefficiencies in the Football Betting Market*, JRSS C 46(2), 265–280. [Rekam publikasi Lancaster University](https://www.research.lancs.ac.uk/portal/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-football-betting-market%28d16276a2-d6e0-483b-a708-1d29663f1992%29.html). Dasar model skor rendah dan pembobotan waktu; tidak dipakai sebagai bukti ROI masa kini.

[^2]: Baio, G., dan Blangiardo, M. (2010). *Bayesian hierarchical model for the prediction of football results*, Journal of Applied Statistics 37(2), 253–264. [UCL Discovery](https://discovery.ucl.ac.uk/id/eprint/16040/). Hierarchical modelling dan masalah overshrinkage; studi Serie A 1991–92.

[^3]: Boshnakov, G., Kharrat, T., dan McHale, I. G. (2017). *A Bivariate Weibull Count Model for Forecasting Association Football Scores*, International Journal of Forecasting 33(2), 458–466. [University of Manchester](https://research.manchester.ac.uk/en/publications/a-bivariate-weibull-count-model-for-forecasting-association-footb/). Alternatif count distribution dan copula.

[^4]: Football-Data.co.uk. *Historical Football Results and Betting Odds Data*, halaman diperbarui 10 September 2026. [Data dan pemberitahuan kualitas feed](https://football-data.co.uk/data.php). Definisi pre-closing/closing dan peringatan feed Pinnacle sejak 23 Juli 2025.

[^5]: Egidi, L., Pauli, F., dan Torelli, N. (2018, preprint). *Combining historical data and bookmakers' odds in modelling football scores*. [Naskah lengkap arXiv](https://arxiv.org/html/1802.08848v1). Model gabungan historis/odds; tidak menyatakan ensemble proyek ini sudah tervalidasi.

[^6]: scikit-learn developers. *Probability calibration*, stable documentation, diakses 12 September 2026. [Panduan resmi](https://scikit-learn.org/stable/modules/calibration.html). Reliability, proper scores, serta pemisahan data fitting dan calibration.

[^7]: Betfair. *Exchange: What is Asian Handicap Betting?*, diakses 12 September 2026. [Panduan resmi](https://support.betfair.com/app/answers/detail/a_id/6418). Split handicap dan push; aturan operator execution tetap harus diperiksa terpisah.

[^8]: Štrumbelj, E. (2014). *On determining probability forecasts from betting odds*, International Journal of Forecasting 30(4), 934–943. [Artikel penerbit](https://www.sciencedirect.com/science/article/pii/S0169207014000533). Perbandingan transformasi odds dan sumber forecast; DOI 10.1016/j.ijforecast.2014.02.008.

[^9]: Yao, Y., Vehtari, A., Simpson, D., dan Gelman, A. (2017 preprint; 2018 publikasi). *Using stacking to average Bayesian predictive distributions*. [arXiv](https://arxiv.org/abs/1704.02030). Dasar penggabungan predictive distributions, bukan bukti keuntungan betting.

[^10]: Kelly, J. L. Jr. (1956). *A New Interpretation of Information Rate*, Bell System Technical Journal 35, 917–926. [Salinan paper di Scuola Normale Superiore](https://homepage.sns.it/marmi/esameIUE/kelly.pdf). Expected log growth dan asumsi probabilitas.

[^11]: FIDE. *Play-Off and Tie-Break Regulations*, berlaku 1 Maret 2026. [Handbook resmi](https://handbook.fide.com/chapter/TieBreakRegulations032026). Terminologi expected score; bukan validasi penerapan Elo pada football.

[^12]: `risetv2.pdf`, dokumen preparation lokal, 5 halaman, 12 September 2026. Sumber tersedia sebagai [file lokal](C:/Users/seaca/Downloads/risetv2.pdf). Halaman 1–2: prinsip/model; 3: market mapping; 4: EV/Kelly/evaluasi; 5: ringkasan. `CODING_BRIEF.md` yang disebut dokumen tidak tersedia untuk pemeriksaan; tidak diasumsikan isinya.

[^13]: Repo lokal, diperiksa 12 September 2026: [store.ts](E:/MLB-Project/lib/fc/store.ts), [types.ts](E:/MLB-Project/lib/fc/types.ts), [fixture scraper](E:/MLB-Project/scripts/fc-scrape-fixtures.py), [historical normalizer](E:/MLB-Project/betting-machine-fc/scraper_historical.py). Pemeriksaan historis DC: commit `83215fe`, `betting-machine-fc/model.py`; bukan file engine aktif pada rebuild.

[^14]: Wheatcroft, E. (2019, preprint). *Evaluating probabilistic forecasts of football matches: The case against the Ranked Probability Score*. [arXiv](https://arxiv.org/abs/1908.08980). Perbandingan proper scores; tidak membuktikan satu metric cukup untuk keputusan profit.
