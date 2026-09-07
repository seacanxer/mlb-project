# PRD — Match Prediction Insight Card (1X2, Asian Handicap, Over/Under, BTTS)

**Versi:** 1.0
**Tanggal:** 7 September 2026
**Status:** Draft untuk review teknis

---

## 1. Latar Belakang & Tujuan

Tool prediksi yang sudah ada saat ini menghasilkan output mentah (probabilitas/odds). Yang diminta adalah **menu ringkasan hasil model** seperti pada mockup: satu kartu yang menampilkan probabilitas 1X2, estimasi xG diff, estimasi total gol, BTTS, dan rekomendasi pick untuk 4 jenis pasar (1X2, Asian Handicap, Over/Under, BTTS) sekaligus.

**Tujuan:**
- Mengubah input "nilai skuad + parameter" menjadi satu set probabilitas yang konsisten secara matematis (semua pasar diturunkan dari satu distribusi skor, bukan dihitung terpisah-pisah).
- Menyediakan API yang bisa dipanggil ulang setiap kali user mengubah parameter (recalculate on the fly), sesuai perilaku card di mockup yang berbunyi "Berdasarkan nilai skuad dan parameter yang dimasukkan".
- Menyediakan komponen frontend yang reusable untuk fixture manapun.

**Non-Goals (fase ini):**
- Tidak membangun exchange/bookmaking sendiri (harga taruhan riil tetap dari scraping odds yang sudah ada).
- Tidak membangun model deep-learning; cukup model statistik klasik yang bisa dijelaskan (explainable), supaya parameter di UI ("nilai skuad", dsb.) benar-benar bisa memengaruhi output secara terlihat.

---

## 2. Pemetaan UI → Kebutuhan Data/Fungsi

| Elemen di mockup | Sumber perhitungan |
|---|---|
| Bar Udinese / Seri / Lazio (%) | P(Home Win), P(Draw), P(Away Win) dari matriks skor |
| Estimasi selisih gol (xG diff) + "favorit: X" | λ_home − λ_away |
| Estimasi total gol | λ_home + λ_away |
| Peluang BTTS Yes | Σ P(i,j) untuk i≥1 dan j≥1 |
| Prediksi 1X2 (dropdown) | argmax(P(Home), P(Draw), P(Away)) |
| Asian Handicap (Home/Away, +/-, line) | Distribusi selisih gol (D = i−j), disesuaikan dengan line & aturan AH (termasuk quarter-line) |
| Over/Under (line) | Σ P(i,j) untuk i+j > line |
| BTTS Ya/Tidak | sama seperti di atas, ditampilkan sebagai toggle biner |

Poin penting: **semua pasar harus diturunkan dari satu matriks skor yang sama**, bukan dihitung dengan rumus terpisah — supaya angkanya tidak saling kontradiksi (mis. BTTS 58% tapi Under 2.5 favorit, padahal total gol 2.93).

---

## 3. Data yang Diperlukan

### 3.1 Data master (relatif statis, di-refresh mingguan)
- Daftar liga, musim, tim (id, nama, negara).
- **Nilai skuad (squad market value)** per tim — sumber: scraping Transfermarkt via Playwright (butuh render JS), atau fallback API-Football bila tersedia field valuation.
- Rata-rata gol liga (home & away) per musim berjalan — dihitung dari histori pertandingan liga tsb, bukan angka tetap, karena berubah tiap musim.

### 3.2 Data historis (untuk kalibrasi model)
- Hasil pertandingan minimal 2 musim terakhir per liga: skor FT, tanggal, home/away, tim.
- Idealnya juga xG pertandingan (jika API-Football/Understat tersedia) — meningkatkan akurasi dibanding gol aktual saja karena gol aktual noise-nya tinggi di sampel kecil.

### 3.3 Data kondisional (diperbarui mendekati kickoff)
- Starting XI / cedera-suspensi pemain kunci (opsional, untuk adjustment manual di parameter).
- Odds pasar (sudah ada di sistem existing) — dipakai untuk **validasi**, bukan input model (supaya model tetap independen, bisa dipakai mendeteksi value bet).

### 3.4 Parameter yang bisa diubah user di UI (sesuai teks "parameter yang dimasukkan")
- Bobot nilai skuad vs bobot performa historis (attack/defense rating).
- Home advantage factor (default terkalibrasi per liga, bisa di-override).
- Adjustment manual (mis. "−1 pemain kunci cedera" → penalti attack rating sekian %).

---

## 4. Model Prediksi

### 4.1 Layer 1 — Attack/Defense Rating dari histori (baseline statistik)

Gunakan pendekatan **Poisson regression / Dixon-Coles**, standar industri untuk model gol sepak bola:

```
AttackRating_home  = GolDicetak_home / RataRataGolLiga_home
DefenseRating_away = GolDikebobol_away / RataRataGolLiga_away

λ_home = RataRataGolLiga_home × AttackRating_home × DefenseRating_away × HomeAdvantage
λ_away = RataRataGolLiga_away × AttackRating_away × DefenseRating_home
```

Rating diestimasi via maximum likelihood dari histori pertandingan (bukan rata-rata sederhana saja) agar lebih stabil untuk sampel kecil — ini pekerjaan batch job (`ratings/recalculate`), dijalankan tiap minggu setelah pekan liga selesai.

### 4.2 Layer 2 — Adjustment dari nilai skuad & parameter manual

Nilai skuad tidak dipakai untuk menghitung gol secara langsung (skala uang ≠ skala gol), melainkan sebagai **modifier** terhadap rating Layer 1:

```
RelativeSquadStrength_home = MV_home / (MV_home + MV_away)     // 0..1
SquadAdjustment_home = 1 + β × (RelativeSquadStrength_home − 0.5)

λ_home_final = λ_home × SquadAdjustment_home × ManualAdjustment_home
λ_away_final = λ_away × SquadAdjustment_away × ManualAdjustment_away
```

- `β` adalah bobot pengaruh nilai skuad (parameter yang bisa diatur di UI/admin, mis. 0.0–0.4).
- `ManualAdjustment` adalah multiplier bebas dari override manual (cedera, motivasi, dsb.), default = 1.
- `β = 0` berarti model murni berbasis histori; `β` besar berarti nilai skuad sangat dominan — berguna untuk tim/liga dengan histori data tipis (promosi, liga minor).

### 4.3 Matriks Probabilitas Skor (Dixon-Coles)

```
P(i,j) = Poisson(i; λ_home_final) × Poisson(j; λ_away_final) × τ(i,j)

Poisson(k; λ) = (λ^k × e^(−λ)) / k!

τ(0,0) = 1 − λ_home×λ_away×ρ
τ(0,1) = 1 + λ_home×ρ
τ(1,0) = 1 + λ_away×ρ
τ(1,1) = 1 − ρ
τ(i,j) = 1   untuk i,j ≥ 2
```

`ρ` adalah parameter korelasi skor rendah (biasanya sekitar −0.05 s.d. −0.15), diestimasi dari histori bersama dengan Layer 1. Hitung matriks untuk i,j = 0..8 (probabilitas di atas 8 gol dapat diabaikan/dimasukkan ke sel terakhir sebagai sisa).

### 4.4 Menurunkan semua output UI dari matriks yang sama

```
P(Home Win) = Σ P(i,j)  untuk i > j
P(Draw)     = Σ P(i,j)  untuk i = j
P(Away Win) = Σ P(i,j)  untuk i < j

xG diff       = λ_home_final − λ_away_final
Total gol     = λ_home_final + λ_away_final

BTTS Yes = Σ P(i,j) untuk i ≥ 1 dan j ≥ 1
BTTS No  = 1 − BTTS Yes

Over(X)  = Σ P(i,j) untuk i+j > X
Under(X) = 1 − Over(X)
```

**Asian Handicap** — hitung dari distribusi selisih gol `D(d) = Σ P(i,j) untuk i−j = d`, lalu terapkan aturan AH standar:
- Line bulat (0, 1, 2, …): win/draw(push)/loss dari `D(d)` langsung.
- Line .5 (0.5, 1.5, …): tidak ada push, langsung win/loss.
- Line .25/.75 (quarter line, sesuai contoh "0,25" di mockup): split 50/50 antara dua line terdekat (mis. AH 0.25 = rata-rata hasil AH 0 dan AH 0.5).

Contoh untuk mockup: **Away (Lazio) −0.25** berarti taruhan dibagi setengah ke AH 0 away dan setengah ke AH −0.5 away, hasil akhir gabungan dari kedua sub-hasil tersebut.

**Rekomendasi pick otomatis** (dropdown 1X2, tombol Over/Under, toggle BTTS) = ambil opsi dengan probabilitas tertinggi di masing-masing pasar (argmax), ditampilkan sebagai default state, tetap bisa diubah manual oleh user.

---

## 5. Arsitektur Teknis (mapping ke stack yang ada)

### 5.1 Skema Database (Prisma, tambahan ke schema existing)

```prisma
model TeamRating {
  id            Int      @id @default(autoincrement())
  teamId        Int
  seasonId      Int
  attackRating  Float
  defenseRating Float
  updatedAt     DateTime @updatedAt

  @@unique([teamId, seasonId])
}

model SquadValuation {
  id           Int      @id @default(autoincrement())
  teamId       Int
  marketValueM Float    // dalam juta EUR
  source       String   // "transfermarkt" | "manual"
  scrapedAt    DateTime
}

model LeagueBaseline {
  id                Int    @id @default(autoincrement())
  leagueId          Int
  seasonId          Int
  avgGoalsHome      Float
  avgGoalsAway      Float
  homeAdvantage     Float
  rho               Float  // parameter Dixon-Coles
}

model ModelParameter {
  id          Int    @id @default(autoincrement())
  key         String @unique   // "beta_squad_weight", dst
  value       Float
  description String?
}

model ManualAdjustment {
  id         Int      @id @default(autoincrement())
  fixtureId  Int
  teamId     Int
  multiplier Float    // default 1.0
  reason     String?  // "cedera striker utama", dll
  createdAt  DateTime @default(now())
}

model PredictionCache {
  id             Int      @id @default(autoincrement())
  fixtureId      Int      @unique
  lambdaHome     Float
  lambdaAway     Float
  scoreMatrixJson String  // matriks P(i,j) tersimpan sbg JSON, dipakai ulang oleh frontend
  computedAt     DateTime @default(now())
}
```

### 5.2 API Endpoints (FastAPI)

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | `/api/ratings/recalculate` | Batch job mingguan: hitung ulang AttackRating/DefenseRating/ρ per liga dari histori |
| POST | `/api/squad-values/refresh` | Trigger scraping nilai skuad (Playwright → Transfermarkt) |
| POST | `/api/predictions/{fixtureId}/compute` | Hitung λ_home, λ_away, matriks skor lengkap; simpan ke `PredictionCache`. Body: override parameter opsional (β, manual adjustment) |
| GET | `/api/predictions/{fixtureId}` | Ambil hasil cache (matriks + λ + probabilitas ringkas 1X2/BTTS) |
| GET | `/api/predictions/{fixtureId}/handicap?side=away&line=-0.25` | Hitung probabilitas AH untuk line spesifik dari matriks cache |
| GET | `/api/predictions/{fixtureId}/total-goals?line=3` | Hitung Over/Under untuk line spesifik dari matriks cache |
| PATCH | `/api/fixtures/{fixtureId}/adjustments` | Simpan `ManualAdjustment` (dipakai UI "parameter yang dimasukkan") |

**Desain penting:** endpoint `compute` mengembalikan **seluruh matriks skor (mis. 9×9)**, bukan hanya angka ringkas. Dengan begitu, saat user mengubah line Asian Handicap atau Over/Under di dropdown UI, frontend **tidak perlu roundtrip ke backend** — cukup hitung ulang dari matriks yang sudah di-fetch (lihat 5.4). Ini membuat interaksi UI instan.

### 5.3 Scraping & Scheduling (cron, di server Tencent CVM existing)

| Job | Frekuensi | Keterangan |
|---|---|---|
| Scrape nilai skuad (Transfermarkt via Playwright) | Mingguan | Nilai skuad jarang berubah drastis; hormati robots.txt/ToS situs sumber |
| Recalculate TeamRating & ρ per liga | Mingguan, setelah pekan liga selesai | Batch job MLE fit |
| Refresh LeagueBaseline (avg goals, home advantage) | Mingguan / per akhir musim | |
| Compute ulang PredictionCache untuk fixture mendatang (H-3 hari) | Harian | Supaya angka di UI sudah tersedia sebelum user membuka |
| Sinkron dengan job odds-scraping existing | Sesuai jadwal existing | Dipakai untuk membandingkan probabilitas model vs implied odds (deteksi value bet) — fitur terpisah, opsional |

### 5.4 Frontend (Next.js + Tailwind)

Komponen utama: `<MatchPredictionCard fixtureId />`
- Fetch sekali ke `/api/predictions/{fixtureId}` → dapat `{ lambdaHome, lambdaAway, scoreMatrix, oneXTwo, btts }`.
- State lokal untuk pilihan user: `market1x2`, `ahSide`, `ahLine`, `ouLine`, `bttsChoice`.
- Fungsi utilitas murni di client (tidak perlu API call ulang):
  - `computeHandicap(scoreMatrix, side, line)`
  - `computeOverUnder(scoreMatrix, line)`
- Progress bar (Home/Draw/Away) memakai `oneXTwo` langsung dari response.
- Dropdown line AH/OU memicu re-render lokal saja (instan, tanpa loading state ke backend).

---

## 6. Kalibrasi & Validasi Model

Karena ini model statistik yang menghasilkan angka yang dipakai untuk keputusan (meski bukan nasihat finansial resmi), wajib ada proses validasi:

- **Backtesting**: jalankan model terhadap musim-musim lalu, bandingkan probabilitas prediksi vs hasil aktual.
- **Metrik**: Log-loss dan Brier score untuk kalibrasi probabilitas (bukan sekadar akurasi pick benar/salah).
- **Kalibrasi visual**: reliability diagram (probabilitas prediksi vs frekuensi aktual per bucket 10%).
- **Pembanding**: closing odds dari sumber scraping existing sebagai baseline "market consensus" — jika model konsisten kalah jauh dari implied probability pasar, β dan ρ perlu ditinjau ulang.

---

## 7. Roadmap Implementasi

1. **Fase 1 — Model inti**: Poisson/Dixon-Coles dari data historis saja (tanpa nilai skuad dulu), simpan `TeamRating`, `LeagueBaseline`, endpoint `compute` & `GET predictions`.
2. **Fase 2 — Integrasi nilai skuad**: scraping Transfermarkt, `SquadValuation`, layer adjustment β.
3. **Fase 3 — UI card**: bangun `MatchPredictionCard` sesuai mockup, dengan kalkulasi AH/OU client-side dari matriks.
4. **Fase 4 — Parameter manual**: UI/endpoint untuk `ManualAdjustment` (cedera, dll).
5. **Fase 5 — Kalibrasi & monitoring**: dashboard backtesting, log-loss tracking dari waktu ke waktu.

---

## 8. Risiko & Catatan

- **Scraping Transfermarkt**: rawan berubah struktur HTML/rate-limit; periksa ToS situs sebelum scraping rutin, pertimbangkan cache lokal jangka panjang karena nilai skuad tidak sering berubah.
- **Sampel kecil**: tim promosi/liga minor punya histori tipis → β (bobot nilai skuad) sebaiknya otomatis naik untuk tim dengan sampel data historis < N pertandingan.
- **Model bukan jaminan hasil**: tampilkan sebagai estimasi statistik, bukan kepastian — relevan bila card ini nantinya dipakai user lain (disclaimer di UI).

---

## 9. Open Questions

1. Sumber nilai skuad: full-scrape Transfermarkt atau input manual admin per tim?
2. Berapa liga yang perlu didukung di fase 1 (memengaruhi ukuran job `ratings/recalculate`)?
3. Apakah dibutuhkan fitur pembanding "value bet" (model % vs implied odds) di card ini atau menu terpisah?
4. Siapa yang berwenang mengubah `ModelParameter` (β, ρ, home advantage) — admin panel atau file config?
