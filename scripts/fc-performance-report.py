"""
FC Model Performance Report — PDF Generator
=============================================
Reads tracker_snapshot.json and produces a professional PDF report
with breakdowns by market, tier, league, odds band, and pick type.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image, PageBreak, HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie


# ── paths ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
TRACKER = BASE / "betting-machine-fc" / "tracker_snapshot.json"
OUT_DIR = BASE / "reports"
OUT_DIR.mkdir(exist_ok=True)

NOW = datetime.now()
REPORT_NAME = f"fc-performance-report-{NOW.strftime('%Y-%m-%d')}.pdf"
OUT_PDF = OUT_DIR / REPORT_NAME

# chart temp dir
CHART_DIR = OUT_DIR / ".charts"
CHART_DIR.mkdir(exist_ok=True)


# ── helpers ────────────────────────────────────────────────────────────
def load_tracker():
    with open(TRACKER, "r", encoding="utf-8") as f:
        return json.load(f)


def ev_tier(ev: float) -> str:
    if ev >= 0.15:
        return "T1 (EV ≥ 15%)"
    if ev >= 0.08:
        return "T2 (EV 8–15%)"
    if ev >= 0.03:
        return "T3 (EV 3–8%)"
    return "T4 (EV < 3%)"

TIER_ORDER = ["T1 (EV ≥ 15%)", "T2 (EV 8–15%)", "T3 (EV 3–8%)", "T4 (EV < 3%)"]


def odds_band(odds: float) -> str:
    if odds < 1.5:
        return "1.00–1.49"
    if odds < 2.0:
        return "1.50–1.99"
    if odds < 2.5:
        return "2.00–2.49"
    if odds < 3.0:
        return "2.50–2.99"
    return "3.00+"

ODDS_ORDER = ["1.00–1.49", "1.50–1.99", "2.00–2.49", "2.50–2.99", "3.00+"]


def win_rate(w, l, p):
    total = w + l
    if total == 0:
        return None
    return round(w / total * 100, 1)


def roi(profit, bets):
    if bets == 0:
        return None
    return round(profit / bets * 100, 1)


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.1f}%" if v < 0 or v > 0 else "0.0%"


def fmt_pct_abs(v):
    if v is None:
        return "—"
    return f"{v:.1f}%"


def fmt_profit(v):
    if v is None:
        return "—"
    return f"{v:+.2f}u"


# ── aggregate ──────────────────────────────────────────────────────────
def aggregate(picks, key_fn, order=None):
    buckets = defaultdict(lambda: {"bets": 0, "settled": 0, "wins": 0, "losses": 0, "pushes": 0, "profit": 0.0})
    for p in picks:
        k = key_fn(p)
        b = buckets[k]
        b["bets"] += 1
        if p.get("settled"):
            b["settled"] += 1
            if p.get("won") == 1:
                b["wins"] += 1
            elif p.get("won") == 0:
                b["losses"] += 1
            else:
                b["pushes"] += 1
            b["profit"] += p.get("profit") or 0
    if order:
        rows = [(k, buckets[k]) for k in order if k in buckets]
    else:
        rows = sorted(buckets.items(), key=lambda x: -x[1]["bets"])
    return rows


# ── matplotlib charts ──────────────────────────────────────────────────
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
    ax.set_title(title, color=BRAND_WHITE, fontsize=12, fontweight="bold", pad=10)
    ax.tick_params(colors=BRAND_GRAY, labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(BRAND_GRAY)
    ax.spines["left"].set_color(BRAND_GRAY)
    ax.yaxis.label.set_color(BRAND_GRAY)
    ax.xaxis.label.set_color(BRAND_GRAY)


def chart_market_roi(market_perf, path):
    markets = [m["market"].upper() for m in market_perf]
    rois    = [m["roi_pct"] for m in market_perf]
    bets    = [m["bets"] for m in market_perf]
    bar_colors = [BRAND_GREEN if r >= 0 else BRAND_RED for r in rois]

    fig, ax = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "ROI per Market (settled picks)")
    bars = ax.bar(markets, rois, color=bar_colors, edgecolor="none", width=0.5)
    ax.axhline(0, color=BRAND_GRAY, linewidth=0.5)
    ax.set_ylabel("ROI %")
    for bar, r, n in zip(bars, rois, bets):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                f"{r:+.0f}%\n({n}b)", ha="center", va="bottom",
                color=BRAND_WHITE, fontsize=8, fontweight="bold")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_tier_performance(tier_rows, path):
    labels  = [t[0].split("(")[0].strip() for t in tier_rows]
    settled = [t[1]["settled"] for t in tier_rows]
    wins    = [t[1]["wins"] for t in tier_rows]
    losses  = [t[1]["losses"] for t in tier_rows]

    fig, ax = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "Settled Picks by Tier")
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w/2 for i in x], wins, w, label="Wins", color=BRAND_GREEN)
    ax.bar([i + w/2 for i in x], losses, w, label="Losses", color=BRAND_RED)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend(facecolor=BRAND_SURFACE, edgecolor=BRAND_GRAY, labelcolor=BRAND_WHITE, fontsize=8)
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_cumulative_profit(settled_picks, path):
    sorted_picks = sorted(settled_picks, key=lambda p: p.get("settled_at") or "")
    cum = []
    running = 0.0
    for p in sorted_picks:
        running += p.get("profit") or 0
        cum.append(running)
    dates = list(range(1, len(cum) + 1))

    fig, ax = plt.subplots(figsize=(6, 3.0))
    fig.patch.set_facecolor(BRAND_DARK)
    style_ax(ax, "Cumulative Profit (units)")
    ax.fill_between(dates, cum, alpha=0.15, color=BRAND_ACCENT)
    ax.plot(dates, cum, color=BRAND_ACCENT, linewidth=2, marker="o", markersize=4)
    ax.axhline(0, color=BRAND_GRAY, linewidth=0.5, linestyle="--")
    ax.set_xlabel("Bet #")
    ax.set_ylabel("Profit (u)")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_odds_band(odds_rows, path):
    labels  = [r[0] for r in odds_rows]
    bets    = [r[1]["bets"] for r in odds_rows]
    settled = [r[1]["settled"] for r in odds_rows]
    profit  = [r[1]["profit"] for r in odds_rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6, 3.0))
    fig.patch.set_facecolor(BRAND_DARK)

    style_ax(ax1, "Bets per Odds Band")
    ax1.bar(labels, bets, color=BRAND_PURPLE, width=0.5)
    for i, (b, s) in enumerate(zip(bets, settled)):
        ax1.text(i, b + 1, f"{b}\n({s}s)", ha="center", va="bottom",
                 color=BRAND_WHITE, fontsize=7)
    ax1.tick_params(axis="x", rotation=30)

    style_ax(ax2, "Profit per Odds Band")
    bar_colors = [BRAND_GREEN if p >= 0 else BRAND_RED for p in profit]
    ax2.bar(labels, profit, color=bar_colors, width=0.5)
    ax2.axhline(0, color=BRAND_GRAY, linewidth=0.5)
    ax2.tick_params(axis="x", rotation=30)

    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_win_loss_pie(summary, path):
    labels = []
    sizes = []
    pie_colors = []
    if summary.get("wins", 0):
        labels.append(f"Win ({summary['wins']})")
        sizes.append(summary["wins"])
        pie_colors.append(BRAND_GREEN)
    if summary.get("losses", 0):
        labels.append(f"Loss ({summary['losses']})")
        sizes.append(summary["losses"])
        pie_colors.append(BRAND_RED)
    if summary.get("pushes", 0):
        labels.append(f"Push ({summary['pushes']})")
        sizes.append(summary["pushes"])
        pie_colors.append(BRAND_AMBER)

    if not sizes:
        return

    fig, ax = plt.subplots(figsize=(3, 3))
    fig.patch.set_facecolor(BRAND_DARK)
    ax.set_facecolor(BRAND_DARK)
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.0f%%", startangle=90,
        colors=pie_colors, textprops={"color": BRAND_WHITE, "fontsize": 9},
    )
    for at in autotexts:
        at.set_fontweight("bold")
    ax.set_title("Win / Loss / Push", color=BRAND_WHITE, fontsize=11, fontweight="bold")
    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


# ── PDF builder ────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4

# Brand colors for reportlab
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
    ss.add(ParagraphStyle("Title_FC", parent=ss["Title"], fontName="Helvetica-Bold",
                          fontSize=22, textColor=RL_WHITE, alignment=TA_LEFT, spaceAfter=2*mm))
    ss.add(ParagraphStyle("Subtitle_FC", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, textColor=RL_GRAY, alignment=TA_LEFT, spaceAfter=6*mm))
    ss.add(ParagraphStyle("SectionHead", parent=ss["Heading2"], fontName="Helvetica-Bold",
                          fontSize=14, textColor=RL_ACCENT, spaceBefore=8*mm, spaceAfter=4*mm))
    ss.add(ParagraphStyle("BodyFC", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=9, textColor=RL_WHITE, leading=12))
    ss.add(ParagraphStyle("CellFC", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=8, textColor=RL_WHITE, leading=10, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CellFC_Left", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=8, textColor=RL_WHITE, leading=10, alignment=TA_LEFT))
    ss.add(ParagraphStyle("InsightFC", parent=ss["Normal"], fontName="Helvetica-Oblique",
                          fontSize=9, textColor=RL_AMBER, leading=12, spaceBefore=3*mm, spaceAfter=3*mm))
    ss.add(ParagraphStyle("FooterFC", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=7, textColor=RL_GRAY, alignment=TA_CENTER))
    return ss


def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(RL_DARK)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # footer
    canvas.setFillColor(RL_GRAY)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(PAGE_W / 2, 12 * mm,
                             f"FC Performance Report — Generated {NOW.strftime('%Y-%m-%d %H:%M')} — Page {doc.page}")
    canvas.restoreState()


def make_table(header, rows, col_widths=None):
    """Build a styled Table with dark theme."""
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), RL_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), RL_WHITE),
        ("FONTNAME",  (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (-1, 0), 8),
        ("FONTNAME",  (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), RL_WHITE),
        ("ALIGN",     (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",     (0, 0), (0, -1), "LEFT"),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",      (0, 0), (-1, -1), 0.5, RL_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        bg = RL_ROW_ALT if i % 2 == 0 else RL_ROW_BG
        style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle(style_cmds))
    return t


def build_pdf(tracker):
    ss = build_styles()
    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=18*mm, bottomMargin=20*mm,
    )
    elements = []

    summary = tracker["summary"]
    market_perf = tracker["market_performance"]
    settled = tracker.get("settled", [])
    overdue = tracker.get("overdue", [])
    all_picks = settled + overdue
    built_at = tracker.get("built_at", "unknown")

    # ── Title ──
    elements.append(Paragraph("⚽ FC Model — Laporan Performa", ss["Title_FC"]))
    elements.append(Paragraph(
        f"Snapshot: {built_at[:19] if len(built_at) >= 19 else built_at} UTC &nbsp;|&nbsp; "
        f"Report: {NOW.strftime('%Y-%m-%d %H:%M')} WIB &nbsp;|&nbsp; "
        f"Unit size: {tracker.get('unit_size', 1)}",
        ss["Subtitle_FC"],
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=RL_ACCENT, spaceAfter=4*mm))

    # ── Section 1: Executive Summary ──
    elements.append(Paragraph("1 · Ringkasan Eksekutif", ss["SectionHead"]))

    summary_header = ["Metrik", "Nilai"]
    summary_rows = [
        ["Total Picks (locked + overdue)", str(summary.get("locked_picks", 0) + summary.get("pending_picks", 0) + summary.get("settled_picks", 0))],
        ["Settled", str(summary.get("settled_picks", 0))],
        ["Wins / Losses / Pushes", f"{summary.get('wins', 0)} / {summary.get('losses', 0)} / {summary.get('pushes', 0)}"],
        ["Win Rate (excl. push)", fmt_pct_abs(summary.get("hit_rate_pct"))],
        ["Total Profit", fmt_profit(summary.get("profit_units"))],
        ["ROI", fmt_pct(summary.get("roi_pct"))],
        ["Pending (overdue)", str(summary.get("overdue_picks", 0))],
    ]
    elements.append(make_table(summary_header, summary_rows, col_widths=[120, 100]))
    elements.append(Spacer(1, 4*mm))

    # pie chart
    pie_path = str(CHART_DIR / "win_loss_pie.png")
    chart_win_loss_pie(summary, pie_path)
    if os.path.exists(pie_path):
        elements.append(Image(pie_path, width=55*mm, height=55*mm))
    elements.append(Spacer(1, 2*mm))

    # cumulative profit chart
    if settled:
        cum_path = str(CHART_DIR / "cumulative_profit.png")
        chart_cumulative_profit(settled, cum_path)
        elements.append(Image(cum_path, width=150*mm, height=75*mm))
    elements.append(Spacer(1, 4*mm))

    # ── Section 2: Performance by Market ──
    elements.append(Paragraph("2 · Performa per Market", ss["SectionHead"]))

    mkt_header = ["Market", "Bets", "W", "L", "P", "Win %", "Profit", "ROI"]
    mkt_rows = []
    for m in market_perf:
        wr = win_rate(m["wins"], m["losses"], m["pushes"])
        mkt_rows.append([
            m["market"].upper(),
            str(m["bets"]),
            str(m["wins"]),
            str(m["losses"]),
            str(m["pushes"]),
            fmt_pct_abs(wr),
            fmt_profit(m["profit_units"]),
            fmt_pct(m["roi_pct"]),
        ])
    elements.append(make_table(mkt_header, mkt_rows, col_widths=[50, 35, 30, 30, 30, 45, 55, 50]))

    # market roi chart
    roi_chart_path = str(CHART_DIR / "market_roi.png")
    chart_market_roi(market_perf, roi_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(roi_chart_path, width=150*mm, height=80*mm))

    # insight
    best_mkt = max(market_perf, key=lambda m: m["roi_pct"]) if market_perf else None
    worst_mkt = min(market_perf, key=lambda m: m["roi_pct"]) if market_perf else None
    if best_mkt and worst_mkt:
        elements.append(Paragraph(
            f"💡 <b>Insight:</b> Market <b>{best_mkt['market'].upper()}</b> memberikan ROI terbaik "
            f"({best_mkt['roi_pct']:+.1f}%) dari {best_mkt['bets']} bet. "
            f"Market <b>{worst_mkt['market'].upper()}</b> memerlukan perbaikan "
            f"({worst_mkt['roi_pct']:+.1f}% ROI, {worst_mkt['bets']} bet).",
            ss["InsightFC"],
        ))

    elements.append(PageBreak())

    # ── Section 3: Performance by Tier ──
    elements.append(Paragraph("3 · Performa per Tier (EV Band)", ss["SectionHead"]))

    tier_rows = aggregate(all_picks, lambda p: ev_tier(p.get("ev", 0)), order=TIER_ORDER)
    tier_header = ["Tier", "Total", "Settled", "W", "L", "P", "Win %", "Profit", "ROI"]
    tier_data = []
    for label, b in tier_rows:
        wr = win_rate(b["wins"], b["losses"], b["pushes"])
        r = roi(b["profit"], b["settled"])
        tier_data.append([
            label, str(b["bets"]), str(b["settled"]),
            str(b["wins"]), str(b["losses"]), str(b["pushes"]),
            fmt_pct_abs(wr), fmt_profit(b["profit"]), fmt_pct(r),
        ])
    elements.append(make_table(tier_header, tier_data,
                               col_widths=[80, 35, 40, 30, 30, 30, 45, 55, 50]))

    # tier chart
    tier_chart_path = str(CHART_DIR / "tier_performance.png")
    chart_tier_performance(tier_rows, tier_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(tier_chart_path, width=150*mm, height=80*mm))

    # insight
    tier_settled = [(t, b) for t, b in tier_rows if b["settled"] > 0]
    if tier_settled:
        best_tier = max(tier_settled, key=lambda x: roi(x[1]["profit"], x[1]["settled"]) or -999)
        elements.append(Paragraph(
            f"💡 <b>Insight:</b> Tier <b>{best_tier[0]}</b> menghasilkan ROI terbaik "
            f"({fmt_pct(roi(best_tier[1]['profit'], best_tier[1]['settled']))}) dari "
            f"{best_tier[1]['settled']} settled picks. "
            f"Sebagian besar picks masih pending/overdue ({summary.get('overdue_picks',0)}) — "
            f"settlement penuh diperlukan sebelum kesimpulan final.",
            ss["InsightFC"],
        ))

    elements.append(Spacer(1, 6*mm))

    # ── Section 4: Odds Band ──
    elements.append(Paragraph("4 · Distribusi per Odds Band", ss["SectionHead"]))
    odds_rows = aggregate(all_picks, lambda p: odds_band(p.get("odds", 0)), order=ODDS_ORDER)
    odds_header = ["Odds Band", "Total", "Settled", "W", "L", "P", "Win %", "Profit", "ROI"]
    odds_data = []
    for label, b in odds_rows:
        wr = win_rate(b["wins"], b["losses"], b["pushes"])
        r = roi(b["profit"], b["settled"])
        odds_data.append([
            label, str(b["bets"]), str(b["settled"]),
            str(b["wins"]), str(b["losses"]), str(b["pushes"]),
            fmt_pct_abs(wr), fmt_profit(b["profit"]), fmt_pct(r),
        ])
    elements.append(make_table(odds_header, odds_data,
                               col_widths=[60, 35, 40, 30, 30, 30, 45, 55, 50]))

    odds_chart_path = str(CHART_DIR / "odds_band.png")
    chart_odds_band(odds_rows, odds_chart_path)
    elements.append(Spacer(1, 3*mm))
    elements.append(Image(odds_chart_path, width=150*mm, height=75*mm))

    settled_odds = [(o, b) for o, b in odds_rows if b["settled"] > 0]
    if settled_odds:
        best_odds = max(settled_odds, key=lambda x: roi(x[1]["profit"], x[1]["settled"]) or -999)
        elements.append(Paragraph(
            f"💡 <b>Insight:</b> Odds band <b>{best_odds[0]}</b> memberikan performa terbaik "
            f"({fmt_pct(roi(best_odds[1]['profit'], best_odds[1]['settled']))} ROI). "
            f"Perhatikan bahwa odds tinggi (2.50+) belum memiliki settled picks yang cukup untuk evaluasi.",
            ss["InsightFC"],
        ))

    elements.append(PageBreak())

    # ── Section 5: League Breakdown ──
    elements.append(Paragraph("5 · Performa per Liga", ss["SectionHead"]))

    league_rows = aggregate(all_picks, lambda p: p.get("league", "Unknown"))
    lg_header = ["Liga", "Total", "Settled", "W", "L", "P", "Profit", "ROI"]
    lg_data = []
    for label, b in league_rows:
        r = roi(b["profit"], b["settled"])
        short_label = label if len(label) <= 35 else label[:32] + "…"
        lg_data.append([
            short_label, str(b["bets"]), str(b["settled"]),
            str(b["wins"]), str(b["losses"]), str(b["pushes"]),
            fmt_profit(b["profit"]), fmt_pct(r),
        ])
    elements.append(make_table(lg_header, lg_data,
                               col_widths=[110, 35, 40, 30, 30, 30, 55, 50]))

    league_settled = [(l, b) for l, b in league_rows if b["settled"] >= 2]
    if league_settled:
        best_lg = max(league_settled, key=lambda x: roi(x[1]["profit"], x[1]["settled"]) or -999)
        worst_lg = min(league_settled, key=lambda x: roi(x[1]["profit"], x[1]["settled"]) or 999)
        elements.append(Paragraph(
            f"💡 <b>Insight:</b> Liga terbaik: <b>{best_lg[0]}</b> "
            f"({fmt_pct(roi(best_lg[1]['profit'], best_lg[1]['settled']))} ROI, "
            f"{best_lg[1]['settled']} settled). "
            f"Liga terburuk: <b>{worst_lg[0]}</b> "
            f"({fmt_pct(roi(worst_lg[1]['profit'], worst_lg[1]['settled']))} ROI).",
            ss["InsightFC"],
        ))

    elements.append(Spacer(1, 6*mm))

    # ── Section 6: Pick Type ──
    elements.append(Paragraph("6 · Performa per Jenis Pick", ss["SectionHead"]))

    pick_type_rows = aggregate(all_picks, lambda p: f"{p.get('market','?').upper()} · {p.get('pick','?')}")
    pt_settled = [(k, b) for k, b in pick_type_rows if b["settled"] > 0]
    pt_header = ["Pick Type", "Total", "Settled", "W", "L", "P", "Profit", "ROI"]
    pt_data = []
    for label, b in pt_settled:
        r = roi(b["profit"], b["settled"])
        short_label = label if len(label) <= 30 else label[:27] + "…"
        pt_data.append([
            short_label, str(b["bets"]), str(b["settled"]),
            str(b["wins"]), str(b["losses"]), str(b["pushes"]),
            fmt_profit(b["profit"]), fmt_pct(r),
        ])
    if pt_data:
        elements.append(make_table(pt_header, pt_data,
                                   col_widths=[100, 35, 40, 30, 30, 30, 55, 50]))
    else:
        elements.append(Paragraph("Belum ada pick type yang ter-settle.", ss["BodyFC"]))

    elements.append(PageBreak())

    # ── Section 7: Detail Settled Picks ──
    elements.append(Paragraph("7 · Detail Settled Picks", ss["SectionHead"]))

    sorted_settled = sorted(settled, key=lambda p: p.get("settled_at") or "")
    sp_header = ["#", "Match", "Liga", "Market", "Pick", "Odds", "EV", "Score", "Result", "P/L"]
    sp_data = []
    for i, p in enumerate(sorted_settled, 1):
        result = "W" if p.get("won") == 1 else ("L" if p.get("won") == 0 else "P")
        score = f"{p.get('home_score', '?')}–{p.get('away_score', '?')}"
        match_name = p.get("match", "?")
        short_match = match_name if len(match_name) <= 25 else match_name[:22] + "…"
        league = p.get("league", "?")
        short_league = league if len(league) <= 20 else league[:17] + "…"
        sp_data.append([
            str(i),
            short_match,
            short_league,
            p.get("market", "?").upper(),
            p.get("pick", "?"),
            f"{p.get('odds', 0):.3f}",
            f"{p.get('ev', 0):.1%}",
            score,
            result,
            fmt_profit(p.get("profit")),
        ])
    elements.append(make_table(sp_header, sp_data,
                               col_widths=[18, 80, 65, 30, 55, 35, 35, 30, 25, 40]))

    elements.append(Spacer(1, 6*mm))

    # ── Section 8: Rekomendasi ──
    elements.append(Paragraph("8 · Rekomendasi untuk Peningkatan Model", ss["SectionHead"]))

    # Generate dynamic recommendations based on the data
    recs = []

    # Market analysis
    if market_perf:
        losing_markets = [m for m in market_perf if m["roi_pct"] < 0]
        for m in losing_markets:
            recs.append(
                f"<b>{m['market'].upper()}</b>: ROI negatif ({m['roi_pct']:+.1f}%). "
                f"Evaluasi ulang parameter model untuk market ini — "
                f"apakah probabilitas overestimate atau line selection kurang optimal?"
            )

    # Tier analysis
    for label, b in tier_rows:
        if b["settled"] > 0:
            r = roi(b["profit"], b["settled"])
            if r is not None and r < -10:
                recs.append(
                    f"<b>{label}</b>: ROI rendah ({fmt_pct(r)}). "
                    f"Pertimbangkan filter tambahan atau naikkan EV threshold minimum untuk tier ini."
                )

    # Odds band analysis
    for label, b in odds_rows:
        if b["settled"] >= 3:
            r = roi(b["profit"], b["settled"])
            if r is not None and r < -10:
                recs.append(
                    f"Odds band <b>{label}</b>: ROI rendah ({fmt_pct(r)}). "
                    f"Cek apakah model overvalue odds di range ini."
                )

    # General recommendations
    recs.extend([
        "<b>Sample Size</b>: Dengan hanya 18 settled picks, semua metrik masih sangat volatile. "
        "Target minimal 100–200 settled picks sebelum melakukan perubahan besar pada model.",
        "<b>Settlement</b>: Ada 185 picks overdue yang belum ter-settle. "
        "Prioritaskan settlement untuk mendapatkan gambaran yang lebih akurat.",
        "<b>Second Source</b>: Second source belum dikonfigurasi. "
        "Validasi odds dari sumber kedua dapat mengurangi risiko stale odds.",
        "<b>Calibration</b>: Track predicted probability vs actual win rate per decile "
        "untuk mendeteksi systematic bias pada model Dixon-Coles.",
    ])

    for i, rec in enumerate(recs, 1):
        elements.append(Paragraph(f"{i}. {rec}", ss["BodyFC"]))
        elements.append(Spacer(1, 2*mm))

    # ── Build ──
    doc.build(elements, onFirstPage=page_bg, onLaterPages=page_bg)
    return str(OUT_PDF)


# ── main ───────────────────────────────────────────────────────────────
def main():
    print(f"Loading tracker from {TRACKER} ...")
    tracker = load_tracker()
    print(f"  Summary: {json.dumps(tracker['summary'], indent=2)}")
    print(f"  Settled: {len(tracker.get('settled', []))}")
    print(f"  Overdue: {len(tracker.get('overdue', []))}")
    print(f"  Market perf: {len(tracker.get('market_performance', []))} markets")
    print()

    print("Generating charts ...")
    print("Building PDF ...")
    path = build_pdf(tracker)
    print(f"\n[OK] Report saved to: {path}")
    print(f"   File size: {os.path.getsize(path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
