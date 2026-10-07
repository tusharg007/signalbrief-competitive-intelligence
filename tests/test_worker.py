import httpx

from signalbrief.delivery import deliver_one
from signalbrief.worker import Worker
from signalbrief.agents import AgentProviderError, rate_limited_call
from signalbrief.worker import classify_failure


async def test_worker_checkpoints_and_revision_skip_research(settings, store, event, source, dossier, report, monkeypatch):
    calls = {"collect": 0, "research": 0, "analysis": 0}

    def collect(*args):
        calls["collect"] += 1
        return [source], []

    def research(*args):
        calls["research"] += 1
        return dossier, [{"framework": "CrewAI", "agent": "researcher", "content": "test output"}], {}

    async def analysis(*args):
        calls["analysis"] += 1
        return report, [{"framework": "AutoGen", "agent": "editor", "content": report.model_dump_json()}], {}

    monkeypatch.setattr("signalbrief.worker.collect_sources", collect)
    monkeypatch.setattr("signalbrief.worker.agents.research", research)
    monkeypatch.setattr("signalbrief.worker.agents.council", analysis)
    run_id, _ = store.enqueue(event, 20)
    worker = Worker(settings, store)
    await worker.process(store.claim(180, 3))
    assert store.get_run(run_id)["status"] == "awaiting_approval"
    store.review(run_id, 1, "revise", "Explain limitations", "http://localhost")
    await worker.process(store.claim(180, 3))
    run = store.get_run(run_id)
    assert run["version"] == 2 and len(run["history"]) == 2
    assert calls == {"collect": 1, "research": 1, "analysis": 2}


async def test_model_failure_does_not_publish(settings, store, event, source, monkeypatch):
    monkeypatch.setattr("signalbrief.worker.collect_sources", lambda *args: ([source], []))

    def failure(*args):
        raise ValueError("Unsupported model")

    monkeypatch.setattr("signalbrief.worker.agents.research", failure)
    run_id, _ = store.enqueue(event, 20)
    await Worker(settings, store).process(store.claim(180, 3))
    run = store.get_run(run_id)
    assert run["status"] == "failed" and run["report"] is None and run["deliveries"] == []


async def test_delivery_receipt_retry_and_dedup_key(settings, store, ready_run):
    received = []

    def handler(request):
        received.append(request.headers["X-SignalBrief-Delivery-ID"])
        return httpx.Response(503 if len(received) == 1 else 200)

    transport = httpx.MockTransport(handler)
    assert await deliver_one(store, settings, transport)
    delivery = store.get_run(ready_run)["deliveries"][0]
    assert delivery["status"] == "pending"
    with store.transaction() as conn:
        conn.execute("UPDATE deliveries SET available_at=0 WHERE id=?", (delivery["id"],))
    assert await deliver_one(store, settings, transport)
    after = store.get_run(ready_run)["deliveries"][0]
    assert after["status"] == "sent"
    assert received[0] == received[1] == after["id"]
    assert after["receipt"]["accepted_by"] == "zapier"


async def test_rate_limit_pacing_is_bounded_and_preserves_provider_status():
    calls, waits = [], []

    async def failing():
        calls.append(1)
        raise AgentProviderError(429)

    async def sleep(seconds):
        waits.append(seconds)

    import pytest
    with pytest.raises(AgentProviderError):
        await rate_limited_call(failing, sleep)
    assert len(calls) == 4 and waits == [20, 40, 60]
    assert classify_failure(AgentProviderError(404))[1] is False
    assert classify_failure(AgentProviderError(429))[1] is True


async def test_rate_limit_pacing_can_recover_without_replaying_previous_agent_turns():
    calls = []

    async def operation():
        calls.append(1)
        if len(calls) == 1:
            raise AgentProviderError(429)
        return "actual response"

    async def sleep(seconds):
        pass

    assert await rate_limited_call(operation, sleep) == "actual response"
    assert len(calls) == 2
