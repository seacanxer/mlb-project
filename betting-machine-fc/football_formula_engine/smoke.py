"""Offline boundary check only. Never writes picks, calls providers, or fits a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .contracts import ContractError, object_fields, require, validate_snapshot

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent.parent


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ContractError('Nonfinite JSON constant: ' + value)

    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=pairs, parse_constant=invalid_constant)


def validate_config(config):
    object_fields(config, 'schema_version mode engine_enabled official_enabled staking_enabled storage_backend')
    require(config['schema_version'] == 'fc-contract-v2', 'Unsupported config version')
    require(config['mode'] == 'offline_smoke', 'Only offline smoke supported')
    for key in ('engine_enabled', 'official_enabled', 'staking_enabled'):
        require(config[key] is False, key + ' must remain false in Phase 1')
    require(config['storage_backend'] == 'unconfigured', 'Production storage not configured')
    return config


def digest(paths):
    value = hashlib.sha256()
    for path in paths:
        # Ordered bytes, each length-prefixed, independent of checkout location.
        data = Path(path).read_bytes()
        value.update(len(data).to_bytes(8, 'big'))
        value.update(data)
    return value.hexdigest()


def run_smoke(fixture, config):
    validate_config(read_json(config))
    data = validate_snapshot(read_json(fixture))
    require(data['decision']['status'] == 'projection_only', 'Smoke input must be projection-only')
    require(not data['capabilities']['official_enabled'], 'Smoke may not enable official')
    return {
        'checkpoint_version': 1,
        'task': 'phase1-offline-contract-smoke',
        'status': 'complete',
        'schema_version': 'fc-contract-v2',
        'input_sha256': digest([fixture]),
        'config_sha256': digest([config]),
        'implementation_sha256': digest([
            PACKAGE / '__init__.py', PACKAGE / '__main__.py',
            PACKAGE / 'contracts.py', PACKAGE / 'smoke.py',
            ROOT / 'lib/fc/contracts-v2.ts',
        ]),
        'official_enabled': False,
        'model_fitted': False,
        'completed_units': ['config_validation', 'projection_contract_validation'],
    }


def checkpoint(path, result, resume=False):
    path = Path(path)
    if resume:
        require(json.dumps(read_json(path), sort_keys=True) == json.dumps(result, sort_keys=True),
                'Checkpoint mismatch: re-run with a new checkpoint path')
        return
    # Publish complete content without overwriting any existing path. A partial
    # temp file after interruption is not a checkpoint. No cleanup of other files.
    handle, temporary = tempfile.mkstemp(prefix='.fc-smoke-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)  # atomic create-if-absent, same filesystem
    finally:
        os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=ROOT / 'tests/fixtures/fc-v2-contract.json')
    parser.add_argument('--config', type=Path, default=PACKAGE / 'config.json')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args(argv)
    if args.resume and args.checkpoint is None:
        parser.error('--resume requires --checkpoint')
    try:
        result = run_smoke(args.fixture, args.config)
        if args.checkpoint is not None:
            checkpoint(args.checkpoint, result, args.resume)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc), 'official_enabled': False}))
        return 1
