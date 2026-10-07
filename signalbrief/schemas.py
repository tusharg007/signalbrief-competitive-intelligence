import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Competitor(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    domains: list[str] = Field(min_length=1, max_length=10)
    reference_urls: list[str] = Field(default_factory=list, max_length=3)
    our_context: str = Field(min_length=20, max_length=3000)


class Event(StrictModel):
    event_id: str = Field(min_length=3, max_length=160, pattern=r"^[A-Za-z0-9_.:/-]+$")
    competitor: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=5, max_length=250)
    source_url: str = Field(min_length=10, max_length=2000)
    published_at: datetime | None = None


class Source(StrictModel):
    source_id: str
    url: str
    title: str
    fetched_at: str
    sha256: str
    text: str


class Citation(StrictModel):
    source_id: str
    excerpt: str = Field(min_length=15, max_length=1000)


class Finding(StrictModel):
    claim: str = Field(min_length=10, max_length=900)
    citations: list[Citation] = Field(min_length=1, max_length=3)


class Action(StrictModel):
    action: str = Field(min_length=10, max_length=650)
    rationale: str = Field(min_length=10, max_length=900)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    priority: Literal["high", "medium", "low"]
    owner: str = Field(min_length=2, max_length=80)
    validation_step: str = Field(min_length=10, max_length=500)


class ResearchDossier(StrictModel):
    headline: str = Field(min_length=5, max_length=200)
    summary: str = Field(min_length=20, max_length=1200)
    findings: list[Finding] = Field(min_length=1, max_length=10)
    unknowns: list[str] = Field(min_length=1, max_length=8)
    baseline_actions: list[Action] = Field(min_length=1, max_length=4)


class StrategyReport(StrictModel):
    strategic_summary: str = Field(min_length=20, max_length=1400)
    implications: list[str] = Field(min_length=1, max_length=5)
    challenged_assumptions: list[str] = Field(min_length=1, max_length=5)
    actions: list[Action] = Field(min_length=1, max_length=4)
    limitations: list[str] = Field(min_length=1, max_length=6)


class Review(StrictModel):
    decision: Literal["approve", "reject", "revise"]
    version: int = Field(ge=1)
    feedback: str = Field(default="", max_length=2000)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def canonical_excerpt(text: str, excerpt: str) -> str | None:
    """Resolve typographic equivalents back to a literal span of the saved source text."""
    punctuation = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                                "‘": "'", "’": "'", "“": '"', "”": '"'})

    def fold(value: str):
        output, positions = [], []
        for index, char in enumerate(value):
            if unicodedata.category(char) == "Cf":
                continue
            part = unicodedata.normalize("NFKC", char).translate(punctuation).casefold()
            for c in part:
                if c.isspace():
                    if output and output[-1] == " ":
                        continue
                    c = " "
                output.append(c)
                positions.append(index)
        return "".join(output), positions

    haystack, positions = fold(text)
    needle, _ = fold(excerpt)
    needle = needle.strip()
    offset = haystack.find(needle)
    if offset < 0:
        # Models often add sentence punctuation to a source bullet. Keep the stored quote literal.
        needle = needle.rstrip(".!?")
        offset = haystack.find(needle)
    if offset < 0 or not needle:
        return None
    return text[positions[offset]:positions[offset + len(needle) - 1] + 1]


def validate_dossier(dossier: ResearchDossier, sources: list[Source]) -> None:
    evidence = {s.source_id: s for s in sources}
    for finding in dossier.findings:
        for citation in finding.citations:
            source = evidence.get(citation.source_id)
            literal = canonical_excerpt(source.text, citation.excerpt) if source else None
            if literal is None:
                raise ValueError("Research contains an unknown source or a quote absent from fetched evidence")
            citation.excerpt = literal
    validate_actions(dossier.baseline_actions, set(evidence))


def validate_actions(actions: list[Action], evidence_ids: set[str]) -> None:
    for action in actions:
        if not set(action.evidence_ids) <= evidence_ids:
            raise ValueError("Action references an unknown evidence ID")
        if len(action.evidence_ids) != len(set(action.evidence_ids)):
            raise ValueError("Action repeats an evidence ID")


def validate_strategy(report: StrategyReport, dossier: ResearchDossier) -> None:
    ids = {c.source_id for finding in dossier.findings for c in finding.citations}
    validate_actions(report.actions, ids)
