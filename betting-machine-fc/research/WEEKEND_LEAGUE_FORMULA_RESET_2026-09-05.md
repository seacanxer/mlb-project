# Reset Formula O/U & AH per Liga/Kasta

**FC Betting Machine — keputusan riset, 5 September 2026 (WIB)**
Scope: England, Germany, Scotland, Norway, Iceland, Poland, Spain, Sweden
Status: desain siap diimplementasikan; **belum mengubah formula produksi**

## Keputusan utama

Kita perlu mereset arsitektur prediksi, bukan menghapus histori atau database.

Formula baru sebaiknya memakai **satu mesin skor inti yang hierarkis dan dinamis**, lalu mempelajari parameter berbeda untuk setiap negara, kasta, grup regional, fase kompetisi, dan market. Jadi bukan tujuh rumus hardcode seperti `Iceland = Over` atau `Spain = Under`.

Alasannya jelas dari data:

- Bundesliga dan 2. Bundesliga memang konsisten tinggi gol, tetapi strategi blind Over tetap rugi setelah margin bookmaker.
- Spain Segunda rendah secara historis, tetapi bergerak dari 2.02 ke 2.53 gol/match dalam tiga musim—rata-rata statis mudah terlambat membaca perubahan.
- Sweden Ettan North dan South, walaupun satu kasta, memiliki profil sangat berbeda.
- Scottish Premiership, Championship, League One, dan League Two tidak bisa memakai baseline atau home advantage yang sama.
- Iceland sangat tinggi gol, tetapi harga utamanya sering berada di 3.0–3.5. Tinggi gol tidak sama dengan harga Over yang murah.

Literatur terbaru juga menunjukkan bahwa model terbaik dapat berbeda menurut liga dan periode: pada evaluasi Bundesliga, EPL, dan La Liga, model dinamis berbobot mengungguli versi statis, tetapi keluarga distribusi terbaik tidak selalu sama. [Bayesian weighted dynamic football models, 2026](https://academic.oup.com/jrsssc/advance-article/doi/10.1093/jrsssc/qlag032/8704597). Fondasi attack/defence dinamis berasal dari [Dixon–Coles](https://rss.onlinelibrary.wiley.com/doi/pdf/10.1111/1467-9876.00065) dan pengembangan [dynamic bivariate Poisson](https://academic.oup.com/jrsssa/article-abstract/178/1/167/7058470).

## Masalah nyata pada engine sekarang

Slate WIB yang tersimpan untuk 5 September berisi **346 pertandingan dari 188 label liga**, tetapi hanya **14 pertandingan (4.0%)** yang dikenali oleh model strength.

| Negara | Match di slate | Ter-cover strength | Label liga berbeda |
|---|---:|---:|---:|
| Germany | 20 | 1 | 8 |
| Scotland | 2 | 0 | 2 |
| Norway | 4 | 0 | 2 |
| Iceland | 2 | 0 | 1 |
| Poland | 7 | 0 | 5 |
| Spain | 5 | 2 | 5 |
| Sweden | 14 | 0 | 8 |
| England | 16 | 2 | 7 |

Scanner sebenarnya sudah luas. Yang belum ada adalah **router kualitas**: pertandingan tak dikenal masih bisa masuk proses seolah-olah model memiliki pengetahuan liga dan tim yang cukup.

Ada tiga cacat formula yang harus dibereskan lebih dulu:

1. Lambda live dibentuk dari odds 1X2. Total yang dihitung dari market O/U hanya ditampilkan, tidak dipakai untuk memilih O/U.
2. Formula strength salah skala sehingga rating netral tidak mengembalikan rata-rata gol liga. Ini dapat menekan projected total secara material dan menciptakan Under palsu.
3. Ranking sekarang lebih berat ke raw probability, padahal yang dibutuhkan adalah probabilitas terkalibrasi dan **expected payout** pada line yang benar.

## Formula inti yang direkomendasikan

### 1. Historical scoring model

```text
log(lambda_home_hist) = mu[country, tier, group, season, phase, t]
                        + home_adv[country, tier, t]
                        + attack[home, t]
                        + defence_weakness[away, t]
                        + beta_league * context

log(lambda_away_hist) = mu[country, tier, group, season, phase, t]
                        + attack[away, t]
                        + defence_weakness[home, t]
                        + beta_league * context
```

Parameter ditarik secara bertingkat:

```text
global -> country -> tier/group -> team
```

Dengan partial pooling, liga kecil tetap bisa belajar dari kelompok yang mirip tanpa dianggap identik. Tim promosi membawa prior dari kasta sebelumnya melalui transition offset yang dipelajari, dengan uncertainty lebih besar pada awal musim.

`context` hanya boleh berisi data yang tersedia sebelum kickoff dan lolos validasi, misalnya lineup/goalkeeper, rest termasuk pertandingan cup, suspensi, travel, serta xG/shot-quality. Nama liga atau narasi “sering hujan gol” tidak menjadi pick otomatis.

### 2. Fit market yang benar-benar dimainkan

Dari harga no-vig:

```text
T_market = expected total yang membuat payout O/U main line seimbang
M_market = expected goal margin yang membuat payout AH main line seimbang
```

Lalu gabungkan dengan model historis memakai bobot berbasis precision/uncertainty yang dipelajari:

```text
log(T_final) = wT[league, line, coverage] * log(T_hist)
               + (1-wT) * log(T_market)

M_final = wM[league, line, coverage] * M_hist
          + (1-wM) * M_market

lambda_home = (T_final + M_final) / 2
lambda_away = (T_final - M_final) / 2
```

Bobot 40% global dihapus. Bundesliga, Iceland Besta, Spain Segunda, dan Scotland League Two tidak boleh memiliki bobot market/history yang sama.

Reference market dan target price harus dipisahkan. Bila harga bookmaker yang sama dipakai untuk membentuk probabilitas sekaligus mengklaim edge terhadap harga itu, hasilnya circular. Riset memang mendukung penggabungan histori dan bookmaker odds, tetapi sebagai sumber informasi yang berbeda. [Egidi–Pauli–Torelli](https://arxiv.org/abs/1802.08848).

### 3. Satu score distribution untuk O/U dan AH

Mulai dari dynamic bivariate Poisson/Dixon-Coles, lalu uji negative binomial atau Poisson-mixture hanya pada liga yang menunjukkan tail/dispersion bermasalah. Jangan menetapkan satu `rho` global.

- Germany Bundesliga 1/2: historical prior kuat; uji Skellam/NB untuk margin AH.
- Spain dan liga dengan banyak low-score: estimasi low-score dependence per pool.
- OBOS, Ettan North, Iceland: uji overdispersion dan phase/regime state.
- Liga kecil: parameter distribution di-shrink ke country/tier family sampai sampel cukup.

### 4. Hitung Asian settlement secara utuh

```text
EV_OU = sum_score P(score) * net_return_OU(score, line, side, odds)
EV_AH = sum_score P(score) * net_return_AH(score, line, side, odds)
```

Quarter line dipecah ke dua adjacent lines; integer line mempertahankan push; outcome harus membedakan full win, half win, push, half loss, dan full loss. Studi UCD menunjukkan struktur refund mengubah expected loss dan tidak boleh direduksi menjadi win probability biner. [Hegarty–Whelan](https://www.ucd.ie/economics/t4media/WP23_13.pdf).

### 5. Calibration dan conservative edge

Model dipilih berdasarkan chronological walk-forward calibration, bukan hit rate tertinggi. Untuk betting, kualitas probabilitas lebih penting daripada accuracy klasifikasi. [Walsh–Joshi](https://arxiv.org/abs/2303.06021).

```text
EV_conservative = EV_calibrated
                  - uncertainty_penalty
                  - stale_price_penalty
                  - data_quality_penalty
                  - settlement_risk_penalty
```

Threshold tidak di-hardcode dari sekarang. Nilainya dipilih dari forward folds dan dipisahkan menurut market, liga/kasta, serta keluarga line.

## Playbook per liga dan kasta

Angka berikut berasal dari hasil match-level yang direkonstruksi. Ini adalah **prior lingkungan**, bukan rekomendasi blind bet.

### England

| Kasta | Match | GPG | O2.5 | Approach |
|---|---:|---:|---:|---|
| Premier League | 1,140 | 3.022 | 58.0% | Higher-total prior; full dynamic model, market weight tinggi |
| Championship | 1,654 | 2.521 | 46.9% | Neutral/Under-leaning; schedule congestion dan squad rotation penting |
| League One | 1,653 | 2.577 | 48.9% | Separate calibration; jangan ikut baseline EPL |
| League Two | 1,652 | 2.607 | 47.7% | Lebih volatile; uncertainty lebih lebar |
| National League | 1,284 | 2.840 | 52.8% | Scan luas, tetapi coverage/settlement gate lebih keras |

Blind Over 2.5 rugi di kelima kasta pada sample ini. Volume pertandingan England pada weekend adalah keuntungan untuk seleksi, bukan alasan menurunkan threshold.

### Germany

| Kasta | Season evidence | GPG | O2.5 | Approach |
|---|---|---:|---:|---|
| Bundesliga | 3 musim, 918 match | 3.175 | 60.9% | High-total prior stabil; history lebih kuat, HA tetap dinamis |
| 2. Bundesliga | 3 musim, 918 | 3.021 | 59.4% | High-total prior; model tersendiri dari D1 |
| 3. Liga | 2023/24–2024/25, 760 | 2.854 | 54.1% | Moderate, bukan otomatis Over; staged shadow |
| Regionalliga | 5 grup resmi | belum tervalidasi | — | Model per grup; jangan digabung sebagai satu liga |
| Oberliga | banyak grup regional | belum tervalidasi | — | Scan boleh, Official diblokir sampai ID/odds/settlement lengkap |

DFB mengonfirmasi Regionalliga terdiri dari lima grup dengan jalur promosi berbeda, sehingga label `Germany Regionalliga` terlalu kasar untuk model. [DFB](https://www.dfb.de/news/detail/aufstieg-von-regionalliga-zur-3-liga-fragen-und-antworten-208044).

### Scotland

| Kasta | Match | GPG | O2.5 | Home margin | Approach |
|---|---:|---:|---:|---:|---|
| Premiership | 656 | 2.886 | 56.6% | 0.389 | Pisahkan pre/post split; team imbalance besar |
| Championship | 519 | 2.713 | 52.0% | 0.224 | Current-season state lebih berat |
| League One | 524 | 2.964 | 57.3% | 0.128 | Volatile; shrinkage kuat, jangan blanket Over |
| League Two | 529 | 2.641 | 48.8% | 0.312 | Kasta berbeda nyata; data-quality gate keras |

Premiership memainkan 33 round sebelum split, kemudian top-six/bottom-six. Ini mengubah opponent mix dan home/away balance sehingga phase harus menjadi bagian model. [SPFL](https://spfl.co.uk/news/202526-post-split-fixtures-qa).

### Norway

| Kasta | GPG by season | Approach |
|---|---|---|
| Eliteserien | 3.117 / 2.838 / 3.175 | High but regime-sensitive; update season intercept weekly |
| OBOS | 2.779 / 3.192 / 3.196 | Deteksi change-point 2024; long-run mean tidak cukup |
| 2. divisjon | 2 grup resmi | Pool per grup, lalu shrink ke Norway family |
| 3. divisjon | 6 grup resmi | Shadow-only sampai tiga musim + odds/settlement terverifikasi |

NFF memang memisahkan Eliteserien, OBOS, dua grup 2.divisjon, dan enam grup 3.divisjon. [NFF competition documents](https://www.fotball.no/lov-og-reglement/ligaverktoykasse/). Artificial turf × home familiarity layak diuji untuk **AH/home advantage**, tetapi belum ada dasar untuk menjadikannya boost Over.

### Iceland

| Kasta | GPG by season | O2.5 | Approach |
|---|---|---:|---|
| Besta deild | 3.457 / 3.556 / 3.321 | 64–67% pada 2023–24 | Goal-rich; price lines 3.0–3.5 secara exact, phase-specific |
| 1. deild | indikasi 3.2–3.6 | data konflik | Shadow-only; rebuild dari KSI match IDs |
| 2./3. deild | belum tervalidasi | — | Scan/observe, bukan Official |

Besta split setelah 22 round menjadi championship/relegation groups, jadi regular dan split phase tidak boleh dicampur. [KSÍ report](https://www.ksi.is/api/download/media/yx1hkirx/sky-rsla-starfsho-ps-ksi-2026.pdf). Iceland adalah prior Over terkuat dalam riset ini, tetapi juga liga yang paling mudah memberi false confidence bila line bookmaker sudah 3.25/3.5.

### Poland

| Kasta | Evidence | GPG | O2.5 | Approach |
|---|---|---:|---:|---|
| Ekstraklasa | 2023/24–2025/26 | sekitar 2.73 | sekitar 50% | Stable neutral-total; HA cukup kuat, cocok untuk AH research |
| I Liga | satu file belum penuh | 2.664 | 52.3% | Shadow sampai multi-season feed lengkap |
| II/Liga 3/4 | sumber konflik | — | Diblokir dari Official |

Laporan resmi 2025/26 mencatat 837 gol dari 306 match atau 2.74 GPG, konsisten dengan baseline netral—bukan liga blanket Under. [Ekstraklasa](https://ekstraklasa.org/en/news/the-most-insane-season-in-years-summary/).

### Spain

| Kasta | Match | GPG | O2.5 | Approach |
|---|---:|---:|---:|---|
| La Liga | 1,140 | 2.592 | 47.5% | Lower-total prior; dynamic DC/low-score calibration |
| Segunda | 1,386 | 2.266 | 40.1% | Strong Under prior, tetapi regime berubah cepat |
| Primera Federación | 2 grup × 20 tim | belum tervalidasi | — | Model/group IDs terpisah, shadow |
| Segunda/Tercera Federación | banyak grup | belum tervalidasi | — | Diblokir sampai coverage dan settlement lengkap |

Segunda bergerak dari **2.017 ke 2.530 GPG** pada 2022/23–2024/25. Jadi historical Under tetap berguna, tetapi wajib memiliki season trend/change-point. RFEF sendiri membedakan kompetisi profesional dan federated lower tiers; Primera Federación dibagi dua grup. [RFEF](https://rfef.es/es/federacion/bases-de-competicion-202526), [group structure](https://rfef.es/es/noticias/aprobados-los-grupos-de-primera-federacion-para-la-temporada-202526).

### Sweden

| Kasta/grup | Match | GPG | O2.5 | Approach |
|---|---:|---:|---:|---|
| Allsvenskan | 720 | 2.817 | 54.0% | Moderate-high, stabil; selective Over/AH |
| Superettan | 720 | 2.768 | 54.7% | Season volatile; stronger current-season state |
| Ettan North | 623 | 3.169 | 62.9% | High-total candidate; test overdispersion |
| Ettan South | 624 | 2.800 | 54.8% | Jangan mewarisi prior North |
| Div 2/3/4 | banyak grup regional | — | Shadow-only sampai canonical IDs lengkap |

SvFF memelihara komposisi terpisah untuk Allsvenskan, Superettan, Ettan, dan grup regional. [SvFF competition documents](https://www.svenskfotboll.se/serier-cuper/tavlingsdokument/).

## Bagaimana memproses weekend slate besar

Weekend adalah persoalan **throughput dan selection**, bukan bonus probabilitas. Pada sample tiga musim, perbedaan GPG weekend vs weekday tidak konsisten: Bundesliga 3.173 vs 3.192; Spain Segunda 2.266 vs 2.265; Eliteserien 3.019 vs 3.097; Allsvenskan 2.765 vs 2.950. Jadwal weekday juga terpengaruh postponement, cup, dan TV selection.

Kebijakan yang direkomendasikan:

1. Kelompokkan tampilan slate berdasarkan tanggal **Asia/Jakarta/WIB**.
2. Untuk feature `weekday`, `season phase`, dan kickoff environment, gunakan tanggal/waktu lokal venue—bukan WIB.
3. Scan semua senior fixture yang memiliki canonical competition ID.
4. Precompute rating sekali per liga/season, batch fetch odds, dan cache score grid; jangan fit ulang seluruh liga untuk setiap match.
5. Routing berurutan: `SUPPORTED -> SHADOW -> BLOCKED`, bukan fallback diam-diam.
6. Youth, reserve, cup dengan rotation tak terukur, dan regional league tanpa feed lengkap tidak masuk Official ROI.

## Official Picks dan Top Picks

Official Picks boleh banyak; Top Picks adalah sinyal kualitas, bukan sekadar lima probability terbesar.

### Official Pick

Harus lolos:

- canonical competition/team IDs dan senior/men format benar;
- odds dua sisi, line, timestamp, dan reference source lengkap;
- historical/market fit valid;
- model league/line sudah lulus walk-forward calibration;
- `EV_conservative > 0` setelah semua penalty;
- settlement mapping terverifikasi;
- maksimum satu posisi Official per fixture agar tidak menggandakan exposure korelatif.

### Top Pick

Ambil maksimal **5** dari Official Picks dan wajib memenuhi level tambahan:

- data-quality Grade A;
- edge bertahan di beberapa forward folds, bukan satu musim/liga saja;
- calibration slope/intercept sehat di league/line family;
- reference price fresh dan tidak circular;
- tidak terkonsentrasi pada satu liga, tim, atau outcome yang sama;
- rank berdasarkan lower confidence bound EV, lalu CLV stability dan settlement reliability.

State UI yang disarankan:

```text
TOP PICK | OFFICIAL | WATCHLIST | SHADOW | NO BET / UNSUPPORTED
```

Dengan ini kita bisa tetap agresif dalam coverage tanpa agresif dalam menyatakan kepastian.

## Urutan implementasi

### Phase 0 — correctness sebelum model baru

1. Perbaiki scale `strength_lam()` sehingga tim netral mengembalikan league baseline.
2. O/U memakai total yang benar-benar di-fit dari Asian O/U main line.
3. AH memakai expected margin dari kedua harga AH, bukan side probability 1X2.
4. Satukan fungsi live scan, backtest, lock, dan settlement agar satu formula version menghasilkan angka identik.
5. Unsupported league menjadi eksplisit; tidak boleh menghasilkan Official Pick melalui fallback.

### Phase 1 — canonical league registry

Tambahkan `competition_id`, country, tier, group, phase, season convention, gender/age, local timezone, data grade, odds coverage, dan settlement coverage. Normalisasi 188 label provider ke registry ini.

### Phase 2 — hierarchical model dan market anchor

Implementasikan shared core, league/tier parameters, promoted-team transition, dynamic season state, exact Asian payout, dan market/reference separation. Kandidat distribution dibandingkan secara chronological per league family.

### Phase 3 — shadow backtest

Jalankan minimum beberapa forward folds dan breakdown per:

- league, tier, group, season phase;
- O/U versus AH dan exact line family;
- odds band, data grade, formula version;
- full/half win, push, half/full loss;
- calibration intercept/slope, Brier/log loss/RPS;
- flat 1-unit ROI, CLV, drawdown, dan sample concentration.

Tidak ada promotion ke Official bila keuntungan hanya berasal dari beberapa longshot atau satu fold.

### Phase 4 — staged production

Urutan awal yang paling defensible:

1. Bundesliga 1/2, La Liga, Segunda, England E0–E3 setelah correctness fix.
2. Allsvenskan, Eliteserien, Ekstraklasa, Scottish Premiership setelah reference-price dan settlement audit.
3. OBOS, Superettan, Germany 3.Liga, Ettan groups, Iceland Besta setelah shadow calibration.
4. Regionalliga/Oberliga, Iceland/Poland/Spain regional lower tiers tetap blocked sampai data lengkap.

## Kesimpulan

Target kita bukan “lebih banyak Over dari liga hujan gol.” Targetnya adalah menemukan kapan **projected total atau margin kita berbeda secara terkalibrasi dari reference market**, dan seberapa yakin perbedaan itu bertahan setelah uncertainty serta margin bookmaker.

Reset ini tetap agresif karena seluruh fixture senior dapat discan dan jumlah Official tidak dipaksa kecil. Namun hanya lima Top Picks yang membawa sinyal terkuat. Itu memberi breadth yang user inginkan tanpa mengulang masalah sekarang: coverage palsu, probability terlalu percaya diri, dan ROI yang rusak oleh pick dari liga yang belum benar-benar dimodelkan.

### Data sources dan keterbatasan

Perhitungan memakai [Club Football Match Data](https://github.com/xgabora/Club-Football-Match-Data-2000-2025), [Swedish Football Dataset](https://github.com/Mongosaurusrex/swedish-football-dataset), [OpenFootball Europe](https://github.com/openfootball/europe), dan [OpenFootball Germany](https://github.com/openfootball/deutschland). Beberapa lower-tier source tidak memiliki closing O/U/AH historis atau mencampur regular season, playoff, serta administrative results. Karena itu angka lower-tier tersebut dipakai untuk menentukan arah riset dan status shadow—bukan untuk mengklaim betting edge.

Tidak ada formula yang menjamin profit. Formula ini dirancang untuk memperbaiki correctness, calibration, selection quality, dan kejujuran uncertainty sebelum ROI dinilai kembali.
