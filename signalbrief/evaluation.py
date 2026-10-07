"""Evaluate a stored real run without making another model request."""
import argparse
import json
from pathlib import Path

from signalbrief.config import Settings
from signalbrief.schemas import ResearchDossier, Source, StrategyReport, validate_dossier, validate_strategy
from signalbrief.store import Store


def action_metrics(actions: list, valid_ids: set[str]) -> dict:
    return {
        "action_count": len(actions),
        "valid_evidence_reference_rate": sum(set(a.evidence_ids) <= valid_ids for a in actions) / len(actions),
        "explicit_validation_step_rate": sum(bool(a.validation_step.strip()) for a in actions) / len(actions),
        "assigned_owner_rate": sum(bool(a.owner.strip()) for a in actions) / len(actions),
        "action_text_characters": sum(len(a.action) + len(a.rationale) for a in actions),
    }


def evaluate(run: dict) -> dict:
    dossier = ResearchDossier.model_validate(run["research"])
    sources = [Source.model_validate(s) for s in run["sources"]]
    report = StrategyReport.model_validate(run["report"])
    validate_dossier(dossier, sources)
    validate_strategy(report, dossier)
    valid_ids = {c.source_id for f in dossier.findings for c in f.citations}
    return {
        "run_id": run["id"], "version": run["version"], "source_count": len(sources),
        "exact_quote_validation": "passed", "research_finding_count": len(dossier.findings),
        "research_only": action_metrics(dossier.baseline_actions, valid_ids),
        "research_plus_critique": action_metrics(report.actions, valid_ids),
        "critic_objections_recorded": len(report.challenged_assumptions),
        "execution": run["metrics"],
        "interpretation": "These are structural and traceability checks, not semantic truth or business impact scores.",
        "human_review_rubric": [
            "Does each factual claim accurately paraphrase its cited excerpt?",
            "Did the critic identify an assumption that materially changed an action?",
            "Would an independent product manager consider the actions useful and reversible?",
            "Does the additional quality justify the measured analysis latency and token usage?",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation.json"))
    args = parser.parse_args()
    settings = Settings()
    run = Store(settings.database_path, settings.database_url.get_secret_value()).get_run(args.run_id)
    if run is None or run["report"] is None:
        raise SystemExit("A completed real run is required")
    result = evaluate(run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
