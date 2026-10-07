import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from signalbrief.store import BudgetExceeded, Conflict, Store


def test_event_deduplication_is_atomic(store, event):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.enqueue(event, 20), range(8)))
    assert len({r[0] for r in results}) == 1
    assert sum(r[1] for r in results) == 1


def test_event_id_cannot_be_reused_for_another_payload(store, event):
    store.enqueue(event, 20)
    with pytest.raises(Conflict):
        store.enqueue(event.model_copy(update={"title": "A completely different announcement"}), 20)


def test_daily_budget_and_duplicates(store, event):
    store.enqueue(event, 1)
    assert store.enqueue(event, 1)[1] is False
    with pytest.raises(BudgetExceeded):
        store.enqueue(event.model_copy(update={"event_id": "next-event"}), 1)


def test_only_one_worker_claims_run(store, event):
    store.enqueue(event, 20)
    with ThreadPoolExecutor(max_workers=5) as pool:
        claims = list(pool.map(lambda _: store.claim(180, 3), range(5)))
    assert sum(c is not None for c in claims) == 1


def test_expired_worker_cannot_publish(store, event, dossier, report):
    run_id, _ = store.enqueue(event, 20)
    first = store.claim(180, 3)
    with store.transaction() as conn:
        conn.execute("UPDATE runs SET lease_until=? WHERE id=?", (time.time() - 1, run_id))
    second = store.claim(180, 3)
    assert second["id"] == first["id"]
    assert not store.heartbeat(run_id, first["lease_token"], 180)
    with pytest.raises(Conflict):
        store.finish(run_id, first["lease_token"], dossier.model_dump(), report.model_dump(), [], {}, "http://localhost")


def test_checkpoint_survives_new_store_instance(store, event, source):
    run_id, _ = store.enqueue(event, 20)
    item = store.claim(180, 3)
    store.checkpoint(run_id, item["lease_token"], "evidence_collected", "sources_json", [source.model_dump()])
    restored = Store(store.path, store.database_url).get_run(run_id)
    assert restored["sources"][0]["sha256"] == source.sha256


def test_approval_creates_one_outbox_delivery(store, ready_run):
    before = store.get_run(ready_run)
    assert all(d["kind"] != "approved_report" for d in before["deliveries"])
    store.review(ready_run, 1, "approve", "Reviewed", "http://localhost")
    with pytest.raises(Conflict):
        store.review(ready_run, 1, "approve", "", "http://localhost")
    after = store.get_run(ready_run)
    assert after["status"] == "approved"
    assert sum(d["kind"] == "approved_report" for d in after["deliveries"]) == 1
    assert store.claim_delivery(90, True)["kind"] == "approved_report"


def test_rejection_never_schedules_approved_delivery(store, ready_run):
    store.review(ready_run, 1, "reject", "Not sufficient", "http://localhost")
    assert store.claim_delivery(90, True) is None
    assert all(d["kind"] != "approved_report" for d in store.get_run(ready_run)["deliveries"])


def test_stale_approval_and_empty_revision_denied(store, ready_run):
    with pytest.raises(Conflict):
        store.review(ready_run, 2, "approve", "", "http://localhost")
    with pytest.raises(ValueError):
        store.review(ready_run, 1, "revise", "", "http://localhost")


def test_revision_preserves_evidence_and_version_history(store, ready_run):
    store.review(ready_run, 1, "revise", "Challenge adoption assumptions", "http://localhost")
    run = store.get_run(ready_run)
    assert run["version"] == 2 and run["report"] is None and run["research"]
    assert len(run["history"]) == 1
    assert run["feedback"] == "Challenge adoption assumptions"
    assert store.claim_delivery(90, True) is None


def test_delivery_requires_configuration_and_can_resume(store, ready_run):
    assert store.claim_delivery(90, False) is None
    assert store.get_run(ready_run)["deliveries"][0]["status"] == "blocked"
    item = store.claim_delivery(90, True)
    assert item["kind"] == "review_requested"


def test_review_cancels_outdated_delivery_replay(store, ready_run):
    store.claim_delivery(90, False)
    delivery_id = store.get_run(ready_run)["deliveries"][0]["id"]
    store.review(ready_run, 1, "reject", "", "http://localhost")
    with pytest.raises(Conflict):
        store.retry_delivery(delivery_id)


def test_exhausted_worker_lease_becomes_failed(store, event):
    run_id, _ = store.enqueue(event, 20)
    store.claim(180, 1)
    with store.transaction() as conn:
        conn.execute("UPDATE runs SET lease_until=? WHERE id=?", (time.time() - 1, run_id))
    assert store.claim(180, 1) is None
    assert store.get_run(run_id)["status"] == "failed"


def test_cancel_preserves_record_and_stops_queue_claim(store, event):
    run_id, _ = store.enqueue(event, 20)
    store.cancel_run(run_id)
    run = store.get_run(run_id)
    assert run["status"] == "cancelled"
    assert run["event"]["event_id"] == event.event_id
    assert run["audit"][-1]["event"] == "human_cancel"
    assert store.claim(180, 3) is None
    with pytest.raises(Conflict):
        store.retry_run(run_id)


def test_cancel_does_not_interrupt_claimed_or_reviewable_work(store, event, ready_run):
    run_id, _ = store.enqueue(event, 20)
    store.claim(180, 3, run_id=run_id)
    for target in [run_id, ready_run]:
        with pytest.raises(Conflict):
            store.cancel_run(target)
