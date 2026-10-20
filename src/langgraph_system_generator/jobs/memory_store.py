"""Deterministic transactional test double; never a durable backend fallback."""

from collections.abc import Callable
from copy import deepcopy
from threading import RLock

from .service import Document, T, Transaction, TransactionalJobStore


class MemoryTransaction:
    def __init__(self, documents: dict[str, Document]):
        self.documents = documents
        self.writing = False

    def get(self, path: str) -> Document | None:
        if self.writing:
            raise AssertionError("transaction read after write")
        return deepcopy(self.documents.get(path))

    def set(self, path: str, value: Document) -> None:
        self.writing = True
        self.documents[path] = deepcopy(value)

    def delete(self, path: str) -> None:
        self.writing = True
        self.documents.pop(path, None)


class MemoryDatabase:
    def __init__(self):
        self.documents: dict[str, Document] = {}
        self.lock = RLock()

    def run(self, callback: Callable[[Transaction], T]) -> T:
        with self.lock:
            candidate = deepcopy(self.documents)
            result = callback(MemoryTransaction(candidate))
            self.documents = candidate
            return result

    def due(
        self,
        collection: str,
        field: str,
        now: float,
        limit: int,
        *,
        deadline_field: str | None = None,
    ) -> list[str]:
        with self.lock:
            candidates = [
                (
                    (
                        (data[deadline_field], data[field])
                        if deadline_field
                        else (data[field],)
                    ),
                    path,
                )
                for path, data in self.documents.items()
                if path.count("/") == 1
                and path.startswith(collection + "/")
                and data.get(field) is not None
                and data[field] <= now
                and (deadline_field is None or data.get(deadline_field, 0) > now)
            ]
            return [path for _, path in sorted(candidates)[:limit]]


class InMemoryJobStore(TransactionalJobStore):
    def __init__(self, idempotency_secret: bytes, **kwargs):
        super().__init__(MemoryDatabase(), idempotency_secret, **kwargs)
