import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError, validate_snapshot

FIXTURE = json.loads((ROOT / 'tests/fixtures/fc-v2-contract.json').read_text(encoding='utf-8'))
CASES = json.loads((ROOT / 'tests/fixtures/fc-v2-cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('vector', CASES, ids=[v['name'] for v in CASES])
def test_shared_vectors(vector):
    value = copy.deepcopy(FIXTURE)
    for path, replacement in vector['changes']:
        keys = path.split('.')
        target = value
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = replacement
    if vector['valid']:
        assert validate_snapshot(value) is value
    else:
        with pytest.raises(ContractError):
            validate_snapshot(value)


@pytest.mark.parametrize('price', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite(price):
    value = copy.deepcopy(FIXTURE)
    value['quote']['decimal_odds'] = price
    with pytest.raises(ContractError):
        validate_snapshot(value)
