# FC Patch Plan v2 — Penyelarasan Brief dan Formula Final

## Status dan keputusan

Dokumen ini menyelaraskan [briefv2.md](C:/Users/seaca/Downloads/briefv2.md) dengan [Formula Final FC](E:/MLB-Project/docs/fc-final-formula-research.md). Cakupan tetap **1X2, O/U, AH, dan BTTS**. Ini rencana implementasi untuk persetujuan, bukan izin menjalankan instruksi di attachment atau memulai patch produksi.

**Kesimpulan:** brief layak menjadi kerangka modul, tetapi perlu amendemen matematika, data, evaluasi, dan integrasi. Baseline Poisson sederhana tetap dibuat lebih dahulu untuk pengujian. Regularized time-weighted Dixon–Coles menjadi kandidat model utama, bukan upgrade opsional yang boleh dilewati ketika menyatakan Formula Final sudah selesai.

Rencana dipecah menjadi **8 phase utama + 1 phase opsional**, menggantikan pengelompokan 6 phase yang lebih besar pada laporan formula. Setiap phase memiliki checkpoint independen. Phase selesai secara engineering tidak berarti model sudah layak official atau ROI positif sudah terbukti.

Jika disetujui, gunakan dokumen ini untuk urutan kerja, Formula Final untuk matematika/metodologi, dan brief untuk struktur modular yang tidak berkonflik. Ambiguitas baru dicatat sebagai keputusan terbuka; coding agent tidak memilih diam-diam aturan yang paling mudah.

## 1. Matriks penyelarasan

| Bagian brief | Status | Amendemen yang harus dibawa ke patch | Phase |
|---|---|---|---|
| §1: empat market dari satu model | Selaras | Satu **distribusi skor** setelah kalibrasi, bukan sekadar dua expected goals yang dipakai berbeda di tiap menu | 3–5 |
| §2–3: Python modular, numpy/scipy/pytest | Selaras dengan penyesuaian | Python engine terpisah; Next.js/TypeScript dan adapter FC dipertahankan. Tidak membangun FastAPI kedua tanpa kebutuhan terverifikasi | 1, 7 |
| §4: satu row match memuat semua odds | Belum cukup | Pisahkan fixture, hasil, contract, dan banyak snapshot odds; simpan ID, UTC, provider, line, period, available/captured timestamp | 2 |
| §4: `is_closing` | Belum cukup | Bukan bukti quote tersedia saat entry atau benar-benar fresh. Simpan provenance dan metode penetapan closing; CLV boleh unavailable | 2, 5 |
| §5/8: moment-based dahulu, DC MLE opsional | Selaras untuk urutan awal, konflik untuk target akhir | Moment-based menjadi baseline. DC terregularisasi, shrinkage, time weighting dan validasi wajib tersedia sebelum target desain dinyatakan implemented | 3, 4 |
| §5: `xi=0.0018` | Bukan parameter optimal tervalidasi | Hubungkan `xi=ln(2)/H`; nilai brief setara half-life sekitar 385 hari. Pilih H lewat inner validation, bukan hard-code universal | 4, 5 |
| §5/10: `max_goals=10` cukup | Konflik | Grid adaptif, tail bound awal ≤1e-8, batas resource eksplisit; kegagalan tidak disembunyikan normalisasi | 3 |
| §5/10: normalisasi sesudah tau | Perlu pembatasan | Periksa tau non-negatif dahulu; normalisasi hanya residual truncation terukur. Tidak clip invalid rho | 3, 4 |
| §5: O/U output hanya over/under | Konflik untuk integer/quarter | Kontrak payout FW/HW/P/HL/FL untuk **AH dan O/U**; half-line boleh menyediakan probabilitas binary tambahan | 3 |
| §6: AH quarter split dan fair odds | Selaras | Tambahkan selected-side orientation home/away, zero-W/all-push, period, dan aturan void | 3, 6 |
| §5: `expected_value(p,o)` | Konflik sebagai fungsi umum | Fungsi umum berdasarkan payout: `(o−1)W−L`, lalu biaya. Binary helper hanya untuk market tanpa push | 3 |
| §5: no-vig proportional | Selaras sebagai baseline | Validasi complete outcomes/bookmaker/time/line; bukan lima probabilitas payout Asian. Reference terpisah dari execution | 2, 3, 5 |
| §5/9: fractional Kelly wajib | Konflik dengan launch policy | Launch paper flat-unit. Kelly generalized, bukan binary untuk semua market, dipindah ke phase opsional | 6, 9 |
| §5/9: walk-forward ≥1 liga, ≥3 musim | Selaras sebagai target smoke dataset | Bukan bukti semua liga/market profitable. Nested chronology, point-in-time quotes, holdout terpisah, uncertainty dan coverage wajib | 5 |
| §9: flag bet `EV > threshold` | Belum cukup | Bedakan positive raw EV, paper candidate, dan official-approved. Seleksi utama memakai EV_lower dan gate data/model | 6 |
| §7: enam unit tests | Belum cukup | Tambah property/golden/leakage/settlement/restart/API/UI tests; float comparison memakai tolerance | 1–7 |
| Kalibrasi, uncertainty, versioning | Belum tercakup | Identity baseline, coherent calibration challenger, bootstrap diagnostics, immutable model/policy versions | 4–6 |
| Top Picks, watch/shadow, lima menu | Belum tercakup | Official-only Top Picks, no quota, satu fixture satu official; watch projection-only dan tidak masuk official ROI | 6, 7 |

Referensi metodologi rinci tetap di Formula Final §4–12. Dokumen yang disebut brief sebagai `Riset_Formula_Analisa_Sepakbola.pdf` belum diverifikasi sebagai file yang sama dengan `risetv2.pdf`; jangan mengasumsikan isi bagian yang tidak diberikan. Daftar provider dalam brief adalah pilihan evaluasi, bukan persetujuan berlangganan, memasukkan kredensial, atau menambah dependensi semuanya.

## 2. Penyesuaian spesifikasi fungsi

Nama di bawah merupakan kontrak konseptual yang perlu dibekukan pada Phase 1, bukan perubahan source sekarang:

```text
load_matches(as_of, source) -> standardized historical matches
load_quotes(fixture_id, as_of, source) -> list[OddsSnapshot]
fit_baseline(matches, cutoff, config) -> ModelArtifact
fit_dixon_coles(matches, cutoff, config) -> ModelArtifact + FitDiagnostics
build_score_matrix(params, fixture, tail_tolerance) -> ScoreDistribution + Diagnostics
calibrate_distribution(distribution, calibration_artifact) -> ScoreDistribution
price_contract(distribution, contract, quote, costs) -> PayoutProbabilities + ValueResult
evaluate_policy(candidates, validation_registry, policy) -> Decisions + GateReasons
settle_contract(locked_contract, result, rules) -> SettlementRevision
run_fold(dataset_manifest, fold_config, model_version, policy_version) -> FoldArtifact
```

Semua pricing dan settlement menggunakan definisi contract yang sama. Line disimpan sebagai kelipatan quarter yang tervalidasi, misalnya integer quarter-units, agar tanda dan float rounding tidak merusak split. `probability` tunggal legacy tidak dijadikan sumber perhitungan Asian.

Pemisahan status wajib: `projection_only`, `paper_candidate`, `official_candidate`, `official_locked`, serta alasan `blocked`. Data paper tidak disamarkan menjadi official. `top_pick` hanya presentasi subset official, bukan jalur approval baru.

## 3. Arsitektur dan ruang lingkup repo

Pemeriksaan lokal: HEAD `c6563df`; [store.ts](E:/MLB-Project/lib/fc/store.ts) membaca artifact JSON dan tidak berisi model; [fixture scraper](E:/MLB-Project/scripts/fc-scrape-fixtures.py) schedule-only. [package.json](E:/MLB-Project/package.json) memiliki script typecheck, Vitest, dan Playwright. Keberadaan script bukan bukti test sudah lulus pada turn ini.

Rekomendasi lokasi engine: `betting-machine-fc/football_formula_engine/`, dengan struktur modul brief yang diperluas `evaluation/`, `policy/`, `ledger/`, dan `artifacts/`. Lokasi final ditetapkan setelah memeriksa instruksi repo dan packaging pada Phase 1. Jangan mengembalikan seluruh engine historis secara otomatis.

Alur integrasi:

```text
Snapshot input → Python engine → versioned run artifacts
                              → FC adapter Next.js → lima menu
Locked contracts → settlement ledger → tracker snapshots
```

Database ledger diputuskan pada Phase 1 setelah memeriksa persistence deployment: SQLite hanya jika disk durable, proses writer terkontrol, dan backup tersedia; jika tidak, gunakan storage bersama yang sesuai deployment. Keberadaan Prisma/Postgres pada aplikasi MLB tidak otomatis mengizinkan migrasi skema MLB. Tidak memilih FastAPI atau database baru hanya karena brief menyebutnya opsional.

Worktree awal memiliki `.claude/` yang tidak terkait dan laporan Formula Final yang belum tracked. Pertahankan keduanya; scope staging kelak eksplisit. Tidak ada pull, commit, push, deploy, atau migrasi dalam pekerjaan penyusunan plan ini.

## 4. Pembagian phase

### Phase 1 — Baseline, kontrak, dan jalur pemulihan

**Tujuan:** pekerjaan selanjutnya bisa dilanjutkan tanpa mengandalkan ingatan percakapan.

- 1A: inventaris branch/dirty files, instruksi repo, runtime Python/Node, artifact reader, scheduler dan storage deployment. Rekam baseline test beserta existing failures.
- 1B: bekukan schema v2, status paper/official, signed contract, format error, pilihan persistence, batas proses dan versioning. Buat skeleton package/test harness tanpa mengubah output website.
- 1C: dokumentasikan checkpoint/resume, smoke fixture deterministik, dan konfigurasi engine baru default off. Tetapkan dataset plan serta protokol evaluasi sebelum tuning.

**Output:** schema decision record, baseline report, test harness, checkpoint template. **Gate:** schema Python/TS dapat divalidasi pada fixture contoh; baseline failure terpisah dari regression. **Rollback:** tidak ada switch reader atau migrasi aktif. **Dependensi:** tidak ada.

### Phase 2 — Integritas data dan snapshot odds

**Tujuan:** mencegah formula benar dijalankan dengan match, waktu, atau harga yang salah.

- 2A: fixture/team/league IDs, kickoff UTC dan tampilan WIB, result status, season mapping, as-of filtering. Pisahkan input pertandingan dari quote.
- 2B: normalizer historical menjaga kolom raw/provenance/closing yang tersedia; quote contract menyimpan bookmaker, time, side, line dan period. Missing odds tetap null, tidak diimputasi menjadi harga.
- 2C: bangun persistence append-only snapshot dan audit input, retry terbatas, deduplication, serta coverage funnel. Mulai mengumpulkan forward quotes hanya setelah sumber yang diizinkan dan aksesnya terverifikasi.

**Output:** versioned dataset manifests, snapshot schema/store, coverage report per market/season. **Gate:** replay input sama deterministik; quote masa depan tidak lolos as-of; status transport error berbeda dari empty schedule. **Rollback:** nonaktifkan collector baru; jangan menghapus snapshot. **Dependensi:** 1.

Jika quote BTTS/alternative line belum tersedia, lanjutkan modelling probabilitas dengan status ROI/CLV unavailable. Kekurangan provider tidak perlu menghentikan pekerjaan math offline yang tidak bergantung padanya.

### Phase 3 — Matematika deterministik empat market

**Tujuan:** mengunci kebenaran probabilitas dan payout sebelum fitting kompleks.

- 3A: baseline averages/ratio, independent Poisson, matriks adaptif, tau DC dengan supplied parameters dan validity diagnostics. Fitter DC belum diperlukan di sini.
- 3B: 1X2, BTTS dan payout AH/O-U semua sisi integer/half/quarter. Golden tests tanda home/away, push, half-result, all-push, zero-win.
- 3C: fair odds, EV net, binary no-vig baseline dengan validasi scope; definisi payout digunakan kembali oleh settlement.

**Output:** pure engine library dan CLI offline fixture. **Gate:** sum/complements dalam tolerance, tail bound terpenuhi, tau invalid ditolak, EV fair odds nol, identitas DC/O-U 2.5 lulus. **Rollback:** package belum tersambung website. **Dependensi:** schema 1 dan standardized data 2; synthetic math tests tidak menunggu provider.

### Phase 4 — Fitting model utama dan artifact versioning

**Tujuan:** mengganti rasio baseline dengan kandidat DC yang dapat direproduksi, tanpa mengklaim sudah profitable.

- 4A: log-link attack/defence, league-season/home advantage, identifiability, penalty/shrinkage dan parameter rho valid.
- 4B: time weighting dengan kandidat H terdaftar, neutral/promoted/missing-team handling, fit convergence dan out-of-domain diagnostics.
- 4C: model artifact menyimpan cutoff, data hash, config, seed, fit diagnostics dan parameter; satu fungsi inference untuk live/offline.

**Output:** fitted candidate + baseline artifacts. **Gate:** reproducible fitting pada data beku, tidak ada future-result leakage, invalid model tidak berubah menjadi confident pick. **Rollback:** pilih artifact baseline untuk analisa atau nonaktifkan kandidat; tidak mengubah locked picks. **Dependensi:** 2–3.

### Phase 5 — Evaluasi, kalibrasi, dan uncertainty

**Tujuan:** menilai kandidat dengan prosedur yang dibekukan, bukan mencari konfigurasi dengan ROI historis tertinggi.

- 5A: jalankan smoke chronological fold dan metric checks; lalu dataset satu liga/tiga musim jika tersedia. Pisahkan training, calibration, policy validation dan untouched test.
- 5B: bandingkan baseline, DC, identity calibration dan coherent tilt challenger. Model lebih kompleks tidak otomatis menang. Koefisien tilt boleh tetap nol bila tidak memberi perbaikan.
- 5C: uncertainty refits, ablation dan per-segment reports; job dibagi per fold/league/model/replicate dengan durable checkpoint. Tidak menjalankan satu job tak terputus untuk seluruh eksperimen.

**Output:** prediction/fold artifacts, metric report, candidate validation registry, limitations. **Gate engineering:** evaluasi lengkap dan dapat di-resume, seluruh kegagalan eksplisit, tidak ada leakage. **Gate kualitas:** terpisah; hasil buruk tetap hasil evaluasi yang sah dan tidak menghambat penyelesaian engineering. **Rollback:** registry kandidat tidak approved; artifact tersimpan untuk audit. **Dependensi:** 2–4.

ROI/CLV tanpa entry quotes bukan nol, melainkan `NOT_EVALUABLE`. Segment approval tidak diwariskan dari satu liga atau O/U 2.5 ke semua market. Kalibrasi dan model complexity harus dipilih pada inner periods; hasil final test tidak dipakai tuning ulang.

### Phase 6 — Selection policy, paper ledger, dan settlement

**Tujuan:** menghasilkan keputusan terstruktur dan catatan return yang benar tanpa memublikasikan sinyal belum terbukti.

- 6A: evaluasi semua sisi yang tersedia; hitung EV_lower, gate data/model/uncertainty; satu fixture satu kandidat terpilih, no quota, watch tidak menjadi official. Simulasi kebijakan memakai fungsi yang sama dengan pipeline nanti.
- 6B: paper flat-unit, immutable quote lock, settlement idempotent dan revision trail; pending/void/half-results punya denominator dan profit konsisten.
- 6C: simulasikan restart/double submit/result correction; tracker memisahkan paper, legacy dan versi baru. Status legacy tidak dipetakan menjadi model-approved.

**Output:** policy version, ledger, tracker artifact, rejection diagnostics. **Gate:** replay tidak menggandakan pick/profit; missing uncertainty tidak menjadi nol; `official_enabled=false` untuk versi baru. **Rollback:** stop generation; ledger dan settlement existing contracts tetap dipertahankan. **Dependensi:** 3, 5 dan storage keputusan 1–2.

### Phase 7 — Integrasi website dan lima menu

**Tujuan:** menyambungkan engine ke aplikasi yang ada tanpa big-bang replacement.

- 7A: schema validator dan adapter artifact v2 di server; contract tests Python JSON → TypeScript. Legacy reader tetap tersedia selama rollout tanpa mencampur cohort ROI.
- 7B: Match Prediction dan Model Detail menampilkan projection/paper, payout Asian, cutoff/version serta missing-data diagnostics.
- 7C: Top Picks official-only dan Market Intel dengan quote/reference terpisah; Parlay Picks mempertahankan history tetapi tidak memakai kandidat baru yang belum approved. Tidak ada forced fill atau klaim ROI parlay dari singles.

**Output:** API/UI integration di balik feature flag. **Gate:** focused Python tests, TS typecheck, Vitest FC, production build dan Playwright flow yang relevan; regression MLB diperiksa tanpa mengubah formulanya. Network/credential-blocked checks dicatat `not-run`, bukan pass. **Rollback:** switch adapter ke snapshot/version yang kompatibel; jangan mengganti file satu per satu. **Dependensi:** 6; UI fixtures dapat disiapkan setelah schema 1 dibekukan.

### Phase 8 — Forward confirmation dan rilis bertahap

**Tujuan:** memisahkan aplikasi yang bekerja dari model yang layak diberi label official.

- 8A: jalankan dry-run/replay deployment, uji graceful stop, recover state, stale snapshot, concurrent run dan rollback. Pastikan observability dan operator runbook tersedia.
- 8B: kumpulkan paper outcomes pada horizon yang dipreregister. Laporkan coverage, calibration, payout ROI/CI, CLV availability dan drawdown per segmen.
- 8C: setelah gate Formula Final §12 terpenuhi dan ada persetujuan aktivasi, enable segmen liga–market terpilih. Segmen lain tetap paper-only; rilis tidak harus serentak empat market.

**Output:** release readiness report dan allowlist versioned. **Gate:** readiness operasional + evidence statistik + persetujuan rilis, bukan sekadar semua unit test hijau. **Rollback:** disable new official generation, pin model/data schema compatible, tetap settle kontrak yang telah terkunci. **Dependensi:** 7 dan forward evidence.

Phase ini tidak dijanjikan selesai dalam satu sesi atau beberapa hari: pengumpulan outcome bergantung kalender dan precision. Agent menyerahkan checkpoint `AWAITING_FORWARD_EVIDENCE` lalu berhenti dengan aman; tidak menunggu tanpa batas atau membuat monitoring otomatis tanpa permintaan.

### Phase 9 — Opsional setelah singles terbukti

Challenger distribution, market-informed ensemble, Elo/xG/lineup, generalized fractional Kelly, dan parlay dianalisa satu eksperimen per checkpoint. Tidak dibundel dengan initial release. Setiap modul memerlukan incremental OOS evidence dan persetujuan scope/data/cost bila berubah. Menunda Phase 9 tidak membuat engine empat market pada Phase 1–8 tidak lengkap.

## 5. Protokol anti-interupsi

Tidak ada rencana yang menjamin proses tidak terputus. Targetnya: **interupsi tidak merusak data, tidak memublikasikan output parsial, dan tidak memaksa pekerjaan diulang dari awal**.

### Batas pekerjaan dan checkpoint

- Jalankan satu subphase A/B/C per batch kerja; setelah lulus gate, laporkan diff, test, limitation dan next action sebelum batch berikutnya.
- Simpan status lokal yang direncanakan pada `docs/fc-patch-progress.md`: phase/subphase, `not_started/in_progress/verified/blocked`, commit/working diff, file terkait, schema/model version, perintah verifikasi, hasil dan langkah resume.
- Simpan metadata job numerik di run manifest, bukan hanya percakapan. Minimal: input/config/code hashes, seed, fold/replicate IDs, completed units, failure reasons, timestamps dan output hashes.
- Resume hanya bila fingerprint kompatibel. Input/config/code berubah → run baru, bukan mencampur partial outputs lama.
- Commit checkpoint hanya jika diminta/disetujui. Tanpa commit tetap ada progress manifest dan scoped working diff. Push/deploy bukan otomatis bagian “phase selesai”.

### Atomic publish dan penyimpanan

- Tulis satu run ke direktori versioned staging; validasi kelengkapan dan checksum sebelum menandainya complete.
- Publikasikan dengan satu manifest/pointer yang diganti secara atomic di filesystem yang sama. Reader mem-pin run ID sekali per request agar picks, matches dan tracker tidak berasal dari run berbeda.
- Pada Windows, tutup file handles sebelum replace; gunakan bounded retry untuk transient sharing locks. Pertahankan last-known-good pointer jika publish gagal.
- Atomic replace bukan pengganti durability: flush/transaction dan backup disesuaikan storage. Integrasi filesystem/DB diuji dalam environment deployment nyata.
- Ledger transactional, snapshot immutable, migrations additive dahulu. Jangan drop kolom/data lama saat reader masih membutuhkan schema tersebut.

### Pekerjaan panjang dan recovery

- Training/backtest dipecah per fold/segmen/refit; tentukan timeout dan resource budget sebelum full run. Smoke sample dahulu, baru skala bertahap.
- Satu writer/publisher aktif dengan lock berisi owner/run ID dan kebijakan stale-lock yang memverifikasi proses. Jangan menghapus lock hanya karena usianya lama.
- Retry terbatas untuk transport/transient error; data invalid dikarantina dengan alasan, tidak di-retry tanpa batas.
- Tes wajib: kill sebelum publish, setelah sebagian fold selesai, duplicate settlement, corrupt snapshot, serta restart worker. Outcome harus tetap konsisten atau kembali ke snapshot terakhir yang valid.
- Jangan menghapus run lama/ledger sebagai langkah otomatis resume. Retention/cleanup material memerlukan target dan kebijakan terpisah.

### Format handoff tiap subphase

```text
Phase/subphase:
Status engineering:
Status model approval:
Base commit + scoped changed files:
Input/schema/model/policy hashes:
Completed outputs:
Tests: command, result, not-run reason:
Known failures/blockers:
Last complete run/fold/replicate:
Resume command + working directory:
Rollback action:
Next bounded task:
```

Dokumen plan ini tidak mengklaim manifest/job/checkpoint machinery tersebut sudah diimplementasikan.

## 6. Definition of Done gabungan

**Engineering complete:** input fixture yang tidak ambigu + as-of menghasilkan empat market dari satu distribution; signed lines dan payout benar; source quote/version tersimpan; CLI, adapter, ledger dan resume path teruji; seluruh menu jujur membedakan missing/projection/paper/official.

**Evaluation complete:** reproducible chronological reports tersedia dengan baseline, uncertainty, limitations dan status per segmen. Hasil ROI negatif tetap dilaporkan. Minimal tiga musim menjadi target coverage evaluasi, bukan alasan menciptakan odds BTTS yang tidak tersedia.

**Official release eligible:** gate kualitas Formula Final dan forward confirmation terpenuhi untuk segmen tertentu, operasional siap dan aktivasi disetujui. `AWAITING_DATA` atau `AWAITING_EVIDENCE` tidak diubah menjadi pass supaya checklist selesai.

**Out of scope awal:** real-money auto-staking, subscription provider baru, AI overriding formula, memaksa volume pick, merombak MLB, dan deployment tanpa persetujuan.

## 7. Langkah berikutnya

Setelah rencana disetujui, mulai **Phase 1A saja**: baseline dan pemetaan kontrak/persistence. Jangan langsung mengerjakan seluruh engine. Phase berikutnya bergerak setelah checkpoint sebelumnya dapat diverifikasi dan dilanjutkan oleh agent lain tanpa menebak konteks.
