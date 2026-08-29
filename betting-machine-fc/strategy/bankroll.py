import json
import math

CAPITAL = 1000.0
STAKE_FRACTION = 0.02  # 2% flat per bet (Kelly-fraction conservative)
MIN_ODDS = 1.66
ROUNDS = 500
MAX_STAKE = 100.0


def kelly_fraction(p, b):
    f = (b * p - (1 - p)) / b
    return max(0.0, min(f, 0.10))


def simulate(p, odds, n=ROUNDS, capital=CAPITAL, stake_pct=STAKE_FRACTION):
    """Flat or fractional-Kelly simulation of a single-bet profile."""
    b = odds - 1
    k = kelly_fraction(p, b)
    bank = capital
    results = []
    for _ in range(n):
        stake = STAKE_FRACTION * bank if stake_pct else k * bank
        if odds < MIN_ODDS:
            results.append({"bet": 0, "bank": bank, "reason": "odds_below_min"})
            continue
        won = (i := 0) or False
        import random
        won = random.random() < p
        bank += (odds - 1) * stake if won else -stake
        results.append({"bet": stake, "won": won, "bank": bank})
    return {"final_bank": bank, "results": results}


def kelly_full(p, odds):
    b = odds - 1
    return kelly_fraction(p, b)


def flat_return(p, odds, n=ROUNDS):
    b = odds - 1
    return n * (p * b - (1 - p))


def monte_carlo_bankroll(p, odds, iterations=1000, capital=CAPITAL, stake_pct=STAKE_FRACTION):
    """Simulates a sequence of independent bets; returns final bank stats."""
    import random
    b = odds - 1
    finals = []
    for _ in range(iterations):
        bank = capital
        for _ in range(ROUNDS):
            stake = STAKE_FRACTION * bank
            if random.random() < p:
                bank += b * stake
            else:
                bank -= stake
        finals.append(bank)
    finals.sort()
    return {
        "median": finals[len(finals) // 2],
        "p5": finals[int(len(finals) * 0.05)],
        "p95": finals[int(len(finals) * 0.95)],
        "ruin_pct": 100 * sum(1 for x in finals if x < capital * 0.5) / len(finals),
    }


if __name__ == "__main__":
    # Sanity: EV profile from the demo scan (Liverpool AH -1 @ 1.74, p≈0.64)
    p, odds = 0.64, 1.74
    mc = monte_carlo_bankroll(p, odds)
    print(f"profile p={p} odds={odds} EV={p*odds-1:+.3f}")
    print(f"monte_carlo(1000 runs, {ROUNDS} bets): {json.dumps(mc, indent=2)}")