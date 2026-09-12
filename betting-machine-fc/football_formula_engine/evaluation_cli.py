"""Run and publish the frozen Phase 5 chronological evaluation."""
import argparse
import json
from pathlib import Path

from .data import load_football_data_csv
from .evaluation import run_chronological_evaluation
from .smoke import read_json
from .snapshot_store import AppendOnlySnapshotStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    package = Path(__file__).resolve().parent
    parser.add_argument('--spec', type=Path, default=package / 'evaluation_spec.json')
    parser.add_argument('--repo-root', type=Path, default=package.parent.parent)
    parser.add_argument('--artifact-root', type=Path, default=package / 'artifacts')
    args = parser.parse_args(argv)
    try:
        spec = read_json(args.spec)
        matches = []
        for source in spec['dataset']:
            normalized, _ = load_football_data_csv(
                args.repo_root / source['path'], competition_id=spec['competition_id'],
                season=source['season'], timezone_name=spec['timezone'])
            matches.extend(normalized)
        bundle = run_chronological_evaluation(matches, spec)
        store = AppendOnlySnapshotStore(args.artifact_root)
        report = bundle['report']
        publication = {
            'report': store.append('evaluations', report['artifact_id'], report),
            'test_model': store.append('models', bundle['test_model_artifact']['artifact_id'],
                                       bundle['test_model_artifact']),
            'test_ratio': store.append('models', bundle['test_ratio_artifact']['artifact_id'],
                                       bundle['test_ratio_artifact']),
            'calibration': store.append(
                'calibrations', bundle['selected_calibration_artifact']['calibration_id'],
                bundle['selected_calibration_artifact']),
            'predictions': {},
        }
        for label, artifact in bundle['prediction_artifacts'].items():
            publication['predictions'][label] = store.append(
                'predictions', artifact['artifact_id'], artifact)
        print(json.dumps({
            'status': 'complete',
            'evaluation_id': report['artifact_id'],
            'selection': report['selection'],
            'test_metrics': report['test_metrics'],
            'quality_gate': report['quality_gate'],
            'validation_status': report['validation_status'],
            'official_enabled': False,
            'publication': publication,
        }, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc),
                          'official_enabled': False}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
