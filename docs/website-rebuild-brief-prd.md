# BRIEF — Bet Picks Website Rebuild

**Project:** Bet picks recommendation website (rebuild)
**Goal:** Satu website cepat dan jelas yang menampilkan hasil analisa + scrape 24 jam sebagai daftar rekomendasi bet, lengkap dengan hasil dan ROI yang jujur.
**User:** Bettor rekreasional–semi serius yang mau lihat "hari ini main apa", cek hasil kemarin, dan lihat jadwal.
**Core loop:** Scan engine (sudah ada, tiap 15 mnt) → API → website tampilkan picks → settlement otomatis → ROI terupdate.

**3 menu utama:**
1. **Today's Pick** — daftar rekomendasi hari ini (AH/HDP, O/U, BTTS, 1X2) + filter & sort.
2. **Result & ROI Dashboard** — hasil settled, W/L/P, profit unit, ROI%, hit rate, grafik equity, breakdown per market.
3. **Today's Schedule** — semua fixture 24 jam ke depan (ada pick atau tidak), jam kickoff WIB, status scan.

**Non-goals (eksplisit):** eksekusi bet / dompet / integrasi sportsbook, parlay builder, live betting odds real-time per detik, multi-user auth & social, AI chatbot.

**Definisi sukses:** user paham dalam 10 detik — berapa pick hari ini, berapa ROI bulan ini, jam berapa main berikutnya. Mobile-first, load <2s.

---

# PRD — Bet Picks Website

## 1. Overview
Rebuild frontend website di atas engine yang sudah berjalan (FastAPI `betting-machine-fc`: scanner 1xbit + model Dixon-Coles + settlement + ROI tracker). Frontend hanya *membaca* via REST API; tidak ada logika model di frontend.

## 2. Functional Requirements

### FR-1 — Today's Pick (`/`)
- Tabel/kartu pick hari ini (kickoff ≥ sekarang, window 24 jam): kolom **Match, Liga, Kickoff (WIB), Market, Pick, Odds, Probabilitas, EV, Stake saran, Status** (Top Pick / Official / Watch).
- Filter: market (AH / O/U / BTTS / 1X2), liga, status. Sort: rank, EV, odds, kickoff. Search tim.
- Badge jelas untuk Top Pick. Watch tampil terpisah/redup (bukan rekomendasi utama).
- Auto-refresh tiap 60 detik + tombol "Run Live Scan" (POST, dengan status polling).
- Empty state jujur: "Belum ada pick yang lolos gate" (jangan tampilkan pick sampah demi mengisi slot).
- Sumber data: `GET /api/picks` (sudah ada; dukung `market, league, min_odds, max_odds, min_ev, search, sort_by, sort_order, limit, offset`).

### FR-2 — Result & ROI Dashboard (`/results`)
- KPI: Settled, Wins–Losses–Pushes, Profit (unit), **ROI %**, Hit rate %.
- Tabel hasil: Date, Match, Liga, Market, Pick, Odds, Skor akhir (FT + status FINAL/LIVE), Result (Won/Lost/Push), Profit.
- Filter: rentang tanggal, market, liga, status. Breakdown per market (tabel kecil: bets, win%, profit, ROI).
- Grafik equity curve (profit kumulatif) — canvas ringan, bukan lib berat.
- Aturan keras: **flat 1-unit stake** untuk semua angka ROI; push = profit 0, bukan win/loss. ROI = profit / settled.
- Sumber data: `GET /api/tracker` (summary + locked + settled + market_performance + by_version), `POST /api/settle` untuk refresh manual.

### FR-3 — Today's Schedule (`/schedule`)
- Daftar semua fixture 24 jam ke depan: Kickoff WIB, Liga, Home vs Away, badge "ada pick" (link ke pick) atau "—".
- Group by liga atau urut kickoff. Countdown ke kickoff terdekat.
- Tandai status data: cakupan model (full/shadow), bukan bahasa teknis.
- Sumber data: `GET /api/matches` (paginasi `limit/offset`).

### FR-4 — Aturan tampilan umum
- Semua waktu: simpan UTC, **tampil WIB** (`Asia/Jakarta`), format `09 Sep 2026 · 22:30 WIB`.
- Odds desimal 2–3 digit. Profit format `+1.85u / −1.00u`. ROI 1 desimal + warna (hijau/merah).
- Setiap pick yang ditampilkan harus punya: `match_id, match, home, away, league, start_ts, market (ah/ou/btts/1x2), pick, odds, probability, ev, conservative_ev, market_probability, edge_pct, kelly_pct, suggested_stake, stake_cap, is_top_pick, selection_status (top_pick/official/shadow), tier, coverage_status, lambda_source, formula_version`.
- Field tak dikenal → render "—", jangan crash.
- Disclaimer kecil permanen di footer: picks = estimasi model yang belum tervalidasi, bukan jaminan profit.

## 3. API Contract (backend sudah ada — jangan ubah tanpa koordinasi)
| Endpoint | Pakai untuk |
|---|---|
| `GET /api/picks?...` | FR-1 |
| `GET /api/tracker` | FR-2 |
| `POST /api/settle` | FR-2 refresh |
| `GET /api/matches?limit=&offset=` | FR-3 |
| `GET /api/scan/status`, `POST /api/scan` | tombol scan + polling |
| `GET /api/health`, `GET /api/config` | status engine, floor odds display |

## 4. Non-Functional
- **Performance:** First load <2s di 4G; daftar pakai pagination server-side (default 50), jangan render 500 row sekaligus; polling ringan (60s, abort saat tab hidden).
- **Mobile-first responsive:** kartu di HP, tabel di desktop. Kontras AA, navigasi keyboard untuk filter.
- **Reliability:** semua fetch dengan timeout + error state ("gagal muat, coba lagi"), tidak ada layar putih. API error (502 settlement) tampil sebagai banner, bukan crash.
- **Timezone:** satu helper `formatWIB(ts)` dipakai di semua komponen — tidak ada format tanggal inline tersebar.
- **SEO/ops:** title + meta description per halaman; tidak perlu SSR untuk data dinamis (client fetch + loading skeleton boleh).

## 5. Acceptance Criteria (Definition of Done)
- [ ] 3 menu jalan dengan data live dari API di atas (bukan mock).
- [ ] Filter/sort/search bekerja di ketiga menu; pagination tidak jebol di 500+ baris.
- [ ] ROI dashboard cocok dengan `POST /api/settle` → angka berubah konsisten (settled bertambah, profit terupdate).
- [ ] Kickoff lampau tidak muncul di Today's Pick/Schedule (hanya future).
- [ ] Jam tampil WIB di semua tempat; odds/profit/ROI format konsisten.
- [ ] Lighthouse mobile Performance ≥80, tidak ada console error.
- [ ] `npm run build && npm run lint` hijau.

## 6. Milestones (untuk coding agent)
- **M1 — Shell + API client:** layout, nav 3 menu, typed API client + `formatWIB` + error/loading states. (Tanpa chart dulu.)
- **M2 — Today's Pick + Schedule:** tabel, filter, sort, search, scan trigger.
- **M3 — ROI Dashboard:** KPI, tabel hasil + skor, breakdown market, equity curve, settle refresh.
- **M4 — Polish:** responsive pass, empty states, disclaimer, SEO meta, DoD checklist hijau.

---

# TECH STACK REKOMENDASI

| Lapisan | Rekomendasi | Alasan |
|---|---|---|
| Frontend | **Next.js 14+ (App Router) + TypeScript + Tailwind CSS** | Sudah ada folder `app/` di repo; routing 3 menu gratis; deploy mudah; TS menangkap perubahan field API |
| Data fetching | **SWR** (atau React Query) | Polling 60s + revalidate + abort bawaan; cocok untuk data scan berkala |
| Chart | **Recharts** (hanya equity curve) atau canvas custom | Cukup untuk 1 grafik; hindari lib berat |
| Backend | **Tetap FastAPI yang ada** (jangan rewrite) | Scan worker, settlement, 20+ endpoint sudah jalan + teruji (100+ tests) |
| Database | **SQLite sekarang → Postgres (Supabase/Neon) saat traffic naik** | SQLite cukup untuk single-writer worker; pindah kalau ada concurrent write/lock |
| Hosting | **VPS existing** (`fc.texasdrill.me`) untuk engine + **Vercel** untuk frontend (atau semua di VPS via Nginx, satu domain + `/api` reverse proxy) | Pisah deploy: frontend bisa update tanpa sentuh engine |
| Timezone | `Intl.DateTimeFormat('id-ID', {timeZone:'Asia/Jakarta'})` terpusat | Satu sumber kebenaran format WIB |
| CI | GitHub Actions: `lint + typecheck + build + pytest backend` | Mencegah deploy pecah (kasus deploy basi kemarin) |

**Sengaja TIDAK dipakai:** WebSocket/SSE (polling 60s cukup), Redux/Zustand (state server di SWR, state UI lokal cukup), CMS, auth (belum perlu — tambah saat multi-user/paid picks).

---

Catatan untuk coding agent: mulai dari M1, jangan ubah API backend. Kalau butuh field baru, minta dulu — jangan mengarang field di frontend. Test manual wajib: bandingkan angka ROI di website vs `GET /api/tracker` mentah, harus identik.
