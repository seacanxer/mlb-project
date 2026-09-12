from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.ingestion import TransportError, ingest


def test_empty_is_not_transport_failure():
    result = ingest(lambda: [], lambda value: value)
    assert result.status == 'empty' and result.attempts == 1 and result.message is None


def test_transport_retries_are_bounded():
    calls, sleeps = [], []
    def fetch():
        calls.append(1)
        raise TransportError('network down')
    result = ingest(fetch, lambda value: value, max_attempts=3, delays=(.1, .2), sleep=sleeps.append)
    assert result.status == 'transport_error' and result.attempts == 3
    assert len(calls) == 3 and sleeps == [.1, .2]


def test_validation_failure_is_not_retried():
    calls = []
    def fetch(): calls.append(1); return [{'bad': True}]
    def validate(value): raise ContractError('bad record')
    result = ingest(fetch, validate)
    assert result.status == 'invalid_data' and len(calls) == 1


def test_success_after_transport_error():
    values = [TransportError('temporary'), [1, 2]]
    def fetch():
        value = values.pop(0)
        if isinstance(value, Exception): raise value
        return value
    result = ingest(fetch, lambda value: value * 2, max_attempts=2, delays=(0,), sleep=lambda _: None)
    assert result.status == 'success' and result.records == (2, 4)
