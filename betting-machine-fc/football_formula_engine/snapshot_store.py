"""Append-only local snapshot store for offline/replay work; no global active pointer."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .contracts import ContractError, require


SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def canonical_bytes(payload):
    try:
        return (json.dumps(payload, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ContractError('Snapshot is not canonical JSON') from exc


class AppendOnlySnapshotStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, kind, snapshot_id):
        require(type(kind) is str and SAFE_ID.fullmatch(kind), 'Invalid snapshot kind')
        require(type(snapshot_id) is str and SAFE_ID.fullmatch(snapshot_id), 'Invalid snapshot ID')
        folder = self.root / kind
        folder.mkdir(exist_ok=True)
        return folder / f'{snapshot_id}.json'

    def append(self, kind, snapshot_id, payload):
        target = self._path(kind, snapshot_id)
        data = canonical_bytes(payload)
        digest = hashlib.sha256(data).hexdigest()
        if target.exists():
            require(target.read_bytes() == data, 'Snapshot ID conflict')
            return {'status': 'deduplicated', 'sha256': digest, 'path': str(target)}
        handle, temporary = tempfile.mkstemp(prefix='.snapshot-', dir=target.parent)
        try:
            with os.fdopen(handle, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                require(target.read_bytes() == data, 'Concurrent snapshot ID conflict')
                return {'status': 'deduplicated', 'sha256': digest, 'path': str(target)}
        finally:
            os.unlink(temporary)
        return {'status': 'created', 'sha256': digest, 'path': str(target)}

    def get(self, kind, snapshot_id):
        target = self._path(kind, snapshot_id)
        if not target.exists():
            return None
        try:
            def pairs(items):
                value = {}
                for key, item in items:
                    if key in value:
                        raise ValueError('Duplicate JSON key')
                    value[key] = item
                return value
            def invalid_constant(value):
                raise ValueError('Nonfinite JSON constant: ' + value)
            return json.loads(target.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                              parse_constant=invalid_constant)
        except (OSError, ValueError) as exc:
            raise ContractError('Corrupt snapshot') from exc
