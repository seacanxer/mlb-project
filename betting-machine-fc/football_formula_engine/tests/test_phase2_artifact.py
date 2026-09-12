import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'betting-machine-fc'))
from football_formula_engine.data import dataset_manifest, load_football_data_csv


def test_e0_2526_manifest_reproduces_from_tracked_csv():
    source = ROOT / 'betting-machine-fc/data/E0_2526.csv'
    artifact = json.loads((ROOT / 'betting-machine-fc/football_formula_engine/artifacts/phase2-e0-2526-manifest.json').read_text(encoding='utf-8'))
    matches, quotes = load_football_data_csv(source, competition_id='E0', season='2526', timezone_name='Europe/London')
    generated = dataset_manifest(matches, quotes)
    for key, value in generated.items():
        assert artifact[key] == value
    assert artifact['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
