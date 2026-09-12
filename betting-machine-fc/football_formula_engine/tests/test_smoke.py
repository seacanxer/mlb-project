import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.contracts import ContractError
from football_formula_engine.smoke import PACKAGE, checkpoint, main, read_json, run_smoke, validate_config

FIXTURE = ROOT / 'tests/fixtures/fc-v2-contract.json'
CONFIG = PACKAGE / 'config.json'


def test_deterministic_smoke():
    first = run_smoke(FIXTURE, CONFIG)
    assert first == run_smoke(FIXTURE, CONFIG)
    assert first['official_enabled'] is False
    assert first['model_fitted'] is False


@pytest.mark.parametrize('key', ['engine_enabled', 'official_enabled', 'staking_enabled'])
@pytest.mark.parametrize('value', [True, 'false', 0, None])
def test_fail_closed_config(key, value):
    config = read_json(CONFIG)
    config[key] = value
    with pytest.raises(ContractError):
        validate_config(config)


def test_publish_resume_no_overwrite(tmp_path):
    path = tmp_path / 'checkpoint.json'
    result = run_smoke(FIXTURE, CONFIG)
    checkpoint(path, result)
    checkpoint(path, result, resume=True)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        checkpoint(path, result)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.fc-smoke-*'))


@pytest.mark.parametrize('field', ['input_sha256', 'config_sha256', 'implementation_sha256', 'status'])
def test_resume_rejects_incompatible_checkpoint(tmp_path, field):
    path = tmp_path / 'checkpoint.json'
    result = run_smoke(FIXTURE, CONFIG)
    checkpoint(path, result)
    with pytest.raises(ContractError):
        checkpoint(path, {**result, field: 'changed'}, resume=True)


def test_corrupt_checkpoint_rejected(tmp_path):
    path = tmp_path / 'checkpoint.json'
    path.write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        checkpoint(path, run_smoke(FIXTURE, CONFIG), resume=True)


@pytest.mark.parametrize('content', ['{"a":1,"a":2}', '{"a":NaN}'])
def test_strict_json(tmp_path, content):
    path = tmp_path / 'bad.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ContractError):
        read_json(path)


def test_cli_checkpoint_roundtrip(tmp_path, capsys):
    path = str(tmp_path / 'checkpoint.json')
    assert main(['--checkpoint', path]) == 0
    assert main(['--checkpoint', path, '--resume']) == 0
    assert main(['--checkpoint', path]) == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status'] == 'error'


def test_missing_file_fails_closed(tmp_path, capsys):
    assert main(['--fixture', str(tmp_path / 'missing.json')]) == 1
    assert json.loads(capsys.readouterr().out)['official_enabled'] is False


def test_failed_publish_leaves_no_checkpoint(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('simulated publish failure')
    monkeypatch.setattr('football_formula_engine.smoke.os.link', fail)
    path = tmp_path / 'checkpoint.json'
    with pytest.raises(OSError):
        checkpoint(path, run_smoke(FIXTURE, CONFIG))
    assert not path.exists()
    assert not list(tmp_path.glob('.fc-smoke-*'))


def test_resume_rejects_bool_replaced_by_number(tmp_path):
    path = tmp_path / 'checkpoint.json'
    result = run_smoke(FIXTURE, CONFIG)
    checkpoint(path, {**result, 'official_enabled': 0})
    with pytest.raises(ContractError):
        checkpoint(path, result, resume=True)
