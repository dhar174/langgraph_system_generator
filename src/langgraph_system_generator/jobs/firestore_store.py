"""Lazy Firestore Native adapter. No Google import or ADC discovery at import."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .models import JobError
from .service import Document, T, Transaction, TransactionalJobStore


class FirestoreTransaction:
    def __init__(self, client: Any, transaction: Any):
        self.client = client
        self.transaction = transaction

    def get(self, path: str) -> Document | None:
        snapshot = self.client.document(path).get(
            transaction=self.transaction, timeout=10
        )
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        data.pop("delete_after", None)
        return data

    def set(self, path: str, value: Document) -> None:
        data = dict(value)
        # Firestore TTL requires a timestamp, not numeric epoch seconds.
        if "expires_at" in data:
            data["delete_after"] = datetime.fromtimestamp(
                data["expires_at"], timezone.utc
            )
        self.transaction.set(self.client.document(path), data)

    def delete(self, path: str) -> None:
        self.transaction.delete(self.client.document(path))


class FirestoreDatabase:
    def __init__(
        self, project: str, database: str = "(default)", *, client: Any = None
    ):
        self.project = project
        self.database = database
        self._client = client

    def _connect(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import firestore

                self._client = firestore.Client(
                    project=self.project, database=self.database
                )
            except Exception:  # noqa: BLE001 - sanitize optional SDK/ADC failures
                raise JobError("job_backend_unavailable", 503) from None
        return self._client

    def run(self, callback: Callable[[Transaction], T]) -> T:
        try:
            from google.cloud import firestore

            client = self._connect()
            transaction = client.transaction(max_attempts=5)

            @firestore.transactional
            def operation(tx: Any) -> T:
                return callback(FirestoreTransaction(client, tx))

            return operation(transaction)
        except JobError:
            raise
        except Exception:  # noqa: BLE001 - sanitize SDK failures at storage boundary
            # Never reflect ADC paths, endpoints, prompts or SDK response bodies.
            raise JobError("job_backend_unavailable", 503) from None

    def due(self, collection: str, field: str, now: float, limit: int) -> list[str]:
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = (
                self._connect()
                .collection(collection)
                .where(filter=FieldFilter(field, "<=", now))
                .order_by(field)
                .limit(limit)
            )
            return [snapshot.reference.path for snapshot in query.stream(timeout=10)]
        except Exception:  # noqa: BLE001 - sanitize SDK failures at storage boundary
            raise JobError("job_backend_unavailable", 503) from None


class FirestoreJobStore(TransactionalJobStore):
    def __init__(
        self,
        project: str,
        idempotency_secret: bytes,
        database: str = "(default)",
        *,
        client: Any = None,
        **kwargs: Any,
    ):
        super().__init__(
            FirestoreDatabase(project, database, client=client),
            idempotency_secret,
            **kwargs,
        )
