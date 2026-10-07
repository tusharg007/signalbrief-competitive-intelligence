from signalbrief.schemas import ResearchDossier, StrategyReport


def markdown_report(run: dict) -> str:
    dossier = ResearchDossier.model_validate(run["research"])
    report = StrategyReport.model_validate(run["report"])
    sources = {s["source_id"]: s for s in run["sources"]}
    lines = [f"# {dossier.headline}", "", f"Status: {run['status']} · Version: {run['version']}",
             "", "## Research summary", "", dossier.summary, "", "## Evidence-backed findings", ""]
    for finding in dossier.findings:
        lines += [f"- {finding.claim}"]
        for citation in finding.citations:
            source = sources[citation.source_id]
            lines += [f"  - Source: {source['url']} (fetched {source['fetched_at']})",
                      f"    > {citation.excerpt}"]
    lines += ["", "## Strategic interpretation — hypotheses", "", report.strategic_summary, ""]
    lines += [f"- {s}" for s in report.implications]
    lines += ["", "## Proposed actions — human validation required", ""]
    for action in report.actions:
        lines += [f"### {action.priority.upper()} · {action.action}", "", f"Owner: {action.owner}",
                  "", action.rationale, "", f"Validation: {action.validation_step}", "",
                  "Evidence: " + ", ".join(sources[i]["url"] for i in action.evidence_ids), ""]
    for heading, values in (("Challenged assumptions", report.challenged_assumptions),
                            ("Research unknowns", dossier.unknowns), ("Limitations", report.limitations)):
        lines += ["", "## " + heading, ""] + ["- " + s for s in values]
    lines += ["", "## Execution record", "", "```json", __import__("json").dumps(run["metrics"], indent=2), "```",
              "", "Citation and quote validation verifies traceability, not the truth of every interpretation."]
    return "\n".join(lines) + "\n"
