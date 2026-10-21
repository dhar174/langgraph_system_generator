"""Execute the browser's real recovery code in Node with deterministic transports."""

import shutil
import subprocess
from pathlib import Path

import pytest


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
let postCalls = 0, resultCalls = 0, uuid = 0;
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
    if (resultCalls < 3) return {ok: false, status: 503};
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
