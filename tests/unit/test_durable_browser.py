"""Execute the browser's real recovery code in Node with deterministic transports."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_browser_renders_outcome_and_keeps_diagnostic_downloads():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for executable browser rendering")
    source = (
        Path(__file__).parents[2] / "src/langgraph_system_generator/api/static/app.js"
    )
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
class Element {
  constructor(tag) {this.tag = tag; this.children = []; this.style = {}; this.textContent = '';}
  appendChild(child) {this.children.push(child); return child;}
  replaceChildren() {this.children = [];}
  addEventListener() {}
  scrollIntoView() {}
}
const flatten = element => [element, ...element.children.flatMap(flatten)];
const context = {
  document: {createElement: tag => new Element(tag)},
  resultContent: new Element('div'), resultCard: new Element('div'),
  hideResults() {}, copyTextToClipboard() {},
  buildArtifactDownloadUrl: path => path,
  appendLabeledValue(parent, label, value) {
    const element = new Element('p'); element.textContent = label + ': ' + value; parent.appendChild(element);
  },
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function appendQaSummary('), source.indexOf('// Update character count')), context);
vm.runInContext(source.slice(source.indexOf('function showResult('), source.indexOf('function extractErrorMessage(')), context);
for (const [status, expected] of [
  ['completed', 'No Known QA Blockers'], ['advisories', 'With Advisories'],
  ['blocked', 'Diagnostic Downloads'], ['unverified', 'Qualification Unknown'],
  ['failed', 'Pipeline Failed'], ['legacy', 'Qualification Unknown'],
]) {
  const outcome = {schema_version: 1, status, usability: status === 'blocked' || status === 'failed' ? 'blocked' : 'unknown',
    static_qa: status === 'completed' ? 'passed' : 'not_run',
    environment_smoke: {result: 'not_run'}, checks: ['static:python_syntax']};
  const manifest = {warnings: [], qa_summary: {artifacts_usable: null, findings: [{severity: 'warning', message: 'Review advisory', suggestions: ['Inspect code']}]}, artifact_contract: {standalone_files: [
    {exists: true, manifest_key: 'notebook_path', api_download_path: '/artifacts?run_id=opaque&artifact=notebook.ipynb'},
  ]}};
  if (status !== 'legacy') manifest.generation_outcome = outcome;
  context.showResult({success: true, mode: 'stub', manifest});
  const elements = flatten(context.resultContent), text = elements.map(e => e.textContent).join('\n');
  assert(text.includes(expected), text);
  assert(text.includes('Generated notebook execution: not_run'), text);
  assert(text.includes('functional'), text);
  assert(!text.includes('Generation Successful!'), text);
  assert(!text.includes('remain usable'), text);
  if (status === 'legacy' || status === 'unverified') assert(text.includes('Artifact usability is unknown'), text);
  assert(elements.some(e => e.tag === 'a' && e.href.includes('notebook.ipynb')));
}
console.log('outcome banners, evidence limits and diagnostic downloads verified');
for (const [result, expected] of [
  ['passed', 'Evaluation passed under declared conditions'],
  ['failed', 'Evaluation failed'], ['unavailable', 'Evaluation unavailable'],
  ['incomplete', 'Evaluation incomplete'], ['not_run', 'Not evaluated'],
]) {
  context.showResult({success: true, mode: 'live', manifest: {generation_outcome: {
    schema_version: 2, status: result === 'failed' ? 'blocked' : 'unverified', usability: 'unknown',
    generated_execution: {result, case_id: 'support-router', case_version: 1,
      assertions_passed: 34, assertions_required: 34, failed_assertions: ['billing:executed_nodes'], executed: ['LangGraph'],
      environment: {kernel: 'private fixture kernel'}, dependencies: {langgraph: 'unit-version'}, isolation: ['fixture child process'],
      receipt_reference: 'evaluation-receipt.json', receipt_sha256: 'abc123',
      mocked: ['fake model'], untested: ['live services'], limitations: ['trusted fixture only']},
  }}});
  const text = flatten(context.resultContent).map(e => e.textContent).join('\n');
  for (const value of [expected, 'support-router v1', '34/34 assertions passed', 'billing:executed_nodes', 'LangGraph', 'fake model', 'live services', 'trusted fixture only', 'private fixture kernel', 'unit-version', 'fixture child process', 'evaluation-receipt.json', 'abc123']) {
    assert(text.includes(value), text);
  }
}
context.showResult({manifest: {generation_outcome: {schema_version: 99, generated_execution: {result: 'passed'}}}});
assert(!flatten(context.resultContent).some(e => e.textContent.includes('Evaluation passed')));
"""
    result = subprocess.run(
        [node, "-e", script, str(source)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "verified" in result.stdout


def test_browser_submit_retries_share_key_reconnect_and_result_never_generate():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for browser recovery harness")
    source = (
        Path(__file__).parents[2] / "src/langgraph_system_generator/api/static/app.js"
    )
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
const submitCode = source.slice(source.indexOf('async function startAsyncGeneration('), source.indexOf('async function startSyncGeneration('));
const resultCode = source.slice(source.indexOf('async function fetchCompletedJobResult('), source.indexOf('async function startAsyncGeneration('));
const streamCode = source.slice(source.indexOf('function streamGeneration('), source.indexOf('async function fetchCompletedJobResult('));
const calls = [], events = [], listeners = {};
let postCalls = 0, resultCalls = 0, uuid = 0, resultUnavailable = false;
class EventSource {
  constructor(path) {this.path = path; this.readyState = 0; events.push(this);}
  addEventListener(name, fn) {listeners[name] = fn;}
  close() {this.readyState = 2;}
}
EventSource.CLOSED = 2;
const context = {
  console, URL, EventSource, setTimeout: fn => fn(),
  serverCapabilities: {durable_jobs: true}, crypto: {randomUUID: () => 'key-' + (++uuid)},
  currentEventSource: null, durableJobId: null, progressPercentage: {textContent: '0'},
  window: {location: {origin: 'https://api.test'}},
  rememberDurableJob: () => {}, showProgress: () => {}, extractErrorMessage: () => 'transport failure',
  closeProgressStream: () => {},
  fetch: async (path, options) => {
    calls.push({path, options});
    if (path === '/generate-async') {
      postCalls++;
      if (postCalls === 1) throw new Error('response lost after acceptance');
      return {ok: true, status: 200, json: async () => ({durable: true, job_id: 'a'.repeat(32), stream_url: '/stream/' + 'a'.repeat(32)})};
    }
    resultCalls++;
    if (resultCalls < 3 || resultUnavailable) return {ok: false, status: 503};
    return {ok: true, status: 200, json: async () => ({success: true})};
  }
};
vm.createContext(context);
vm.runInContext(resultCode + streamCode + submitCode, context);
(async () => {
  const pending = context.startAsyncGeneration({prompt: 'action'});
  for (let i=0;i<20 && events.length===0;i++) await Promise.resolve();
  assert.equal(postCalls, 2);
  assert.equal(calls[0].options.headers['Idempotency-Key'], calls[1].options.headers['Idempotency-Key']);
  assert.equal(uuid, 1);
  events[0].onerror({}); // transient EventSource loss: reconnect same stream
  assert.equal(postCalls, 2);
  listeners.complete({data: JSON.stringify({result_url: '/jobs/' + 'a'.repeat(32) + '/result'})});
  assert.equal((await pending).success, true);
  assert.equal(resultCalls, 3);
  assert.equal(postCalls, 2);
  const second = context.startAsyncGeneration({prompt: 'new action'});
  for (let i=0;i<20 && events.length<2;i++) await Promise.resolve();
  assert.equal(calls.filter(c => c.path === '/generate-async')[2].options.headers['Idempotency-Key'], 'key-2');
  listeners.complete({data: JSON.stringify({success: true})});
  await second;
  assert.equal(postCalls, 3);
  resultUnavailable = true;
  const third = context.startAsyncGeneration({prompt: 'committed result temporarily lost'});
  for (let i=0;i<20 && events.length<3;i++) await Promise.resolve();
  listeners.complete({data: JSON.stringify({result_url: '/jobs/' + 'a'.repeat(32) + '/result'})});
  await assert.rejects(third, /Generation completed, but its result is temporarily unavailable/);
  assert.equal(postCalls, 4); // only this explicit new user action submitted
  assert.equal(resultCalls, 6); // bounded GET retries never submitted again
  assert(!source.includes('localStorage.setItem(\'Idempotency'));
  console.log('same-key submit recovery; same-job reconnect; bounded result retries; new-action key verified');
})().catch(error => {console.error(error); process.exitCode=1;});
"""
    result = subprocess.run(
        [node, "-e", script, str(source)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "verified" in result.stdout
