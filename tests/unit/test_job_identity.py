"""Signed IAP identity tests with injected keys and clocks, no network."""

from unittest.mock import Mock

import pytest

from langgraph_system_generator.api.identity import (
    ISSUER,
    IAPVerifier,
    TrustedIAPKeys,
    verified_principal,
)
from langgraph_system_generator.jobs.models import JobError

AUDIENCE = "/projects/123456/locations/us-central1/services/notebook-api"


@pytest.fixture
def identity():
    jwt = pytest.importorskip("jwt")
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    private = ec.generate_private_key(ec.SECP256R1())
    public = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    fetch = Mock(return_value={"trusted": public})
    clock = Mock(return_value=1000.0)
    keys = TrustedIAPKeys(fetch, clock=clock, ttl=300)
    verifier = IAPVerifier(AUDIENCE, keys, clock=clock)

    def sign(changes=None, headers=None, signing_key=None, algorithm="ES256"):
        claims = {
            "iss": ISSUER,
            "sub": "stable-user-id",
            "aud": AUDIENCE,
            "iat": 990,
            "exp": 1500,
            "email": "display@example.test",
        }
        claims.update(changes or {})
        return jwt.encode(
            claims,
            signing_key or private,
            algorithm=algorithm,
            headers={"kid": "trusted", **(headers or {})},
        )

    return verifier, sign, fetch, clock, ec


def test_verified_subject_ignores_unsigned_owner(identity):
    verifier, sign, fetch, _, _ = identity
    principal = verified_principal(
        {
            "x-goog-iap-jwt-assertion": sign(),
            "x-goog-authenticated-user-id": "forged-owner",
            "x-goog-authenticated-user-email": "forged@example.test",
        },
        verifier,
    )
    assert principal.owner == (ISSUER, "stable-user-id")
    assert (
        verifier.verify(sign({"email": "changed@example.test"})).owner
        == principal.owner
    )
    assert fetch.call_count == 1
    with pytest.raises(JobError, match="identity_invalid"):
        verified_principal({"x-goog-authenticated-user-id": "forged-owner"}, verifier)


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://forged.test"},
        {"aud": "https://worker.run.app"},
        {"aud": "/projects/123456/global/backendServices/111"},
        {"aud": [AUDIENCE]},
        {"exp": 900},
        {"iat": 1100},
        {"exp": 2000},
        {"exp": "1500"},
        {"iat": True},
        {"sub": ""},
        {"sub": None},
    ],
)
def test_invalid_claims_fail_closed(identity, changes):
    verifier, sign, _, _, _ = identity
    with pytest.raises(JobError, match="identity_invalid"):
        verifier.verify(sign(changes))


@pytest.mark.parametrize("token", [None, "", "malformed", "a.b.c", "x" * 16385])
def test_malformed_tokens(identity, token):
    with pytest.raises(JobError):
        identity[0].verify(token)


def test_forged_signature_algorithm_and_remote_key_urls(identity):
    verifier, sign, fetch, _, ec = identity
    for token in (
        sign(
            {"sub": "other-owner"}, signing_key=ec.generate_private_key(ec.SECP256R1())
        ),
        sign(headers={"jku": "https://attacker.test/keys"}),
        sign(headers={"x5u": "http://169.254.169.254/"}),
        sign(headers={"kid": "unknown"}),
    ):
        with pytest.raises(JobError):
            verifier.verify(token)
    jwt = pytest.importorskip("jwt")
    with pytest.raises(JobError):
        verifier.verify(jwt.encode({"sub": "forged-owner"}, "", algorithm="none"))
    with pytest.raises(JobError):
        verifier.verify(
            jwt.encode({"sub": "forged-owner"}, "fake-secret", algorithm="HS256")
        )
    assert fetch.call_count <= 1


def test_keys_expire_refresh_and_failure_has_bounded_negative_cache(identity):
    verifier, sign, fetch, clock, _ = identity
    verifier.verify(sign())
    clock.return_value = 1301
    fetch.side_effect = RuntimeError("network details and token must not escape")
    for _ in range(3):
        with pytest.raises(JobError, match="identity_verification_unavailable"):
            verifier.verify(sign())
    assert fetch.call_count == 2


def test_audience_is_direct_cloud_run_only():
    for audience in ("", "https://worker.run.app", "/projects/123/apps/project"):
        with pytest.raises(JobError, match="identity_configuration_invalid"):
            IAPVerifier(audience)
