---
title: Durable backend postmerge qualification
description: Credential-free SDK and Firestore emulator evidence, without cloud activation.
---

Part of #380; related epic #378. PR #395 is a qualification PR. No production
source, dependency declaration, existing workflow, staging activation variable,
production protection, IAM, secret, billing or cloud resource was changed.

## Source provenance and boundaries

`git fetch origin main` exited 0. The refreshed base is
`6b0348783a0ee141608466bf928884179e7ede38`, which matches the supplied historical
reference after live verification. GitHub reports these PRs merged:

| PR | Merge SHA | Merged UTC |
| --- | --- | --- |
| #392 / B1 | `305274f7eca82655e3556b2df50f0406f2d7905c` | 2026-10-21 00:45:07 |
| #393 / B2 | `101f14fcf2ab009360a2562181521c6aeb531ea0` | 2026-10-21 03:54:29 |
| #394 / B3 | `6b0348783a0ee141608466bf928884179e7ede38` | 2026-10-21 18:57:41 |

Implementation commits are `7f512666dc70fa5ff7f31d565cbc2b2a9fb6eceb` and
`d5221318eba05d34fd491cf79cb746d24f72d000`. This receipt is a documentation-only
descendant; PR metadata records the publication head. The open-PR inventory
contained #373, #372, #367, #316 and #313, with no overlapping durable work.
The original checkout's Memory Bank edits and `.playwright-mcp/` were preserved;
all changes use the isolated `codex/380-postmerge-durable-qualification` branch.

Read authority included AGENTS.md, CONTRIBUTING.md, Memory Bank instructions and
context/task files, applicable Python/CI/Markdown instructions, both existing
Python/staging workflows, setup.py, requirements.txt, the rollout runbook and B3
receipt, durable unit suites, and both emulator harnesses. Current source takes
precedence over older receipts, including old optional-dependency test counts.

Each runner preflight verifies `langgraph_system_generator.__file__` is under
this worktree's `src/`, with that source prepended for subprocess imports. The
Python 3.10 core and SDK environments are separate virtualenvs; no older editable
installation supplies product imports. Setup downloads are separate from tests.

## Test inventory and evidence levels

| Level | Designated coverage | Dependencies / opt-in | Result |
| --- | --- | --- | --- |
| Core / ephemeral | Optional dependency guards, worker import safety, Phase A lifecycle, core import/network guard | Core/API libraries and test tools; no cloud SDK installation | 64 collected, 64 passed, 0 skipped; exit 0 |
| SDK-equipped offline | Durable contracts, identity, Firestore store, dispatch, worker, private artifacts, configuration/provider policy, API, browser and runner regressions | `.[gcp]`, normal runtime/test dependencies, Node; injected transports | 223 collected, 223 passed, 0 skipped; exit 0 |
| Real local Firestore emulator | Both integration files; independent clients/processes and disk object transport | `LNF_TEST_FIRESTORE_EMULATOR=1`, loopback emulator, anonymous credentials | Two fresh namespaces, 4 collected / 4 passed / 0 skipped each; exit 0 |
| Approved staging | Actual GCS, Tasks, IAP/OIDC, IAM, indexes, service limits, migration and teardown | Separately approved resources and authentication | Not run; no activation authorized |
| Production | Reviewed staging and owner rollout acceptance | Separate explicit authorization | Not run; #380 remains open |

These counts were repeated on implementation commit `d522131` with fresh
receipt directories. Final emulator projects were `demo-lnf-c17c1c3853464f71`
and `demo-lnf-f5d2585e9268494c`, taking 77.09s and 71.52s. Acceptance replay
properties were `[0,0,0,0]` and `[1,1,1,1]`; claims were `[0,0]` and `[1,1]`.
The runner exited 0, its Java process was reaped, and port 8081 was free after
teardown. This includes rejection of an expired worker before replacement and
a superseded worker after the winning commit.

The SDK fixture in `test_firestore_job_store.py` gates Firestore-backed parameters
of durable contract/API/artifact/worker/provider tests through `importorskip`.
`test_managed_dispatch.py` has a module-level Google API exception import skip
and imports Tasks in its fake queue. Identity tests need PyJWT, cryptography and
Google auth. Browser recovery needs Node. The new runner explicitly imports the
SDKs and checks Node before collection, then compares exact collected node IDs
against JUnit results. Missing dependencies, absent suites, skipped required
cases, failures, timeouts and partial results return nonzero.

The default full suite intentionally leaves four emulator cases opted out and
three packaging installation scenarios disabled (`RUN_PACKAGING_SMOKE=1`). The
packaging cases perform isolated installations; they are not cloud qualification.
The only platform skip allowance in the designated runner is the exact pair of
Windows lifecycle tests with the exact reasons `Windows path casing contract`
and `Windows trailing-space path alias`, on non-Windows hosts. No SDK/emulator
skip allowance exists. Cloud staging/production recipes remain separate gates.

## Toolchain and exact commands

| Component | Observed local version |
| --- | --- |
| Baseline test Python / OS | CPython 3.10.19, Windows 10.0.26340 AMD64 |
| Additional broad-test Python | CPython 3.12.2, same Windows host |
| Emulator Java | Temurin JRE 21.0.12.1+1 LTS, task-private installation |
| Firestore emulator | Official Firebase-distributed JAR 1.22.0 |
| JAR SHA-256 | `9b6498b7f62714d67f48f59b3818883cd682dbcd46b9f59511de81c97bb5166c` |
| Google Cloud CLI inventory | 584.0.0; not used to start/authenticate the emulator |
| Firestore / Tasks / Storage | 2.34.1 / 2.26.0 / 3.17.1 |
| google-auth / google-api-core / grpcio | 2.62.0 / 2.42.0 / 1.84.0 |
| PyJWT / cryptography / psutil | 2.15.1 / 50.0.2 / 7.2.2 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 |
| Local Node / proposed CI Node | 24.13.0 / 22 |
| Flake8 / Ruff / Black / mypy | 7.4.1 / 0.17.1 / 26.10.1 / 2.4.0 |

The [official emulator instructions](https://docs.cloud.google.com/firestore/native/docs/emulator)
require Java 21 for newer emulator releases and document transaction-lock, index
and production-limit differences. The downloaded JAR's size and SHA-256 matched
the [official Firebase download metadata](https://github.com/firebase/firebase-tools/blob/master/src/emulator/downloadableEmulatorInfo.json).
Java 17 was present initially; an isolated Java 21 download was verified before
use. No global Java, Google CLI configuration or user dotenv file was modified.
Google SDKs emitted Python 3.10 support warnings, retained in the preflight logs;
the repository's supported 3.10 baseline still executed all designated cases.

From the worktree, with task-private interpreter paths substituted:

```powershell
& $corePython scripts/qualify_durable_backend.py --level core --test-timeout 180 --receipts output/qualification/core310-d522131
& $sdkPython scripts/qualify_durable_backend.py --level sdk --test-timeout 300 --receipts output/qualification/sdk310-d522131
& $sdkPython scripts/qualify_durable_backend.py --level emulator --java $java21 --emulator-jar $firestoreJar --port 8081 --repeat 2 --test-timeout 300 --receipts output/qualification/emulator310-d522131
```

The emulator invocation expands to:

```text
java -jar cloud-firestore-emulator-v1.22.0.jar --host 127.0.0.1 --port 8081
python -m pytest tests/integration/test_firestore_job_emulator.py tests/integration/test_durable_api_emulator.py -v -rs --asyncio-mode=auto -o junit_family=xunit1 -p collection_plugin --junitxml=<receipt>/junit-N.xml
```

The runner sets both emulator variables itself, checks readiness with a bounded
REST collection probe, owns the direct Java child, and keeps it alive across
application replacements and fresh projects. It never adopts an occupied port.
Teardown terminates only the owned process tree and removes only its temporary
HOME/config directories. Windows Java may return 1 when terminated by the
runner; `emulator_terminated_by_runner` distinguishes that teardown from an
unexpected service exit. Overall test/runner exits are recorded separately.

Subprocess configuration uses an OS-variable allowlist, a private HOME/TEMP,
explicit source paths and dotenv/tracing/telemetry disablement. Ambient provider
keys, Google credentials, cloud hosting settings, proxies and tracing keys are
not forwarded. The inherited Python guard denies non-loopback DNS/TCP and native
gRPC channels. Emulator clients use `AnonymousCredentials` and `demo-lnf-...`
projects. Loopback kernel/emulator traffic remains permitted. No live Google,
metadata, tracing or model service was contacted by the designated tests.

## Emulator assertions and failure history

The final harness proves shared Firestore state through independent clients and
fresh processes; same-owner/key retries resolve to exactly one job and one
creation, while payload conflicts fail. Two process claimants preserve the
original version/fence/intent and settle as one winner and one conflict, with
attempt count and fence equal to 1.

A worker exits with code 23 after disk-object upload and before pointer commit.
Its expired lease cannot finalize before replacement; its superseded fence
cannot overwrite the replacement's committed result. Fresh API processes read
accepted/completed status, at least five monotonic retained event IDs, one
terminal event, result references, a manifest matching the winning ArtifactRef's
size/hash, and notebook bytes matching the committed object receipt. Wrong-owner
and logical-expiry checks deny status, result, stream and notebook downloads.
Expiry probes use newly valid synthetic identity assertions, so job retention
is the tested rejection boundary.

| Attempt / observation | Exit / correction |
| --- | --- |
| Initial SDK/emulator preflight parsed warning-prefixed stdout as JSON | Exit 1; retain SDK warnings and parse the explicit final JSON record |
| Initial readiness URL omitted the collection | Exit 1 after bounded readiness timeout; corrected to a valid Firestore collection probe |
| Original three emulator cases | 2 passed, 1 failed; acceptance race exhausted transaction retries |
| Focused diagnostic of the unchanged race | First repeat passed; eight fresh diagnostic cases yielded 5 passed / 3 failed; captured `ValueError: Failed to commit transaction in 5 attempts`, caused by SDK `Aborted` / gRPC `ABORTED: Transaction lock timeout` |
| Initial extended harness | 3 passed, 1 failed; new assertion selected metadata absent from the fixture; corrected to authoritative `manifest.objects` receipts |
| Uncalibrated races repeated | 2 passed, 2 failed; all contenders can exhaust emulator lock retries; no duplicate owner or stale commit was observed |
| Calibrated caller replay | Two namespaces passed 4/4 each; acceptance replay counts `[0,1,1,1]` and `[1,1,1,1]`; claims `[0,0]` both runs |
| Explicit expired-fence assertion added | Two namespaces passed 4/4 each; no production change |
| Final reporting/CI-bound corrections | Core 64/64, SDK 223/223, emulator 4/4 twice; zero skips; runner exits 0 |
| First real smoke validation | CLI exit 0; API probe exit 1 because it assumed four downloads; actual manifest registers six, including plan/cells; corrected the probe to verify all registered files and require the requested artifact names |
| Initial static baseline extraction under ignored output | Black reported no files; discarded as invalid baseline evidence and reran outside the ignored tree |
| Initial fatal Flake8 scan included the task virtualenv | Owned scan stopped, exit 15; moved the virtualenv outside the worktree and reran the exact gate, exit 0 / 0 findings |

Caller replay calibration is test-only: initial requests remain simultaneous;
only sanitized backend 503 is replayed, at most twice, with deterministic stagger.
The production adapter's five-attempt SDK policy is unchanged. Acceptance must
still resolve all callers to one job and exactly one creation; claim callers
must retain the original CAS values and produce exactly one winner. Final 503,
unexpected errors or conflicting ownership fail the test. Retry counts are
preserved in JUnit/logs even on a failed race. Independent read-only review
agreed this tests safe idempotent replay through emulator contention, without
asserting every first concurrent request succeeds immediately.

## Broad local verification and static baseline

Python 3.12.2 used a task-private installation of requirements.txt plus `.[gcp]`
and Flake8. The baseline comparison uses an archive of the exact base's `src/`
and `tests/`, the same interpreter/tools, and normalized diagnostic/file paths.

| Command | Actual result | Exit |
| --- | --- | --- |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 1,209 collected: 1,208 passed, 1 optional PDF skip; 230.57s pytest time | 0 |
| `python -m pytest tests/patterns/ -v` | 82 collected/passed, 0 skipped; 27.11s | 0 |
| `python -m pytest --asyncio-mode=auto` | 1,334 collected: 1,326 passed, 8 skipped; 270.66s | 0 |
| `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` | 0 fatal findings, corrected run outside the virtualenv | 0 |
| Focused `ruff check`, `black --check`, `mypy --explicit-package-bases --follow-imports=silent` | Changed Python files clean; mypy uses `MYPYPATH=src` and installed third-party typing stubs | 0 |
| `ruff check src/ tests/` | 1,235 findings in base and head; no added/removed diagnostic identities | 1 |
| `black --check src/ tests/` | 74 files require formatting in base and head; identical failure paths | 1 |
| `mypy src/` | 104 errors in 14 files in base and head; no added/removed diagnostic identities | 1 |
| `node --check src/langgraph_system_generator/api/static/app.js` | Syntax accepted; JavaScript was unchanged | 0 |
| `git diff --check`, staged check, tracked-tree conflict scan | No whitespace errors or conflict-marker lines | 0 |

Broad Ruff, Black and mypy are **not passing gates**. Baseline comparison does
not turn existing debt into a pass. No test, static-analysis configuration or
core optional-dependency guard was weakened.

Protected Git inventories for `src/`, setup.py, requirements.txt, the existing
Python/staging workflows and `docs/config/durable/` contain the same 104 entries
as the base, aggregate SHA-256
`d9058d7fffc5f590e1cc56c61ddbbd4ca83f21d842736ee077f4063a04edefdc`.

The PDF skip is `tests/unit/test_notebook.py::test_export_to_pdf`: no suitable
Chromium executable was available under the isolated HOME for optional webpdf
export. The default full suite additionally skips the four emulator cases and
three packaging scenarios described above. No designated durable test skipped.
Broad warnings were the existing LangChain community deprecation, the deliberately
invalid HMAC token's PyJWT key-length warning, and Windows ZMQ selector fallback;
raw warning text remains
in the local logs. JUnit data, not a grep of console summaries, supplies counts.

## Real CLI and ephemeral API smoke

The real CLI ran `python -m langgraph_system_generator.cli generate "Create a
support router" --mode stub --output cli --formats ipynb html zip` under a
repo-contained `LNF_OUTPUT_BASE`. A fresh API process used the real ASGI app and
real generator, with no patched generation function or credentials. Both
notebooks validated with nbformat v4 and 16 serialized cells matching manifest
`cell_count` / `cell_count_source=serialized_notebook`. ZIP CRC and notebook
content were checked. All six registered API downloads matched actual disk bytes.

| Surface / file | Bytes | SHA-256 |
| --- | --- | --- |
| CLI notebook.ipynb | 17,331 | `f83b40a6e36927e3491d0dad14dc99b265e1852c212e1a6ff463afaa6a921835` |
| CLI notebook.html | 338,068 | `763188e6fb4e6b3b1169d30d8b2bf0e2cd648c4da1b192d40e2c701056302deb` |
| CLI manifest.json | 18,635 | `21572d41e29e931661e9fe350d5bb5befe71999c22e9feaf06d1df22e0fe8f71` |
| CLI notebook_bundle.zip | 76,008 | `791070d1fc1fec8535231f225fb54f20b2f99b9b22c88fbc7e2079301f8bcd12` |
| API notebook.ipynb | 17,331 | `56ba357e0c4508857e777d16501dd7cfbf9bd5718e8df57743ae3924c5f9b208` |
| API notebook.html | 338,068 | `b4f1f1048f7bb6d77acaf2dd9345349637ea3eae43399a14800d8b3915c79e56` |
| API manifest.json | 21,326 | `548de67ba19784dcd379eec10e0cbeb1a3ea3b4a8ff40ec0537314773a46af2f` |
| API notebook_bundle.zip | 76,019 | `f01ca2c47944cfb5375096914a5edfed39c833d4948a537f144e7e1b033025ef` |

Local raw evidence is under ignored `output/qualification/`: final runner
directories listed above, `broad312/`, `static-baseline312-corrected/`, earlier
failure receipts, and `smoke312-corrected/{receipt,artifacts}.json`. Synthetic
signing keys live only inside owned test temporary directories, not published
receipts. CI retains sanitized summaries, JUnit, collection IDs and emulator
logs for seven days; no credential or environment dump is uploaded.

## Independent findings, hosted evidence and remaining gates

Read-only review identified missing emulator assertions and hardcoded project
names, a cleanup PID-reuse risk, aggregate CI timeout mismatch, missing retry
evidence on failure, ambiguous intentional Java termination, and a weak socket
guard assertion. These were addressed with fresh namespaces, retained process
identity/reaped-process checks, bounded per-run CI budgets with setup margin,
failure-preserving replay counts, explicit teardown metadata, and guard-specific
error assertions. Production source remains byte-for-byte unchanged from base.

The initial published head `7f512666dc70fa5ff7f31d565cbc2b2a9fb6eceb` passed the
[ordinary PR qualification run](https://github.com/dhar174/langgraph_system_generator/actions/runs/39667349608).
This is observed hosted evidence, separate from local Windows qualification:

| Hosted environment | JUnit/receipt result |
| --- | --- |
| Ubuntu 24.04.5, Python 3.10.22, core install | 64 collected, 62 passed; exactly the two allowed Windows-only skips; exit 0 |
| Same baseline, GCP SDKs installed | 223 collected/passed, zero skips; exit 0 |
| Same baseline, Java 21.0.12.1 / emulator 1.22.0 | Two namespaces, 4 collected/passed and zero skips each; exit 0 |

Downloaded JUnit and receipts agree with those counts. Artifacts
`12378710506` (core) and `12378361873` (SDK/emulator) expire after seven days.
The PR workflow checked out synthetic merge
`d5aab0212a685dd681a515304af2306c67b292eb`, merging that head into the verified
base; this was not a repository merge. Final-code hosted evidence is recorded
below. No owner-disabled workflow
was enabled or manually rerun, and deployment/staging workflows were untouched.

Implementation commit `d5221318eba05d34fd491cf79cb746d24f72d000` also passed
[the ordinary follow-up PR run](https://github.com/dhar174/langgraph_system_generator/actions/runs/39668634014).
Downloaded JUnit and receipts again show core 64 collected / 62 passed / the
same two allowed platform skips, SDK 223/223 with zero skips, and emulator 4/4
with zero skips in each of `demo-lnf-7b1895d5a75940ea` and
`demo-lnf-789588e3b30a4de6`. All runner exits are 0. Artifacts `12378293565`
and `12378263495` retain those receipts for seven days. The unchanged Python
application, Documentation, and CodeQL checks also reported success on that
implementation head. This receipt commit changes documentation only; its
publication-head checks are reported separately in the PR.

This qualification proves local Firestore persistence across application
process replacement while the emulator stays running. The emulator database is
in memory and does **not** survive emulator restart. Disk-backed object storage
remains a test double. Live GCS generations/IAM, Tasks dispatch/redelivery and
OIDC, two-principal IAP access, production composite indexes/limits, reviewed
migration, budgets, staging teardown and owner acceptance are still required.
No merge, cloud activation, deployment or closure of #380 is authorized here.

## PR review follow-up

The [review of publication head a7e42c0](https://github.com/dhar174/langgraph_system_generator/pull/395#pullrequestreview-5606102443)
identified five qualification-harness concerns. This follow-up addresses each
without changing product source, dependencies, cloud configuration or activation.

| Concern | Correction and regression evidence |
| --- | --- |
| Zombie descendants falsely reported as executing | Cleanup assertions accept absence, a non-running identity or `STATUS_ZOMBIE`, with a bounded wait for termination. A deterministic zombie regression covers a PID that still exists. Windows does not reproduce the Linux container reaping condition; Linux results are reported separately in PR CI. |
| Orphans survive a normal parent exit | Commands and the emulator use an owned POSIX session/process group or an unnamed Windows Job Object. A Windows launcher waits on a private pipe until job assignment, so command descendants inherit membership before execution. Cleanup runs after success and timeout, without discovering children through a reaped PID. A real normal-exit orphan regression also verifies an unrelated process remains alive. |
| Class methods mismatch JUnit reconstruction | Map collected IDs forward to JUnit's module/class/name tuple, preserving parameter text. Synthetic same-method/different-class coverage and an actual pytest parameterized class-method run pass; missing, duplicate, failed and unexpected-skipped results remain fatal. |
| Trailing warnings corrupt preflight parsing | Emit one explicitly prefixed JSON record and read it independently of surrounding warnings/blank lines. Missing, malformed or invalid records fail closed. |
| Early failures have no CI summary detail | Both summary steps include escaped receipt errors even when `runs` is empty. Execute both actual workflow snippets against a synthetic early-startup failure to verify the diagnostic is present and HTML-escaped. |

A probe loading the exact reviewed runner from `git show a7e42c0:scripts/qualify_durable_backend.py`
reproduced a live orphan after normal exit and class-identity rejection; the old
final-line parsing expression also rejected trailing teardown output. The probe
terminated only the child it created. Results are in ignored
`output/qualification/review395-probes.json`.

Local follow-up uses the same private Python 3.10.19 environments and SDK/Java/JAR
versions recorded above. The focused runner file passed 19 tests; the updated
SDK runner passed 232/232 and the separate core runner passed 64/64, all with zero
skips and exits 0. The emulator runner also passed 4/4, zero skips, twice in
`demo-lnf-40bff50b45544034` and `demo-lnf-b30b1eeda8e64c49`, keeping the same
emulator alive across application replacements. Its runner/test exits were 0;
the owned Windows launcher/job was intentionally terminated (exit 1), and port
8081 was available after teardown. Receipts are `review395-sdk310/`,
`review395-core310/`, `review395-emulator310/` and `review395-focused-final.xml`
under `output/qualification/`. Run commands use the documented private core/SDK
interpreters with `--level core`, `--level sdk`, or `--level emulator --java
<private-java21> --emulator-jar <verified-1.22.0.jar> --port 8081 --repeat 2`,
`--test-timeout 300` and the corresponding fresh `--receipts` directory. Focused Ruff,
Black and mypy pass for the three changed Python files; the fatal Flake8 gate
again reports 0 findings/exit 0. Intermediate static checks rejected an exception
type and the direct-script import layout; both were corrected before the clean
checks. The broad static debt and earlier full-suite results above remain
historical observations; this harness-only follow-up does not relabel them as
new passes. Ordinary hosted results for the follow-up SHA are recorded in the PR.

The process containment is for this runner's cooperative test commands. POSIX
process groups do not contain a command deliberately escaping into a new session;
this is resource cleanup, not an operating-system security sandbox. Windows
cleanup uses the job handle and returns its intentional termination code
separately from test/runner exits. The emulator still stays alive across the
application replacements; object storage is still a double and live cloud gates
remain unqualified.

Process ownership follows Python's documented
[`start_new_session` behavior](https://docs.python.org/3/library/subprocess.html)
and Microsoft's documented
[Job Object membership and termination](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
