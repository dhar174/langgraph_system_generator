"""Offline contracts for ephemeral job ownership and API artifact boundaries."""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import nbformat
import pytest

from langgraph_system_generator.api import progress_streaming as streaming
from langgraph_system_generator.api import server
from langgraph_system_generator.utils.error_handling import GenerationError


@pytest.fixture(autouse=True)
async def isolated_api_state(tmp_path, monkeypatch):
    """No test can inherit another test's task, output reservation or credentials."""
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("LNF_API_ACCESS_MODE", raising=False)
    monkeypatch.delenv("LNF_EPHEMERAL_ASYNC_ENABLED", raising=False)
    monkeypatch.setattr(server, "_BASE_OUTPUT", tmp_path)
    monkeypatch.setattr(server, "_DEFAULT_API_OUTPUT", tmp_path / "api")
    monkeypatch.setattr(server, "_api_runs", {})
    monkeypatch.setattr(server, "_active_generation_count", 0)
    monkeypatch.setattr(server, "_generation_lock", asyncio.Lock())
    monkeypatch.setattr(server, "_MAX_CONCURRENT_GENERATIONS", 5)
    monkeypatch.setattr(server, "_shutting_down", False)
    monkeypatch.setattr(streaming, "_active_jobs", {})
    monkeypatch.setattr(streaming, "_owned_tasks", {})
    yield
    assert await streaming.shutdown_owned_tasks(timeout=1) == 0


async def _settle(job_id):
    task = streaming._owned_tasks.get(job_id)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
    done = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(done.set_result, None)
    await done


def _request(prompt="test generation"):
    return server.GenerationRequest(
        prompt=prompt, output_dir="shared", formats=["ipynb", "zip"]
    )


async def _fake_generation(prompt, *, output_dir, **kwargs):
    """Materialize real files so publication tests do not trust mock paths."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell(prompt)])
    notebook_path = output / "notebook.ipynb"
    nbformat.write(notebook, notebook_path)
    zip_path = output / "notebook_bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as bundle:
        bundle.write(notebook_path, "notebook.ipynb")
    manifest = {
        "mode": "stub",
        "prompt": prompt,
        "cell_count": 1,
        "notebook_path": str(notebook_path),
        "zip_path": str(zip_path),
        "artifact_contract": {
            "version": 1,
            "standalone_files": [
                {
                    "manifest_key": key,
                    "path": str(path),
                    "exists": True,
                    "size_bytes": path.stat().st_size,
                }
                for key, path in [
                    ("notebook_path", notebook_path),
                    ("zip_path", zip_path),
                ]
            ],
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "mode": "stub",
        "prompt": prompt,
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "output_dir": str(output),
    }


@pytest.mark.asyncio
async def test_accepted_job_retains_owner_and_releases_capacity_once(monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def generation(*args, **kwargs):
        entered.set()
        await finish.wait()
        return await _fake_generation(*args, **kwargs)

    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=generation))
    started = await server.start_async_generation(_request())
    task = streaming._owned_tasks[started.job_id]
    assert not task.done()
    assert server._active_generation_count == 1
    await entered.wait()
    assert streaming.get_job_status(started.job_id)["status"] == "running"
    finish.set()
    await _settle(started.job_id)
    assert started.job_id not in streaming.owned_task_ids()
    assert server._active_generation_count == 0
    assert streaming.get_job_status(started.job_id)["status"] == "completed"
    assert not streaming.emit_error(started.job_id, "late")
    assert server._active_generation_count == 0


@pytest.mark.asyncio
async def test_task_creation_failure_rolls_back_job_capacity_and_namespace(
    monkeypatch, tmp_path
):
    def fail_create(coroutine, **kwargs):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(server.asyncio, "create_task", fail_create)
    with pytest.raises(server.HTTPException) as error:
        await server.start_async_generation(_request())
    assert error.value.status_code == 503
    assert server._active_generation_count == 0
    assert not streaming._active_jobs
    assert not streaming._owned_tasks
    assert not server._api_runs
    assert not list(tmp_path.glob("shared/generations/*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception",
    [
        RuntimeError("Bearer fake-secret"),
        GenerationError(
            "provider refused api_key=fake-secret",
            code="provider_failed",
            status_code=502,
        ),
    ],
)
async def test_generation_exception_records_sanitized_terminal_failure(
    monkeypatch, exception
):
    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=exception))
    started = await server.start_async_generation(_request())
    await _settle(started.job_id)
    record = streaming._active_jobs[started.job_id]
    terminals = [
        event for event in record.events if event["event"] in {"complete", "error"}
    ]
    assert len(terminals) == 1
    assert terminals[0]["event"] == "error"
    assert record.status == "failed"
    assert "fake-secret" not in json.dumps(record.events)
    assert server._active_generation_count == 0
    assert not server._api_runs


@pytest.mark.asyncio
@pytest.mark.parametrize("before_start", [True, False])
async def test_cancellation_before_or_during_execution_never_reports_success(
    monkeypatch, before_start
):
    entered = asyncio.Event()

    async def generation(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=generation))
    started = await server.start_async_generation(_request())
    task = streaming._owned_tasks[started.job_id]
    if not before_start:
        await entered.wait()
    task.cancel()
    await _settle(started.job_id)
    record = streaming._active_jobs[started.job_id]
    assert record.status == "cancelled"
    assert [event["event"] for event in record.events].count("error") == 1
    assert not any(event["event"] == "complete" for event in record.events)
    assert server._active_generation_count == 0
    assert not streaming._owned_tasks
    assert not server._api_runs


@pytest.mark.asyncio
async def test_lifespan_shutdown_cancels_owner_and_stops_maintenance(monkeypatch):
    entered = asyncio.Event()

    async def generation(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=generation))
    before = asyncio.all_tasks()
    async with server._lifespan(server.app):
        started = await server.start_async_generation(_request())
        await entered.wait()
    await _settle(started.job_id)
    assert streaming.get_job_status(started.job_id)["status"] == "cancelled"
    assert server._active_generation_count == 0
    assert not streaming._owned_tasks
    assert not [task for task in asyncio.all_tasks() - before if not task.done()]


@pytest.mark.asyncio
async def test_job_record_capacity_failure_does_not_leak_slot(monkeypatch):
    monkeypatch.setattr(streaming, "_MAX_TRACKED_JOBS", 1)
    existing = streaming.create_job()
    with pytest.raises(server.HTTPException) as error:
        await server.start_async_generation(_request())
    assert error.value.status_code == 503
    assert server._active_generation_count == 0
    assert set(streaming._active_jobs) == {existing}
    assert not server._api_runs


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_concurrent_api_requests_isolate_real_files(monkeypatch, tmp_path, route):
    entered, release = asyncio.Event(), asyncio.Event()
    paths = []

    async def generation(*args, **kwargs):
        paths.append(Path(kwargs["output_dir"]))
        if len(paths) == 2:
            entered.set()
        await release.wait()
        return await _fake_generation(*args, **kwargs)

    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=generation))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        first = asyncio.create_task(
            client.post(route, json=_request("first").model_dump())
        )
        second = asyncio.create_task(
            client.post(route, json=_request("second").model_dump())
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert len(set(paths)) == 2
        assert server._active_generation_count == 2
        server._prune_api_runs(now=10**12)
        assert all(
            path.exists() for path in paths
        )  # Active reservations survive cleanup.
        release.set()
        responses = await asyncio.gather(first, second)
        assert all(response.status_code == 200 for response in responses)
        if route.endswith("async"):
            job_ids = [response.json()["job_id"] for response in responses]
            await asyncio.gather(*[_settle(job) for job in job_ids])
            payloads = [
                (await client.get(f"/jobs/{job}/result")).json() for job in job_ids
            ]
        else:
            payloads = [response.json() for response in responses]
        assert {Path(payload["output_dir"]) for payload in payloads} == set(paths)
        for payload in payloads:
            output = Path(payload["output_dir"])
            assert output.is_relative_to(tmp_path)
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            assert manifest == payload["manifest"]
            notebook = nbformat.read(output / "notebook.ipynb", as_version=4)
            nbformat.validate(notebook)
            assert len(notebook.cells) == manifest["cell_count"]
            assert notebook.cells[0].source == payload["prompt"]
            for entry in manifest["artifact_contract"]["standalone_files"]:
                if entry.get("path"):
                    assert Path(entry["path"]).parent == output
            with zipfile.ZipFile(output / "notebook_bundle.zip") as bundle:
                assert (
                    bundle.read("notebook.ipynb")
                    == (output / "notebook.ipynb").read_bytes()
                )
        assert server._active_generation_count == 0


@pytest.mark.asyncio
async def test_download_only_registered_run_files_and_retention(monkeypatch, tmp_path):
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    result = await server.generate_notebook(_request())
    output = Path(result.output_dir)
    secret = tmp_path / ".env"
    secret.write_text("DO_NOT_DOWNLOAD=secret", encoding="utf-8")
    unrelated = output / "unrelated.txt"
    unrelated.write_text("not generated", encoding="utf-8")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        valid = await client.get(
            "/artifacts", params={"run_id": result.run_id, "artifact": "notebook.ipynb"}
        )
        assert valid.status_code == 200
        assert valid.content == (output / "notebook.ipynb").read_bytes()
        for name in [".env", "unrelated.txt", "../manifest.json", str(secret)]:
            denied = await client.get(
                "/artifacts", params={"run_id": result.run_id, "artifact": name}
            )
            assert denied.status_code in {404, 422}
            assert "DO_NOT_DOWNLOAD" not in denied.text
        assert (
            await client.get("/artifacts", params={"path": str(secret)})
        ).status_code == 422
        assert (
            await client.get(
                "/artifacts", params={"run_id": "0" * 32, "artifact": "notebook.ipynb"}
            )
        ).status_code == 404
        (output / "notebook.ipynb").unlink()
        assert (
            await client.get(
                "/artifacts",
                params={"run_id": result.run_id, "artifact": "notebook.ipynb"},
            )
        ).status_code == 404
        run = server._api_runs[result.run_id]
        server._prune_api_runs(
            now=run.completed_at + server._API_ARTIFACT_RETENTION_SECONDS + 1
        )
        assert not output.exists()
        assert (
            await client.get(
                "/artifacts",
                params={"run_id": result.run_id, "artifact": "manifest.json"},
            )
        ).status_code == 404


@pytest.mark.asyncio
async def test_other_run_reference_cannot_select_a_file_by_absolute_path(monkeypatch):
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    first = await server.generate_notebook(_request("first"))
    second = await server.generate_notebook(_request("second"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/artifacts",
            params={
                "run_id": first.run_id,
                "artifact": str(Path(second.output_dir) / "notebook.ipynb"),
            },
        )
    assert response.status_code in {404, 422}


@pytest.mark.asyncio
async def test_traversal_and_symlink_parent_are_rejected(monkeypatch, tmp_path):
    with pytest.raises(server.HTTPException):
        server._resolve_output_dir("inside/../escape")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"OS cannot create directory symlinks: {exc}")
    with pytest.raises(server.HTTPException):
        server._resolve_output_dir("link")


@pytest.mark.asyncio
async def test_registered_file_replaced_by_symlink_is_not_downloadable(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    result = await server.generate_notebook(_request())
    notebook = Path(result.output_dir) / "notebook.ipynb"
    notebook.unlink()
    secret = tmp_path / "secret"
    secret.write_text("private", encoding="utf-8")
    try:
        notebook.symlink_to(secret)
    except OSError as exc:
        pytest.skip(f"OS cannot create file symlinks: {exc}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/artifacts", params={"run_id": result.run_id, "artifact": "notebook.ipynb"}
        )
    assert response.status_code == 404
    assert secret.read_text(encoding="utf-8") == "private"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, "multi-user", "disabled"])
async def test_hosted_mode_fails_closed_without_single_operator_ack(monkeypatch, mode):
    monkeypatch.setenv("K_SERVICE", "unit-test-service")
    if mode is not None:
        monkeypatch.setenv("LNF_API_ACCESS_MODE", mode)
    generate = AsyncMock(side_effect=AssertionError("must not generate"))
    monkeypatch.setattr(server, "generate_artifacts", generate)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        for route in ["/generate", "/generate-async"]:
            response = await client.post(
                route,
                json=_request().model_dump(),
                headers={
                    "X-Goog-Authenticated-User-Email": "accounts.google.com:admin@example.com",
                    "X-Goog-IAP-JWT-Assertion": "unsigned-client-assertion",
                },
            )
            assert response.status_code == 503
        for route in [
            "/jobs/unknown",
            "/jobs/unknown/result",
            "/stream/unknown",
            "/artifacts?run_id=" + "0" * 32 + "&artifact=manifest.json",
        ]:
            assert (await client.get(route)).status_code == 503
        health = (await client.get("/health")).json()
        assert health["generation_enabled"] is False
    generate.assert_not_awaited()
    assert server._active_generation_count == 0
    assert not streaming._active_jobs
    assert not server._api_runs


@pytest.mark.asyncio
async def test_hosted_single_operator_has_request_bound_fallback(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "unit-test-service")
    monkeypatch.setenv("LNF_API_ACCESS_MODE", "single-operator")
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        health = (await client.get("/health")).json()
        assert health["generation_enabled"] is True
        assert health["async_generation"] is False
        assert (
            await client.post("/generate-async", json=_request().model_dump())
        ).status_code == 503
        sync = await client.post("/generate", json=_request().model_dump())
        assert sync.status_code == 200
        assert sync.json()["success"] is True


@pytest.mark.asyncio
async def test_process_state_loss_never_reconstructs_job_or_download_access(
    monkeypatch,
):
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    started = await server.start_async_generation(_request())
    await _settle(started.job_id)
    result = await server.get_job_result(started.job_id)
    assert Path(result["manifest_path"]).exists()
    streaming._active_jobs.clear()
    server._api_runs.clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        assert (await client.get(f"/jobs/{started.job_id}")).status_code == 404
        assert (await client.get(f"/jobs/{started.job_id}/result")).status_code == 404
        assert (
            await client.get(
                "/artifacts",
                params={"run_id": result["run_id"], "artifact": "manifest.json"},
            )
        ).status_code == 404
    assert Path(result["manifest_path"]).exists()  # Disk presence alone grants nothing.


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_cooperative_timeout_has_explicit_failure_and_releases_capacity(
    monkeypatch, route
):
    monkeypatch.setattr(server, "_JOB_TIMEOUT_SECONDS", 0.001)

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "generate_artifacts", AsyncMock(side_effect=blocked))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(route, json=_request().model_dump())
        if route.endswith("async"):
            assert response.status_code == 200
            job_id = response.json()["job_id"]
            await _settle(job_id)
            record = streaming._active_jobs[job_id]
            assert record.status == "expired"
            assert record.events[-1]["event"] == "error"
            assert record.events[-1]["data"]["code"] == "generation_timeout"
            assert (await client.get(f"/jobs/{job_id}/result")).status_code == 409
        else:
            assert response.status_code == 504
            assert response.json()["detail"]["code"] == "generation_timeout"
    assert server._active_generation_count == 0
    assert not server._api_runs


@pytest.mark.asyncio
async def test_unexpected_owner_exception_is_consumed_and_finalized(monkeypatch):
    monkeypatch.setattr(
        server,
        "_run_generation_with_progress",
        AsyncMock(side_effect=RuntimeError("Bearer fake-secret")),
    )
    started = await server.start_async_generation(_request())
    await _settle(started.job_id)
    record = streaming._active_jobs[started.job_id]
    assert record.status == "failed"
    assert record.events[-1]["data"]["code"] == "generation_task_failed"
    assert "fake-secret" not in json.dumps(record.events)
    assert not streaming._owned_tasks
    assert not server._api_runs
    assert server._active_generation_count == 0


@pytest.mark.asyncio
async def test_output_capacity_never_evicts_before_promised_retention(monkeypatch):
    monkeypatch.setattr(server, "_MAX_TRACKED_API_RUNS", 1)
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    first = await server.generate_notebook(_request())
    with pytest.raises(server.HTTPException) as error:
        await server.generate_notebook(_request("second"))
    assert error.value.status_code == 503
    assert Path(first.manifest_path).is_file()
    assert set(server._api_runs) == {first.run_id}
    assert server._active_generation_count == 0


@pytest.mark.asyncio
async def test_artifact_access_prunes_at_ttl_without_waiting_for_maintenance(
    monkeypatch,
):
    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=_fake_generation)
    )
    first = await server.generate_notebook(_request())
    run = server._api_runs[first.run_id]
    completed = run.completed_at
    ttl = server._API_ARTIFACT_RETENTION_SECONDS
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        monkeypatch.setattr(server.time, "time", lambda: completed + ttl - 1)
        params = {"run_id": first.run_id, "artifact": "notebook.ipynb"}
        assert (await client.get("/artifacts", params=params)).status_code == 200
        monkeypatch.setattr(server.time, "time", lambda: completed + ttl)
        assert (await client.get("/artifacts", params=params)).status_code == 404
    assert first.run_id not in server._api_runs


@pytest.mark.asyncio
async def test_large_manifest_stays_out_of_bounded_terminal_event(monkeypatch):
    async def large_generation(*args, **kwargs):
        result = await _fake_generation(*args, **kwargs)
        result["manifest"]["large_advisory"] = "x" * 50_000
        return result

    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=large_generation)
    )
    started = await server.start_async_generation(_request())
    await _settle(started.job_id)
    record = streaming._active_jobs[started.job_id]
    terminal = record.events[-1]
    assert terminal["event"] == "complete"
    assert terminal["data"]["success"] is True
    assert terminal["data"]["result_url"] == f"/jobs/{started.job_id}/result"
    assert len(json.dumps(terminal)) < 1000
    result = await server.get_job_result(started.job_id)
    assert len(result["manifest"]["large_advisory"]) == 50_000


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_timeout_cannot_be_turned_into_success_by_suppressed_cancellation(
    monkeypatch, route
):
    monkeypatch.setattr(server, "_JOB_TIMEOUT_SECONDS", 0.001)

    async def suppress_cancellation(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return await _fake_generation(*args, **kwargs)

    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=suppress_cancellation)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(route, json=_request().model_dump())
        if route.endswith("async"):
            job_id = response.json()["job_id"]
            await _settle(job_id)
            assert streaming.get_job_status(job_id)["status"] == "expired"
            assert streaming._active_jobs[job_id].events[-1]["event"] == "error"
        else:
            assert response.status_code == 504
    assert not server._api_runs
    assert server._active_generation_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_explicit_cancellation_cannot_be_suppressed_into_success(
    monkeypatch, route
):
    entered = asyncio.Event()

    async def suppress_cancellation(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return await _fake_generation(*args, **kwargs)

    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=suppress_cancellation)
    )
    if route.endswith("async"):
        started = await server.start_async_generation(_request())
        owner = streaming._owned_tasks[started.job_id]
        await entered.wait()
        owner.cancel()
        await _settle(started.job_id)
        assert streaming.get_job_status(started.job_id)["status"] == "cancelled"
    else:
        owner = asyncio.create_task(server.generate_notebook(_request()))
        await entered.wait()
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
    assert not server._api_runs
    assert server._active_generation_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/generate", "/generate-async"])
async def test_missing_manifest_cannot_be_published_as_success(monkeypatch, route):
    async def no_manifest(prompt, *, output_dir, **kwargs):
        return {
            "mode": "stub",
            "prompt": prompt,
            "manifest": {},
            "manifest_path": str(Path(output_dir) / "manifest.json"),
            "output_dir": output_dir,
        }

    monkeypatch.setattr(
        server, "generate_artifacts", AsyncMock(side_effect=no_manifest)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(route, json=_request().model_dump())
        if route.endswith("async"):
            job_id = response.json()["job_id"]
            await _settle(job_id)
            assert streaming.get_job_status(job_id)["status"] == "failed"
            assert streaming._active_jobs[job_id].events[-1]["event"] == "error"
            assert (
                streaming._active_jobs[job_id].events[-1]["data"]["code"]
                == "artifact_manifest_unavailable"
            )
        else:
            assert response.status_code == 500
            assert response.json()["detail"]["code"] == "artifact_manifest_unavailable"
    assert not server._api_runs
    assert server._active_generation_count == 0
