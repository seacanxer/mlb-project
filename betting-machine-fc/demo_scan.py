import json
import sys

sys.path.insert(0, "/tmp/betting-machine-fc")
from model import (
    ah_ev,
    ah_ev_away,
    match_probs,
    btts_prob,
    over_prob,
    under_prob,
    lam_from_odds,
    ev,
)

MID = "746420692"
j = json.load(open("/tmp/game_dump.json"))
v = j["Value"]
odds = v.get("E", [])
o1 = next(e["C"] for e in odds if e["G"] == 1 and e["T"] == 1)
od = next(e["C"] for e in odds if e["G"] == 1 and e["T"] == 2)
o2 = next(e["C"] for e in odds if e["G"] == 1 and e["T"] == 3)
oov = next(e["C"] for e in odds if e["G"] == 17 and e["P"] == 2.5 and e["T"] == 9)
oun = next(e["C"] for e in odds if e["G"] == 17 and e["P"] == 2.5 and e["T"] == 10)
ah_home = [(e.get("P"), e.get("C")) for e in odds if e.get("G") == 2 and e.get("T") == 7 and e.get("P") is not None]
ah_away = [(e.get("P"), e.get("C")) for e in odds if e.get("G") == 2 and e.get("T") == 8 and e.get("P") is not None]

print(f"MATCH: {v['O1']} vs {v['O2']} ({v['L']})")
print(f"odds 1X2: {o1} / {od} / {o2}")
print(f"O/U2.5: Over {oov} | Under {oun}")
print(f"AH home lines: {ah_home[:6]}")
print(f"AH away lines: {ah_away[:6]}")
print()

lh, la, fair, fair_over = lam_from_odds(o1, od, o2, oov, oun, 2.5)
print(f"derived λ: home={lh:.3f} away={la:.3f} | fair1X2={[round(x,3) for x in fair]} | fair Over2.5={fair_over:.3f}")
ph, pd, pa = match_probs(lh, la)
print(f"DC probs: P1={ph:.3f} PD={pd:.3f} P2={pa:.3f}")
pbt = btts_prob(lh, la)
po = over_prob(2.5, lh, la)
pu = under_prob(2.5, lh, la)
print(f"BTTS yes={pbt:.3f} | O2.5={po:.3f} U2.5={pu:.3f}")
print()

MINO = 1.66


def show(market, pick, p, odds):
    e = ev(p, odds)
    flag = "BET" if (e > 0 and odds >= MINO) else ("REJECT-LOW-ODDS" if odds < MINO else "NO")
    print(f"  {market:14s} {pick:24s} p={p:.3f} odds={odds:.3f} EV={e:+.3f} [{flag}]")


print("=== Market scan (min odds 1.66) ===")
show("1X2", "Home " + v["O1"], ph, o1)
show("1X2", "Draw", pd, od)
show("1X2", "Away " + v["O2"], pa, o2)
show("O/U", "Over 2.5", po, oov)
show("O/U", "Under 2.5", pu, oun)
print()
for line, c in ah_home:
    if c < MINO:
        continue
    e_home = ah_ev(line, c, lh, la)
    print(f"  AH home {line:+.2f} @ {c:.3f} EV={e_home:+.3f} [{'BET' if e_home > 0 else 'NO'}]")
print()
for line, c in ah_away:
    if c < MINO:
        continue
    e_away = ah_ev_away(line, c, lh, la)
    print(f"  AH away {line:+.2f} @ {c:.3f} EV={e_away:+.3f} [{'BET' if e_away > 0 else 'NO'}]")
print()
print(f"BLEND CHECK: Poisson λ_total = {lh + la:.2f} → fair O2.5 = {fair_over:.3f} vs market {1/oov:.3f}")