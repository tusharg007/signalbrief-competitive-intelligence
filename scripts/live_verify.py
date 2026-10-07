"""Run the actual collector and frameworks; never publish or auto-approve a report."""
import argparse
import asyncio
import json
import time
from pathlib import Path

from signalbrief.config import Settings
from signalbrief.schemas import Event
from signalbrief.store import Store
from signalbrief.worker import Worker


async def verify(args):
    settings = Settings()
    settings.require_auth()
    store = Store(settings.database_path, settings.database_url.get_secret_value())
    store.initialize()
    if args.run_id:
        run_id = args.run_id
        existing = store.get_run(run_id)
        if existing is None:
            raise RuntimeError("Run does not exist")
        if existing["status"] == "failed":
            store.retry_run(run_id)
    else:
        event = Event(event_id="live-verification-" + str(int(time.time())), competitor=args.competitor,
                      title=args.title, source_url=args.source_url)
        run_id, _ = store.enqueue(event, settings.max_daily_runs)
    worker = Worker(settings, store)
    # Claim the newly enqueued run through the durable queue, with no outbound notifications.
    item = store.claim(settings.lease_seconds, settings.max_attempts, run_id=run_id)
    if item is None:
        raise RuntimeError("No eligible run found")
    if item["id"] != run_id:
        raise RuntimeError("Other queued work exists; start the regular worker instead")
    await worker.process(item)
    run = store.get_run(run_id)
    result = {"run_id": run_id, "status": run["status"], "stage": run["stage"],
              "source_urls": [s["url"] for s in run["sources"] or []], "metrics": run["metrics"],
              "error": run["error"], "external_delivery_tested": False}
    Path("data").mkdir(exist_ok=True)
    Path("data/live-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if run["status"] != "awaiting_approval":
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", help="Resume an eligible existing run from its saved checkpoints")
    parser.add_argument("--competitor", default="Linear")
    parser.add_argument("--source-url", default="https://linear.app/changelog/2026-09-24-new-controls-for-linear-coding-agent")
    parser.add_argument("--title", default="Linear announces new controls for its coding agent")
    asyncio.run(verify(parser.parse_args()))


if __name__ == "__main__":
    main()
