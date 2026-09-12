# FC Phase 1A — Today's Pick baseline

## Checkpoint

Scope: subphase 1A dari [Patch Plan v2](E:/MLB-Project/docs/fc-patch-phase-plan-v2.md). Pemeriksaan lokal pada 12 September 2026, branch `codex/rebuild-patch`, HEAD `c6563df`. Belum ada perubahan runtime, UI, formula, schema/database, snapshot, atau aktivasi official. Pemeriksaan ini bukan audit deployment live.

Phase 1A selesai sebagai inventaris dan baseline lokal. Phase 1 secara keseluruhan **belum selesai**: schema v2/test harness (1B) dan konfigurasi/default-off/smoke-resume (1C) belum dibangun. Formula Final saat ini spesifikasi desain, bukan engine terlatih yang siap menghasilkan pick.

## Jalur aktual Today's Pick

```text
NavBar: Today's Pick → /fc → redirect /fc/schedule
Schedule → /api/fc/matches → matches_detailed.json
Scrape jadwal → POST /api/fc/scan → python3 fc-scrape-fixtures.py
                                      → fixture-only JSON

/api/fc/picks → readPicks() → picks.json (tidak tersedia lokal)
```

Sumber: [NavBar](E:/MLB-Project/components/NavBar.tsx:19), [entry route](E:/MLB-Project/app/fc/page.tsx:1), [schedule page](E:/MLB-Project/app/fc/schedule/page.tsx:1), [scan route](E:/MLB-Project/app/api/fc/scan/route.ts:1), [store](E:/MLB-Project/lib/fc/store.ts:1).

Komponen [PickTable](E:/MLB-Project/components/fc/PickTable.tsx:1) masih ada, tetapi penelusuran route FC tidak menemukan halaman yang memasangnya. Membetulkan ranking di komponen ini saja tidak akan memulihkan Today's Pick. Mengubah redirect saja juga belum menghasilkan analisa karena engine dan artifact pick belum tersedia.

## Temuan dan urutan penanganan

| ID | Temuan baseline | Dampak | Phase penanganan |
|---|---|---|---|
| F01 | `/fc` redirect ke schedule meskipun label navigasi Today's Pick | Pengguna tidak memperoleh halaman daftar pick | 7; kontrak halaman dibekukan di 1B |
| F02 | Scan route dan scraper secara eksplisit fixture-only | Refresh jadwal tidak menghasilkan probabilitas, EV, atau official picks | 3–6 untuk engine; 7 integrasi |
| F03 | `picks.json` tidak ada; engine model/selection tidak ada pada tracked Python sources saat ini | Belum ada output Formula Final yang dapat ditampilkan | 1B skeleton, 3–5 engine/evaluasi |
| F04 | `engineOffline()` hanya memeriksa apakah kedua file picks dan matches sama-sama tidak ada | Schedule-only snapshot dapat dilabeli healthy meskipun analisa tidak tersedia | 1B capability/status contract, 7 reader |
| F05 | `readJson()` menelan semua read/parse errors menjadi fallback | Missing/corrupt/unreadable dapat terlihat seperti empty data; schema salah yang parseable juga belum divalidasi | 1B error contract, 2/7 validasi |
| F06 | `readPicks()` mempercayai flag legacy, menghitung official lewat `coverage_status=full`, dan tidak menegakkan satu fixture satu official | Coverage bukan bukti model approval; tidak aman langsung memasang reader lama sebagai shortlist v2 | 1B status contract, 6 policy |
| F07 | `PickTable`/badge memakai flag top tanpa gate approval model | Payload legacy/kontradiktif dapat tampil sebagai Top Pick bila komponen kelak dipasang | 6/7 validated DTO dan UI |
| F08 | Snapshot scraper ditulis langsung ke file target; scan lock berupa variabel proses | Restart/concurrent process dapat meninggalkan output tidak konsisten; lock bukan lintas worker | 2 snapshot persistence, 7/8 atomic publish/recovery |
| F09 | API scan memanggil `python3`; lokal yang ditemukan `python.exe`, Python 3.13.14 | Portabilitas executable perlu dibekukan; scan lokal belum dieksekusi untuk menguji fallback/alias | 1B runtime contract |
| F10 | E2E FC masih mengharapkan heading Today's Pick, filters, dan disabled Run Live Scan pada `/fc` | Expectation tidak cocok dengan redirect dan schedule saat ini | Catat baseline; perbarui terhadap approved page contract di 7 |

F04 dibuktikan dari kondisi kode dan keberadaan file lokal, bukan dari respons HTTP production. F06–F07 adalah risiko jalur legacy, bukan klaim telah terjadi taruhan resmi yang salah pada deployment saat ini. Tidak ada patch sementara untuk mempromosikan fixture atau shadow menjadi pick.

## Runtime, storage, dan scheduler

- Node `v24.18.0`; executable `C:/Program Files/nodejs/node.exe`.
- Python `3.13.14`; executable `C:/Users/seaca/AppData/Local/Programs/Python/Python313/python.exe`; `pytest 9.1.1` tersedia. Belum ada suite engine v2 yang dijalankan.
- Next.js/React/TypeScript dengan Prisma pada aplikasi utama; Python numerik belum memiliki package engine v2 pada checkout ini. Tidak ada instalasi dependency dilakukan.
- `betting-machine-fc/config.json` hanya memuat source, tracking unit, dan scan window 24 jam. Tidak ada model/version registry v2 atau flag official v2 yang sudah aktif.
- File lokal: `matches_detailed.json` 546602 byte, `tracker_snapshot.json` 38618 byte, `bets.db` 65536 byte; `picks.json` absent. Ukuran ini hanya inventaris, bukan validasi data atau bukti freshness quote.
- [Snapshot script](E:/MLB-Project/scripts/fc-snapshot.py:1) mendokumentasikan pembacaan SQLite `bets.db` dan penulisan tracker JSON. Tidak dijalankan karena dapat menulis ulang artifact.
- [Worker aplikasi](E:/MLB-Project/scripts/worker.ts:1) mempunyai cron MLB; penelusuran tidak menemukan integrasi FC di file tersebut. Scheduler FC eksternal, PM2/systemd/cron aktual belum diverifikasi.
- [deploy.sh](E:/MLB-Project/deploy.sh:1) menjalankan pull/install/Prisma generate/build dan meminta restart proses secara terpisah. File ini tidak membuktikan durable volume, jumlah writer, atau backup produksi. Tidak dieksekusi.

**Keputusan persistence belum final.** Pada 1B, kontrak storage dapat dibangun terpisah dari backend, dengan fixture in-memory untuk test. SQLite production hanya dipilih setelah durable disk dan single-writer terverifikasi; jangan otomatis memigrasikan database MLB. Akses host/deployment tidak diperlukan untuk memulai pure schema/tests, tetapi diperlukan sebelum aktivasi persistence produksi.

## Baseline pengujian

Working directory seluruh perintah: `E:/MLB-Project`.

| Pemeriksaan | Perintah | Hasil |
|---|---|---|
| Unit FC | `npm.cmd run test -- tests/unit/fc-format.test.ts tests/unit/fc-grouping.test.ts tests/unit/fc-kickoff.test.ts` | PASS: 3 files, 17 tests |
| Seluruh unit suite | `npm.cmd run test -- tests/unit` | PASS: 15 files, 176 tests; termasuk 17 FC di atas, bukan tambahan 17 |
| TypeScript | `npm.cmd run typecheck` | PASS, exit 0 |
| Python tooling | `python --version` dan `python -m pytest --version` | Python 3.13.14, pytest 9.1.1 |
| E2E/browser | Belum dijalankan | NOT RUN; mismatch expectation ditemukan melalui inspeksi source, bukan hasil eksekusi gagal |
| Production build | Belum dijalankan | NOT RUN pada checkpoint inventaris ini |
| Engine backtest/ROI | Belum tersedia | NOT RUN; tidak ada klaim model quality |
| Provider scan/settlement | Sengaja tidak dipicu | Menghindari perubahan snapshot/ledger selama baseline |

Vite mengeluarkan warning deprecation CJS Node API; tests tetap pass. Git memperingatkan akses global ignore file tidak diizinkan. Penelusuran luas sebelumnya menemukan cache `.pytest_cache` tidak dapat diakses; inventaris source dibatasi agar tidak bergantung pada cache tersebut. Tidak ada bukti regression baru dari perubahan produksi karena produksi belum diubah.

## Scope preservation

Worktree awal: untracked `.claude/`, `docs/fc-final-formula-research.md`, dan `docs/fc-patch-phase-plan-v2.md`. Semuanya dipertahankan. Tidak ada AGENTS.md ditemukan pada parent langsung/repo dan pencarian source yang diperiksa. Tidak membaca/mengubah secrets, menjalankan deploy, mengubah database, pull, commit, push, atau melakukan pembersihan cache.

Dokumen baru subphase ini: baseline ini dan [progress checkpoint](E:/MLB-Project/docs/fc-patch-progress.md). Runtime belum berubah, jadi rollback runtime tidak diperlukan; dokumen dapat dipertahankan sebagai audit trail.

## Handoff ke 1B

Tugas berikutnya: bekukan schema v2 dan skeleton/test harness **tanpa mengganti route `/fc` dulu**.

1. DTO terpisah untuk fixture, quote snapshot, prediction/payout, decision, dan run diagnostics; UTC timestamps dan quarter-unit signed lines.
2. Capability status terpisah: schedule available, prediction available, model validated, official enabled. Keberadaan matches tidak membuktikan kemampuan analisa.
3. Status projection/paper/official, error missing/corrupt/invalid/stale, immutable versions dan storage interface; jangan mengadopsi `coverage_status=full` sebagai approval.
4. Fixture smoke yang sama divalidasi Python dan TypeScript. Engine skeleton belum menghitung probabilitas; default official off.
5. Rekam pilihan runtime command dan batas persistence yang belum terverifikasi, lalu jalankan ulang baseline serta contract tests baru.

UI Today's Pick akan diaktifkan sesuai Phase 7 setelah tersedia data contract dan pipeline yang benar, bukan melalui daftar pick sintetis. Bila ingin memajukan pembangunan UI projection-only, itu perubahan urutan yang perlu disepakati eksplisit, tanpa melewati approval formula.
