"""Competition tiers: where picks are allowed and how they are ranked.

Tier 1: big-five leagues and UEFA club competitions.
Tier 2: other major top flights, second divisions of big-five countries,
        major continental club cups and senior national-team competitions.
Tier 3: everything else (lower divisions, youth, women, regional, cups).

Walk-forward replay of the v5 sharp-reference rule (Bet365 price vs Pinnacle
fair, 2022/23-2025/26): big five ROI +16.2% / CLV +4.1%, second tier
+6.4% / +1.6%, lower leagues +1.5% / +2.5%. Market efficiency and data
quality fall with the tier, so value picks are restricted to tiers 1-2 and
tier-3 fixtures are not analysed unless a domestic goal model exists, in
which case they are display-only.
"""

TIER1_CODES = frozenset({'E0', 'SP1', 'D1', 'I1', 'F1'})
TIER2_CODES = frozenset({'E1', 'N1', 'P1', 'D2', 'I2', 'F2', 'SP2', 'B1', 'T1', 'SC0', 'G1', 'MEX1'})

# 1xbit league labels, lower-cased.
TIER1_LEAGUES = frozenset({
    'england. premier league', 'spain. la liga', 'germany. bundesliga', 'italy. serie a',
    'france. ligue 1', 'uefa champions league', 'uefa europa league',
    'uefa conference league', 'uefa europa conference league',
})
TIER2_LEAGUES = frozenset({
    'england. championship', 'netherlands. eredivisie', 'portugal. primeira liga',
    'germany. 2. bundesliga', 'italy. serie b', 'france. ligue 2', 'spain. segunda division',
    'belgium. jupiler league', 'belgium. first division a', 'turkey. superliga', 'turkey. super lig',
    'turkiye. super lig', 'scotland. premier league', 'scotland. premiership',
    'greece. super league', 'austria. bundesliga', 'switzerland. super league',
    'denmark. superliga', 'norway. eliteserien', 'sweden. allsvenskan', 'poland. ekstraklasa',
    'czech republic. chance liga', 'usa. mls', 'brazil. campeonato brasileiro. serie a',
    'argentina. primera division', 'mexico. liga mx', 'japan. j-league', 'south korea. k league 1',
    'saudi arabia. saudi professional league', 'copa libertadores', 'copa sudamericana',
    'afc champions league elite',
})
TIER_LABELS = {1: 'Liga besar', 2: 'Liga utama', 3: 'Liga minor'}


def league_tier(league, code=None, national=False):
    """1, 2 or 3. ``national`` marks a senior national-team competition."""
    name = (league or '').strip().lower()
    if code in TIER1_CODES or name in TIER1_LEAGUES:
        return 1
    if code in TIER2_CODES or name in TIER2_LEAGUES or national:
        return 2
    return 3
