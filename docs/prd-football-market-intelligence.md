# PRD — Football Market Intelligence

**Status:** Draft v2.0 — repository-aligned  
**Tanggal:** 6 September 2026  
**Produk:** modul Football di aplikasi `mlb-analytics`  
**UI/BFF:** Next.js 14 App Router, React 18, TypeScript 5, Tailwind CSS 3  
**Calculation service:** FastAPI/Python di `betting-machine-fc`  
**Database target:** PostgreSQL melalui Prisma 5  
**Validation:** Zod di Next.js; Pydantic di FastAPI  
**Testing:** Vitest, pytest, Playwright  
**Waktu:** simpan UTC, tampilkan Asia/Jakarta (WIB)

## 1. Ringkasan

Kita akan menambahkan Football Market Intelligence ke website analytics yang sudah ada. Produk ini mengambil pola kerja publik `@Parlindunganup`, bukan menyalin merek, desain, atau mengklaim mengetahui algoritma internalnya.

Dari delapan post yang dianalisis, workflow-nya adalah:

1. menghasilkan probabilitas 1X2, estimasi gol home/away, total, dan goal difference;
2. membaca opening line serta perubahan Asian Handicap dan Over/Under;
3. membandingkan bookmaker untuk mencari konsensus atau disagreement;
4. menambahkan konteks pertandingan;
5. memilih line yang lebih defensif daripada output mentah model.

Versi kita menambahkan no-vig probability, exact Asian settlement, conservative EV, data-quality gates, snapshot sebelum kickoff, calibration, closing-line value, serta histori lengkap termasuk `NO BET`.

## 2. Arsitektur yang dipakai

Repository saat ini memiliki dua aplikasi yang saling melengkapi:

- root `mlb-analytics`: Next.js, TypeScript, Tailwind, PostgreSQL/Prisma, worker Node, dan UI/API patterns yang sudah stabil;
- `betting-machine-fc`: FastAPI, Python, Dixon-Coles/Poisson, O/U dan AH settlement-aware EV, league router, scraper, SQLite tracker, worker, dan pytest.

Arsitektur target:

```text
Browser
  -> Next.js pages + route handlers
       -> PostgreSQL/Prisma (authoritative state)
       -> FastAPI football engine (calculation only)
       -> external providers (server-side only)

Background jobs
  -> Node worker orchestration
  -> FastAPI calculation endpoints
  -> PostgreSQL snapshots, decisions, results, settlement
```

| Komponen | Tanggung jawab |
|---|---|
| Next.js | halaman, filtering, browser API, formatting WIB, UI states |
| Prisma/PostgreSQL | fixture, observation, odds history, model run, lock, result, settlement |
| FastAPI/Python | lambda, score grid, probability, fair odds, exact AH/O/U EV, calibration |
| Node worker | jadwal refresh, retry, orchestration, health log |
| Provider | fixture, score, team data, multi-book odds |

FastAPI tidak menjadi database kedua. Setelah migrasi, JSON dan SQLite hanya untuk test fixture atau compatibility export.

### Reuse tanpa rewrite

- `betting-machine-fc/model.py`: devig, fair odds, AH/O/U returns, EV, CLV.
- `betting-machine-fc/prediction.py`: Formula `ou-ah-v4.0.0`, market fit, lambdas, coverage.
- `betting-machine-fc/league_profiles.py` dan `strength_rating.py`: rated/shadow/blocked routing.
- `betting-machine-fc/settlement.py`: quarter/integer Asian settlement.
- Tracker `locked/live/overdue/settled` yang sudah ada.
- Prisma patterns `SourceObservation`, `InputSnapshot`, `ModelRun`, `Forecast`, `Settlement` dari domain MLB.

UI lama `static/index.html` dan `static/app.js` tidak menjadi UI production. `bets.db`, `picks.json`, dan `matches_detailed.json` dipertahankan read-only selama migrasi dan parity check.

## 3. Masalah produk saat ini

- UI football terpisah dari website dan design system utama.
- Audit history tersebar di JSON dan SQLite.
- Satu source tidak cukup untuk analisis consensus bookmaker.
- Odds belum disimpan sebagai opening/current/pre-kickoff/closing time series.
- Reference market dan target price belum dipisahkan secara ketat, sehingga edge bisa circular.
- Coverage liga berbeda; hanya `rated` yang layak menjadi official candidate.
- Calibration dan CLV belum menjadi production gate yang terlihat.

## 4. Tujuan dan non-goals

### Tujuan MVP

- Menampilkan slate football dalam WIB di website Next.js sekarang.
- Menyatukan model, market movement, context, dan keputusan dalam Match Detail.
- Menyimpan observation dan keputusan audit-ready di PostgreSQL.
- Menghasilkan `BET`, `WATCH`, `SHADOW`, `NO BET`, atau `UNSUPPORTED` secara deterministik.
- Memisahkan reference consensus dari executable target price.
- Mendukung exact O/U dan AH settlement, termasuk half outcomes dan push.
- Mengukur calibration, CLV, dan flat 1-unit ROI.

### Non-goals MVP

- Tidak memasang taruhan atau mengelola saldo.
- Tidak membuat auto-bet, martingale, atau bankroll management.
- Tidak menjamin profit.
- Parlay bukan rekomendasi utama.
- AI tidak boleh mengubah framework atau melewati hard gate.
- Engine tidak ditulis ulang ke TypeScript.
- Youth, reserve, cup, friendly, dan liga tanpa canonical mapping tidak menjadi official picks.

## 5. Scope market dan liga

### Market MVP

1. Over/Under sebagai market utama.
2. Asian Handicap sebagai market kedua.
3. 1X2 sebagai input/reference dan diagnostic, bukan official pick.
4. BTTS tetap shadow-only sampai live/backtest menggunakan formula dan calibration path yang sama.

### League routing

- `rated/full`: boleh menjadi official candidate setelah seluruh gate lolos;
- `shadow`: terlihat dan tercatat, tetapi bukan official pick;
- `market_only`: diagnostic/watch saja;
- `blocked`: `UNSUPPORTED`.

Router awal tetap memakai `league_profiles.py`. Perubahan status harus versioned dan tidak mengubah model run lama.

## 6. User journey

1. Worker mengambil fixture dalam configured scan window.
2. Adapter menormalisasi competition/team IDs dan menyimpan checksum raw observation.
3. Worker mengambil odds reference dan target jika tersedia.
4. Setiap quote disimpan sebagai immutable snapshot.
5. Next.js meminta proyeksi ke FastAPI dengan input snapshot tervalidasi.
6. FastAPI mengembalikan Formula v4 output, coverage, fair prices, exact EV, dan warnings.
7. Server policy menghasilkan status keputusan.
8. Analyst melihat model-versus-market dan line movement.
9. Eligible decision dikunci sebelum kickoff.
10. Score provider memperbarui fixture.
11. Python settlement menghitung full/half win/loss, push, atau void.
12. Website memperbarui P/L, CLV, Brier/log loss, dan calibration.

## 7. Functional requirements

### FR-1 — Routes dan Market Board

Tambahkan route tanpa mengubah halaman MLB:

```text
/football
/football/matches/[fixtureId]
/football/tracker
/football/calibration
/football/data-health
/football/settings
```

Market Board menampilkan slate date dan kickoff WIB, league/coverage badge, teams, main O/U dan AH, opening/current movement, projected lambdas/total, best candidate, status, reason, dan freshness. Default maksimal satu official candidate per fixture; tidak ada kuota pick wajib.

### FR-2 — Match Detail

Lima panel:

1. Fixture & data quality: source, freshness, mapping, route, warnings.
2. Model: lambda home/away, total, margin, score probabilities, weights.
3. Market: implied/raw, overround, no-vig, fair odds, reference dan target price.
4. Movement: opening sampai latest/closing per bookmaker.
5. Audit: gates, decision, lock snapshot, result, settlement.

Setiap angka membawa `asOf`, source, dan formula version. Missing data bukan nol.

### FR-3 — FastAPI calculation contract

Internal versioned endpoints:

```text
POST /v1/projections
POST /v1/markets/evaluate
POST /v1/settlements/grade
POST /v1/calibration/evaluate
GET  /v1/health
GET  /v1/formulas
```

Request proyeksi minimal memuat fixture ID, league, teams, kickoff UTC, reference 1X2/O/U/AH, target market, dan formula version. Response minimal memuat lambdas, market total/margin, source/weight, coverage/data grade, fair prices, raw/conservative EV, payout distribution, warnings, hard blocks, dan version.

Pydantic menolak payload tidak lengkap dan odds `<= 1.0`. Next.js memvalidasi response FastAPI dengan Zod sebelum menyimpan atau mengirimkannya ke browser.

### FR-4 — Odds snapshots dan movement

Setiap quote menyimpan provider, bookmaker, event ID, market, side, line, decimal price, `observedAt`, optional `providerUpdatedAt`, role `reference|target`, freshness, warnings, dan raw observation ID.

Derived labels:

- `opening`: snapshot valid pertama;
- `current`: snapshot valid terbaru;
- `pre_kickoff`: snapshot valid terakhir sebelum kickoff;
- `closing`: provider-defined close atau snapshot terakhir dalam closing window.

Line dan price movement ditampilkan terpisah. `CONSENSUS` memerlukan minimal tiga bookmaker valid; jika kurang, tampilkan `LIMITED MARKET COVERAGE`.

### FR-5 — Reference versus target

Model boleh memakai no-vig reference consensus sebagai market prior. EV dihitung terhadap target quote berbeda. Jika hanya satu bookmaker tersedia, proyeksi tetap terlihat tetapi diberi `CIRCULAR_PRICE_RISK` dan maksimal berstatus `WATCH`/`SHADOW`.

### FR-6 — Context

Context MVP bersifat manual dan structured: lineup/goalkeeper, absences, rest/congestion, coach change, travel/venue exception, dan notes. Simpan source reference, observed/effective time, author, dan confidence.

Sebelum adjustment rule versioned dan diuji, context hanya boleh menurunkan status menjadi `WATCH`/`NO BET`, bukan menciptakan `BET`.

### FR-7 — Decision policy

- `BET`: full coverage dan semua production gate lolos.
- `WATCH`: sinyal ada, tetapi price/freshness/context/uncertainty belum cukup.
- `SHADOW`: dicatat untuk evaluasi tanpa official recommendation.
- `NO BET`: didukung tetapi tidak ada value atau hard gate gagal.
- `UNSUPPORTED`: league, market, atau data path belum tervalidasi.

```text
EV_raw = exact expected net return pada target line dan price

EV_conservative = EV_calibrated
                  - uncertainty_penalty
                  - stale_price_penalty
                  - data_quality_penalty
                  - settlement_risk_penalty
```

Threshold berasal dari versioned football config. Hard blocks: kickoff lewat, league unsupported, mapping ambiguity, reference incomplete, target stale/missing, inactive formula, invalid engine response, circular single-book price, atau unreliable settlement identity.

### FR-8 — Lock dan audit

Lock menyimpan selection/line/odds, reference dan target snapshot IDs, input/model run IDs, config/formula version, EV, coverage/data grade, reasons/warnings, `lockedAt` UTC, dan slate date WIB.

Lock tidak ditimpa. Perubahan menjadi revision/invalidation event. Satu authoritative official position per fixture menjadi default.

### FR-9 — Tracker dan settlement

Pertahankan bucket:

- `locked`: belum kickoff;
- `live`: kickoff lewat, masih dalam completion buffer;
- `overdue`: belum settled setelah kickoff + 105 menit;
- `settled`: final dan selesai dinilai.

Settlement mendukung full win, half win, push, half loss, full loss, dan void. P/L flat 1 unit. Result hanya final ketika source menyatakan final. Refresh, lock, dan settlement harus idempotent.

### FR-10 — Calibration dan performance

Tampilkan settled/pending count, flat-unit P/L dan ROI, Brier/log loss, calibration bins, CLV, breakdown market/league/line/odds/version/coverage, sample warning, serta kontribusi kemenangan high-odds. Hit rate bukan activation criterion tunggal.

### FR-11 — Data Health

Ikuti pola `/data-health` sekarang. Tampilkan provider health, last success/failure, freshness, mapping conflicts, reference/target coverage, rated/shadow/blocked counts, engine/version health, settlement backlog, worker status, dan next run.

Transport failure harus menjadi explicit failure, bukan `NO BET` atau empty slate.

## 8. Prisma data model

Gunakan model domain football terpisah:

```text
FootballCompetition
FootballTeam
FootballFixture
FootballSourceObservation
FootballOddsSnapshot
FootballContextObservation
FootballInputSnapshot
FootballModelDefinition
FootballModelConfigVersion
FootballModelRun
FootballModelWarning
FootballDecision
FootballDecisionRevision
FootballResult
FootballSettlement
FootballCalibrationRun
FootballWorkerRun
```

Constraint utama:

- fixture identity unique per provider;
- canonical fixture memerlukan home, away, competition, kickoff;
- odds immutable dan indexed by fixture/market/bookmaker/time;
- model run menunjuk exact input/config version;
- official decision unique sesuai fixture/market policy;
- settlement unique per decision;
- semua timestamps UTC; `slateDateWib` boleh menjadi audit field;
- raw payload mengikuti pola JSON string schema sekarang sampai native JSON diputuskan terpisah.

### Migrasi SQLite/JSON

1. Tambahkan Prisma schema secara additive.
2. Buat importer read-only dari `bets.db`, `picks.json`, `matches_detailed.json`.
3. Simpan legacy ID dan source marker.
4. Bandingkan counts, settled P/L, statuses, dan sample rows.
5. Jalankan dual-read untuk verifikasi, bukan dual-write permanen.
6. Setelah parity disetujui, PostgreSQL menjadi source of truth.
7. Backup lama tetap immutable.

## 9. Next.js API routes

Browser hanya berkomunikasi dengan Next.js:

```text
GET  /api/football/slates/[date]
POST /api/football/slates/[date]/refresh
GET  /api/football/fixtures/[fixtureId]
POST /api/football/fixtures/[fixtureId]/analyze
POST /api/football/fixtures/[fixtureId]/lock
GET  /api/football/odds/[fixtureId]
POST /api/football/context
GET  /api/football/tracker
POST /api/football/results/refresh
GET  /api/football/performance
GET  /api/football/calibration
GET  /api/football/data-health
GET  /api/football/settings
POST /api/football/settings
```

Route handlers memakai Zod, Prisma, dan internal FastAPI. Error code eksplisit mencakup `FOOTBALL_ENGINE_UNAVAILABLE`, `ODDS_PROVIDER_NOT_CONFIGURED`, `REFERENCE_MARKET_INCOMPLETE`, `TARGET_PRICE_STALE`, `FIXTURE_MAPPING_CONFLICT`, `LEAGUE_UNSUPPORTED`, dan `RESULT_NOT_FINAL`.

## 10. Worker dan environment

Perluas `scripts/worker.ts` atau buat `scripts/footballWorker.ts`:

```dotenv
FOOTBALL_ENGINE_URL=http://127.0.0.1:8000
FOOTBALL_SCHEDULE_PROVIDER=
FOOTBALL_ODDS_REFERENCE_PROVIDER=
FOOTBALL_ODDS_TARGET_PROVIDER=
FOOTBALL_SCORE_PROVIDER=
FOOTBALL_SCAN_CRON=*/15 * * * *
FOOTBALL_RESULTS_CRON=*/10 * * * *
FOOTBALL_SCAN_WINDOW_HOURS=16
FOOTBALL_CLOSING_WINDOW_MINUTES=5
FOOTBALL_STALE_ODDS_MINUTES=15
```

Credentials server-side. Worker membutuhkan timeout, bounded retry, idempotency key, run log, dan partial-failure reporting.

Adapter unofficial `1xbit` dan scraper Flashscore boleh menjadi development/compatibility source, tetapi harus berlabel unofficial dan bukan multi-book consensus. Provider produksi tetap harus dipilih dan diverifikasi.

## 11. AI policy

Pola AI Picker yang sudah ada dapat dipakai kelak sebagai reviewer opsional. Framework tetap authoritative; AI hanya `AGREE`, `DISAGREE`, atau `ABSTAIN`; AI tidak mengubah probability, EV, line, lock, atau hard gate; failure tampil `AI UNAVAILABLE`. AI bukan bagian MVP pertama.

## 12. UX requirements

- Gunakan Tailwind dan design tokens/custom CSS yang sekarang.
- Desktop table; mobile cards atau accessible horizontal scroll.
- Status memakai teks, bukan warna saja.
- Odds/probability menampilkan source dan timestamp.
- Loading, empty, unavailable, stale, partial, conflict, dan error dibedakan.
- Gunakan utility timezone yang ada untuk WIB; storage tetap UTC.
- Jangan tampilkan `BET` bila belum terkunci atau target quote tidak tersedia.

## 13. Security dan operasional

- Provider keys dan FastAPI secrets tidak masuk browser.
- Settings/context mutation disiapkan untuk future-auth boundary.
- Validasi size dan shape raw payload.
- Jangan log secret/header.
- Gunakan checksum/idempotency untuk ingestion.
- Prisma migration additive dan kompatibel dengan `prisma migrate deploy`.
- Docker boleh menjalankan FastAPI, tetapi JSON volumes bukan persistence production setelah cutover.

## 14. Acceptance criteria MVP

1. `/football` tersedia tanpa merusak route MLB.
2. Slate/kickoff konsisten dalam WIB; database menyimpan UTC.
3. Browser tidak langsung mengakses FastAPI/provider.
4. Semua boundaries memakai Zod/Pydantic.
5. O/U dan AH memakai shared Python score-distribution path.
6. Asian quarter/integer lines lulus full/half win/loss dan push tests.
7. Reference dan target price tersimpan terpisah.
8. Opening/current/pre-kickoff/closing berasal dari immutable snapshots.
9. League routes menghasilkan decision status yang benar.
10. Missing/stale/conflicting data tidak menghasilkan official `BET`.
11. Lock menyimpan input, config, formula, line, price, EV, dan time.
12. Refresh, lock, dan settlement idempotent.
13. Tracker menampilkan locked/live/overdue/settled dan counts.
14. Score disimpan final hanya setelah provider mengonfirmasi final.
15. P/L cocok dengan regression cases pada engine sekarang.
16. Calibration/CLV dapat difilter per market, league, version, coverage.
17. Provider/engine failure terlihat di Data Health.
18. `npm run typecheck`, `npm test`, pytest, build, dan Playwright critical flow lulus.

## 15. Activation gates

MVP dimulai dalam shadow mode. Promotion per market-league memerlukan:

- minimal 300 settled observations yang representatif;
- chronological walk-forward evaluation;
- calibration mengalahkan reference baseline yang disepakati;
- Brier/log loss tidak memburuk pada forward folds;
- median CLV non-negatif pada comparable lines;
- ROI tidak bergantung pada sedikit kemenangan odds tinggi;
- settlement/mapping error di bawah batas operasional;
- reference dan target market coverage mencukupi.

Threshold tidak dipilih dari in-sample ROI.

## 16. Roadmap

### Phase 0 — Contract dan regression baseline

Bekukan tests Formula v4/tracker/settlement, definisikan Pydantic contract, buat Zod mirror, dan versioned error codes.

### Phase 1 — PostgreSQL foundation

Tambahkan Prisma football models/migration, repositories, importer legacy, dan parity report.

### Phase 2 — Engine service extraction

Ekspos pure calculation endpoints, hilangkan DB side effects dari calculation request, pertahankan Python sebagai calculation truth, dan tambahkan integration tests.

### Phase 3 — Read-only website

Bangun Market Board, Match Detail, movement, dan Data Health. Tampilkan `WATCH`, `SHADOW`, `NO BET`, `UNSUPPORTED`; belum ada official `BET`.

### Phase 4 — Lock, tracker, settlement

Implementasikan immutable decision, pindahkan tracker ke Prisma, integrasikan final result dan exact settlement, lalu verifikasi parity.

### Phase 5 — Evaluation dan activation

Bangun Calibration/CLV views, jalankan shadow period, lalu promote market-league satu per satu setelah gates lolos.

### Phase 6 — Optional

Context automation, advisory AI review, BTTS setelah recalibration, dan parlay research terpisah dari main recommendations.

## 17. Risiko

| Risiko | Mitigasi |
|---|---|
| Rewrite formula mengubah hasil | Python tetap calculation source; contract tests |
| Dua database | migrasi ke PostgreSQL; SQLite read-only saat parity |
| Edge circular | pisahkan consensus reference dan executable target |
| Scraper gagal | adapter boundary, explicit health, provider fallback |
| Salah team/league match | canonical IDs, kickoff tolerance, conflict state |
| Stale odds | timestamps, freshness gate, immutable snapshots |
| ROI menyesatkan | flat unit, CLV, calibration, breakdown, warnings |
| Liga kecil overconfident | rated/shadow/blocked router dan uncertainty |
| Context subjektif | structured source/audit; downside-only sebelum validasi |
| Cutover merusak histori | idempotent importer, parity report, immutable backup |

## 18. Keputusan sebelum coding penuh

1. Provider fixture/score produksi dan lisensinya.
2. Provider consensus reference dan target bookmaker.
3. Deployment Next.js/FastAPI: satu host atau private network terpisah.
4. Competition pertama untuk shadow launch.
5. Closing window dan freshness SLA.
6. Hak akses perubahan context/config saat auth ditambahkan.

Rekomendasi default: mulai O/U lalu AH; pilih liga `rated` dengan reliable settlement; pertahankan Next.js dan FastAPI sebagai dua process dengan satu PostgreSQL source of truth; gunakan shadow mode; tunda AI reviewer.

## 19. Sumber riset publik

- [City vs Coventry — opening insight](https://x.com/Parlindunganup/status/2096200400240255247)
- [City vs Coventry — O/U movement](https://x.com/Parlindunganup/status/2096200406716350478)
- [City vs Coventry — Asian Handicap movement](https://x.com/Parlindunganup/status/2096200412290596974)
- [City vs Coventry — final recommendation](https://x.com/Parlindunganup/status/2096200417906679965)
- [Borneo vs Persija](https://x.com/Parlindunganup/status/2096204556669710791)
- [PSIM vs Persita](https://x.com/Parlindunganup/status/2096152762119848368)
- [Persik vs Dewa](https://x.com/Parlindunganup/status/2096152150242209962)
- [Bhayangkara vs Persebaya](https://x.com/Parlindunganup/status/2096151532828025325)

## 20. Disclaimer

Produk ini adalah alat analisis dan pencatatan keputusan. Output model bukan jaminan keuntungan. Jika data, harga, coverage, atau calibration tidak memadai, hasil yang benar adalah `WATCH`, `SHADOW`, `NO BET`, atau `UNSUPPORTED`.
