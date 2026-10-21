## LLM endpoint and credential policy

The hosted API treats `custom_endpoint` as untrusted input. Both generation routes
authorize it before output paths, job admission, credentials, or LLM clients are
used. IAP authentication does not authorize outbound destinations.

The official provider is explicitly bound to `https://api.openai.com/v1` and
`OPENAI_API_KEY`. An absent registry disables custom hosted endpoints. Invalid
registry configuration fails closed, including requests for the default provider.

### Register a hosted provider

Configure this non-secret environment variable on the server:

```json
{
  "example-provider": {
    "base_url": "https://llm.example.com/v1",
    "api_key_env": "LNF_LLM_EXAMPLE_API_KEY"
  }
}
```

Store that JSON in `LNF_TRUSTED_LLM_ENDPOINTS`. Mount the provider's own Secret
Manager secret as `LNF_LLM_EXAMPLE_API_KEY`; the variable name must match
`LNF_LLM_*_API_KEY`. The registry contains variable names, never key values.
Alternative providers never fall back to OpenAI or tracing credentials.

The deployment workflow sets `LNF_LLM_ENDPOINT_POLICY=hosted` and merges existing
environment/secret bindings. Administrator-managed registrations survive later
deployments. This setting also enforces hosted policy for package and factory
calls in that process. API routes enforce hosted policy independently of it.

Send the registered URL and a real model identifier in the existing API fields:

```json
{"prompt":"Build a support router","mode":"live","model":"provider-model","custom_endpoint":"https://llm.example.com/v1"}
```

Matching includes scheme, hostname, port and case-sensitive base path. Hostname
case, default ports and one optional trailing slash are normalized. Paths,
subdomains, hostname suffixes and alternate ports are not implicitly authorized.
URLs with credentials, queries, fragments, ambiguous encodings or local/metadata
destinations are rejected. Hosted providers require HTTPS. Duplicate definitions,
unknown fields and unsafe definitions invalidate the whole registry.

Errors use structured codes: `invalid_endpoint` (400), `endpoint_not_allowed`
(403), and `endpoint_policy_unavailable` or `credentials_required` (503).
Rejected URL strings and provider response bodies are not reflected to clients.
Stub requests follow the same destination policy without reading credentials.

### Trusted local CLI and package use

CLI endpoint/model flags are additive. Existing invocations keep their defaults.
For a remote compatible service, set `LNF_CUSTOM_LLM_API_KEY` to that provider's
credential and use an HTTPS endpoint:

```powershell
lnf generate "Build a support router" --mode live --model provider-model --custom-endpoint https://llm.example.com/v1
```

For an intentionally unauthenticated local LM Studio service, leave
`LNF_CUSTOM_LLM_API_KEY` unset and opt in explicitly:

```powershell
$env:LNF_CUSTOM_LLM_NO_AUTH = "true"
lnf generate "Build a support router" --mode live --model local-model --custom-endpoint http://127.0.0.1:1234/v1
```

No-auth is loopback-only and uses the non-sensitive `lnf-local-no-auth` SDK key.
Combining no-auth with a custom key is a configuration error. Package callers use
the existing `custom_endpoint` and `model` arguments; `endpoint_policy="hosted"`
selects stricter policy when embedding the package behind untrusted inputs.
A process configured as hosted cannot downgrade this setting.

Migration: arbitrary API URLs must be registered by an administrator. Local
custom providers must use a dedicated key or explicit loopback no-auth. Implicit
`OPENAI_API_BASE`, `OPENAI_BASE_URL`, gateway and proxy redirection do not select
the generator destination. Environment key values override dotenv settings.

### Transport, errors and artifacts

The shared factory supplies explicit credentials, verifies effective request
destinations, and replaces ambient authentication headers. Its synchronous and
asynchronous HTTP clients verify TLS, disable redirects and ignore environment
proxy settings. SDK-default connect/read/write/pool timeouts are preserved explicitly in both
clients and model requests. Automatic SDK retries are disabled; provider failures are
classified without exposing remote error bodies. Stateless SDK/HTTP logging
filters remove endpoint URLs and omit SDK/HTTPcore diagnostic payloads, including
successful-response headers and raw HTTP/1.1, HTTP/2 and connection traces. Filters
attach directly to the emitting loggers. Live generation owns transport
cleanup, including failure and cancellation. Direct agent/factory callers own
the returned clients' lifecycle.

Manifests expose `llm_provider` and `endpoint_policy`, not the raw endpoint.
Configuration dumps exclude endpoint URLs and custom credential values.
Generated custom-provider notebooks retain centralized `make_llm(...)` and use
the notebook runner's `LNF_NOTEBOOK_API_BASE` and `LNF_NOTEBOOK_LLM_API_KEY`, with
existing environment/Colab secret loading. They never contain the hosted key or
server-only endpoint. `LNF_NOTEBOOK_LLM_NO_AUTH=true` explicitly enables loopback
no-auth for the notebook runner. Composed Deep Agents also obtain their model
from `make_llm()` and pass that model instance into the optional SDK; standalone
Deep Agents snippets keep their model-string configuration. Tool-specific
credentials remain separate.

### Bounded credential diagnostics

Compound secret names in query/key=value and JSON/dict diagnostics are scanned
as disjoint Unicode word/hyphen tokens. Each name is checked against a fixed
set of secret fragments, each value is consumed once, and output slices are
joined once. This removes the ambiguous repeated matching reported as CodeQL
security alerts 277 and 278, including the malformed-URL fallback. URL trailing
punctuation is separated with one strip and slice rather than repeated copying.
Public sanitizer signatures and Python 3.10 compatibility are preserved.

Valid RAG URLs retain safe host/path/query provenance; generation diagnostics
continue to omit complete endpoints. URLs that cannot be parsed are replaced
in full with `[invalid URL omitted]`. Quoted credentials honor escaped quotes;
an unterminated quoted secret consumes the rest of that diagnostic string.
These intentional omissions prevent partial secrets from being returned.
There is no input truncation or chunking before redaction. SDK/HTTPcore payload
suppression and the endpoint isolation established by #379 remain in force.

`tests/fixtures/credential_redaction_probe.py` provides synthetic legacy and
candidate inputs. Run it only through a parent subprocess watchdog (as in
`tests/unit/test_credential_redaction.py`); it caps the child at 512 MiB and
accepts at most 65,536 repetitions. Regression assertions check output and
generous watchdog completion, with a separate Python traversal-step bound.
Timing observations are diagnostic evidence, not portable timing thresholds.

### Network assumptions and limitations

This is an exact administrator allowlist, not a custom DNS resolver. The process
does not resolve a host once and pretend that a later independent resolution is
pinned. Administrators must control registered DNS names, trust the endpoint's
TLS identity and configure appropriate network egress restrictions. A compromised
registered provider or DNS/network configuration remains a trust-boundary risk;
complete connection-time DNS-rebinding prevention is not claimed.

This correction does not change RAG source precedence, IAP/IAM permissions,
Cloud Run persistence, or generated-artifact execution qualification.


### Qualification evidence

Local qualification used a fresh environment satisfying `requirements.txt`, with
`langchain-openai 1.7.2`, `openai 3.31.0`, `langgraph 1.2.15` and `httpx 0.28.1`.
The baseline was `89c4a67069452ebb6ed7dee959c57381cc9a4857`. An offline reproduction
of its original factory forwarded a fake OpenAI credential to an inherited
untrusted destination; the isolation assertion failed with exit 1. No real
credential or network request was used.

| Gate | Observed result | Process exit |
| --- | --- | --- |
| Dedicated endpoint security tests | 98 passed | 0 |
| Notebook composer tests | 61 passed | 0 |
| Unit suite | 898 passed, 2 warnings | 0 |
| Pattern suite | 82 passed | 0 |
| Full repository suite | 1,016 passed, 3 skipped, 2 warnings | 0 |
| CI fatal-error flake8 command | 0 findings | 0 |
| Credential-free CLI stub smoke | Notebook, HTML and manifest verified | 0 |
| Broad Ruff | Baseline 1,275 findings; changed tree 1,269; no additional file/code findings | 1 |
| Broad Black check | Baseline 80 files; changed tree 78; no additional failing files | 1 |
| Broad mypy | Baseline 134 errors; changed tree 106; no additional diagnostics | 1 |

The broad static checks are **not green**. Existing unrelated findings were left
in place. Newly added Python modules and the focused security test file pass
Ruff and Black. Hosted CI and owner review must be assessed independently at the
published PR head.

The focused security suite maps the issue's acceptance criteria to executable
checks:

| Acceptance criterion | Regression coverage |
| --- | --- |
| Fake server key never reaches an untrusted destination | Actual sync/async supported clients with mocked HTTP transports; official and alternative credentials inspected in effective URLs, headers and bodies |
| Both API routes reject before generation side effects | Admission tests prohibit output-path resolution, client creation, credential lookup, job/task creation and generation; URL/IPv4/IPv6/metadata/path/port cases are parameterized |
| Trusted default and registered alternative work | Canonical registration, non-default port, environment/gateway poisoning, provider-specific credential availability and route forwarding |
| Errors, logs and artifacts avoid disclosure | Redirect/provider-error responses, DEBUG logs, SSE events, nested error payloads, config dumps, generated notebook cells and ZIP members |
| CLI/local migration remains explicit | New flags, package preflight, dedicated local key, actual loopback no-auth request and hosted downgrade rejection |
| Stub mode remains offline and deterministic | Credentials, model, graph, docs and network entry points blocked; repeat cell-content comparison and credential-free CLI smoke |
| Shared ownership and concurrency | Overlapping official/alternative generations, transport closure on success, failure and cancellation |

Redirect tests return 301, 302, 303, 307 and 308 toward untrusted hosts, metadata
and same-host unauthorized paths, and assert that no second request occurs.
Unregistered destinations perform no DNS lookup. Registered DNS names remain
subject to the network assumptions above.


### Review follow-up qualification

Codex review `5527089222` and Copilot review `5527094547` identified the timeout,
SDK response-header diagnostics, HTTPcore diagnostics, and composed Deep Agents
provider-helper gaps. The regressions exercise effective sync/async request
timeouts, SDK 2-style header messages, successful SDK responses, and real HTTPcore
HTTP/1.1 response parsing using an in-memory network backend. No socket or live
provider is needed. HTTP/2, proxy and SOCKS emitting logger records are also
covered. Generated Deep Agents cells execute against a fake optional SDK with
only dedicated notebook-runner credentials or explicit loopback no-auth, and
preserve fallback behavior when configuration or the optional SDK is missing.

A committed-head offline reproduction confirmed the SDK header-format leak and
Deep Agents helper bypass with exit 1. The initial review regression run also
failed on the timeout and HTTPcore records; two test-harness failures were
corrected separately. The qualification table above describes the original
published head. Review follow-up evidence is separate:

| Follow-up gate | Result | Process exit |
| --- | --- | --- |
| Final review regressions and all five agent parameter contracts | 20 passed | 0 |
| Deep Agents composer subset | 2 passed | 0 |
| Full repository run | 1,030 passed, 3 skipped; one unchanged example subprocess exceeded 30 seconds | 1 |
| Full repository retry | 1,029 passed, 3 skipped; two different unchanged example subprocesses exceeded 30 seconds | 1 |
| Original example-file focused rerun | 6 passed without code or timeout edits | 0 |
| Latest affected-example selection | 4 passed; unchanged LLM-judge subprocess exceeded 30 seconds | 1 |
| CI fatal-error flake8 command | 0 findings | 0 |

All 113 endpoint-security cases passed within both full runs. The nonzero local
full-suite exits remain qualification limitations, not green results. No example
code or test timeout was changed to conceal them. The published correction still
requires a full hosted CI result at its exact head. Broad Ruff and mypy remain
nonzero with no additional findings compared with the previous PR head; focused
Ruff and Black checks pass on the security modules and tests.
