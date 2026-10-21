"""Google OIDC service tokens, separate from signed IAP user assertions."""

import re
from collections.abc import Callable
from typing import Any

from .models import JobError, ServiceIdentity


class GoogleOIDCVerifier:
    def __init__(self, audience: str, *, request: Callable[..., Any] | None = None):
        if not re.fullmatch(r"https://[a-z0-9.-]+\.run\.app/?", audience):
            raise JobError("worker_identity_configuration_invalid", 503)
        self.audience, self.request = audience, request

    def verify(self, authorization: str) -> ServiceIdentity:
        if not authorization.startswith("Bearer ") or len(authorization) > 16384:
            raise JobError("worker_identity_invalid", 401)
        token = authorization[7:]
        if len(token.split(".")) != 3 or "SIGNATURE_REMOVED" in token:
            raise JobError("worker_identity_invalid", 401)
        try:
            from google.oauth2.id_token import verify_oauth2_token

            request = self.request
            session = None
            if request is None:
                import requests
                from google.auth.transport.requests import Request

                session = requests.Session()
                session.trust_env = False
                transport = Request(session=session)

                def bounded_request(url, method="GET", **kwargs):
                    return transport(url, method=method, timeout=5)

                request = bounded_request
            try:
                claims = verify_oauth2_token(token, request, audience=self.audience)
            finally:
                if session is not None:
                    session.close()
            # Signature, trusted issuer, aud, iat and exp verified by google-auth.
            # Identity allowlisting is route-specific in WorkerJobService.
            if (
                claims.get("email_verified") is not True
                or not isinstance(claims.get("sub"), str)
                or not claims["sub"]
                or not isinstance(claims.get("email"), str)
                or not re.fullmatch(
                    r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", claims["email"]
                )
                or type(claims.get("iat")) is not int
                or type(claims.get("exp")) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 3600
            ):
                raise ValueError("invalid service identity")
            return ServiceIdentity(
                service_account=claims["email"], audience=self.audience
            )
        except ImportError:
            raise JobError("worker_identity_unavailable", 503) from None
        except Exception as error:  # noqa: BLE001 - token/key errors fail closed
            from google.auth.exceptions import TransportError

            if isinstance(error, TransportError):
                raise JobError("worker_identity_unavailable", 503) from None
            raise JobError("worker_identity_invalid", 401) from None
