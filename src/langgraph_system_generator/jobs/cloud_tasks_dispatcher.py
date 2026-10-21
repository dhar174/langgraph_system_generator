"""Lazy Cloud Tasks adapter. Queue operations never run in DB transactions."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .models import DispatchIntent, JobError


@dataclass(frozen=True)
class CloudTasksConfig:
    queue: str
    worker_url: str
    audience: str
    service_account: str
    dispatch_deadline: int = 360

    def __post_init__(self) -> None:
        url, audience = urlsplit(self.worker_url), urlsplit(self.audience)
        if (
            not re.fullmatch(
                r"projects/[a-z][a-z0-9-]{4,61}[a-z0-9]/locations/[a-z0-9-]+/queues/[A-Za-z0-9_-]{1,100}",
                self.queue,
            )
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port not in (None, 443)
            or url.path != "/internal/execute"
            or not url.hostname.endswith(".run.app")
            or audience.scheme != "https"
            or audience.netloc != url.netloc
            or audience.path not in ("", "/")
            or audience.query
            or audience.fragment
            or not re.fullmatch(
                r"[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,61}[a-z0-9]\.iam\.gserviceaccount\.com",
                self.service_account,
            )
            or self.service_account.split("@")[-1]
            != self.queue.split("/")[1] + ".iam.gserviceaccount.com"
            or type(self.dispatch_deadline) is not int
            or not 15 <= self.dispatch_deadline <= 1800
        ):
            raise JobError("dispatch_configuration_invalid", 503)


class CloudTasksDispatcher:
    def __init__(self, config: CloudTasksConfig, *, client: Any = None):
        self.config, self._client = config, client

    def _connect(self) -> Any:
        if self._client is None:
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def dispatch(self, intent: DispatchIntent) -> str:
        if (
            not re.fullmatch(r"[a-f0-9]{32}", intent.job_id)
            or intent.intent_id != f"{intent.job_id}-{intent.generation}"
            or not intent.pending
        ):
            raise JobError("dispatch_intent_invalid", 400)
        digest = hashlib.sha256(
            f"v1:{intent.job_id}:{intent.generation}".encode()
        ).hexdigest()
        name = f"{self.config.queue}/tasks/{digest}"
        request = {
            "parent": self.config.queue,
            "task": {
                "name": name,
                "dispatch_deadline": {"seconds": self.config.dispatch_deadline},
                "http_request": {
                    "http_method": "POST",
                    "url": self.config.worker_url,
                    "headers": {"Content-Type": "application/json"},
                    "oidc_token": {
                        "service_account_email": self.config.service_account,
                        "audience": self.config.audience,
                    },
                    "body": json.dumps(
                        {
                            "schema_version": 1,
                            "job_id": intent.job_id,
                            "dispatch_generation": intent.generation,
                        }
                    ).encode(),
                },
            },
        }
        try:
            client = self._connect()
            try:
                task = client.create_task(request=request, retry=None, timeout=10)
            except Exception as error:
                from google.api_core.exceptions import (
                    AlreadyExists,
                    DeadlineExceeded,
                    ServiceUnavailable,
                )

                if not isinstance(
                    error, (AlreadyExists, DeadlineExceeded, ServiceUnavailable)
                ):
                    raise
                try:
                    task = client.get_task(
                        request={"name": name}, retry=None, timeout=10
                    )
                except Exception as lookup_error:
                    from google.api_core.exceptions import NotFound

                    if isinstance(lookup_error, NotFound):
                        raise JobError("dispatch_tombstone", 503) from None
                    raise
            if task.name != name:
                raise JobError("dispatch_reference_invalid", 503)
            return name
        except JobError:
            raise
        except Exception:  # noqa: BLE001 - redact SDK and credential errors
            raise JobError("dispatch_unavailable", 503) from None
