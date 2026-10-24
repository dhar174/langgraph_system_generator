# Generated notebook evaluation (381-A)

This repository-only harness evaluates trusted deterministic fixtures. Default
runs preserve generation outcome version 1. Explicit qualification adds subsequent
version-2 outcomes in separate local bundles.
Environment smoke proves kernel health; these separate receipts prove only the
generated graph behaviors actually observed. Qualification validates receipt
provenance before integrating execution evidence.

## Execution qualification (381-B)

From a clean committed repository, with the notebook evaluation dependencies
installed, choose a fresh empty output directory:

```powershell
python scripts/run_generated_notebook_eval.py --qualify-outcomes --output output/qualified-notebook-eval
```

The selected output directory may be unignored. Only that subtree is excluded
from the final Git status check; the initial clean-tree check, source hashes and
committed diff still protect provenance.

This executes the three canonical fixture-generated artifacts and all four
negative controls. Custom prompts, notebooks and datasets cannot obtain approved
qualification. The command exits nonzero for a required behavioral failure,
unavailable/incomplete qualification, unsupported configuration or export failure.
Ordinary `lnf generate` exits and defaults do not change.

Each case has an `evaluated/` directory containing a sanitized immutable
`evaluation-receipt.json`, the exact `executed-source.ipynb`, a new notebook with
updated QA prose, HTML, ZIP, and a final manifest with byte hashes and sizes.
`report.json` and `summary.md` expose compact case outcomes. The original generated
files and v1 outcome remain unchanged. The new manifest explicitly distinguishes
generation-time quality from subsequent evaluation and the exact executed source
from presentation derivatives sharing the same code candidate.

The sanitized receipt contains assertion names/results and provenance, never
prompts, invocation inputs, state, provider transcripts, secret values or raw logs.
Raw #381-A diagnostics remain local to the trusted fixture run. Do not upload them
as telemetry. A digest proves byte identity, not evaluator authenticity: raw JSON
cannot import runner authority. Serialized v2 metadata alone is limited by the
ordinary reader; there is no offline reattestation or cloud evaluation service.

The operator and fixed evaluator code are trusted. Child JSON is supervised local
IPC, not a protected channel against a hostile same-user process. Python private
capabilities prevent accidental/request deserialization; they are not a security
sandbox. Filesystem access and native networking limitations below still apply.

Passing means only the recorded graph behaviors passed under these mocks and
conditions. Live provider/tool integrations, broader prompts and requirements,
production execution and other architectures remain unverified. Dependency/kernel
or isolation failures are unavailable; pre-graph or ambiguous partial execution,
including exhausted evidence/output capture budgets, is incomplete. Observed
generated behavior defects block evaluated usability.

Ordinary API and durable generation still return v1/`not_run`. API types/browser
rendering support scoped v2 presentation, but no API accepts receipt uploads or
caller-provided execution results. Durable publication rejects local v2 claims.

## Investigation and implementation plan

Base: `1f674b4da8552d8a258fd44fc438436e4a1d61e5` (origin/main refreshed
2026-10-22). Issue 381 and its comments were read. PR 397 merged as
`9cb1aadba2c9aab25f988591bed32504fe206483`; its `not_run` contract is preserved.
Open PRs 373, 372, 367, 316 and 313 concern reports, memory, a sample notebook,
and diagrams; none implements this harness.

1. `generate_artifacts` serializes `CellSpec` records to generated_cells.json;
   notebook/composer orders sections and supplies missing scaffolding; the
   exporter writes notebook.ipynb. Recompose the serialized cells and compare
   `notebook_candidate_id` with the exported file and manifest candidate.
2. State, node definitions, graph construction, execution helpers and export
   cells can run with installed dependencies and a deterministic model fixture.
   Dependency installation is explicitly excluded. Credential prompts must not
   read host secrets; normal config receives a synthetic fixture value.
3. Patch module-local generator `ChatOpenAI` imports before construction. In the
   kernel, inject the model constructor externally before original cells run;
   the generated `make_llm` factory remains real. Retrieval is mocked offline.
4. Observe real `graph.stream` updates, checkpoint snapshots and tool messages;
   fixture model call records include inputs and deterministic replies. No source
   inspection alone counts as graph execution.
5. Reuse notebook/runtime's nbclient backend and existing candidate identity.
   Its convenience execute_notebook API cannot supply lifecycle hooks or bounded
   output, so the child uses NotebookClient directly. Reuse ProcessScope and
   qualification sitecustomize rather than building another process supervisor.
6. Scrub the child environment, use a temporary working directory, disable
   dotenv/tracing/telemetry, allow loopback for kernel transport, bound cell and
   total runtime and output, apply OS resource limits, and clean the whole tree.
   Python socket guards are not a security sandbox for hostile code.
7. Keep typed models and execution/fixture helpers in qa, with a repository CLI
   under scripts. No API or worker integration. Use one production writer and
   independent read-only isolation/behavior/evidence review.

The implementation adds three clean fixtures and four mutations of generated
copies, then focused and repository regression checks, a verification receipt,
and a single unmerged PR. Small generator corrections are permitted only where
the executable cases expose a missing declared behavior.

## API references and environment

The requested LangChain docs MCP search tool is not exposed in this session.
Official documentation was reviewed directly:

- [Graph API: Send, reducers, recursion limits](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [Thread-aware persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [nbclient execution and cell timeouts](https://nbclient.readthedocs.io/en/latest/client.html)

Investigation environment: CPython 3.12 on Windows; langgraph 1.2.16,
langchain 1.4.6, langchain-core 1.6.12, langchain-openai 1.7.2,
nbclient 0.10.4, nbformat 5.10.4, ipykernel 7.2.0, pydantic 2.14.1.
Some installed notebook/dev dependencies are older than requirements.txt floors;
receipts record actual versions rather than claiming dependency-floor parity.

## Running

```powershell
python scripts/run_generated_notebook_eval.py --dataset tests/evaluation/generated_notebook_cases.json --output output/generated-notebook-eval
```

Further implementation details and verification evidence accompany this document.

## Fixture and receipt contracts

`qa/execution_models.py` defines strict version-1 case, invocation, dataset,
assertion and result models. Unknown fields, duplicate case IDs, absent fixture
families, and a dataset without normal composition coverage are rejected.
The checked-in dataset uses the normal (`live`) generator graph with deterministic
model replies for all three cases. This is an offline mocked generation mode:
no live provider is contacted. Retrieval and environment-smoke nodes are mocked;
requirements parsing, architecture override, graph validation/export, tool
planning, composition, static validation and packaging run normally. Repairs
are disabled so a failing generated candidate cannot be silently substituted.

The support fixture classifies billing, technical and unsupported inputs. The
supervisor dispatches researcher and reviewer in the same superstep, checks
their instructions and distinct reducer results, synthesizes them, and tests
the declared abort-on-worker-error policy. The chatbot uses real InMemorySaver
thread checkpoints, tests retained and separate-thread context, and executes
the generated calculator through ToolNode. Tool-start callback inputs and
ToolMessage results establish actual tool execution. Interactive input raises
immediately; the original `RUN_INTERACTIVE_LOOP=False` setting is asserted.

The harness verifies the original notebook is already valid nbformat v4 and
matches generated_cells.json and the manifest under `notebook-cells-v1`.
Outputs and execution counts are excluded by that existing identity algorithm.
The byte hash, original path, serialized cell count, source revision, dirty flag,
tracked diff hash, full source-file hash map, actual dependency versions, case
specification, isolation controls, cell indices, traces, checkpoints, assertions,
errors and limitations are retained. A source-tree digest includes untracked
implementation files; the diff digest alone is not source provenance.

Original notebook files are never instrumented in place. A separately hashed
derived notebook adds a bootstrap and behavioral-probe cell, preserving the
original executable sources except for explicitly excluded installation cells.
Original and derived attempted/completed cell indices are recorded separately.
The derived executed notebook retains bounded outputs for diagnostics. It is
not byte-identical to the original export. Mutations create separate copies and
record both original and changed candidate identities.

Each clean case produces an original notebook, generated cells, plan, manifest,
derived execution notebook, executed notebook, process log and JSON receipt.
The runner writes report.json and summary.md. It requires a new empty output
directory inside the shared trusted output root and rejects traversal or reuse
of existing evidence. It exits nonzero for required-case failure, missing
execution, setup failure, an undetected mutation, or skipped negative controls.
There are no uploads. The historical release evaluator remains unchanged.

## Isolation guarantees and limits

The repository CLI supervises each child with the existing ProcessScope, owning
a Windows Job Object or POSIX process group. The child launches a private
current-interpreter ipykernel in a fresh temporary working directory. The default
case limits are 20 seconds per cell, 180 seconds overall, 2 GiB memory, 90 seconds
CPU and 64 KiB captured output/evidence. Immediate kernel shutdown avoids a
graceful-shutdown wait when a cell loops. Whole-tree cleanup also occurs after
normal child exit, timeout and cancellation. Observed descendant PIDs and their
exit checks accompany the cleanup result.

Windows enforces aggregate Job Object committed-memory and user-CPU limits.
POSIX applies inherited per-process address-space and CPU rlimits; those are
not aggregate tree quotas. Unavailable limit setup is a failure. Abrupt kills
without conclusive OS evidence report resource-limit outcome `unknown` rather
than asserting that a memory/CPU quota was responsible.

The allowlisted environment retains OS launch requirements and replaces home,
Jupyter, IPython and temporary directories. Provider credentials are scrubbed;
only a synthetic fixture value is supplied. Dotenv, LangSmith tracing, OpenTelemetry
and anonymous telemetry are disabled. The inherited qualification guard blocks
external Python TCP connects, UDP sendto, DNS and gRPC channel factories, while
allowing loopback for the kernel. Native libraries can bypass Python guards.
Other ordinary socket APIs such as POSIX `sendmsg` are also outside this guard.
The child keeps the current user's OS filesystem privileges. This is **not a
security sandbox for arbitrary or malicious code** and must not be offered as a
production user-notebook executor. Docker is not required for trusted fixtures.

The four negative controls break graph construction, change a valid route,
bypass the tool executor, and loop inside a real graph node. Detection requires
the clean candidate to pass, the mutation to be applied, cleanup to complete,
and the corresponding named behavioral failure or classified runtime/timeout
failure to appear. An unrelated import, generation or isolation error cannot
count as detecting the mutation.

## Composer extension behavior

Canonical subagent fan-out is selected by the notebook-composer registry's
`subagents_graph` section builder. Plugin architectures can reuse it with
`section_overrides={"graph": "subagents_graph"}`. It identifies dispatch sources
by coordinator/supervisor roles, or the entry point for legacy schemas without
those roles. Other graph builders retain scalar routing unless they explicitly
supply their own route prelude. Deterministic chatbot assistant and ToolNode
cells carry fallback warnings and structured composition feedback like other
deterministic node templates.

## Phase 381-B handoff

Current status (2026-10-23): PR #399 merged at `4f17c2d`; the explicit
qualification path above delivers this handoff. #381 is closed for the accepted
controlled-fixture scope. The following paragraph records the original #381-A
boundary, not unfinished implementation instructions. See the
[v1.1 acceptance matrix](../plans/current-plan.md).

B must validate a receipt's source/case/fixture/environment provenance and
associate its candidate SHA with the selected artifact before deriving a new
public execution result. Version-1 `GeneratedExecutionOutcome` still accepts
only `not_run`. This PR adds no automatic runtime QA gate, API/worker execution,
durable-job mutation, public quality-label change or arbitrary-code service.
Live model fidelity, broader architectures, hostile code containment, persistent
checkpoints across process restarts and deployment remain unverified.
