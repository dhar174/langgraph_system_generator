# Evidence

- Fresh origin/main fetch completed exit 0 without errors with login=false.
- Worktree creation completed and branch switch exited 0.
- Baseline focused registry/outcome tests: 41 passed, exit 0.
- Planning read-only reviewer found no architecture blocker; implementation still
  requires independent final review and tests.
- Initial typed contract/legacy regressions: 48 passed; reviewer call tests: 20
  passed, including actual SDK fake HTTP request counts for success/400/429/500,
  timeout/cancellation cleanup and context tracer/collector isolation.
- New extension tests: 14 passed. Latest durable attempt/publication plus ephemeral
  API/download subset: 5 passed in task-private SDK environment, exit 0.
- Early surface failures retained in transcript: missing fixture original prompt,
  method patch signature, redundant fixture imports removed by import cleanup,
  trusted API root setup, and missing inherited-venv nbconvert template assets.
  Corrected fixtures/setup; nbconvert reinstalled at the same 7.16.6 version into
  private environment. No production guard or assertion weakened.
- Actual credential-free stub CLI export: output/verification334/stub-smoke;
  command/stdout/stderr/exit/source hashes in stub-smoke receipt. Exit 0, v1,
  generated execution not_run, usability unknown. Artifact identity readback passed.
- Static base snapshot is git archive of exact 96baddc src/tests/scripts/setup/
  pytest.ini under ignored output/verification334/base. First directory Black
  baseline saw zero files due parent .gitignore and is not valid coverage;
  explicit-file rerun exited 1, 77 files needing formatting. Broad debt is not green.
- Final focused tests: 71 passed, exit 0; patterns: 82 passed, exit 0. Counts are
  separate checkpoints, not summed as unique coverage.
- Actual shared compiled-graph fake-review export: one reviewer call, 25 notebook
  cells, v1 execution not_run, reviewed advisories. Candidate
  f64c5c532458f23a6381a3f2c06dbab32bcee837b01411833024cbd83320ffe2.
  nbformat v4, manifest/notebook IDs, HTML and exact ZIP members passed readback.
  Approved #381 dataset digest remained
  913aa00c5c2ce30527ccbc31c1f8263a3ab798560e4a569ca13fb0642b0dfb47.
- Initial unit suite: 1508 passed/1 API fixture shutdown setup failure; fixture
  now initializes the same server state as the established lifecycle fixtures.
  Second unit suite: 1510 passed/1 Windows PermissionError on unchanged directory
  rename test. Lifecycle recheck: all 65 passed, exit 0, no source change.
- Exact-base static comparison uses relative file + code/message multisets, not
  only totals: Ruff 1244/1244, mypy 107/107, Black 77/77, no added or removed
  diagnostics. Both broad sides exit 1. Invalid zero-file Black run is excluded.
- Independent read-only contract/privacy/final reviews: callback inheritance,
  raw-source fingerprint and omitted source-location blockers fixed and rechecked;
  mixed-policy concurrent invocations covered. No remaining concrete built-in
  blocker reported. No live accuracy claim; admin plugin modules are trusted code.
- Final unit delivery: 1511 passed, exit 0 in 371.98 seconds. Full suite: 1629
  passed, 1 failed, 7 skipped, exit 1 in 895.46 seconds. Nontermination control
  timed out in bootstrap fixture import, not the intended graph loop. All clean
  fixtures and other controls passed, all cleanup verified. Exact integration
  recheck subsequently passed (1 test, 216.43 seconds, exit 0), without source or
  limit changes. This does not turn the original full-suite exit into a pass.
- Durable SDK qualification: 243 passed, no skips, exit 0; preflight confirmed
  imports from this worktree and installed SDK versions. No cloud service used.
- Delivery source readback: all 209 source/test/script fingerprints match all four
  final unit/full/recheck/SDK receipts. No conflict markers or whitespace errors.
  Complete results and limitations: docs/verification/2026-10-23-334-a-requirements-reviewer.md.
