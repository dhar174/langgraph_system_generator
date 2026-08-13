# SSE Progress Streaming Quick Start

## Overview

The LangGraph Notebook Foundry now supports real-time progress tracking via Server-Sent Events (SSE). This allows clients to monitor long-running generation tasks and receive progress updates, logs, and final results in real-time.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The key new dependency for SSE support is `sse-starlette>=2.0.0`.

### 2. Start the Server

```bash
python -m uvicorn langgraph_system_generator.api.server:app --reload
```

Server will start on `http://localhost:8000`

### 3. Test with Interactive UI

Open your browser to:
```
http://localhost:8000/static/sse_test.html
```

Click "Start Generation Test" to see SSE streaming in action!

### 4. Test with Python Script

```bash
# Install test dependencies
pip install httpx httpx-sse

# Run automated test
python scripts/test_sse_streaming.py
```

## API Endpoints

### Original Synchronous Endpoint (Still Available)

**POST `/generate`**
- Blocks until generation completes
- Returns final result only
- Use for simple integrations

### New Async Endpoint with SSE Streaming

**POST `/generate-async`**
- Starts generation in background
- Returns immediately with `job_id` and `stream_url`
- Use for better UX with long-running tasks

**GET `/stream/{job_id}`**
- Server-Sent Events endpoint
- Streams progress, logs, and results
- Auto-closes on completion or error

## Usage Example (Python)

```python
import asyncio
import json
import httpx
from httpx_sse import aconnect_sse

async def generate_with_progress():
    # Start generation
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/generate-async",
            json={
                "prompt": "Build a customer support chatbot",
                "mode": "stub",
                "output_dir": "./output/my_project",
                "formats": ["ipynb", "html"]
            }
        )
        result = response.json()
        print(f"Job started: {result['job_id']}")
    
    # Connect to SSE stream
    async with httpx.AsyncClient() as client:
        async with aconnect_sse(
            client, "GET", f"http://localhost:8000/stream/{result['job_id']}"
        ) as event_source:
            async for sse in event_source.aiter_sse():
                data = json.loads(sse.data)
                
                if sse.event == "progress":
                    print(f"[{data['percentage']:3d}%] {data['message']}")
                elif sse.event == "complete":
                    print("✓ Generation complete!")
                    print(f"  Mode: {data['mode']}")
                    print(f"  Output: {data['output_dir']}")
                    break
                elif sse.event == "error":
                    print(f"✗ Error: {data['error']}")
                    break

asyncio.run(generate_with_progress())
```

## Usage Example (JavaScript)

```javascript
// Start generation
const response = await fetch('/generate-async', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        prompt: 'Build a customer support chatbot',
        mode: 'stub',
        output_dir: './output/my_project',
        formats: ['ipynb', 'html']
    })
});

const {job_id, stream_url} = await response.json();
console.log('Job started:', job_id);

// Connect to SSE stream
const eventSource = new EventSource(stream_url);

eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    console.log(`[${data.percentage}%] ${data.message}`);
    // Update your UI progress bar here
});

eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    console.log('✓ Complete!', data);
    eventSource.close();
});

eventSource.addEventListener('error', (e) => {
    const data = JSON.parse(e.data);
    console.error('✗ Error:', data.error);
    eventSource.close();
});
```

## Event Types

### Progress Event
```json
{
  "event": "progress",
  "data": {
    "node": "export_ipynb",
    "percentage": 72,
    "message": "Exporting to Jupyter notebook...",
    "status": "running"
  }
}
```

### Log Event
```json
{
  "event": "log",
  "data": {
    "level": "info",
    "message": "Retrieved 5 relevant documentation chunks"
  }
}
```

### Complete Event
```json
{
  "event": "complete",
  "data": {
    "success": true,
    "mode": "stub",
    "manifest": {
      "architecture_type": "router",
      "cell_count": 15,
      "cell_count_source": "serialized_notebook",
      "generated_cell_spec_count": 8,
      "plan_title": "Customer Support Chatbot",
      "artifact_contract": {
        "standalone_files": [],
        "zip_members": []
      }
    },
    "output_dir": "/path/to/output"
  }
}
```

### Error Event
```json
{
  "event": "error",
  "data": {
    "error": "Generation failed: Invalid prompt",
    "details": {"type": "ValueError"}
  }
}
```

## Progress Stages

The generation process reports progress through these stages:

| Stage | Percentage | Description |
|-------|-----------|-------------|
| init | 5% | Initializing generation |
| graph_init | 10% | Creating generator graph (live mode) |
| graph_invoke | 15% | Invoking generator graph |
| graph_complete | 60% | Graph execution complete |
| serialize | 62% | Serializing results |
| compose | 65% | Composing notebook |
| export_init | 70% | Starting exports |
| export_ipynb | 72% | Exporting to Jupyter |
| export_html | 78% | Exporting to HTML |
| export_docx | 84% | Exporting to Word |
| export_pdf | 90% | Exporting to PDF |
| export_zip | 95% | Creating ZIP archive |
| finalize | 98% | Finalizing artifacts |
| complete | 100% | Generation complete |

## Architecture Notes

### Current Implementation (Phase 1)
- In-memory job tracking with `asyncio.Queue`
- Suitable for single-server deployments
- Automatic job cleanup after completion
- 5-minute timeout for stalled jobs

### Future Enhancements (Phase 2+)
- Redis pub/sub for multi-server deployments
- Persistent job history
- Job cancellation support
- Detailed node-level progress from generator graph
- Real log streaming from generator nodes

## Troubleshooting

### "Job not found" error
The job has either completed and been cleaned up, or the job ID is invalid. Jobs are automatically cleaned up after the SSE stream closes.

### SSE stream doesn't complete
Check server logs for errors. The stream has a 5-minute timeout - if no events are received within 5 minutes, the stream will error.

### Progress stuck at one percentage
This indicates the generation is actually running at that stage. Live mode with real LLM calls can take 30-60+ seconds per stage.

## Documentation

For more details, see:
- `docs/API_PROGRESS_STREAMING_ANALYSIS.md` - Detailed analysis and design
- `docs/SSE_IMPLEMENTATION_SUMMARY.md` - Complete implementation summary
- Interactive test page: `http://localhost:8000/static/sse_test.html`

## Backward Compatibility

The original `/generate` endpoint is unchanged and fully functional. You can migrate to `/generate-async` + SSE at your own pace.
