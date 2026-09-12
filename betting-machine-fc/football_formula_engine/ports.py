"""Persistence boundaries only. No backend, migrations, or production writer."""
from typing import Any, Mapping, Protocol


class SnapshotRepository(Protocol):
    def append(self, kind: str, snapshot_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Append immutable content; same ID/different content must be rejected."""
        ...

    def get(self, kind: str, snapshot_id: str) -> Mapping[str, Any] | None:
        ...


class RunPublisher(Protocol):
    def publish_complete(self, run_id: str, manifest: Mapping[str, Any]) -> None:
        """Validate all outputs then atomically switch the complete-run pointer."""
        ...


class SettlementRepository(Protocol):
    def append_revision(self, bet_id: str, revision_id: str, payload: Mapping[str, Any]) -> None:
        """Transactional and idempotent by bet/revision; never overwrite locked odds."""
        ...
