# API Progress & Log Streaming Analysis

## Executive Summary

**Current State**: The FastAPI backend has basic generation endpoints but NO real-time progress/log streaming. The web UI simulates progress with hardcoded timeouts.

**Gap**: Web UI expects real-time progress updates but currently uses client-side simulation. For production use with live LLM generation (which can take 30-60+ seconds), users need actual progress feedback.

**Recommendation**: Implement Server-Sent Events (SSE) for streaming progress and logs from the generator graph to the web UI.

---

## Current Backend Architecture

### Existing Endpoints

#### 1. `GET /` - Web Interface
- **Purpose**: Serves the static HTML web UI
- **Status**: ✅ Working
- **Location**: `src/langgraph_system_generator/api/server.py:142`

#### 2. `GET /health` - Health Check
- **Purpose**: Simple server status check
- **Status**: ✅ Working
- **Location**: `src/langgraph_system_generator/api/server.py:154`
- **Response**: `{"status": "ok"}`

#### 3. `POST /generate` - Generate Notebook
- **Purpose**: Main generation endpoint
- **Status**: ✅ Working but **NO progress streaming**
- **Location**: `src/langgraph_system_generator/api/server.py:172`
- **Behavior**: 
  - Synchronously calls `generate_artifacts()` from CLI module
  - Blocks until entire generation completes (30-60+ seconds for live mode)
  - Returns final result only after completion
  - **No intermediate progress updates**

### Current Progress Handling

#### Web UI (Client-Side)
**Location**: `src/langgraph_system_generator/api/static/app.js:682-722`

```javascript
// Current implementation uses SIMULATED progress:
showProgress(1, 10, 'Validating input...');

setTimeout(() => {
    showProgress(2, 25, 'Preparing generation context...');
}, 500);

setTimeout(() => {
    showProgress(3, 50, 'Invoking LLM...');
}, 1000);

// Then waits for single response
const response = await fetch('/generate', {method: 'POST', ...});
```

**Issues**:
- Progress is fake/simulated with hardcoded delays
- No correlation to actual backend progress
- User has no way to know if generation is stalled vs. actively processing
- Logs are never shown (UI has logs container but it's unused)

#### Backend (Server-Side)
**Location**: `src/langgraph_system_generator/cli.py:250-430`

```python
async def generate_artifacts(...) -> GenerationArtifacts:
    # Calls generator graph
    if mode == "live":
        graph = create_generator_graph()
        result = await graph.ainvoke(_default_state(prompt))
    else:
        result = _build_stub_result(prompt)
    
    # Returns only final result
    return GenerationArtifacts(...)
```

**Issues**:
- Generator graph has 10+ nodes (intake, rag_retrieval, architecture_selection, graph_design, tooling_plan, notebook_assembly, static_qa, runtime_qa, repair, package_outputs)
- Each node can take seconds to minutes
- No progress updates emitted during execution
- No way to track which node is currently executing

---

## Generator Graph Execution Flow

**Location**: `src/langgraph_system_generator/generator/graph.py:73-115`

The generator processes through these nodes sequentially:

1. **intake** - Parse and validate user prompt (5-10%)
2. **rag_retrieval** - Search documentation (10-20%)
3. **architecture_selection** - Choose pattern (20-30%)
4. **graph_design** - Design workflow (30-45%)
5. **tooling_plan** - Plan tools/dependencies (45-55%)
6. **notebook_assembly** - Generate notebook cells (55-75%)
7. **static_qa** - Static validation (75-80%)
8. **runtime_qa** - Runtime validation (80-85%)
9. **repair** - Fix issues (conditional, 85-90%)
10. **package_outputs** - Export formats (90-100%)

**Current Limitation**: No instrumentation to track node transitions or emit progress events.

---

## Recommended Implementation

### Option 1: Server-Sent Events (SSE) [RECOMMENDED]

#### Why SSE?
- Native browser support (EventSource API)
- One-way server-to-client streaming (perfect for progress)
- Automatic reconnection
- Simple to implement in FastAPI
- No WebSocket complexity needed

#### Implementation Plan

##### 1. Add SSE Progress Endpoint

**New File**: `src/langgraph_system_generator/api/progress_streaming.py`

```python
"""Server-Sent Events for real-time progress and log streaming."""

import asyncio
import json
from typing import AsyncGenerator, Dict, Any
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

# In-memory job tracking (use Redis for production)
_active_jobs: Dict[str, asyncio.Queue] = {}

async def progress_generator(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream progress events for a specific job."""
    if job_id not in _active_jobs:
        yield {"event": "error", "data": json.dumps({"error": "Job not found"})}
        return
    
    queue = _active_jobs[job_id]
    try:
        while True:
            event = await queue.get()
            if event.get("type") == "complete":
                yield event
                break
            yield event
    finally:
        # Cleanup
        if job_id in _active_jobs:
            del _active_jobs[job_id]

@router.get("/stream/{job_id}")
async def stream_progress(job_id: str):
    """SSE endpoint for streaming job progress."""
    return EventSourceResponse(progress_generator(job_id))

def emit_progress(job_id: str, event: Dict[str, Any]):
    """Emit a progress event to the job's queue."""
    if job_id in _active_jobs:
        _active_jobs[job_id].put_nowait(event)
```

##### 2. Instrument Generator Graph

**File**: `src/langgraph_system_generator/generator/nodes.py`

Add progress callbacks to each node:

```python
def intake_node(state: GeneratorState) -> GeneratorState:
    """Parse and validate user input."""
    _emit_node_progress("intake", 10, "Parsing user prompt...")
    
    # Existing logic...
    
    _emit_node_progress("intake", 10, "Intake complete", status="complete")
    return state

def _emit_node_progress(node: str, percentage: int, message: str, status: str = "running"):
    """Helper to emit progress from nodes."""
    job_id = _get_current_job_id()  # Thread-local or context var
    if job_id:
        emit_progress(job_id, {
            "event": "progress",
            "data": {
                "node": node,
                "percentage": percentage,
                "message": message,
                "status": status
            }
        })
```

##### 3. Update Main Generation Endpoint

**File**: `src/langgraph_system_generator/api/server.py`

```python
import uuid
from langgraph_system_generator.api.progress_streaming import _active_jobs, emit_progress

@app.post("/generate-async", response_model=GenerationStartResponse)
async def start_generation(request: GenerationRequest) -> GenerationStartResponse:
    """Start async generation and return job ID for progress tracking."""
    
    job_id = str(uuid.uuid4())
    _active_jobs[job_id] = asyncio.Queue()
    
    # Start generation in background
    asyncio.create_task(_run_generation(job_id, request))
    
    return GenerationStartResponse(
        job_id=job_id,
        stream_url=f"/stream/{job_id}"
    )

async def _run_generation(job_id: str, request: GenerationRequest):
    """Run generation with progress tracking."""
    try:
        emit_progress(job_id, {
            "event": "start",
            "data": {"message": "Generation started"}
        })
        
        # Set job_id in context for nodes to access
        _set_current_job_id(job_id)
        
        artifacts = await generate_artifacts(
            request.prompt,
            output_dir=str(_resolve_output_dir(request.output_dir)),
            mode=request.mode,
            # ... other params
        )
        
        emit_progress(job_id, {
            "event": "complete",
            "data": {"artifacts": artifacts}
        })
    except Exception as e:
        emit_progress(job_id, {
            "event": "error",
            "data": {"error": str(e)}
        })
```

##### 4. Update Web UI

**File**: `src/langgraph_system_generator/api/static/app.js`

```javascript
async function handleGenerate(data) {
    // Start generation
    const response = await fetch('/generate-async', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    
    const {job_id, stream_url} = await response.json();
    
    // Connect to SSE stream
    const eventSource = new EventSource(stream_url);
    
    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        showProgress(data.node, data.percentage, data.message);
        
        // Show in logs
        appendLog(`[${data.node}] ${data.message}`);
    });
    
    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        showResult(data.artifacts);
        eventSource.close();
    });
    
    eventSource.addEventListener('error', (e) => {
        const data = JSON.parse(e.data);
        showError(data.error);
        eventSource.close();
    });
}
```

---

### Option 2: WebSocket (Alternative)

**Pros**:
- Bidirectional communication
- Can send cancellation requests

**Cons**:
- More complex (connection management, reconnection)
- Overkill for one-way progress streaming
- Requires WebSocket infrastructure

**Verdict**: Not recommended for this use case

---

### Option 3: Polling (Not Recommended)

**Implementation**: Client polls `/status/{job_id}` endpoint every 1-2 seconds

**Cons**:
- Wasteful (many empty responses)
- Higher latency
- More complex state management
- Poor user experience

---

## Implementation Priority

### Phase 1: Minimal SSE Support (Recommended)
**Time**: 2-4 hours
**Files to modify**: 3-4 files

1. Add `src/langgraph_system_generator/api/progress_streaming.py`
2. Update `src/langgraph_system_generator/api/server.py`:
   - Add `/generate-async` endpoint
   - Add in-memory job tracking
3. Add basic progress emission in `generate_artifacts()`
4. Update `app.js` to use SSE

**Result**: Real progress updates instead of simulated ones

### Phase 2: Detailed Node Progress (Future)
**Time**: 4-8 hours
**Files to modify**: 10+ files

1. Instrument all generator nodes with progress callbacks
2. Add log streaming support
3. Add cancellation support
4. Persist job status (Redis/database)

---

## Dependencies Needed

### Python Packages
```txt
sse-starlette==1.8.2  # SSE support for FastAPI
```

### No Changes Needed
- FastAPI already installed ✅
- Web UI already has progress/logs UI ✅
- Generator graph structure supports this ✅

---

## File Structure Summary

### Current Files
```
src/langgraph_system_generator/api/
├── __init__.py              # API package exports
├── server.py                # FastAPI app with /generate endpoint
└── static/
    ├── index.html           # Web UI with progress/logs containers
    ├── app.js               # Client with simulated progress
    └── style.css            # Styling for progress UI
```

### Proposed New Files
```
src/langgraph_system_generator/api/
├── __init__.py
├── server.py                # Updated with /generate-async
├── progress_streaming.py    # NEW: SSE endpoints and job tracking
├── job_manager.py           # NEW: Job state management (Phase 2)
└── static/
    ├── index.html           # Minor updates for SSE
    ├── app.js               # Updated to consume SSE
    └── style.css
```

---

## Security Considerations

### Current Security (Good)
- Path traversal protection via `_resolve_output_dir()` ✅
- Input validation with Pydantic models ✅
- Character limits on prompts ✅

### New Security Concerns
1. **Job ID exposure**: Use UUIDs (already planned) ✅
2. **Job hijacking**: Add authentication/session validation (Phase 2)
3. **Memory exhaustion**: Limit concurrent jobs (Phase 2)
4. **Queue cleanup**: Auto-expire old jobs (already in code)

---

## Testing Strategy

### Unit Tests
```python
# tests/api/test_progress_streaming.py
async def test_progress_emission():
    """Test progress events are emitted correctly."""
    
async def test_sse_stream():
    """Test SSE endpoint streams events."""

async def test_job_cleanup():
    """Test jobs are cleaned up after completion."""
```

### Integration Tests
```python
# tests/api/test_generation_flow.py
async def test_full_generation_with_progress():
    """Test end-to-end generation with progress tracking."""
```

### Manual Testing
1. Start server: `python -m langgraph_system_generator.api.server`
2. Open browser to http://localhost:8000
3. Submit generation request
4. Verify progress updates in real-time
5. Check logs toggle functionality

---

## Metrics & Observability

### Proposed Metrics
- Generation duration by node
- Success/failure rates
- Average time per architecture type
- Queue depth and wait times

### Logging
- Structured JSON logs for each node
- Correlation IDs for request tracing
- Error stack traces for debugging

---

## Migration Path

### Backward Compatibility
Keep both endpoints initially:
- `/generate` - Original synchronous endpoint
- `/generate-async` - New async endpoint with SSE

### Deprecation Timeline
1. **v0.1.x**: Both endpoints available
2. **v0.2.0**: Deprecate `/generate`, recommend `/generate-async`
3. **v0.3.0**: Remove `/generate`

---

## Conclusion

**Current State**: ❌ No real progress tracking  
**Proposed State**: ✅ Real-time SSE progress streaming  
**Effort**: Low-Medium (Phase 1 can be done in a few hours)  
**Impact**: High (significantly better UX, especially for live mode)

**Next Steps**:
1. Add `sse-starlette` to requirements.txt
2. Implement Phase 1 (minimal SSE support)
3. Test with stub and live modes
4. Plan Phase 2 enhancements
