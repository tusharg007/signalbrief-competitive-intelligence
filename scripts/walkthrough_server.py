"""Isolated walkthrough workspace: real agents, copied historical proof, no outbound Slack."""
import argparse
import json
import logging
import secrets
import sqlite3
from pathlib import Path

import uvicorn
from dotenv import dotenv_values
from fastapi.responses import FileResponse

from signalbrief.config import Settings
from signalbrief.hosted import create_hosted_app

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "walkthrough"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--prepare-rejection-replay", action="store_true")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    db = WORK / "workspace.sqlite3"
    if args.prepare:
        if db.exists():
            raise SystemExit("Walkthrough database already exists; retain it rather than overwrite.")
        with sqlite3.connect(ROOT / "data" / "signalbrief.sqlite3") as source:
            with sqlite3.connect(db) as target:
                source.backup(target)
                # Only prune the disposable COPY, never the original operator database.
                target.execute("DELETE FROM deliveries WHERE run_id IN (SELECT id FROM runs WHERE status!='approved')")
                target.execute("DELETE FROM reports WHERE run_id IN (SELECT id FROM runs WHERE status!='approved')")
                target.execute("DELETE FROM audit WHERE run_id IN (SELECT id FROM runs WHERE status!='approved')")
                target.execute("DELETE FROM runs WHERE status!='approved'")
                target.execute("DELETE FROM worker_health")
        (WORK / "operator.json").write_text(json.dumps({
            "admin_password": secrets.token_urlsafe(24), "webhook_api_key": secrets.token_urlsafe(32),
            "session_secret": secrets.token_urlsafe(32)}), encoding="utf-8")
        print("Isolated copy prepared; historical records retained; temporary credentials stay ignored.")
        return
    if args.prepare_rejection_replay:
        from signalbrief.schemas import Event
        from signalbrief.store import Store
        store = Store(db)
        rows = [r for r in store.list_runs() if r["status"] == "approved" and r["version"] == 2]
        if len(rows) != 1:
            raise SystemExit("Expected the single fresh version-2 demo approval.")
        original = store.get_run(rows[0]["id"])
        event = Event.model_validate({**original["event"], "event_id": "walkthrough-rejection-replay",
                                      "title": "REPLAY EXERCISE: reject the retained Notion report"})
        run_id, created = store.enqueue(event, 20)
        if created:
            item = store.claim(180, 3, run_id=run_id)
            if item is None:
                raise SystemExit("Replay was claimed elsewhere; do not fabricate a completion.")
            store.checkpoint(run_id, item["lease_token"], "evidence_collected", "sources_json", original["sources"])
            store.checkpoint(run_id, item["lease_token"], "research_completed", "research_json", original["research"])
            store.finish(run_id, item["lease_token"], original["research"], original["report"],
                         original["messages"], {"walkthrough_replay_of": original["id"],
                         "real_model_calls_for_this_replay": 0}, "http://127.0.0.1:8013")
        (WORK / "rejection-replay.json").write_text(json.dumps({"run_id": run_id,
            "replayed_from": original["id"], "purpose": "control-only rejection demonstration; no new inference"}), encoding="utf-8")
        print("Clearly labelled rejection replay prepared; actual prior report retained; no new model call.")
        return
    credentials = json.loads((WORK / "operator.json").read_text(encoding="utf-8"))
    local = dotenv_values(ROOT / ".env")
    hosting = dotenv_values(ROOT / "data" / "hosting.env")
    key = hosting.get("GROQ_API_KEY") or local.get("GROQ_API_KEY") or local.get("LLM_API_KEY")
    if not key:
        raise SystemExit("Configure an existing Groq credential locally before real-model recording.")
    settings = Settings(_env_file=None, database_path=db, database_url="", **credentials,
                        competitors_path=ROOT / "competitors.json", groq_api_key=key, llm_api_key="",
                        public_base_url="http://127.0.0.1:8013", zapier_hook_url="", secure_cookies=False,
                        max_source_chars=4000,
                        showcase_run_ids="d1434228a9ad4f92acc120d45af1c437,1764a413980b4e7aabc2af41f8adfb8c")
    app = create_hosted_app(settings)

    @app.get("/walkthrough-proof", include_in_schema=False)
    def proof():
        return FileResponse(WORK / "proof.html")

    @app.get("/walkthrough-asset/{name}", include_in_schema=False)
    def asset(name: str):
        allowed = {"zapier-rss-live.png", "slack-review.png", "slack-approved.png"}
        if name not in allowed:
            from fastapi import HTTPException
            raise HTTPException(404)
        return FileResponse(ROOT / "docs" / "assets" / name)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in ("httpx", "openai", "crewai", "autogen_core.events"):
        logging.getLogger(name).setLevel(logging.ERROR)
    uvicorn.run(app, host="127.0.0.1", port=8013, access_log=False)


if __name__ == "__main__":
    main()
