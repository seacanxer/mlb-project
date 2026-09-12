"""Bounded ingestion outcomes. Providers are injected; this module performs no network I/O."""
from dataclasses import dataclass
import time

from .contracts import ContractError, require


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionResult:
    status: str
    records: tuple
    attempts: int
    message: str | None = None


def ingest(fetch, validate, *, max_attempts=3, delays=(0.0, 0.0), sleep=time.sleep):
    require(type(max_attempts) is int and 1 <= max_attempts <= 5, 'Invalid retry limit')
    require(len(delays) >= max_attempts - 1, 'Retry delays missing')
    for attempt in range(1, max_attempts + 1):
        try:
            raw = fetch()
            require(type(raw) in (list, tuple), 'Provider payload must be a collection')
            records = tuple(validate(value) for value in raw)
            return IngestionResult('empty' if not records else 'success', records, attempt)
        except TransportError as exc:
            if attempt == max_attempts:
                return IngestionResult('transport_error', (), attempt, str(exc))
            delay = delays[attempt - 1]
            require(type(delay) in (int, float) and type(delay) is not bool and 0 <= delay <= 30, 'Invalid retry delay')
            sleep(delay)
        except (ContractError, TypeError, ValueError) as exc:
            return IngestionResult('invalid_data', (), attempt, str(exc))
    raise AssertionError('unreachable')
