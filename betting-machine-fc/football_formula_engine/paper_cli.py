"""Reproducible Phase 6 offline checkpoint; synthetic locks never become picks."""
import argparse
import json
import tempfile
from pathlib import Path

from .ledger import PaperLedger
from .policy import select_candidates
from .smoke import read_json
from .snapshot_store import AppendOnlySnapshotStore


def run_checkpoint():
    root = Path(__file__).resolve().parents[2]
    snapshot = read_json(root / 'tests/fixtures/fc-v2-contract.json')
    # Current registry supplies no approval; all input opportunities stay blocked.
    registry = read_json(Path(__file__).parent / 'artifacts/phase5-validation-registry.json')
    assert all(value != 'approved' for value in registry['segment_status'].values())
    policy = select_candidates([snapshot], {}, decision_at=snapshot['decision_at'])
    with tempfile.TemporaryDirectory(prefix='fc-phase6-') as folder:
        ledger = PaperLedger(Path(folder) / 'paper.db')
        empty = ledger.tracker()
    return {'schema_version': 'fc-phase6-checkpoint-v1', 'policy_version': policy['policy_version'],
            'input_provenance': 'synthetic contract harness; not real fixture opportunities',
            'validation_id': registry['validation_id'], 'status': policy['status'],
            'selected_count': len(policy['selected']), 'rejection_counts': policy['rejection_counts'],
            'tracker': empty, 'official_enabled': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path)
    args = parser.parse_args(argv)
    result = run_checkpoint()
    if args.artifact_root:
        AppendOnlySnapshotStore(args.artifact_root).append('phase6', 'paper-checkpoint-v1', result)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
