# Internal research source record

Research date: 2026-09-05 (WIB)
Scope: O/U and Asian Handicap formula reset for England, Germany, Scotland, Norway, Iceland, Poland, Spain, and Sweden.
Status: internal evidence ledger; not the user-facing deliverable.

## Research question and decision rule

The user wants aggressive broad scanning, many acceptable Official Picks, and a clearly smaller Top Picks signal. The research question is not which leagues score the most, but how league and tier differences should enter a calibrated O/U/AH probability engine without turning descriptive goal averages into automatic bets.

Evidence is accepted for production design only when it is either primary research, an official competition source, or a transparent match-level dataset whose arithmetic can be reproduced. Secondary league-summary sites are used only for corroboration or to identify a data gap. Conflicting or phase-mixed lower-tier aggregates remain shadow-only.

## Local code and slate audit

- `model.py:234-241`: live lambdas are fitted from 1X2 and `strength_lam()` divides normalized attack/defence by the league average again, so neutral ratings do not reproduce the league scoring baseline.
- `server.py:199-215`: the O/U 2.5 total is fitted, but only `fair_over` is retained; selections continue with the 1X2-derived lambdas and a fixed 0.4 strength blend.
- `main.py:261-284`: ranking is driven primarily by raw probability, then a capped edge term and global quota caps.
- `strength_rating.py:38-65`: only a small set of league labels is mapped. Scotland lower tiers are known as codes but not mapped from provider labels; Norway, Iceland, Poland, and Sweden are absent.
- Stored WIB slate 2026-09-05: 346 matches, 188 distinct league labels. Only 14 matches (4.0%) resolve to a strength league. Country counts/covered: Germany 20/1, Scotland 2/0, Norway 4/0, Iceland 2/0, Poland 7/0, Spain 5/2, Sweden 14/0, England 16/2.

## Recomputed match-level evidence

### Club Football Match Data

Source: https://github.com/xgabora/Club-Football-Match-Data-2000-2025
Raw file: https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv
Visible evidence: dated rows with full-time home/away goals and, for many covered leagues, O/U and AH prices.
Method: winter leagues filtered to 2022-07-01 through 2025-06-30; Norway filtered to complete calendar seasons 2022-2024. O2.5 means total goals >= 3. Home margin means mean(home goals - away goals).
Confidence: high for reproduced arithmetic; medium-high for provenance because it is a public mirror derived primarily from Football-Data.co.uk.
Limit: odds fields and league coverage are incomplete; it is not a universal lower-tier feed.

Key three-season aggregates:

| Code | n | GPG | O2.5 | Home margin | Weekend GPG | Weekday GPG | Blind Over ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| E0 | 1,140 | 3.022 | 58.0% | 0.276 | 3.045 | 2.948 | -3.54% |
| E1 | 1,654 | 2.521 | 46.9% | 0.307 | 2.515 | 2.531 | -7.76% |
| E2 | 1,653 | 2.577 | 48.9% | 0.241 | 2.577 | 2.578 | -6.57% |
| E3 | 1,652 | 2.607 | 47.7% | 0.254 | 2.591 | 2.642 | -8.40% |
| EC | 1,284 | 2.840 | 52.8% | 0.298 | 2.872 | 2.788 | -8.16% |
| D1 | 918 | 3.175 | 60.9% | 0.356 | 3.173 | 3.192 | -2.55% |
| D2 | 918 | 3.021 | 59.4% | 0.306 | 2.992 | 3.127 | -2.86% |
| SC0 | 656 | 2.886 | 56.6% | 0.389 | 2.828 | 3.112 | +1.90% |
| SC1 | 519 | 2.713 | 52.0% | 0.224 | 2.598 | 3.014 | -2.50% |
| SC2 | 524 | 2.964 | 57.3% | 0.128 | 2.946 | 3.175 | -2.66% |
| SC3 | 529 | 2.641 | 48.8% | 0.312 | 2.635 | 2.702 | -10.49% |
| SP1 | 1,140 | 2.592 | 47.5% | 0.336 | 2.664 | 2.421 | -5.65% |
| SP2 | 1,386 | 2.266 | 40.1% | 0.374 | 2.266 | 2.265 | -7.90% |
| POL | 705 | 2.569 | 45.4% | 0.333 | 2.668 | 2.458 | unavailable |
| NOR | 570 | 3.053 | 59.8% | 0.386 | 3.019 | 3.097 | unavailable |

Interpretation: raw weekend differences are inconsistent in sign and are confounded by fixture mix, television scheduling, postponements, and season phase. Day of week is not justified as a standalone boost. Blind Over returns are mostly negative even in high-total leagues, showing that league style is already priced.

### Swedish Football Dataset

Source: https://github.com/Mongosaurusrex/swedish-football-dataset
Visible evidence: dated result rows for Allsvenskan, Superettan, Ettan Norra, and Ettan Sodra.
Method: completed 2023-2025 seasons.
Confidence: high for arithmetic, medium for underlying scraped provenance.
Limit: no consistent historical target/reference odds.

| League | n | GPG | O2.5 | Home margin | 2023/2024/2025 GPG |
|---|---:|---:|---:|---:|---:|
| Allsvenskan | 720 | 2.817 | 54.0% | 0.247 | 2.771 / 2.833 / 2.846 |
| Superettan | 720 | 2.768 | 54.7% | 0.379 | 2.804 / 2.642 / 2.858 |
| Ettan Norra | 623 | 3.169 | 62.9% | 0.311 | 2.957 / 3.274 / 3.275 |
| Ettan Sodra | 624 | 2.800 | 54.8% | 0.306 | 2.736 / 2.740 / 2.923 |

Interpretation: North and South cannot share one unqualified `Sweden Div 1` prior. Superettan and both Ettan groups need stronger partial pooling and current-season state than Allsvenskan.

### OpenFootball Europe and Germany

Europe source: https://github.com/openfootball/europe
Germany source: https://github.com/openfootball/deutschland
Visible evidence: dated score files, CC0/open data.
Confidence: high for complete-file arithmetic; medium provenance because volunteer-maintained.
Limit: several 2025 files in the Europe repository are incomplete and were excluded from completed-season conclusions.

- Iceland Besta: 2023 n=162, 3.457 GPG, 64.2% O2.5, home margin 0.481; 2024 n=162, 3.556 GPG, 66.7% O2.5, margin 0.432. A separate 2025 complete summary gives 3.321 GPG. Regular/championship/relegation phases must be tagged.
- Norway Eliteserien: complete seasons 2023 3.117 GPG; 2024 2.838; independently reconstructed 2025 3.175. The regime is high but materially dynamic.
- Norway OBOS: complete summaries 2023 2.779 GPG; 2024 3.192; 2025 3.196. This is evidence of a level shift, not a stable long-run average.
- Poland Ekstraklasa: 2023/24 2.690 GPG, 48.7% O2.5; 2024/25 2.755, 49.7%. Official 2025/26 reporting gives 2.74 GPG.
- Poland I Liga 2024/25 OpenFootball: n=277 in the available file, 2.664 GPG, 52.3% O2.5; not treated as a complete multi-season production baseline.
- Germany 3.Liga: 2023/24 n=380, 2.805 GPG, 51.8% O2.5; 2024/25 n=380, 2.903, 56.3%. The 2025/26 file is incomplete and excluded.

## Primary methods

1. Dixon and Coles, dynamic attack/defence Poisson with time weighting and low-score correction. https://rss.onlinelibrary.wiley.com/doi/pdf/10.1111/1467-9876.00065
   Confidence: high. Limit: original English data and older market period; architecture still useful, profitability does not transfer automatically.
2. Koopman and Lit, dynamic bivariate Poisson/state-space strengths. https://academic.oup.com/jrsssa/article-abstract/178/1/167/7058470
   Confidence: high. Limit: EPL evaluation, not every lower division.
3. Bayesian weighted dynamic football models, 2026. https://academic.oup.com/jrsssc/advance-article/doi/10.1093/jrsssc/qlag032/8704597
   Visible evidence: adaptively borrowed attack/defence information; compares Poisson, Dixon-Coles, negative binomial, Skellam and zero-inflated Skellam on Bundesliga, EPL, and La Liga; the best family varies by league/period.
   Confidence: high. Implication: model-family and evolution speed are validation choices, not global constants.
4. Egidi, Pauli, and Torelli, combining historical scores and bookmaker odds. https://arxiv.org/abs/1802.08848
   Confidence: medium-high. Implication: the market is an informative anchor, but target-price circularity must be avoided.
5. Walsh and Joshi, calibration versus accuracy in sports betting. https://arxiv.org/abs/2303.06021
   Confidence: medium-high; direct experiment is NBA, general probability decision principle applies. Limit: reported ROI must not be transferred to football.
6. Hegarty and Whelan, Asian Handicap refund structures. https://www.ucd.ie/economics/t4media/WP23_13.pdf
   Visible evidence: quarter lines split into adjacent lines; integer/quarter lines create full or half refunds; realized losses track settlement-aware expected losses in large football samples.
   Confidence: high. Implication: AH must use exact payout EV, never binary win probability.

## Official competition structure sources

- Germany: DFB confirms five Regionalliga groups with distinct promotion paths. https://www.dfb.de/news/detail/aufstieg-von-regionalliga-zur-3-liga-fragen-und-antworten-208044
- Scotland: SPFL confirms four professional divisions and Premiership post-split scheduling. https://spfl.co.uk/news/spfl-fixtures-for-202526 and https://spfl.co.uk/news/202526-post-split-fixtures-qa
- Norway: NFF publishes separate rules for Eliteserien, OBOS, two groups of 2.divisjon, and six groups of 3.divisjon. https://www.fotball.no/lov-og-reglement/ligaverktoykasse/
- Sweden: SvFF publishes separate Allsvenskan, Superettan, Ettan and regional composition documents. https://www.svenskfotboll.se/serier-cuper/tavlingsdokument/
- Spain: RFEF distinguishes professional Primera/Segunda and non-professional Primera/Segunda/Tercera Federacion; Primera Federacion has two groups. https://rfef.es/es/federacion/bases-de-competicion-202526 and https://rfef.es/es/noticias/aprobados-los-grupos-de-primera-federacion-para-la-temporada-202526
- Iceland: KSI competition records expose top/lower tiers and phases. https://www.ksi.is/oll-mot/ . KSI's 2026 working-group report states that Besta splits after 22 rounds. https://www.ksi.is/api/download/media/yx1hkirx/sky-rsla-starfsho-ps-ksi-2026.pdf
- Poland: official Ekstraklasa 2025/26 summary reports 837 goals in 306 matches (2.74 GPG). https://ekstraklasa.org/en/news/the-most-insane-season-in-years-summary/

## Gap matrix

| Area | Evidence available | Remaining gap | Production status |
|---|---|---|---|
| Bundesliga 1/2, La Liga, Segunda, England E0-E3 | 3+ seasons results and historical prices | fresh independent reference prices and unified live/backtest path | eligible after formula repair |
| Scotland Premiership | results and some odds, official phase structure | explicit pre/post-split model and better current reference feed | shadow then staged release |
| Scotland lower | score history but conflicting/incomplete recent summaries | complete IDs, odds, settlement, regime validation | shadow |
| Eliteserien/Allsvenskan | complete score history, official structures | closing O/U/AH reference history | shadow then staged release |
| OBOS/Superettan | score history with clear regime movement | closing prices and change-point validation | shadow |
| Ettan groups | separate score history, only partial market evidence | third audited season/odds/settlement by group | shadow |
| Iceland Besta | high-quality score baseline and known phase split | complete reference-price history and phase-specific calibration | shadow initially |
| Iceland 1.deild | conflicting aggregates | KSI match-ID reconstruction | blocked from Official |
| Ekstraklasa | stable score baseline plus official corroboration | full reference O/U/AH feed | shadow then staged release |
| Poland lower | weak/conflicting aggregates | authoritative match-level reconstruction | blocked from Official |
| Germany Regionalliga/Oberliga, Spain federated lower tiers | official structure only | group-level results, canonical IDs, odds and settlement | blocked from Official |

## Reconciled design conclusion

Use one hierarchical dynamic score engine with country -> tier/group -> team partial pooling. Learn league/tier season intercept, home advantage, evolution speed, dispersion/dependence, market blend, and calibration separately where sample size supports it. Preserve exact phase/group identities. A competition can be scanned while remaining `SHADOW`; it cannot become `OFFICIAL` merely because it has a high goal average.
