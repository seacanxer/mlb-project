"""Run/resume Phase 5 moving-block refits and publish validation status."""
import argparse
import json
from pathlib import Path

from .data import load_football_data_csv
from .evaluation import EVALUATION_SCHEMA, validate_sealed_artifact
from .smoke import read_json
from .snapshot_store import AppendOnlySnapshotStore
from .uncertainty import (build_validation_registry, run_bootstrap_replicate,
                          summarize_uncertainty)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    package = Path(__file__).resolve().parent
    parser.add_argument('--evaluation-id', required=True)
    parser.add_argument('--spec', type=Path, default=package / 'evaluation_spec.json')
    parser.add_argument('--repo-root', type=Path, default=package.parent.parent)
    parser.add_argument('--artifact-root', type=Path, default=package / 'artifacts')
    args = parser.parse_args(argv)
    store = AppendOnlySnapshotStore(args.artifact_root)
    try:
        spec = read_json(args.spec)
        evaluation = store.get('evaluations', args.evaluation_id)
        if evaluation is None:
            raise ValueError('Evaluation artifact not found')
        validate_sealed_artifact(evaluation, kind='evaluation', schema_version=EVALUATION_SCHEMA)
        matches = []
        for source in spec['dataset']:
            normalized, _ = load_football_data_csv(
                args.repo_root / source['path'], competition_id=spec['competition_id'],
                season=source['season'], timezone_name=spec['timezone'])
            matches.extend(normalized)
        replicates, statuses = [], []
        for index in range(spec['bootstrap']['replicates']):
            checkpoint_id = f"{args.evaluation_id}-r{index:04d}"
            existing = store.get('bootstrap-replicates', checkpoint_id)
            if existing is not None:
                validate_sealed_artifact(existing, kind='bootstrap',
                                         schema_version='fc-bootstrap-replicate-v1')
                if (existing.get('evaluation_id') != args.evaluation_id
                        or existing.get('replicate_index') != index):
                    raise ValueError('Bootstrap checkpoint mismatch')
                replicate = existing
                status = 'resumed'
            else:
                replicate = run_bootstrap_replicate(matches, spec, evaluation, index)
                store.append('bootstrap-replicates', checkpoint_id, replicate)
                status = 'created'
            replicates.append(replicate)
            statuses.append({'replicate_index': index, 'status': status,
                             'artifact_id': replicate['artifact_id']})
        uncertainty = summarize_uncertainty(spec, evaluation, replicates)
        validation = build_validation_registry(spec, evaluation, uncertainty)
        publications = {
            'uncertainty': store.append('uncertainty', uncertainty['artifact_id'], uncertainty),
            'validation': store.append('validation', validation['artifact_id'], validation),
        }
        print(json.dumps({
            'status': 'complete',
            'evaluation_id': args.evaluation_id,
            'replicates': statuses,
            'uncertainty_id': uncertainty['artifact_id'],
            'uncertainty_status': uncertainty['status'],
            'metric_quantiles': uncertainty['metric_quantiles'],
            'validation_id': validation['artifact_id'],
            'overall_status': validation['overall_status'],
            'segments': validation['segments'],
            'official_enabled': False,
            'publication': publications,
        }, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc),
                          'official_enabled': False}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
