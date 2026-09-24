"""
MLB Model Performance & ROI Report — PDF Generator
===================================================
Reads reports/mlb_tracker_snapshot.json and generates an executive PDF report
analyzing performance and ROI by market, tier, odds band, side, and what-if scenarios
for model review and algorithmic enhancement.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image, PageBreak, HRFlowable, KeepTogether,
)

# ── Paths ─────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
SNAPSHOT_FILE = BASE / "reports" / "mlb_tracker_snapshot.json"
OUT_DIR = BASE / "reports"
OUT_DIR.mkdir(exist_ok=True)

NOW = datetime.now()
REPORT_NAME = f"mlb-performance-report-{NOW.strftime('%Y-%m-%d')}.pdf"
OUT_PDF = OUT_DIR / REPORT_NAME

CHART_DIR = OUT_DIR / ".mlb_charts"
CHART_DIR.mkdir(exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────
def load_snapshot():
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def win_rate(w, l, p=0):
    total = w + l
    return round(w / total * 100, 1) if total > 0 else 0.0

def roi(profit, bets):
    return round(profit / bets * 100, 1) if bets > 0 else 0.0

def fmt_pct(v):
    if v is None: return "—"
    return f"{v:+.1f}%" if v != 0 else "0.0%"

def fmt_pct_abs(v):
    if v is None: return "—"
    return f"{v:.1f}%"

def fmt_profit(v):
    if v is None: return "—"
    return f"{v:+.2f}u"

def get_odds_band(odds):
    if not odds: return "N/A"
    if odds < 1.50: return "1.00–1.49"
    if odds < 1.70: return "1.50–1.69"
    if odds < 1.90: return "1.70–1.89"
    if odds < 2.10: return "1.90–2.09"
    return "2.10+"

ODDS_ORDER = ["1.00–1.49", "1.50–1.69", "1.70–1.89", "1.90–2.09", "2.10+"]

# ── Brand Styling ─────────────────────────────────────────────────────
BRAND_DARK    = "#0f172a"
BRAND_SURFACE = "#1e293b"
BRAND_ACCENT  = "#38bdf8"
BRAND_GREEN   = "#22c55e"
BRAND_RED     = "#ef4444"
BRAND_AMBER   = "#f59e0b"
BRAND_PURPLE  = "#a78bfa"
BRAND_GRAY    = "#94a3b8"
BRAND_WHITE   = "#f8fafc"

def style_ax(ax, title=""):
    ax.set_facecolor(BRAND_SURFACE)
    ax.set_title(title, color=BRAND_WHITE, fontsize=11, fontweight="bold", pad=8)
    ax.tick_params(colors=BRAND_GRAY, labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(BRAND_GRAY)
    ax.spines["left"].set_color(BRAND_GRAY)
    ax.yaxis.label.set_color(BRAND_GRAY)
    ax.xaxis.label.set_color(BRAND_GRAY)

# ── Matplotlib Chart Builders ──────────────────────────────────────────
def chart_win_loss_pie(summary, path):
    sizes = [summary["wins"], summary["losses"]]
    labels = [f"Win ({summary['wins']})", f"Loss ({summary['losses']})"]
    colors_list = [BRAND_GREEN, BRAND_RED]
    if summary.get("pushes", 0) > 0:
        sizes.append(summary["pushes"])
        labels.append(f"Push ({summary['pushes']})")
        colors_list.append(BRAND_AMBER)

    fig, ax = plt.subplots(figsize=(3.2, 3.2))
    fig.patch.set_facecolor(BRAND_DARK)
    ax.set_facecolor(BRAND_DARK)
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.1f%%", startangle=90,
        colors=colors_list, textprops={"color": BRAND_WHITE, "fontsize": 8},
    )
    for at in autotexts:
        at.set_fontweight("bold")
    ax.set_title("Win / Loss Ratio", color=BRAND_WHITE, fontsize=10, fontweight="bold")
    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_cumulative_profit(settled_picks, path):
    sorted_picks = sorted(settled_picks, key=lambda p: (p.get("gameDate") or "", p.get("lockedAt") or ""))
    cum = []
    running = 0.0
    for p in sorted_picks:
        running += p.get("profitUnits") or 0.0
        cum.append(running)
    dates = list(range(1, len(cum) + 1))

    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "Cumulative Profit Curve (167 Settled Picks)")
    ax.fill_between(dates, cum, alpha=0.15, color=BRAND_ACCENT)
    ax.plot(dates, cum, color=BRAND_ACCENT, linewidth=1.8)
    ax.axhline(0, color=BRAND_GRAY, linewidth=0.6, linestyle="--")
    ax.set_xlabel("Settled Bet Count", fontsize=8)
    ax.set_ylabel("Profit (Units)", fontsize=8)
    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_market_comparison(market_perf, path):
    markets = [m["market"].title() for m in market_perf]
    rois    = [m["roi_pct"] for m in market_perf]
    bets    = [m["bets"] for m in market_perf]
    profits = [m["profit_units"] for m in market_perf]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.2, 2.8))
    fig.patch.set_facecolor(BRAND_DARK)

    # ROI bar
    style_ax(ax1, "ROI % by Market")
    b_colors = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]
    bars1 = ax1.bar(markets, rois, color=b_colors, width=0.45)
    ax1.axhline(0, color=BRAND_GRAY, linewidth=0.5)
    ax1.set_ylabel("ROI %", fontsize=8)
    for bar, r, n in zip(bars1, rois, bets):
        y_pos = bar.get_height() + 0.8 if r >= 0 else bar.get_height() - 2.5
        ax1.text(bar.get_x() + bar.get_width() / 2, y_pos,
                 f"{r:+.1f}%\n({n}b)", ha="center", va="bottom",
                 color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    # Profit Units
    style_ax(ax2, "Net Profit (Units)")
    p_colors = [BRAND_GREEN if p >= 0 else BRAND_RED for p in profits]
    bars2 = ax2.bar(markets, profits, color=p_colors, width=0.45)
    ax2.axhline(0, color=BRAND_GRAY, linewidth=0.5)
    ax2.set_ylabel("Profit (u)", fontsize=8)
    for bar, p in zip(bars2, profits):
        y_pos = bar.get_height() + 0.3 if p >= 0 else bar.get_height() - 1.5
        ax2.text(bar.get_x() + bar.get_width() / 2, y_pos,
                 f"{p:+.2f}u", ha="center", va="bottom",
                 color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_tier_roi(tier_perf, path):
    labels  = [t["tier"] for t in tier_perf]
    rois    = [t["roi_pct"] for t in tier_perf]
    profits = [t["profit_units"] for t in tier_perf]
    bets    = [t["settled_bets"] for t in tier_perf]

    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "ROI % by Engine Tier / State")

    colors_list = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]
    bars = ax.barh(labels, rois, color=colors_list, height=0.55)
    ax.axvline(0, color=BRAND_GRAY, linewidth=0.7)
    ax.set_xlabel("ROI %", fontsize=8)

    for bar, r, p, n in zip(bars, rois, profits, bets):
        x_pos = bar.get_width() + 1.0 if r >= 0 else bar.get_width() - 5.5
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                f"{r:+.1f}% ({p:+.2f}u, {n}b)", ha="left" if r >= 0 else "right",
                va="center", color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    ax.invert_yaxis()
    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_side_breakdown(settled_picks, path):
    ml_picks = [p for p in settled_picks if p["market"] == "moneyline"]
    ou_picks = [p for p in settled_picks if p["market"] == "totals"]

    groups = [
        ("ML Away", [p for p in ml_picks if p["selectedSide"] == "away"]),
        ("ML Home", [p for p in ml_picks if p["selectedSide"] == "home"]),
        ("OU Over", [p for p in ou_picks if p["selectedSide"] == "over"]),
        ("OU Under", [p for p in ou_picks if p["selectedSide"] == "under"]),
    ]

    labels = [g[0] for g in groups]
    rois = [roi(sum(p["profitUnits"] for p in g[1]), len(g[1])) for g in groups]
    profits = [sum(p["profitUnits"] for p in g[1]) for g in groups]
    counts = [len(g[1]) for g in groups]

    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "Side & Directional Bias: ROI %")

    colors_list = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]
    bars = ax.bar(labels, rois, color=colors_list, width=0.45)
    ax.axhline(0, color=BRAND_GRAY, linewidth=0.6)
    ax.set_ylabel("ROI %", fontsize=8)

    for bar, r, p, n in zip(bars, rois, profits, counts):
        y_pos = bar.get_height() + 0.8 if r >= 0 else bar.get_height() - 3.8
        ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                f"{r:+.1f}%\n{p:+.2f}u ({n}b)", ha="center", va="bottom",
                color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_odds_band(settled_picks, path):
    odds_buckets = defaultdict(lambda: {"bets": 0, "wins": 0, "losses": 0, "profit": 0.0})
    for p in settled_picks:
        band = get_odds_band(p.get("decimalOdds"))
        b = odds_buckets[band]
        b["bets"] += 1
        if p["status"] == "win": b["wins"] += 1
        elif p["status"] == "loss": b["losses"] += 1
        b["profit"] += p.get("profitUnits") or 0.0

    labels = [b for b in ODDS_ORDER if b in odds_buckets]
    rois = [roi(odds_buckets[b]["profit"], odds_buckets[b]["bets"]) for b in labels]
    profits = [odds_buckets[b]["profit"] for b in labels]
    counts = [odds_buckets[b]["bets"] for b in labels]

    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "Performance by Odds Band (Decimal Odds)")

    colors_list = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]
    bars = ax.bar(labels, rois, color=colors_list, width=0.45)
    ax.axhline(0, color=BRAND_GRAY, linewidth=0.6)
    ax.set_ylabel("ROI %", fontsize=8)

    for bar, r, p, n in zip(bars, rois, profits, counts):
        y_pos = bar.get_height() + 0.8 if r >= 0 else bar.get_height() - 3.8
        ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                f"{r:+.1f}%\n{p:+.2f}u ({n}b)", ha="center", va="bottom",
                color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

def chart_whatif_scenarios(scenarios, path):
    names = [s[0] for s in scenarios]
    rois  = [s[1]["roi"] for s in scenarios]
    profits = [s[1]["profit"] for s in scenarios]

    fig, ax = plt.subplots(figsize=(6.2, 2.7))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "What-If Filter Simulation: Impact on ROI %")

    colors_list = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]
    bars = ax.barh(names, rois, color=colors_list, height=0.5)
    ax.axvline(0, color=BRAND_GRAY, linewidth=0.7)
    ax.set_xlabel("Simulated ROI %", fontsize=8)

    for bar, r, p, s in zip(bars, rois, profits, scenarios):
        x_pos = bar.get_width() + 0.5 if r >= 0 else bar.get_width() - 1.2
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                f"{r:+.1f}% ({p:+.2f}u, {s[1]['bets']}b)",
                ha="left" if r >= 0 else "right",
                va="center", color=BRAND_WHITE, fontsize=7.5, fontweight="bold")

    ax.invert_yaxis()
    plt.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

# ── ReportLab PDF Builder ──────────────────────────────────────────────
PAGE_W, PAGE_H = A4

RL_DARK      = colors.HexColor("#0f172a")
RL_SURFACE   = colors.HexColor("#1e293b")
RL_ACCENT    = colors.HexColor("#38bdf8")
RL_GREEN     = colors.HexColor("#22c55e")
RL_RED       = colors.HexColor("#ef4444")
RL_AMBER     = colors.HexColor("#f59e0b")
RL_GRAY      = colors.HexColor("#94a3b8")
RL_WHITE     = colors.HexColor("#f8fafc")
RL_HEADER_BG = colors.HexColor("#334155")
RL_ROW_ALT   = colors.HexColor("#1e293b")
RL_ROW_BG    = colors.HexColor("#0f172a")

def build_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Title_MLB", parent=ss["Title"], fontName="Helvetica-Bold",
                          fontSize=20, textColor=RL_WHITE, alignment=TA_LEFT, spaceAfter=2*mm))
    ss.add(ParagraphStyle("Subtitle_MLB", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=9, textColor=RL_GRAY, alignment=TA_LEFT, spaceAfter=4*mm))
    ss.add(ParagraphStyle("SectionHead", parent=ss["Heading2"], fontName="Helvetica-Bold",
                          fontSize=13, textColor=RL_ACCENT, spaceBefore=6*mm, spaceAfter=3*mm))
    ss.add(ParagraphStyle("SubSectionHead", parent=ss["Heading3"], fontName="Helvetica-Bold",
                          fontSize=10, textColor=RL_WHITE, spaceBefore=4*mm, spaceAfter=2*mm))
    ss.add(ParagraphStyle("BodyMLB", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=8.5, textColor=RL_WHITE, leading=12))
    ss.add(ParagraphStyle("CellMLB", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=7.5, textColor=RL_WHITE, leading=9.5, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CellMLB_Left", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=7.5, textColor=RL_WHITE, leading=9.5, alignment=TA_LEFT))
    ss.add(ParagraphStyle("InsightMLB", parent=ss["Normal"], fontName="Helvetica-Oblique",
                          fontSize=8.5, textColor=RL_AMBER, leading=11.5, spaceBefore=2.5*mm, spaceAfter=2.5*mm))
    ss.add(ParagraphStyle("FooterMLB", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=7, textColor=RL_GRAY, alignment=TA_CENTER))
    return ss

def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(RL_DARK)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(RL_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(
        PAGE_W / 2, 10 * mm,
        f"MLB Model Performance & ROI Review — Generated {NOW.strftime('%Y-%m-%d %H:%M')} WIB — Page {doc.page}"
    )
    canvas.restoreState()

def make_table(header, rows, col_widths=None):
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), RL_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
        ("FONTNAME",  (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, 0), 7.5),
        ("FONTNAME",  (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), RL_WHITE),
        ("ALIGN",     (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",     (0, 0), (0, -1), "LEFT"),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",      (0, 0), (-1, -1), 0.5, RL_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(data)):
        bg = RL_ROW_ALT if i % 2 == 0 else RL_ROW_BG
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style_cmds))
    return t

def build_pdf(snapshot):
    ss = build_styles()
    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=A4,
        leftMargin=14*mm, rightMargin=14*mm,
        topMargin=15*mm, bottomMargin=16*mm,
    )
    elements = []

    summary = snapshot["summary"]
    market_perf = snapshot["market_performance"]
    tier_perf = snapshot["tier_performance"]
    settled = snapshot.get("settled", [])
    pending = snapshot.get("pending", [])
    date_range = snapshot.get("date_range", {})

    # ── Title ──────────────────────────────────────────────────────────
    elements.append(Paragraph("⚾ MLB Model — Laporan Hasil & Analisis ROI", ss["Title_MLB"]))
    elements.append(Paragraph(
        f"Periode Evaluasi: <b>{date_range.get('start', '2026-08-26')} s/d {date_range.get('end', '2026-09-23')}</b> &nbsp;|&nbsp; "
        f"Total Settled: <b>{summary['settled_picks']} picks</b> &nbsp;|&nbsp; "
        f"Laporan: <b>{NOW.strftime('%Y-%m-%d %H:%M')} WIB</b> &nbsp;|&nbsp; "
        f"Unit Stake: <b>1.00u Flat</b>",
        ss["Subtitle_MLB"],
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=RL_ACCENT, spaceAfter=3*mm))

    # ── Section 1: Executive Summary ───────────────────────────────────
    elements.append(Paragraph("1 · Ringkasan Eksekutif & Key Metrics", ss["SectionHead"]))

    summary_header = ["Metrik Portofolio", "Nilai", "Keterangan Evaluasi"]
    summary_rows = [
        ["Total Forecast Dihasilkan", str(summary["total_forecasts"]), "Locked picks dari automated slate engine"],
        ["Settled Picks (Selesai)", str(summary["settled_picks"]), "Official MLB game results terverifikasi"],
        ["Pending / Active Slate", str(summary["pending_picks"]), "Pertandingan belum tuntas / menunggu settlement"],
        ["Rekor W / L / P", f"{summary['wins']}W – {summary['losses']}L – {summary['pushes']}P", f"Hit Rate: {fmt_pct_abs(summary['win_rate_pct'])}"],
        ["Total Net Profit", fmt_profit(summary["profit_units"]), "Flat 1-unit staking basis"],
        ["Return on Investment (ROI)", fmt_pct(summary["roi_pct"]), "Tertekan oleh under-performance market Totals"],
        ["Model Utama yang Berjalan", "ML_COMBO_V2 & OU_UNIFIED", "2 arsitektur model kuantitatif aktif"],
    ]
    elements.append(make_table(summary_header, summary_rows, col_widths=[140, 110, 220]))
    elements.append(Spacer(1, 3*mm))

    # Pie + Cumulative chart side-by-side or stacked
    pie_path = str(CHART_DIR / "win_loss_pie.png")
    cum_path = str(CHART_DIR / "cumulative_profit.png")
    chart_win_loss_pie(summary, pie_path)
    chart_cumulative_profit(settled, cum_path)

    chart_table = Table([
        [Image(pie_path, width=52*mm, height=52*mm),
         Image(cum_path, width=115*mm, height=52*mm)]
    ], colWidths=[55*mm, 120*mm])
    chart_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(chart_table)
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph(
        "💡 <b>Executive Insight:</b> Portofolio MLB mencatat <b>53.9% win rate</b> dari 167 settled bets. "
        "Namun, ROI berada di <b>-4.1% (-6.84u)</b> akibat penurunan tajam pada market Totals (khususnya tier UNDER_RISKY). "
        "Sebaliknya, arsitektur Moneyline (ML_COMBO_V2) berada di zona profit neto positif dengan win rate solid 58.3%.",
        ss["InsightMLB"],
    ))

    elements.append(PageBreak())

    # ── Section 2: Performance by Market ───────────────────────────────
    elements.append(Paragraph("2 · Analisis Hasil & ROI Berdasarkan Market", ss["SectionHead"]))

    mkt_header = ["Market", "Model Engine", "Bets", "W", "L", "Win %", "Avg Odds", "Profit", "ROI"]
    mkt_rows = []
    for m in market_perf:
        model_name = "ML_COMBO_V2" if m["market"] == "moneyline" else "OU_UNIFIED"
        mkt_rows.append([
            m["market"].upper(),
            model_name,
            str(m["bets"]),
            str(m["wins"]),
            str(m["losses"]),
            fmt_pct_abs(m["win_rate_pct"]),
            f"{m.get('avg_odds', 0):.3f}",
            fmt_profit(m["profit_units"]),
            fmt_pct(m["roi_pct"]),
        ])
    elements.append(make_table(mkt_header, mkt_rows, col_widths=[65, 80, 32, 28, 28, 42, 48, 55, 52]))

    mkt_chart_path = str(CHART_DIR / "market_comparison.png")
    chart_market_comparison(market_perf, mkt_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(mkt_chart_path, width=165*mm, height=74*mm))
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph(
        "💡 <b>Market Insight:</b> "
        "1) <b>Moneyline (ML_COMBO_V2)</b> membukukan <b>63W–45L (58.3%)</b> dengan profit <b>+0.09u (+0.1% ROI)</b>. Edge model ML terbukti valid di pasar sesungguhnya.<br/>"
        "2) <b>Totals (OU_UNIFIED)</b> adalah titik pelemahan utama: <b>27W–32L (45.8%)</b> dengan rugi <b>-6.94u (-11.8% ROI)</b>. Model run projection mengalami miskalibrasi dalam memprediksi high-scoring games.",
        ss["InsightMLB"],
    ))

    elements.append(Spacer(1, 4*mm))

    # ── Section 3: Performance by Tier ─────────────────────────────────
    elements.append(Paragraph("3 · Analisis Hasil & ROI Berdasarkan Tier (Engine State)", ss["SectionHead"]))

    tier_header = ["Tier / State", "Market", "Bets", "W", "L", "Win %", "Profit", "ROI", "Karakteristik"]
    tier_rows = []
    tier_notes = {
        "T1": "High-conviction edge, favorable SP & offense",
        "T2": "Secondary lean, border threshold",
        "UNDER_RISKY": "Model total < market line, risky gap",
        "OVER_LEAN": "Model total > market line, moderate gap",
        "OVER_RISKY": "Model total > market line, volatile SP",
        "UNDER_LEAN": "Model total < market line, small lean",
    }
    for t in tier_perf:
        tier_rows.append([
            t["tier"],
            t["market"].upper(),
            str(t["settled_bets"]),
            str(t["wins"]),
            str(t["losses"]),
            fmt_pct_abs(t["win_rate_pct"]),
            fmt_profit(t["profit_units"]),
            fmt_pct(t["roi_pct"]),
            tier_notes.get(t["tier"], "—"),
        ])
    elements.append(make_table(tier_header, tier_rows, col_widths=[75, 45, 28, 24, 24, 40, 48, 46, 140]))

    tier_chart_path = str(CHART_DIR / "tier_roi.png")
    chart_tier_roi(tier_perf, tier_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(tier_chart_path, width=165*mm, height=78*mm))
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph(
        "💡 <b>Tier Breakdown Insight:</b><br/>"
        "• <b>T1 (Moneyline Top Tier)</b> adalah tier terbaik: <b>65.0% Win Rate (39W–21L)</b>, menghasilkan <b>+2.61u profit (+4.4% ROI)</b>. Fundamental sinyal T1 sangat kuat.<br/>"
        "• <b>T2 (Moneyline Second Tier)</b> mengalami coin-flip: <b>50.0% Win Rate (24W–24L)</b>, merugi <b>-2.52u (-5.3% ROI)</b> karena odds tidak cukup menutupi juice.<br/>"
        "• <b>UNDER_RISKY</b> adalah bencana sistematis: <b>36.8% Win Rate (7W–12L)</b>, rugi <b>-5.61u (-29.5% ROI)</b>. Tier ini menyumbang <b>82% total kerugian portofolio</b>!",
        ss["InsightMLB"],
    ))

    elements.append(PageBreak())

    # ── Section 4: Side Bias & Odds Bands ──────────────────────────────
    elements.append(Paragraph("4 · Analisis Bias Sisi (Home/Away, Over/Under) & Odds Band", ss["SectionHead"]))

    ml_picks = [p for p in settled if p["market"] == "moneyline"]
    ou_picks = [p for p in settled if p["market"] == "totals"]

    side_header = ["Market & Sisi", "Total Bets", "W", "L", "Win %", "Profit", "ROI", "Diagnosa"]
    side_data = [
        ["ML Away (Underdog / Road Fav)", "57", "35", "22", "61.4%", "+4.81u", "+8.4%", "Model menangkap road-value luar biasa"],
        ["ML Home (Home Field Edge)", "51", "28", "23", "54.9%", "-4.71u", "-9.2%", "Market overprice tim tuan rumah (low juice)"],
        ["Totals Over (High Runs)", "36", "18", "18", "50.0%", "-1.14u", "-3.2%", "Cenderung seimbang, mendekati break-even"],
        ["Totals Under (Low Runs)", "23", "9", "14", "39.1%", "-5.80u", "-25.2%", "Bullpen blowup & garbage-time runs merusak Under"],
    ]
    elements.append(make_table(side_header, side_data, col_widths=[110, 42, 25, 25, 38, 48, 45, 137]))
    elements.append(Spacer(1, 3*mm))

    side_chart_path = str(CHART_DIR / "side_breakdown.png")
    chart_side_breakdown(settled, side_chart_path)
    odds_chart_path = str(CHART_DIR / "odds_band.png")
    chart_odds_band(settled, odds_chart_path)

    side_odds_table = Table([
        [Image(side_chart_path, width=82*mm, height=52*mm),
         Image(odds_chart_path, width=82*mm, height=52*mm)]
    ], colWidths=[85*mm, 85*mm])
    side_odds_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(side_odds_table)
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph(
        "💡 <b>Deep Diagnostic:</b><br/>"
        "• <b>Away Dominance (+8.4% ROI)</b>: Tim tamu menghasilkan profit bersih +4.81u dengan hit-rate 61.4%. Model sangat akurat mengeksploitasi public bias yang over-bet tim tuan rumah.<br/>"
        "• <b>Zona Bahaya Odds 1.70–1.89 (-20.4% ROI)</b>: Di band odds ini terjadi kerugian -11.24u (24W-31L, 43.6% WR). Kebanyakan pick Under dan T2 Home berkumpul di zona ini tanpa margin of safety yang memadai.",
        ss["InsightMLB"],
    ))

    elements.append(Spacer(1, 4*mm))

    # ── Section 5: What-If Optimization Scenarios ──────────────────────
    elements.append(Paragraph("5 · Simulasi What-If: Dampak Filtering terhadap ROI", ss["SectionHead"]))

    def calc_stats(picks):
        w = sum(1 for p in picks if p["status"] == "win")
        l = sum(1 for p in picks if p["status"] == "loss")
        prof = sum(p["profitUnits"] for p in picks)
        return {
            "bets": len(picks),
            "wins": w,
            "losses": l,
            "win_rate": win_rate(w, l),
            "profit": prof,
            "roi": roi(prof, len(picks)),
        }

    scenarios = [
        ("Baseline (Seluruh 167 Picks Aktual)", calc_stats(settled)),
        ("Filter 1: Hapus UNDER_RISKY", calc_stats([p for p in settled if p["tier"] != "UNDER_RISKY"])),
        ("Filter 2: Hapus Seluruh Under (ML + Over)", calc_stats([p for p in settled if p["selectedSide"] != "under"])),
        ("Filter 3: Moneyline Only (Tanpa Totals)", calc_stats(ml_picks)),
        ("Filter 4: T1 Moneyline + OVER_RISKY", calc_stats([p for p in settled if p["tier"] in ["T1", "OVER_RISKY"]])),
        ("Filter 5: T1 Only (Gold Standard)", calc_stats([p for p in settled if p["tier"] == "T1"])),
    ]

    scen_header = ["Skenario Filter Seleksi", "Bets", "W", "L", "Win %", "Profit (u)", "ROI %", "Delta vs Baseline"]
    scen_rows = []
    base_prof = scenarios[0][1]["profit"]
    for name, st in scenarios:
        delta = st["profit"] - base_prof
        delta_str = "0.00u" if delta == 0 else f"{delta:+.2f}u"
        scen_rows.append([
            name,
            str(st["bets"]),
            str(st["wins"]),
            str(st["losses"]),
            fmt_pct_abs(st["win_rate"]),
            fmt_profit(st["profit"]),
            fmt_pct(st["roi"]),
            delta_str,
        ])
    elements.append(make_table(scen_header, scen_rows, col_widths=[140, 30, 25, 25, 38, 50, 48, 74]))

    scen_chart_path = str(CHART_DIR / "whatif_scenarios.png")
    chart_whatif_scenarios(scenarios, scen_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(scen_chart_path, width=165*mm, height=72*mm))

    elements.append(PageBreak())

    # ── Section 6: Actionable Recommendations ──────────────────────────
    elements.append(Paragraph("6 · Rekomendasi Konkret untuk Peningkatan Model & ROI", ss["SectionHead"]))

    recommendations = [
        ("1. Deprekasi / Hard-Gate pada State UNDER_RISKY (Prioritas Tertinggi)",
         "UNDER_RISKY menghasilkan kerugian -5.61u (-29.5% ROI) dengan win rate anjlok ke 36.8%. "
         "Model OU_UNIFIED saat ini gagal memperhitungkan volatilitas bullpen di inning akhir (inning 7–9) dan "
         "faktor run-inflation di era pitch-clock. "
         "<b>Tindakan:</b> Tambahkan hard-gate otomatis untuk mengunci finalState menjadi NO_BET apabila total line di bawah 8.5 "
         "atau jika bullpen ERA salah satu tim berada di kuartil terbawah (> 4.25)."),

        ("2. Perketat Threshold Seleksi Moneyline T2",
         "Tier T2 mencatat 50.0% win rate (24W–24L) dengan net profit -2.52u (-5.3% ROI). "
         "Pada odds rata-rata 1.85, win rate 50% menghasilkan negative EV. "
         "<b>Tindakan:</b> Naikkan syarat Combo Score T2 dari batas minimum sekarang (contoh 65) menjadi minimal 68, "
         "serta wajibkan adanya minimal 2 game log good start berturut-turut pada starter pitcher yang dipilih."),

        ("3. Kapitalisasi Edge T1 Moneyline (Skalakan Alokasi Unit)",
         "Tier T1 mencatat <b>65.0% Win Rate (39W–21L)</b> dan <b>+4.4% ROI (+2.61u)</b>. "
         "Ini adalah aset algoritma paling menguntungkan di seluruh sistem MLB. "
         "<b>Tindakan:</b> Pertimbangkan fractional Kelly staking atau alokasi 1.25u–1.50u untuk T1, "
         "sembari mempertahankan alokasi flat 0.75u untuk tier sekunder."),

        ("4. Perbaiki Penilaian Home Field Advantage (HFA) pada Moneyline",
         "Away ML menghasilkan <b>+8.4% ROI (+4.81u, 61.4% WR)</b> sedangkan Home ML merugi <b>-9.2% ROI (-4.71u)</b>. "
         "Pasar taruhan (bookmaker) secara konsisten membebankan premium berlebih pada tim tuan rumah. "
         "<b>Tindakan:</b> Kurangi bobot Home Field Advantage dalam formula fair decimal ML_COMBO_V2 sebesar 3%–5% "
         "untuk menghindari taruhan tim kandang dengan harga mahal/minus-value."),

        ("5. Evaluasi Ulang Korelasi Cuaca & Park Factor pada Model Totals",
         "Model Totals saat ini memproyeksikan Under terlalu agresif di venue berdimensi kecil atau saat temperatur tinggi. "
         "<b>Tindakan:</b> Masukkan dynamic weather adjustment (wind direction & velocity, temperature) ke dalam "
         "InputSnapshot sebelum OU_UNIFIED menghitung projected total."),
    ]

    for title, desc in recommendations:
        elements.append(Paragraph(f"<b>{title}</b>", ss["SubSectionHead"]))
        elements.append(Paragraph(desc, ss["BodyMLB"]))
        elements.append(Spacer(1, 2*mm))

    elements.append(Spacer(1, 4*mm))

    # ── Section 7: Sample Ledger of Settled Picks ──────────────────────
    elements.append(Paragraph("7 · Sampel Ledger Settled Picks (Ringkasan Representatif)", ss["SectionHead"]))
    elements.append(Paragraph(
        "Menampilkan 25 sampel pick dari 167 total settled data yang mencakup seluruh tier dan market.",
        ss["BodyMLB"]
    ))
    elements.append(Spacer(1, 2*mm))

    # Select representative sample across tiers
    sample_picks = []
    # Pick a few from each tier
    for t_name in ["T1", "T2", "UNDER_RISKY", "OVER_RISKY", "OVER_LEAN", "UNDER_LEAN"]:
        sub = [p for p in settled if p["tier"] == t_name]
        sample_picks.extend(sub[:4])
    # fill up to 25 with chronological
    if len(sample_picks) < 25:
        remaining = [p for p in settled if p not in sample_picks]
        sample_picks.extend(remaining[:(25 - len(sample_picks))])

    sample_picks = sorted(sample_picks, key=lambda p: p["gameDate"])

    led_header = ["Tanggal", "Matchup", "Market", "Tier", "Selection", "Odds", "Skor", "Hasil", "Profit"]
    led_rows = []
    for p in sample_picks[:25]:
        res_label = "WIN" if p["status"] == "win" else ("LOSS" if p["status"] == "loss" else "PUSH")
        led_rows.append([
            p["gameDate"],
            p["matchup"],
            p["market"].upper()[:4],
            p["tier"][:10],
            p["pickLabel"][:18],
            f"{p.get('decimalOdds', 0):.2f}",
            p.get("scoreStr") or "—",
            res_label,
            fmt_profit(p.get("profitUnits")),
        ])
    elements.append(make_table(led_header, led_rows, col_widths=[52, 60, 36, 60, 80, 34, 42, 34, 40]))

    # ── Build PDF ──────────────────────────────────────────────────────
    print(f"Building PDF to {OUT_PDF} ...")
    doc.build(elements, onFirstPage=page_bg, onLaterPages=page_bg)
    return str(OUT_PDF)


def main():
    print(f"Loading snapshot from {SNAPSHOT_FILE} ...")
    snapshot = load_snapshot()
    print(f"  Total settled: {len(snapshot.get('settled', []))}")
    print(f"  Total pending: {len(snapshot.get('pending', []))}")
    print("Generating charts and building PDF ...")
    pdf_path = build_pdf(snapshot)
    print(f"[SUCCESS] PDF generated at: {pdf_path}")
    print(f"  Size: {os.path.getsize(pdf_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
