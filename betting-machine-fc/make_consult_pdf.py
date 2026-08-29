from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable

OUT = "/tmp/betting-machine-fc/Football_Betting_Model_Konsultasi.pdf"

styles = getSampleStyleSheet()

H1 = ParagraphStyle("H1x", parent=styles["Heading1"], fontSize=16, spaceAfter=6, textColor=colors.HexColor("#0B3D91"))
H2 = ParagraphStyle("H2x", parent=styles["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0B3D91"))
H3 = ParagraphStyle("H3x", parent=styles["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#333333"))
BODY = ParagraphStyle("BodyX", parent=styles["BodyText"], fontSize=9.5, leading=13.5, spaceAfter=4)
FORM = ParagraphStyle("FormX", parent=styles["Code"], fontSize=9, leading=12.5, backColor=colors.HexColor("#F4F6FA"), borderPadding=5, borderColor=colors.HexColor("#CCCCCC"), borderWidth=0.5, spaceBefore=3, spaceAfter=6)
SMALL = ParagraphStyle("SmallX", parent=styles["BodyText"], fontSize=8, leading=11, textColor=colors.HexColor("#555555"))
BULL = ParagraphStyle("BullX", parent=BODY, leftIndent=10, bulletIndent=2, spaceAfter=2)

def P(t, s=BODY):
    return Paragraph(t, s)

def F(t):
    return Paragraph(t, FORM)

def bullets(items):
    return [Paragraph(f"<bullet>&bull;</bullet>{i}", BULL) for i in items]

doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    leftMargin=18 * mm, rightMargin=18 * mm,
    topMargin=15 * mm, bottomMargin=15 * mm,
    title="Football Betting Model - Perumusan Masalah & Formula per Market",
    author="Hermes Agent",
)

E = []

E.append(P("Football Betting Recommendation Engine", ParagraphStyle("T", parent=styles["Title"], fontSize=19, textColor=colors.HexColor("#0B3D91"))))
E.append(P("Perumusan Masalah & Formula per Market Bet", ParagraphStyle("ST", parent=styles["BodyText"], fontSize=12, textColor=colors.HexColor("#444444"), spaceAfter=2)))
E.append(P("Dokumen konsultasi untuk pakar — pipeline saat ini, formula lengkap, diagnosis kelemahan, dan pertanyaan terbuka. Versi 1.0 — 2026-08-29. Stack: Dixon-Coles bivariate Poisson, sumber odds: 1xbit LineFeed (live), historical: football-data.co.uk. Implementasi: Python stdlib.", SMALL))
E.append(Spacer(1, 4))
E.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0B3D91")))
E.append(Spacer(1, 6))

# 1. Ringkasan
E.append(P("1. Ringkasan Eksekutif", H1))
E.append(P("Kami membangun pipeline rekomendasi taruhan sepakbola. Masalah utama yang kami identifikasi: <b>nilai λ (rata-rata gol) diturunkan dari odds pasar yang sama</b> yang kemudian dipakai menghitung EV — ini <b>circular reasoning</b>. Akibatnya model menghasilkan banyak pick longshot dengan EV positif palsu, tanpa satupun input kekuatan tim (form, xG, rekor H2H, cedera). Early backtest terhadap odds penutup (closing odds) menunjukkan pasar efisien: ROI −1.6% s.d. −3.8% untuk 1X2, −2.2% untuk O/U. Dokumen ini merumuskan masalah dan memaparkan seluruh formula agar pakar dapat memberi arahan."))
E.append(Spacer(1, 2))

# 2. Permasalahan
E.append(P("2. Perumusan Masalah", H1))
E.append(P("2.1 Alur pipeline saat ini (berjalan tiap 15 menit)", H2))
E.append(P("1. <b>Scrape odds</b> — 1xbit LineFeed: BestGamesExtZip (daftar 50 pertandingan aktif) → GetGameZip per pertandingan → ekstrak odds 1X2, O/U 2.5, Asian Handicap home & away."))
E.append(P("2. <b>Derive λ dari odds</b> — odds 1X2 dihilangkan marginnya → probabilitas fair → rasio kekuatan; odds O/U 2.5 → λ total. Lalu λ_home = λ_total × ratio, λ_away = λ_total × (1 − ratio).")) 
E.append(P("3. <b>Model Dixon-Coles</b> — bivariate Poisson dengan korelasi rendah (ρ = −0.13) → P(home/draw/away), P(over/under), P(BTTS), P(cover AH)."))
E.append(P("4. <b>EV</b> — EV = P_model × odds − 1 untuk setiap kandidat."))
E.append(P("5. <b>Filter</b> — hanya EV &gt; 0 dan odds ≥ 1.66 (config berjalan: min_ev = 0.0, min_probability = 0.0)."))
E.append(P("6. <b>Kelly</b> — fraksi Kelly dari probabilitas yang sama, cap 10%."))
E.append(Spacer(1, 2))
E.append(P("2.2 Masalah inti", H2))
E.append(P("<b>M1 — Circular reasoning (paling serius).</b> λ di-fit dari odds yang sama dengan odds yang dipakai menghitung EV. \"EV positif\" bukan edge sungguhan, melainkan selisih antar-market di bookie yang sama (1X2 vs AH vs O/U) dikali kesalahan model. Secara matematis, memakai odds untuk menghasilkan probabilitas lalu membandingkan probabilitas itu ke odds yang sama = identitas yang hampir tautologis; edge hanya muncul dari inkonsistensi internal bookie + noise."))
E.append(P("<b>M2 — Tanpa data tim.</b> Nol input kekuatan tim: form 5 laga, xG (Understat), rekor kandang/tandang, H2H, cedera, motivasi. Model tidak tahu Coventry vs Hull itu siapa."))
E.append(P("<b>M3 — Filter terlalu longgar.</b> min_ev 0.0 + min_probability 0.0 → semua longshot AH (odds 3.5–8.1, varians raksasa) lolos; output 169 pick per scan = noise. Catatan internal kami sendiri (README, \"PRO TIP — LONGSHOT NOISE\") merekomendasikan odds 1.66–3.00, EV ≥ 2%, |AH line| ≤ 2.0, gate hit-rate 45% — tetapi belum diterapkan di config yang berjalan."))
E.append(P("<b>M4 — Gate backtest tidak berjalan.</b> Spec punya \"Phase C gate\" (wajib ROI positif di backtest sebelum go-live) tapi worker hanya scan → dump → tidur; tidak ada pengecekan historis, tidak ada adaptasi."))
E.append(P("<b>M5 — Kelly circular & metrik menyesatkan.</b> Kelly dihitung dari probabilitas yang sama → selalu keluar cap 10%, \"roi_projected\" (EV × 100) dicap sebagai ROI padahal keduanya bukan return realistis."))
E.append(Spacer(1, 2))

# 3. Model inti
E.append(P("3. Model Probabilitas Inti (Dixon-Coles)", H1))
E.append(P("3.1 Distribusi Poisson", H2))
E.append(P("Probabilitas sebuah tim mencetak k gol dengan rata-rata λ:"))
E.append(F("P(X = k | λ) = e^(−λ) · λ^k / k!"))
E.append(P("3.2 Koreksi Dixon-Coles τ (korelasi skor rendah: 0-0, 1-0, 0-1, 1-1)", H2))
E.append(F("τ(0,0) = max(0, 1 − λh·λa·ρ)<br/>τ(1,0) = max(0, 1 + λa·ρ)<br/>τ(0,1) = max(0, 1 + λh·ρ)<br/>τ(1,1) = max(0, 1 − ρ)<br/>τ(x,y) = 1 untuk lainnya<br/>ρ = RHO_DEFAULT = −0.13 (korelasi negatif: skor rendah lebih sering dari Poisson independen)"))
E.append(P("3.3 Score matrix (hingga 10 gol per tim)", H2))
E.append(F("P(x, y) = Pois(x; λh) · Pois(y; λa) · τ(x, y)<br/>P_normalisasi(x, y) = P(x, y) / Σ<sub>u,v</sub> P(u, v)   (normalisasi karena τ membuat total ≠ 1)"))
E.append(P("3.4 Probabilitas hasil pertandingan", H2))
E.append(F("P(home) = Σ P(x,y) untuk x &gt; y<br/>P(draw) = Σ P(x,y) untuk x = y<br/>P(away) = Σ P(x,y) untuk x &lt; y"))
E.append(Spacer(1, 2))

# 4. Formula per market
E.append(P("4. Formula per Market Bet", H1))
E.append(P("Semua market memakai EV = P_model × odds − 1. Berikut formula detail tiap market."))

E.append(P("4.1 Market 1X2 (Match Result)", H2))
E.append(P("Probabilitas: P(home), P(draw), P(away) dari §3.4. Probabilitas implisit & penghapusan margin:"))
E.append(F("Implied(o) = 1 / o<br/>Remove_margin: p<sub>fair,i</sub> = (1/o<sub>i</sub>) / Σ<sub>j</sub>(1/o<sub>j</sub>)<br/>EV = p<sub>model</sub> × odds − 1"))
E.append(P("Kandidat bet: Home / Draw / Away. Filter: EV &gt; min_ev, odds ≥ min_odds (1.66)."))

E.append(P("4.2 Market Asian Handicap (AH)", H2))
E.append(P("Handicap home negatif = home memberi gol (mis. −1.5 = home harus menang 2+). Handicap away positif = away menerima gol. Quarter-line dipecah menjadi dua half-leg:"))
E.append(F("_sub_lines(h): jika h kelipatan 0.5 → [h, h] (stake utuh)<br/>jika quarter (mis. ±0.25, ±0.75) → [h − 0.25, h + 0.25], tiap leg 50% stake"))
E.append(P("Payout per leg (home perspective, margin = selisih gol home − away):"))
E.append(F("adj = margin + leg<br/>adj &gt; 0 → payout = odds<br/>adj = 0 → push, payout = 1.0<br/>adj &lt; 0 → payout = 0<br/>Payout total = rata-rata payout kedua leg"))
E.append(P("Away perspective: adj = −margin + leg (away +0.5 menang saat draw). EV:"))
E.append(F("EV_ah(home) = Σ<sub>x,y</sub> P(x,y) · payout_home(h, odds, x − y) − 1<br/>EV_ah_away(away) = Σ<sub>x,y</sub> P(x,y) · payout_away(a, odds, x − y) − 1"))
E.append(P("Tabel payout terverifikasi (home −0.75 @ odds 1.95): margin +2 → 1.95; +1 → 1.475; 0 → 0.0; −1 → 0.0. Away +0.25 @1.95 saat draw → 1.475 (satu leg menang, satu push); away +0.75 @1.95 saat draw → 1.95.", SMALL))

E.append(P("4.3 Market Over/Under Total Goals (O/U)", H2))
E.append(P("λ_total = λh + λa. Strict probability (push-aware untuk garis integer):"))
E.append(F("over_prob(line) = 1 − Σ<sub>k=0..floor(line)</sub> Pois(k; λt)<br/>under_prob(line) = Σ<sub>k=0..floor(line)−1</sub> Pois(k; λt)  (integer line: total == line adalah PUSH)<br/>quarter line 2.25/2.75 → split [line−0.25, line+0.25], tiap leg 50%"))
E.append(P("Expected value total (menangani push integer + split quarter):"))
E.append(F("Leg integer i, sisi over: ret = odds·(1 − F(i)) + 1·pmf(i)  (push mengembalikan stake)<br/>Leg integer i, sisi under: ret = odds·F(i−1)<br/>Leg non-integer (floor i): over → odds·(1 − F(i)); under → odds·F(i)<br/>EV = Σ ret_leg × bobot − 1"))
E.append(P("Estimasi fair line dari odds (dipakai di lam_from_odds):"))
E.append(F("fair_over = implied(o_over) / (implied(o_over) + implied(o_under))<br/>fit_total_from_ou: cari λ_total ∈ [0.1, 6.0] yang meminimalkan |over_prob(λt/2, λt/2) − fair_over|"))

E.append(P("4.4 Market BTTS (Both Teams To Score)", H2))
E.append(F("P(BTTS) = Σ P(x,y) untuk x ≥ 1 dan y ≥ 1   (dinormalisasi)<br/>EV = P(BTTS) × odds_yes − 1"))

E.append(P("4.5 Derivasi λ dari odds (CURRENT — sumber masalah)", H2))
E.append(F("p_h, p_d, p_a = remove_margin([odds_home, odds_draw, odds_away])<br/>λ_total, fair_over = fit_total_from_ou(odds_over, odds_under, 2.5)<br/>ratio = p_h / (p_h + p_a)<br/>λ_home = λ_total × ratio<br/>λ_away = λ_total × (1 − ratio)"))
E.append(P("<b>Ini yang membuat pipeline circular:</b> λ (input model) diturunkan dari odds (output pembanding EV)."))

E.append(P("4.6 Derivasi λ dari kekuatan tim (PROPOSED)", H2))
E.append(F("λ_home = (att_h / league_avg) × (def_a / league_avg) × league_avg × home_adv<br/>λ_away = (att_a / league_avg) × (def_h / league_avg) × league_avg<br/>home_adv ≈ 1.08<br/>att/def di-fit via MLE Dixon-Coles dari data historis (football-data.co.uk = BACKTEST GOLD: closing+opening odds & hasil)"))
E.append(P("Blending (opsional): λ_blend = w·λ_strength + (1−w)·λ_odds, w ∈ [0,1]. CLV sebagai metrik edge:"))
E.append(F("CLV% = (implied(odds_close) − implied(odds_open)) × 100"))

E.append(P("4.7 Bankroll & Staking (Kelly)", H2))
E.append(F("f* = (b·p − (1 − p)) / b,  b = odds − 1<br/>dibatasi f* ≤ 0.10 (10%)<br/>flat stake = bankroll × stake_pct (config: 2%)"))
E.append(P("Catatan: kelly_pct & roi_projected saat ini dihitung dari probabilitas model yang bersumber dari odds yang sama → nilainya tidak bermakna statistik sampai λ independen.", SMALL))
E.append(Spacer(1, 2))

# 5. Sumber data
E.append(P("5. Sumber Data & Parameter", H1))
E.extend(bullets([
    "<b>Live odds:</b> 1xbit LineFeed (BestGamesExtZip / GetGameZip), no auth, gzip. Grup: G1=1X2, G2 T=7=AH home (P=handicap signed), T=8=AH away, G17=O/U (T=9 over, T=10 under), G11=correct score.",
    "<b>Historical:</b> football-data.co.uk (CSV per liga/season: closing+opening odds + hasil). EPL 2024/25: 380 rows, kolom lengkap.",
    "<b>Parameter:</b> MAX_GOALS=10, RHO_DEFAULT=−0.13, min_odds=1.66, min_ev=0.0 (longgar), bankroll=1000, stake_pct=0.02, scan interval 15 menit, count=50 match.",
]))

# 6. Diagnosis output live
E.append(P("6. Diagnosis Output Live (kenapa keliatan naif)", H1))
E.extend(bullets([
    "Contoh pick asli: <b>Coventry vs Hull — AH Home −1.50 @3.625, prob 0.4038, EV +0.46, kelly 10%, roi_projected 46%</b>. Probabilitas ini bukan dari analisa kekuatan Coventry — melainkan invert odds market yang sama + koreksi Dixon-Coles.",
    "169 pick lolos per scan — semuanya longshot AH / O-U dengan odds ≥1.66, variance tinggi; tidak ada batas jumlah pick per match (satu match bisa keluar 5+ pick).",
    "Backtest EPL 2024/25 (closing odds): 1X2 λ-dari-odds hit 50.0% ROI −1.6%; strength-based 1X2 ROI −3.8%; OU −2.2% → closing odds efisien. Edge sejati hanya dari sinyal independen (xG, line-shopping/CLV, timing odds).",
    "Line movement: opening vs closing odds berbeda di 161/200 baris → indikasi CLV bisa diukur.",
]))

# 7. Arah perbaikan
E.append(P("7. Arah Perbaikan yang Diusulkan", H1))
E.extend(bullets([
    "<b>λ independen:</b> fit strength rating (att/def MLE Dixon-Coles) dari football-data.co.uk per liga; odds hanya pembanding, bukan input.",
    "<b>Filter ketat:</b> odds 1.66–3.00; EV ≥ 2%; min_probability 15–20%; max 1–2 pick per match; |AH line| ≤ 1.5; drop market dengan hit-rate &lt; 45% di avg odds &gt; 2.5.",
    "<b>Backtest gate wajib:</b> model tidak go-live jika ROI backtest ≤ 0; regenerate bulanan dari data terbaru.",
    "<b>Staking:</b> flat 2% sampai sampel ≥ 200, baru fractional Kelly cap 10%.",
    "<b>Output:</b> tiap pick menyertakan analisa (λ_home/λ_away, prob matrix, alasan strength/form/xG) bukan hanya angka EV.",
]))

# 8. Pertanyaan untuk pakar
E.append(P("8. Pertanyaan Terbuka untuk Pakar", H1))
E.extend(bullets([
    "Q1 — Bagaimana praktik terbaik mem-fit λ independen (MLE Dixon-Coles) dengan data terbatas? Berapa minimum observasi per tim per liga? Weighting decay waktu (eksponensial) yang disarankan?",
    "Q2 — Apakah bivariate Poisson + τ sudah cukup untuk market AH/O-U, atau perlu model alternatif (bivariate negative binomial, copula) untuk overdispersion?",
    "Q3 — Ambang filter apa yang menurut pakar optimal: EV cutoff, min probability, batas odds, max pick per match — agar menghindari longshot noise tanpa membunuh edge?",
    "Q4 — Bagaimana menilai edge secara statistik: cukup CLV + backtest ROI, atau perlu metrik lain (Brier, log-loss, calibration) dengan ukuran sampel berapa?",
    "Q5 — Strategi staking yang tepat untuk banyak pick berkorelasi (beberapa pick dari match sama) — flat, fractional Kelly, atau klasterisasi?",
    "Q6 — Sumber data kekuatan tim terbaik yang gratis: Understat xG, FBref, atau cukup football-data.co.uk? Bagaimana menangani cedera/rotasi?",
    "Q7 — Apakah 0.08s delay per match & 50 match/scan sudah memadai untuk menghindari rate limit 1xbit tanpa ketinggalan closing odds?",
]))

doc.build(E)
print("PDF written:", OUT)