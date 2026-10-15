#!/usr/bin/env python3
"""Offline phase-2 evidence. Reads snapshots; writes only --out and temporary probes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'betting-machine-fc'))
from football_formula_engine.live_quotes import QuoteJournal
from football_formula_engine.markets import PayoutProbabilities
from football_formula_engine.quant import quant_metrics
from football_formula_engine.sharp_reference import reference_snapshot
from football_formula_engine.value import expected_value


def dry_run(matches_path, out):
    raw=matches_path.read_bytes()
    matches=json.loads(raw)
    classified, legacy_top, blocked_top, mismatches=Counter(),0,0,0
    for match in matches:
        for p in match.get('projections') or []:
            if p['market'] not in ('1x2','ah','ou','btts') or not p.get('payout') or not p.get('odds'):
                continue
            # A disk snapshot is not fresh observed evidence; no new value can
            # be proven by fitting its own bookmaker's price back to itself.
            q=quant_metrics(PayoutProbabilities(**p['payout']),p['odds'],
                market_no_vig=p.get('market_probability'),
                decision_source=p.get('confidence_source','unknown'),
                gate_reasons=['OFFLINE_SNAPSHOT_NO_FRESH_REFERENCE'])
            classified[q['status']]+=1
            if abs(q['ev']-p['ev'])>.000051:
                mismatches+=1
            if p['odds']>=1.4 and (p.get('confidence_tier')=='TINGGI' or (p.get('confidence') or 0)>=.65):
                legacy_top+=1
                blocked_top+=q['status']!='value'
    log=runpy.run_path(str(ROOT/'scripts/fc-log-projections.py'))
    rows=log['collect_rows'](matches,'2026-10-15T00:00:00Z')
    now=1_900_000_000
    with tempfile.TemporaryDirectory(prefix='fc-quant-proof-',dir=out.parent) as temp:
        journal=QuoteJournal(Path(temp)/'quotes.db')
        obs=journal.record({'match_id':'synthetic','start_ts':now+3600},
            {'odds_1x2':{1:2.,2:4.,3:4.},'odds_ou':{2.5:{9:2.,10:2.}}},{},
            captured_at=now-5,source_updated_at=now-3600,bookmaker='pinnacle')
        fresh=reference_snapshot([obs],'pinnacle',now)
        a={'market':'1x2','side':'home','line_quarters':None,'decimal_odds':2.}
        b={'market':'ou','side':'over','line_quarters':10,'decimal_odds':2.}
        decisions=[journal.record_research_decision(obs['artifact_id'],p,decision_at=now,
            policy_id='test',model={'formula_version':'v2'}) for p in (a,b)]
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'mode':'offline_dry_run',
        'source_sha256':hashlib.sha256(raw).hexdigest(),'fixtures':len(matches),
        'primary_statuses_without_fresh_reference':dict(classified),
        'legacy_top_count':legacy_top,'legacy_top_withheld_from_actionable':blocked_top,
        'payout_ev_mismatches':mismatches,
        'low_odds_1x2_logged':sum(r['market']=='1x2' and 1<r.get('odds',0)<1.3 for r in rows),
        'stale_reference_accepted_contracts':len(fresh['fair']),
        'stale_reference_reason_codes':fresh['reason_codes'],
        'research_distinct_contract_ids':len({p['artifact_id'] for p in decisions})==2,
        'research_second_contract_matches_request':decisions[1]['contract']==b,
        'win_rate_improvement_measured':False,'roi_improvement_measured':False,
        'limitations':['No live provider requests, locks, settlement or retraining.',
                       'Snapshot replay verifies guards, not predictive accuracy.',
                       'Contemporary v5 ledger/grades are absent locally; no new performance claim.']}
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--matches',type=Path,default=ROOT/'betting-machine-fc/matches_detailed.json')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.matches.resolve()==args.out.resolve():
        ap.error('Output must differ from source snapshot')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    print(json.dumps(dry_run(args.matches,args.out),indent=2))
