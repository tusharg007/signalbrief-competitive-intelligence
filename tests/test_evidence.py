import pytest

from signalbrief.agents import AgentOutputError, parse_report
from signalbrief.delivery import valid_hook
from signalbrief.schemas import canonical_excerpt, validate_dossier, validate_strategy
from signalbrief.sources import SourceError, allowed_url, public_addresses


def test_valid_quotes_and_strategy_are_accepted(dossier, source, report):
    validate_dossier(dossier, [source])
    validate_strategy(report, dossier)


def test_typographic_quote_is_restored_to_literal_source_text():
    text = 'Product supports AI-powered workflows and "team search".'
    assert canonical_excerpt(text, 'AI‑powered workflows and “team search”') == 'AI-powered workflows and "team search"'
    assert canonical_excerpt(text, 'AI-powered workflows and private-code execution') is None
    assert canonical_excerpt("Launch includes team controls", "Launch includes team controls.") == "Launch includes team controls"
    assert canonical_excerpt("Heading ⁠ Public details", "Heading ⁠Public details") == "Heading ⁠ Public details"


def test_fabricated_quote_is_rejected(dossier, source):
    dossier.findings[0].citations[0].excerpt = "Revenue increased by fifty percent across all customers."
    with pytest.raises(ValueError):
        validate_dossier(dossier, [source])


def test_unknown_source_is_rejected(dossier, source):
    dossier.findings[0].citations[0].source_id = "src_invented"
    with pytest.raises(ValueError):
        validate_dossier(dossier, [source])


def test_action_cannot_reference_unverified_evidence(dossier, report):
    report.actions[0].evidence_ids = ["src_unverified"]
    with pytest.raises(ValueError):
        validate_strategy(report, dossier)


@pytest.mark.parametrize("url", ["http://linear.app/changelog", "https://linear.app.evil.org/",
    "https://linear.app@127.0.0.1/", "https://linear.app:8443/", "https://linear.app/#fragment",
    "https://localhost/", "file:///etc/passwd", "https://linear.app/\r\nInjected: yes"])
def test_unsafe_urls_are_denied(url):
    with pytest.raises(SourceError):
        allowed_url(url, ["linear.app"])


def test_private_dns_and_mixed_public_private_dns_denied(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(SourceError):
        public_addresses("linear.app")
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("1.1.1.1", 443)), (2, 1, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(SourceError):
        public_addresses("linear.app")


@pytest.mark.parametrize("url", ["https://example.org/hooks/catch/x/y/", "http://hooks.zapier.com/hooks/catch/x/y/",
    "https://hooks.zapier.com:8443/hooks/catch/x/y/", "https://hooks.zapier.com/hooks/catch/x/y/?token=x"])
def test_untrusted_delivery_destinations_denied(url):
    assert not valid_hook(url)


def test_editor_json_parser_rejects_malformed_and_accepts_fences(report):
    assert parse_report('```json\n' + report.model_dump_json() + '\n```') == report
    with pytest.raises(AgentOutputError):
        parse_report("This is not a valid report")
