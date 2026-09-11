# Website Baru — Brief + PRD + Tech Stack + Architecture

**Status:** Siap diteruskan ke coding agent.
**Konteks:** Rebuild frontend di atas engine produksi yang sudah berjalan (`betting-machine-fc`, formula `ou-ah-v4.4.0`). Frontend hanya membaca API; tidak ada logika model di frontend.

---

## 1. BRIEF

**Goal:** Website yang menampilkan rekomendasi bet hasil analisa + scrape 24 jam: daftar pick jelas, hasil + ROI jujur, dan jadwal hari ini. User paham dalam 10 detik: berapa pick hari ini, ROI berapa, main jam berapa.

**User:** Bettor rekreasional–semi serius (single user dulu, tanpa auth).

**Pasaran:** Asian Handicap (HDP), Total Goals Over/Under, BTTS, 1X2 Moneyline.

**3 menu:**
1. **Today's Pick** — rekomendasi hari ini (Top Pick / Official / Watch) + filter & sort.
2. **Result & ROI Dashboard** — hasil settled, W/L/P, profit unit, ROI%, hit rate, equity curve, breakdown per market.
3. **Today's Schedule** — semua fixture 24 jam ke depan; tandai mana yang ada pick.

**Non-goals:** eksekusi bet/dompel/integrasi sportsbook, parlay builder (engine punya, website tidak perlu di MVP), odds live per detik, multi-user/auth/social, AI chatbot.

**Definisi sukses:** load <2s di 4G; angka ROI di website identik dengan `GET /api/tracker` mentah; tidak ada pick fiktif (slot kosong = "belum ada yang lolos", bukan diisi paksa).

---

## 2. KONDISI SISTEM SAAT INI (yang harus dihormati coding agent)

Engine FastAPI di VPS (`fc.texasdrill.me`, PM2: `fc-betting-web` + `fc-betting-worker` interval 15 mnt, Nginx reverse proxy, deploy via `deploy.sh`):

- **Pipeline:** scan 1xbit LineFeed → `build_projection` (primary → paired O/U+AH fallback → OU-only partial) → `analyze_match` → `select_top_picks` → lock ke SQLite → settlement (FlashScore/API-football) → ROI.
- **Coverage tiers (krusial untuk UI):** `full` (rating tim independen), `shadow` (prior liga/unrated — evaluasi, bukan sinyal penuh), `watch` (tier belum tervalidasi), `blocked`/`market_only` (tidak dipublikasikan). Status pick: `top_pick` / `official` / `shadow` (+`top_pick:shadow`).
- **Setiap pick membawa:** `match_id, match, home, away, league, start_ts (UTC), market (ah/ou/btts/1x2), pick, odds, probability, ev, conservative_ev, market_probability, edge_pct, suggested_stake, stake_cap, is_top_pick, selection_status, tier, decision (official/top_pick/watch), coverage_status, lambda_source, formula_version, policy_version, ratings_files, total_disagreement, calibrated_prob (bisa null)`.
- **Aturan main yang tidak boleh dilanggar UI:** ROI flat 1-unit (`profit/s settled`); push = profit 0; `calibrated_prob` boleh null (jangan jadikan angka utama); label `experimental`/`unvalidated` harus tampil apa adanya; pick kedaluwarsa (kickoff lewat) tidak tampil di Pick/Schedule.
- **Pelajaran insiden (wajib di CI):** deploy basi pernah terjadi (PM2 restart tanpa `git pull`). Deploy harus pull + verifikasi versi formula, gagal keras kalau tree kotor.

---

## 3. PRD — FUNCTIONAL REQUIREMENTS

### FR-1 — Today's Pick (`/`)
- Daftar pick kickoff ≥ sekarang (window 24 jam): **Match, Liga, Kickoff WIB, Market, Pick, Odds, Prob, EV, Stake saran, Status** (Top Pick / Official / Watch).
- Top Pick badge menonjol; Watch redup + terpisah (bukan rekomendasi utama).
- Filter: market (AH/O/U/BTTS/1X2), liga, status/decision. Sort: rank, EV, odds, kickoff. Search tim.
- Auto-refresh 60s (pause saat tab hidden) + tombol Run Live Scan (POST + polling status).
- Empty state jujur. Sumber: `GET /api/picks` (param: `market, league, min_odds, max_odds, min_ev, search, sort_by, sort_order, limit, offset`).

### FR-2 — Result & ROI Dashboard (`/results`)
- KPI: Settled, W–L–P, Profit unit, **ROI %**, Hit rate %.
- Tabel: Date, Match, Liga, Market, Pick, Odds, Skor FT (+status FINAL/LIVE), Result, Profit.
- Filter tanggal/market/liga/status. Breakdown per market. Equity curve (canvas ringan).
- Tombol refresh settlement (`POST /api/settle`, polling, tampilkan error 502 sebagai banner).
- Sumber: `GET /api/tracker` (`summary, locked/live/overdue/settled, status_counts, market_performance, by_version`).

### FR-3 — Today's Schedule (`/schedule`)
- Semua fixture 24 jam: Kickoff WIB, Liga, Home vs Away, badge ada-pick (link) atau "—", countdown laga terdekat, status cakupan (full/shadow, bahasa awam).
- Sumber: `GET /api/matches?limit=&offset=`.

### FR-4 — Aturan global
- Waktu: UTC disimpan, **WIB tampil** (`Asia/Jakarta`, `09 Sep 2026 · 22:30 WIB`) via satu helper `formatWIB(ts)`.
- Format: odds 2–3 desimal; profit `+1.85u/−1.00u`; ROI 1 desimal + warna. Field null → "—", jangan crash.
- Footer disclaimer permanen: estimasi model belum tervalidasi, bukan jaminan profit.

## 4. NON-FUNCTIONAL
- Performance: first load <2s (4G); pagination server-side (default 50); tidak render 500 row sekaligus.
- Mobile-first (kartu di HP, tabel di desktop); kontras AA; keyboard-friendly filter.
- Reliability: timeout + error/empty state di semua fetch; tidak ada layar putih.
- SEO: title/meta per halaman. Data dinamis boleh client-fetch + skeleton.

## 5. ACCEPTANCE CRITERIA
- [ ] 3 menu live dari API (bukan mock); angka ROI = `GET /api/tracker` mentah.
- [ ] Filter/sort/search + pagination aman di 500+ baris.
- [ ] `POST /api/settle` → dashboard konsisten (settled +, profit update).
- [ ] Hanya fixture future di Pick/Schedule. WIB di semua tempat.
- [ ] Lighthouse mobile ≥80, nol console error, `build + lint` hijau.

## 6. MILESTONES
- **M1:** Shell + nav + typed API client + `formatWIB` + loading/error states.
- **M2:** Today's Pick + Schedule (tabel, filter, sort, search, scan trigger).
- **M3:** ROI Dashboard (KPI, hasil+skor, breakdown, equity, settle refresh, by_version).
- **M4:** Polish (responsif, empty states, disclaimer, SEO, DoD hijau).

---

## 7. TECH STACK REKOMENDASI

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Frontend | Next.js 14+ App Router + TypeScript + Tailwind | `app/` sudah ada di repo; TS menangkap perubahan field API; deploy mudah |
| Fetching | SWR | polling 60s + revalidate + abort bawaan |
| Chart | Recharts (1 grafik equity) / canvas custom | cukup, hindari lib berat |
| Backend | **Tetap FastAPI existing (jangan rewrite)** | 20+ endpoint + 100+ tests sudah jalan |
| DB | SQLite sekarang → Postgres (Supabase/Neon) bila concurrent write/lock | single-writer worker masih aman di SQLite |
| Hosting | Engine tetap VPS; frontend Vercel **atau** satu VPS via Nginx (`/` → frontend, `/api` → FastAPI) | pisah deploy; frontend update tanpa sentuh engine |
| CI | GitHub Actions: lint + typecheck + build + pytest backend; deploy script wajib `git pull --ff-only` + cetak versi formula (gagal keras bila kotor) | mencegah insiden deploy basi |

**Sengaja tidak dipakai:** WebSocket (polling cukup), Redux (SWR + state lokal cukup), CMS, auth (tambah saat multi-user/paid).

---

## 8. ARSITEKTUR YANG DISARANKAN

```text
                    ┌──────────────────────────────┐
                    │  1xbit LineFeed (odds+jadwal)│
                    │  FlashScore/API-football     │
                    │  football-data.co.uk (CSV)   │
                    └──────────────┬───────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│ ENGINE (VPS, PM2) — betting-machine-fc (FastAPI, Python)     │
│  worker.py (15 mnt): scan → projection → analyze → select    │
│                      → lock SQLite → settlement → ROI        │
│  server.py: /api/picks|tracker|matches|settle|scan|intel...  │
│  data: bets.db + bet_audit, ratings_*.json, ledger, snapshots│
└───────────────────────────┬──────────────────────────────────┘
                            │ REST JSON (satu kontrak §3)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND (Vercel atau VPS-route) — Next.js + TS + Tailwind   │
│  / (Today's Pick)   /results (ROI)   /schedule (jadwal)      │
│  SWR polling 60s · formatWIB terpusat · skeleton + banner    │
└──────────────────────────────────────────────────────────────┘
```

**Prinsip arsitektur (mengikat):**
1. **Satu arah data:** engine → API → UI. Tidak ada logika model/EV/gate di frontend; tidak ada tulis dari UI kecuali trigger scan/settle dan context note.
2. **Kontrak API beku:** field §3 adalah kontrak. Field baru = opsional + nullable; rename/dihapus = versi endpoint baru, bukan diam-diam.
3. **Kejujuran terstruktur:** tier `watch`/`shadow` tidak pernah dipromosikan diam-diam; `calibrated_*` null = belum valid; formula/policy version ikut tiap pick untuk kohort ROI (`by_version`).
4. **Deploy aman:** `deploy.sh` = pull ff-only → verifikasi `FORMULA_VERSION` tercetak → install → pytest → restart. Gagal di langkah mana pun = abort, bukan deploy basi.
5. **Evolusi DB:** tambah kolom via migrasi `ALTER TABLE` + default; SQLite → Postgres hanya saat lock/concurrency jadi masalah (amati `database is locked` di log worker).
6. **Observability murah:** `/api/health` + `scan_state.diagnostics` (counts full/shadow/blocked, coverage_reasons, errors) jadi sumber banner status UI — tanpa sistem monitoring tambahan di MVP.

## 9. RISIKO & KEPUTUSAN TERCATAT
- Volume pick rendah di slate sepi = perilaku benar (gate), bukan bug — jangan isi slot paksa.
- finns/under obscure & longshot >2.75 & EV>0.25 = noise model, tetap diblokir (bukti: EV sweep flat, Brier ≈ koin).
- Kalibrasi (ECE ~9pp) belum valid → `calibrated_*` attach-only sampai validasi OOS lolos.
- UCL/liga tanpa file rating: cross-league domestic history (provenance `ratings_files`); tanpa itu = shadow, bukan full.

## 10. INSTRUKSI UNTUK CODING AGENT
Mulai M1. Jangan ubah API backend. Butuh field baru → minta dulu, jangan mengarang. Verifikasi wajib: ROI website vs `GET /api/tracker` mentah harus identik; hanya fixture future di Pick/Schedule; laporkan Lighthouse + hasil `build/lint`.
