"""Resumable historical two-outer-period evaluation, never an official approval."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from .contracts import ContractError, require
from .data import load_football_data_csv
from .evaluation import (canonical_bytes, resolve_split, run_chronological_evaluation,
                         seal, validate_sealed_artifact, EVALUATION_SCHEMA)
from .snapshot_store import AppendOnlySnapshotStore
from .uncertainty import run_bootstrap_replicate, summarize_uncertainty


def fold_specs(base):
    specs = []
    for calibration_season, test_season in [('2324', '2425'), ('2425', '2526')]:
        spec = copy.deepcopy(base)
        spec['bootstrap']['method'] = 'moving_block_refit_v2'
        spec['coverage_note'] = 'Historical rolling replay; prior inspected results are not fresh holdouts'
        spec['splits'] = {
            'calibration': dict(season=calibration_season, warmup_matches=100, start_index=100, end_index=199),
            'policy_validation': dict(season=calibration_season, warmup_matches=199, start_index=199, end_index=380),
            'untouched_test': dict(season=test_season, warmup_matches=80, start_index=80, end_index=380),
        }
        specs.append(spec)
    return specs


def validate_periods(matches, specs):
    require(len(specs) >= 2, 'At least two outer periods required')
    seen, previous_end = set(), 0
    for spec in specs:
        calibration_cutoff, calibration = resolve_split(matches, spec['splits']['calibration'])
        policy_cutoff, policy = resolve_split(matches, spec['splits']['policy_validation'])
        cutoff, target = resolve_split(matches, spec['splits']['untouched_test'])
        require(max(m.result_available_at_utc for m in calibration) <= policy_cutoff,
                'Calibration results leak into policy period')
        require(max(m.result_available_at_utc for m in policy) <= cutoff,
                'Policy results leak into outer period')
        ids = {m.fixture_id for m in target}
        require(not seen.intersection(ids), 'Outer test fixtures overlap')
        require(min(m.kickoff_utc for m in target) > previous_end, 'Outer periods are unordered')
        seen.update(ids)
        previous_end = max(m.kickoff_utc for m in target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    package = Path(__file__).resolve().parent
    parser.add_argument('--spec', type=Path, default=package / 'evaluation_spec.json')
    parser.add_argument('--repo-root', type=Path, default=package.parent.parent)
    parser.add_argument('--artifact-root', type=Path, default=package / 'artifacts' / 'outer-v1')
    args = parser.parse_args(argv)
    base = json.loads(args.spec.read_text())
    matches, sources = [], []
    for source in base['dataset']:
        path = args.repo_root / source['path']
        sources.append({**source, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        rows, _ = load_football_data_csv(path, competition_id=base['competition_id'],
                                       season=source['season'], timezone_name=base['timezone'])
        matches.extend(rows)
    specs = fold_specs(base)
    validate_periods(matches, specs)
    store = AppendOnlySnapshotStore(args.artifact_root)
    protocol = seal('protocol', {'schema_version': 'fc-outer-protocol-v1',
                                'sources': sources, 'folds': specs,
                                'evidence_type': 'historical_replay', 'official_enabled': False})
    store.append('protocols', protocol['artifact_id'], protocol)
    reports, uncertainties, failed_refits = [], [], []
    for index, spec in enumerate(specs):
        checkpoint_id = protocol['artifact_id'] + f'-fold-{index}'
        existing = store.get('checkpoints', checkpoint_id)
        if existing:
            report = existing['report']
            validate_sealed_artifact(report, kind='evaluation', schema_version=EVALUATION_SCHEMA)
            require(report['evaluation_spec_sha256'] == hashlib.sha256(canonical_bytes(spec)).hexdigest(),
                    'Checkpoint spec mismatch')
        else:
            print(json.dumps({'status': 'running', 'fold': index}), flush=True)
            bundle = run_chronological_evaluation(matches, spec)
            report = bundle['report']
            store.append('evaluations', report['artifact_id'], report)
            for artifact in bundle['prediction_artifacts'].values():
                store.append('predictions', artifact['artifact_id'], artifact)
            for key in ('test_model_artifact', 'test_ratio_artifact'):
                artifact = bundle[key]
                store.append('models', artifact['artifact_id'], artifact)
            cal = bundle['selected_calibration_artifact']
            store.append('calibrations', cal['calibration_id'], cal)
            store.append('fold-specs', checkpoint_id, spec)
            store.append('checkpoints', checkpoint_id, {'report': report})
        reports.append(report)
        print(json.dumps({'status': 'fold_complete', 'fold': index,
                          'evaluation_id': report['artifact_id']}), flush=True)
        replicates, failures = [], []
        for replicate_index in range(spec['bootstrap']['replicates']):
            replicate_id = report['artifact_id'] + f'-r{replicate_index:04d}'
            replicate = store.get('bootstrap-replicates', replicate_id)
            failure = store.get('bootstrap-failures', replicate_id)
            if failure:
                failures.append(failure)
                continue
            if replicate is None:
                try:
                    replicate = run_bootstrap_replicate(matches, spec, report, replicate_index)
                except ContractError as exc:
                    failure = {'evaluation_id': report['artifact_id'], 'replicate_index': replicate_index,
                               'status': 'failed', 'reason': str(exc)}
                    store.append('bootstrap-failures', replicate_id, failure)
                    failures.append(failure)
                    print(json.dumps({'status': 'bootstrap_failed', 'fold': index,
                                      'replicate': replicate_index, 'reason': str(exc)}), flush=True)
                    continue
                store.append('bootstrap-replicates', replicate_id, replicate)
            replicates.append(replicate)
            print(json.dumps({'status': 'bootstrap_checkpoint', 'fold': index,
                              'replicate': replicate_index}), flush=True)
        uncertainty = (summarize_uncertainty(spec, report, replicates) if replicates else
                       seal('uncertainty', {'schema_version': 'fc-uncertainty-report-v1',
                           'evaluation_id': report['artifact_id'], 'successful_replicates': 0,
                           'status': 'UNCERTAINTY_UNAVAILABLE_NO_SUCCESSFUL_REFITS',
                           'official_eligible': False}))
        store.append('uncertainty', uncertainty['artifact_id'], uncertainty)
        uncertainties.append(uncertainty)
        failed_refits.append(failures)
    summary = seal('outer', {
        'schema_version': 'fc-outer-evaluation-v1', 'protocol_id': protocol['artifact_id'],
        'multiple_outer_periods': True, 'outer_period_count': len(reports),
        'evidence_type': 'historical_replay', 'fresh_holdout_claim': False,
        'failed_refits': failed_refits,
        'segment_quality': {
            market: {'beats_league_baseline_in_both_periods': all(
                r['test_metrics']['selected_candidate'][metric] <
                r['test_metrics']['league_average_poisson'][metric] for r in reports),
                'official_enabled': False}
            for market, metric in [('1x2', '1x2_brier'), ('btts', 'btts_brier'), ('ou_2_5', 'ou25_brier')]},
        'uncertainty': [{'artifact_id': u['artifact_id'], 'status': u['status'],
                         'replicates': u['successful_replicates']} for u in uncertainties],
        'periods': [{'evaluation_id': r['artifact_id'], 'selection': r['selection'],
                     'test_metrics': r['test_metrics'], 'quality_gate': r['quality_gate']} for r in reports],
        'remaining_blockers': (['PER_FOLD_UNCERTAINTY'] if any(u['status'] != 'AVAILABLE'
                                                            for u in uncertainties) else []) +
                             ['TIMED_ENTRY_ROI', 'MATCHED_CLOSING_CLV',
                               'SECOND_BOOKMAKER_VALIDATION', 'PROSPECTIVE_VALIDATION'],
        'official_enabled': False,
    })
    store.append('outer-evaluations', summary['artifact_id'], summary)
    print(json.dumps({'status': 'complete', 'artifact_id': summary['artifact_id'],
                      'outer_period_count': len(reports), 'official_enabled': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
