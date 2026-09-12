# FC Phase 2 — Data integrity and quote provenance

## Status

Phase 2A–2C selesai secara lokal untuk boundary/offline pipeline. Belum ada live odds collector, provider subscription, production database, atau perubahan scraper/reader yang sedang aktif. Existing `matches_detailed.json`, tracker snapshot, dan ledger tidak ditulis ulang.

Implementasi:

- [Normalizer](E:/MLB-Project/betting-machine-fc/football_formula_engine/data.py): identitas deterministik, UTC, result status, as-of filtering, quote opening/closing terpisah, raw/provenance hashes, dataset manifest.
- [Ingestion outcomes](E:/MLB-Project/betting-machine-fc/football_formula_engine/ingestion.py): `success`, `empty`, `transport_error`, dan `invalid_data` terpisah; retry hanya untuk transport dan dibatasi 1–5 percobaan.
- [Append-only store](E:/MLB-Project/betting-machine-fc/football_formula_engine/snapshot_store.py): canonical JSON, create-if-absent, idempotent identical content, conflict/corruption/path traversal ditolak.
- [Persistence ports](E:/MLB-Project/betting-machine-fc/football_formula_engine/ports.py): snapshot, complete-run publication, dan settlement revision dipisah tanpa memilih backend produksi secara spekulatif.
- [Read-only manifest CLI](E:/MLB-Project/betting-machine-fc/football_formula_engine/data_cli.py).
- [FC artifact reader](E:/MLB-Project/lib/fc/store.ts) kini memakai allowlist empat path statis. Perilaku data legacy tidak sengaja diubah; perubahan mencegah Next.js tracer menganggap seluruh folder/cache Python sebagai input dinamis.

## Data decisions

- Historical Football-Data `B365*` dan `B365C*` disimpan sebagai quote opening/closing terpisah. AH home memakai `AHh/AHCh`; sisi away menyimpan line dengan tanda berlawanan dari perspektif tim yang dipilih.
- O/U pada file yang diuji hanya line 2.5. Missing quote tetap absent; BTTS tidak direka dari hasil skor.
- File tidak memberi capture/availability timestamp historis. Kedua field dibiarkan null dan freshness `unknown`; quote ini tidak lolos `quotes_as_of` dan tidak menjadi execution/CLV evidence.
- Hasil final historis mendapat availability konservatif kickoff+4 jam dan field basis yang eksplisit. Ini asumsi pencegah leakage, bukan timestamp publikasi provider yang teramati.
- Waktu pertandingan memerlukan IANA timezone atau verified fixed UTC offset. Missing `Time` ditolak. Windows local membutuhkan `tzdata`, kini dideklarasikan pada requirements; tidak ada fallback DST tebakan.
- ID tim default namespaced per competition untuk mencegah collision. Cross-division/promoted-team linkage membutuhkan mapping eksplisit atau shared namespace yang diaudit pada Phase 4.
- `is_closing=true` hanya label kolom sumber; tidak membuktikan freshness atau bahwa harga tersedia ketika strategi membuat keputusan.

## E0 2025/26 replay

[Manifest tersimpan](E:/MLB-Project/betting-machine-fc/football_formula_engine/artifacts/phase2-e0-2526-manifest.json) dibuat dari tracked `data/E0_2526.csv` menggunakan `Europe/London` dan tzdata 2026.3.

| Ukuran | Hasil |
|---|---:|
| Final matches | 380 |
| Total quote records | 5,318 |
| 1X2 | 2,280 |
| O/U | 1,520 |
| AH | 1,518 |
| BTTS | 0 |
| Quote dengan capture timestamp | 0 |

Normalized dataset SHA-256 `149d42...5f68b`; raw CSV SHA-256 `3e3a83...07e62`. Semua market berstatus `NOT_EVALUABLE_NO_TIMED_QUOTES`. Ini tidak berarti model ROI=0: belum ada locked point-in-time policy run yang dapat dihitung. Dua AH records lebih sedikit daripada O/U merefleksikan missing source values, bukan imputasi.

Reproduction command dari `betting-machine-fc`:

```powershell
python -m football_formula_engine.data_cli data/E0_2526.csv --competition E0 --season 2526 --timezone Europe/London
```

## Gate dan batas

Replay deterministik, no-future as-of tests, missing/corrupt distinction, duplicate/conflict handling, bounded retries, signed AH lines, raw quote preservation, dan coverage reporting telah diuji. Store hanya fondasi local/offline: durability directory, active-run pointer, multiwriter lock, retention, backups, dan deployment transaction tetap belum diklaim. Collector produksi belum ada sehingga 2C selesai pada boundary/persistence layer, bukan live coverage.

Rollback runtime tidak diperlukan karena modul belum diimpor route aktif. Hapus/disable collector bukan relevan; tidak ada collector yang diaktifkan. Tahap lanjut Phase 4 harus memakai only `matches_as_of`, bukan seluruh final rows sekaligus.
