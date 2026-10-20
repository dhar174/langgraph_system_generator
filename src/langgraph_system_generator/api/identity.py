"""Verify direct Cloud Run IAP user assertions; never trust unsigned headers."""

import json
import math
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from langgraph_system_generator.jobs.models import JobError, Principal

ISSUER = "https://cloud.google.com/iap"
KEY_URL = "https://www.gstatic.com/iap/verify/public_key"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_keys() -> Mapping[str, str]:
    # Fixed trust root, no proxy inheritance, no redirects, bounded response/time.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(KEY_URL, timeout=5) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("key response too large")
    return json.loads(data)


class TrustedIAPKeys:
    def __init__(
        self,
        fetch: Callable[[], Mapping[str, str]] = _fetch_keys,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl: int = 300,
    ):
        if not 1 <= ttl <= 3600:
            raise JobError("identity_configuration_invalid", 503)
        self.fetch = fetch
        self.clock = clock
        self.ttl = ttl
        self.expires_at = 0.0
        self.keys: dict[str, str] = {}
        self.failed_until = 0.0
        self.lock = threading.Lock()

    def get(self, kid: str) -> str:
        with self.lock:
            now = self.clock()
            if now < self.failed_until:
                raise JobError("identity_verification_unavailable", 503)
            if now >= self.expires_at:
                try:
                    keys = self.fetch()
                    if (
                        not isinstance(keys, Mapping)
                        or not 1 <= len(keys) <= 16
                        or any(
                            not isinstance(k, str)
                            or not isinstance(v, str)
                            or len(k) > 128
                            or len(v) > 4096
                            for k, v in keys.items()
                        )
                    ):
                        raise ValueError("invalid key set")
                    self.keys = dict(keys)
                    self.expires_at = now + self.ttl
                except Exception:  # noqa: BLE001 - fail closed on key-fetch failure
                    self.keys = {}
                    self.failed_until = now + 30
                    raise JobError("identity_verification_unavailable", 503) from None
            # Unknown kid does not cause attacker-controlled repeated refreshes.
            if kid not in self.keys:
                raise JobError("identity_invalid", 401)
            return self.keys[kid]


class IAPVerifier:
    def __init__(
        self,
        audience: str,
        keys: TrustedIAPKeys | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ):
        if not re.fullmatch(
            r"/projects/[0-9]+/locations/[a-z0-9-]+/services/[a-z][a-z0-9-]{0,62}",
            audience,
        ):
            raise JobError("identity_configuration_invalid", 503)
        self.audience = audience
        self.keys = keys if keys is not None else TrustedIAPKeys()
        self.clock = clock

    def verify(self, assertion: str | None) -> Principal:
        if not assertion or len(assertion) > 16384:
            raise JobError("identity_invalid", 401)
        try:
            import jwt

            header = jwt.get_unverified_header(assertion)
            if (
                header.get("alg") != "ES256"
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 128
                or any(key in header for key in ("jku", "x5u", "jwk", "crit"))
            ):
                raise ValueError("invalid header")
            key = self.keys.get(header["kid"])
            claims: dict[str, Any] = jwt.decode(
                assertion,
                key,
                algorithms=["ES256"],
                audience=self.audience,
                issuer=ISSUER,
                options={
                    "require": ["iss", "sub", "aud", "iat", "exp"],
                    "verify_iat": False,
                    "verify_exp": False,
                    "verify_nbf": False,
                    "strict_aud": True,
                },
            )
            now = self.clock()
            iat, exp = claims["iat"], claims["exp"]
            if (
                type(iat) not in (int, float)
                or type(exp) not in (int, float)
                or not math.isfinite(iat)
                or not math.isfinite(exp)
                or iat > now + 30
                or exp <= now - 30
                or not 0 < exp - iat <= 660
                or not isinstance(claims["sub"], str)
                or not claims["sub"].strip()
            ):
                raise ValueError("invalid lifetime or subject")
            return Principal(
                issuer=ISSUER, subject=claims["sub"], email=claims.get("email")
            )
        except JobError:
            raise
        except ImportError:
            raise JobError("identity_verification_unavailable", 503) from None
        except Exception:  # noqa: BLE001 - fail closed on all token parsing errors
            raise JobError("identity_invalid", 401) from None


def verified_principal(headers: Mapping[str, str], verifier: IAPVerifier) -> Principal:
    """Pass request.headers (case-insensitive); unsigned owner/email are ignored."""
    return verifier.verify(headers.get("x-goog-iap-jwt-assertion"))
