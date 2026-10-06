import subprocess, sys, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = sys.executable
SCRIPT = os.path.join(ROOT, 'scripts', 'fc-fetch-match-stats.py')

LEAGUES = [
    ('INT_MEN', 'UEFA Nations League'),
    ('E0', 'Premier League'),
    ('E1', 'Championship'),
    ('E2', 'League One'),
    ('E3', 'League Two'),
    ('EC', 'National League'),
    ('SP1', 'LaLiga'),
    ('SP2', 'LaLiga2'),
    ('D1', 'Bundesliga'),
    ('D2', '2. Bundesliga'),
    ('I1', 'Serie A'),
    ('I2', 'Serie B'),
    ('F1', 'Ligue 1'),
    ('F2', 'Ligue 2'),
    ('N1', 'Eredivisie'),
    ('N2', 'Eerste Divisie'),
    ('P1', 'Liga Portugal'),
    ('B1', 'Belgian Pro League'),
    ('T1', 'Super Lig'),
    ('G1', 'Super League'),
    ('SC1', 'Championship'),
    ('SC2', 'League One'),
    ('SC3', 'League Two'),
    ('J2', 'J. League 2'),
    ('D3', '3. Liga'),
    ('GRLB', 'Regionalliga Bayern'),
    ('GRLN', 'Regionalliga North'),
    ('GRLSW', 'Regionalliga Southwest'),
    ('DEN2', '2. Division'),
    ('DEN3', '3. Division'),
    ('BRASB', 'Serie B'),
    ('MEX2', 'Liga de Expansion MX'),
    ('PRFEF2', 'Primera Federacion - Group 2'),
    ('IRL1', 'First Division'),
    ('EPL2', 'Premier League 2'),
]


def job(entry, days, end, workers):
    code, name = entry
    cmd = [VENV, SCRIPT, '--code', code, '--names', name,
           '--days', str(days), '--workers', str(workers)]
    if end:
        cmd += ['--end', end]
    if code == 'INT_MEN':
        cmd += ['--national-backfill']
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=os.path.join(ROOT, 'scripts'))
    return code, proc.stdout.strip() or proc.stderr.strip()[-300:]


def main():
    days = sys.argv[1] if len(sys.argv) > 1 else '90'
    end = sys.argv[2] if len(sys.argv) > 2 else None
    workers = sys.argv[3] if len(sys.argv) > 3 else '8'
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(job, e, days, end, workers): e for e in LEAGUES}
        for future in as_completed(futures):
            results.append(future.result())
            print(future.result(), flush=True)
    print(f'\nDONE {len(results)} leagues in {time.time()-started:.0f}s')
    import csv
    total = 0
    for code, _ in LEAGUES:
        path = os.path.join(ROOT, 'betting-machine-fc', 'data', f'{code}_stat_history.csv')
        try:
            with open(path, newline='', encoding='utf-8-sig') as handle:
                n = sum(1 for _ in csv.DictReader(handle))
            total += n
            print(f'  {code:8} {n:4} rows')
        except OSError:
            print(f'  {code:8} MISSING')
    print(f'TOTAL stat rows: {total}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
