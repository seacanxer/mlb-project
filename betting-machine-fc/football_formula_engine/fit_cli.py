"""Fit immutable Phase 4 candidate and baseline artifacts from frozen CSV data."""
import argparse
import json
from pathlib import Path

from .contracts import ContractError, require
from .data import load_football_data_csv
from .model import FitConfig, build_ratio_baseline_artifact, fit_dixon_coles
from .snapshot_store import AppendOnlySnapshotStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', action='append', type=Path, required=True,
                        help='Repeat once per season, in the same order as --season')
    parser.add_argument('--season', action='append', required=True)
    parser.add_argument('--competition', required=True)
    parser.add_argument('--timezone', required=True)
    parser.add_argument('--cutoff', type=int, required=True,
                        help='Training cutoff as UTC epoch seconds')
    parser.add_argument('--half-life-days', type=int, default=180, choices=(90, 180, 365))
    parser.add_argument('--artifact-root', type=Path,
                        help='Append-only destination; omit for stdout-only dry run')
    args = parser.parse_args(argv)
    try:
        require(len(args.csv) == len(args.season), '--csv and --season counts must match')
        matches = []
        for path, season in zip(args.csv, args.season):
            normalized, _ = load_football_data_csv(
                path, competition_id=args.competition, season=season,
                timezone_name=args.timezone)
            matches.extend(normalized)
        config = FitConfig(half_life_days=args.half_life_days)
        candidate = fit_dixon_coles(matches, cutoff_utc=args.cutoff, config=config)
        baseline = build_ratio_baseline_artifact(matches, cutoff_utc=args.cutoff)
        result = {
            'status': 'complete',
            'candidate': candidate,
            'baseline': baseline,
            'publication': None,
            'official_enabled': False,
            'validation_status': 'unvalidated',
        }
        if args.artifact_root is not None:
            store = AppendOnlySnapshotStore(args.artifact_root)
            result['publication'] = {
                'candidate': store.append('models', candidate['artifact_id'], candidate),
                'baseline': store.append('models', baseline['artifact_id'], baseline),
            }
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc),
                          'official_enabled': False}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
