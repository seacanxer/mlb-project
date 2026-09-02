import db, time, sys
from datetime import datetime

def main():
    db.init_db()
    now = time.time()
    unsettled = db.get_unsettled()
    stuck = [b for b in unsettled if b.get('start_ts') and now >= b['start_ts'] + 6300]
    if not stuck:
        print('No stuck bets found.')
        return

    print(f'Found {len(stuck)} stuck bets (kickoff +105min ago):')
    for i, b in enumerate(stuck):
        start = datetime.fromtimestamp(b['start_ts']).strftime('%Y-%m-%d %H:%M')
        print(f'{i+1}. ID={b["id"]} {b["home"]} vs {b["away"]} ({b.get("league","?")}) kickoff {start}')

    if len(sys.argv) > 1 and sys.argv[1] == '--list':
        return

    print('\nEnter ID and score like: 6350 2-1')
    print('Type "done" to finish.')
    while True:
        line = input('> ').strip()
        if line.lower() == 'done':
            break
        parts = line.split()
        if len(parts) != 2:
            print('Format: ID home-away')
            continue
        try:
            bid = int(parts[0])
            h, a = parts[1].split('-')
            hg, ag = int(h), int(a)
        except:
            print('Invalid format')
            continue
        # verify bet exists and is stuck
        bet = next((b for b in stuck if b['id'] == bid), None)
        if not bet:
            print('ID not in stuck list')
            continue
        # update
        db.settle_bet(bid, None, None, home_score=hg, away_score=ag, score_status='manual')
        print(f'Bet {bid} settled with {hg}-{ag}')
        # refresh stuck list
        unsettled = db.get_unsettled()
        stuck = [b for b in unsettled if b.get('start_ts') and now >= b['start_ts'] + 6300]
        if not stuck:
            print('All stuck bets settled!')
            break

if __name__ == '__main__':
    main()