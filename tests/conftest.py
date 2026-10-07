import json

import pytest

from signalbrief.config import Settings
from signalbrief.schemas import Action, Citation, Event, Finding, ResearchDossier, Source, StrategyReport
from signalbrief.store import Store


@pytest.fixture
def settings(tmp_path):
    competitors = tmp_path / "competitors.json"
    competitors.write_text(json.dumps([{"name": "Linear", "domains": ["linear.app"],
        "reference_urls": [], "our_context": "Synthetic test company providing small-team project tools."}]))
    return Settings(_env_file=None, database_path=tmp_path / "test.sqlite3", competitors_path=competitors,
                    admin_password="a-secure-test-password", webhook_api_key="k" * 40,
                    session_secret="s" * 40, llm_api_key="test-key", public_base_url="http://testserver",
                    zapier_hook_url="https://hooks.zapier.com/hooks/catch/123456/testonly/")


@pytest.fixture
def store(settings):
    value = Store(settings.database_path)
    value.initialize()
    return value


@pytest.fixture
def event():
    return Event(event_id="linear-launch-001", competitor="Linear", title="Linear introduces a workflow update",
                 source_url="https://linear.app/changelog")


@pytest.fixture
def source():
    return Source(source_id="src_real", url="https://linear.app/changelog", title="Workflow update",
                  fetched_at="2026-10-08T00:00:00+00:00", sha256="a" * 64,
                  text="Linear introduces improved project workflows for engineering teams. "
                       "The announcement describes team collaboration improvements and project planning.")


@pytest.fixture
def action():
    return Action(action="Interview customers about workflow friction.", rationale="The announcement highlights workflows.",
                  evidence_ids=["src_real"], priority="medium", owner="Product team",
                  validation_step="Interview five existing customers before changing the roadmap.")


@pytest.fixture
def dossier(source, action):
    return ResearchDossier(headline="Linear workflow announcement", summary="The announcement describes a workflow improvement.",
        findings=[Finding(claim="Linear announced improved project workflows.", citations=[Citation(
            source_id=source.source_id, excerpt="Linear introduces improved project workflows for engineering teams.")])],
        unknowns=["Customer adoption and revenue impact are unknown."], baseline_actions=[action])


@pytest.fixture
def report(action):
    return StrategyReport(strategic_summary="Workflow improvements may affect how customers compare our products.",
        implications=["Customer workflow expectations may change; this is a hypothesis."],
        challenged_assumptions=["A launch does not prove customer adoption."], actions=[action],
        limitations=["One announcement cannot establish market impact."])


@pytest.fixture
def ready_run(store, event, source, dossier, report):
    run_id, _ = store.enqueue(event, 20)
    item = store.claim(180, 3)
    store.checkpoint(run_id, item["lease_token"], "evidence_collected", "sources_json", [source.model_dump()])
    store.checkpoint(run_id, item["lease_token"], "research_completed", "research_json", dossier.model_dump())
    store.finish(run_id, item["lease_token"], dossier.model_dump(), report.model_dump(), [], {}, "http://testserver")
    return run_id
