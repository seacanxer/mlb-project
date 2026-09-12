import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.snapshot_store import AppendOnlySnapshotStore


def test_append_get_and_idempotent_dedup(tmp_path):
    store = AppendOnlySnapshotStore(tmp_path)
    created = store.append('quotes', 'q-1', {'b': 2, 'a': 1})
    assert created['status'] == 'created'
    assert store.append('quotes', 'q-1', {'a': 1, 'b': 2})['status'] == 'deduplicated'
    assert store.get('quotes', 'q-1') == {'a': 1, 'b': 2}


def test_same_id_different_content_rejected(tmp_path):
    store = AppendOnlySnapshotStore(tmp_path)
    store.append('quotes', 'q-1', {'a': 1})
    with pytest.raises(ContractError):
        store.append('quotes', 'q-1', {'a': 2})


@pytest.mark.parametrize('kind,snapshot_id', [('../escape', 'id'), ('quotes', '../id'), ('', 'id'), ('quotes', 'a/b')])
def test_paths_cannot_escape_store(tmp_path, kind, snapshot_id):
    with pytest.raises(ContractError):
        AppendOnlySnapshotStore(tmp_path).append(kind, snapshot_id, {})


@pytest.mark.parametrize('payload', [{'x': float('nan')}, {'x': {1, 2}}])
def test_noncanonical_payload_rejected(tmp_path, payload):
    with pytest.raises(ContractError):
        AppendOnlySnapshotStore(tmp_path).append('runs', 'r1', payload)


def test_corrupt_snapshot_is_not_empty(tmp_path):
    store = AppendOnlySnapshotStore(tmp_path)
    folder = tmp_path / 'runs'; folder.mkdir()
    (folder / 'r1.json').write_text('{', encoding='utf-8')
    with pytest.raises(ContractError):
        store.get('runs', 'r1')


def test_missing_snapshot_is_explicit_none(tmp_path):
    assert AppendOnlySnapshotStore(tmp_path).get('runs', 'missing') is None


def test_duplicate_key_snapshot_is_corrupt(tmp_path):
    store = AppendOnlySnapshotStore(tmp_path)
    folder = tmp_path / 'runs'; folder.mkdir()
    (folder / 'r1.json').write_text('{"a":1,"a":2}', encoding='utf-8')
    with pytest.raises(ContractError): store.get('runs', 'r1')
