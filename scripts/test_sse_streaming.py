"""Test script for SSE progress streaming endpoints.

Run this script to test the new async generation and SSE streaming endpoints.
"""

import asyncio
import json
import sys
from datetime import datetime

import httpx
from httpx_sse import aconnect_sse


async def test_sse_generation():
    """Test async generation with SSE progress tracking."""
    base_url = "http://localhost:8000"
    
    print("=" * 70)
    print("Testing LangGraph Notebook Foundry SSE Progress Streaming")
    print("=" * 70)
    print()
    
    # Test 1: Health check
    print("[1] Testing health endpoint...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/health")
        print(f"    Status: {response.status_code}")
        print(f"    Response: {response.json()}")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    print("    ✓ Health check passed\n")
    
    # Test 2: Start async generation
    print("[2] Starting async generation...")
    generation_request = {
        "prompt": "Build a customer support chatbot with sentiment analysis",
        "mode": "stub",
        "output_dir": "./output/test_sse",
        "formats": ["ipynb", "html"],
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/generate-async",
            json=generation_request,
            timeout=10.0,
        )
        print(f"    Status: {response.status_code}")
        result = response.json()
        print(f"    Job ID: {result['job_id']}")
        print(f"    Stream URL: {result['stream_url']}")
        assert response.status_code == 200
        assert "job_id" in result
        assert "stream_url" in result
        
        stream_url = result["stream_url"]
    print("    ✓ Generation started\n")
    
    # Test 3: Connect to SSE stream
    print("[3] Connecting to SSE stream...")
    print("    Progress updates:")
    print("    " + "-" * 60)
    
    events_received = []
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with aconnect_sse(
            client, "GET", f"{base_url}{stream_url}"
        ) as event_source:
            async for sse in event_source.aiter_sse():
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                event_type = sse.event
                data = json.loads(sse.data)
                
                events_received.append({"type": event_type, "data": data})
                
                # Format output based on event type
                if event_type == "progress":
                    node = data.get("node", "unknown")
                    percentage = data.get("percentage", 0)
                    message = data.get("message", "")
                    print(f"    [{timestamp}] [{percentage:3d}%] {node:15s} {message}")
                elif event_type == "log":
                    level = data.get("level", "INFO")
                    message = data.get("message", "")
                    print(f"    [{timestamp}] [LOG] {level:7s} {message}")
                elif event_type == "complete":
                    print(f"    [{timestamp}] [DONE] Generation completed successfully!")
                    print("    " + "-" * 60)
                    break
                elif event_type == "error":
                    error = data.get("error", "Unknown error")
                    print(f"    [{timestamp}] [ERROR] {error}")
                    print("    " + "-" * 60)
                    break
    
    print("    ✓ Stream completed\n")
    
    # Test 4: Verify results
    print("[4] Verifying results...")
    assert len(events_received) > 0, "No events received"
    
    # Check we got progress events
    progress_events = [e for e in events_received if e["type"] == "progress"]
    print(f"    Progress events: {len(progress_events)}")
    assert len(progress_events) > 0, "No progress events received"
    
    # Check we got completion
    complete_events = [e for e in events_received if e["type"] == "complete"]
    print(f"    Complete events: {len(complete_events)}")
    assert len(complete_events) == 1, "Should have exactly one complete event"
    
    # Check completion data
    final_result = complete_events[0]["data"]
    print(f"    Success: {final_result.get('success')}")
    print(f"    Mode: {final_result.get('mode')}")
    print(f"    Architecture: {final_result.get('manifest', {}).get('architecture_type')}")
    
    assert final_result.get("success") is True
    assert final_result.get("mode") == "stub"
    assert "manifest" in final_result
    
    print("    ✓ Results verified\n")
    
    print("=" * 70)
    print("All tests passed! ✓")
    print("=" * 70)


if __name__ == "__main__":
    print()
    print("NOTE: Make sure the server is running on http://localhost:8000")
    print("      Start it with: python -m uvicorn langgraph_system_generator.api.server:app")
    print()
    
    try:
        asyncio.run(test_sse_generation())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except httpx.ConnectError:
        print("\n\nERROR: Could not connect to server at http://localhost:8000")
        print("       Make sure the server is running!")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: Test failed with exception:")
        print(f"       {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
