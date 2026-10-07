"""Fetch public HTTPS evidence with host allowlists, DNS pinning, and bounded bodies."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from signalbrief.config import Settings
from signalbrief.schemas import Competitor, Event, Source


class SourceError(Exception):
    pass


def load_competitors(settings: Settings) -> list[Competitor]:
    values = json.loads(settings.competitors_path.read_text(encoding="utf-8"))
    competitors = [Competitor.model_validate(value) for value in values]
    names = [x.name.casefold() for x in competitors]
    if len(names) != len(set(names)):
        raise ValueError("Competitor names must be unique")
    return competitors


def find_competitor(name: str, settings: Settings) -> Competitor:
    match = next((c for c in load_competitors(settings) if c.name.casefold() == name.casefold()), None)
    if match is None:
        raise ValueError("Competitor is not registered in competitors.json")
    return match


def allowed_url(url: str, domains: list[str]) -> str:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise SourceError("Invalid source URL") from exc
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or port not in (None, 443) or parts.fragment):
        raise SourceError("Source URLs must be HTTPS on port 443, without credentials or fragments")
    hostname = parts.hostname.lower()
    if hostname not in {d.lower() for d in domains}:
        raise SourceError("Source hostname is not allowlisted for this competitor")
    if len(parts.path) > 1800 or any(ch in url for ch in ("\r", "\n", "\x00")):
        raise SourceError("Invalid source URL")
    return hostname


def public_addresses(hostname: str) -> list[str]:
    try:
        addresses = list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(
            hostname, 443, type=socket.SOCK_STREAM)))
    except OSError as exc:
        raise SourceError("Source hostname could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise SourceError("Source hostname resolves to a non-public network")
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: int):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the exact validated address while retaining hostname certificate verification.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch_source(url: str, competitor: Competitor, settings: Settings) -> Source:
    for _ in range(4):
        hostname = allowed_url(url, competitor.domains)
        addresses = public_addresses(hostname)
        parsed = urlsplit(url)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        conn = PinnedHTTPSConnection(hostname, addresses[0], settings.source_timeout_seconds)
        try:
            conn.request("GET", path, headers={
                "User-Agent": "SignalBrief/1.0 (competitive research; bounded public-page retrieval)",
                "Accept": "text/html,text/plain", "Accept-Encoding": "identity",
            })
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise SourceError("Source returned a redirect without a location")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise SourceError(f"Source returned HTTP {response.status}")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise SourceError("Source returned an unsupported compressed response")
            mime = response.getheader("Content-Type", "").split(";")[0].strip().lower()
            if mime not in {"text/html", "text/plain", "application/xhtml+xml"}:
                raise SourceError("Source did not return a supported text document")
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise SourceError("Source exceeds the one-megabyte retrieval limit")
        except SourceError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise SourceError("Source retrieval failed or timed out") from exc
        finally:
            conn.close()
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else hostname
        for node in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
            node.decompose()
        content = soup.find("main") or soup.find("article") or soup
        # Animation spans often split a single word. Unwrap inline markup before joining text blocks.
        for node in list(content.find_all(["span", "a", "strong", "em", "b", "i"])):
            node.unwrap()
        content.smooth()
        text = " ".join(content.stripped_strings)[:settings.max_source_chars]
        if len(text) < 100:
            raise SourceError("Source has too little readable evidence; client-rendered pages are unsupported")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return Source(source_id="src_" + hashlib.sha256(url.encode()).hexdigest()[:16], url=url,
                      title=title[:250], fetched_at=datetime.now(timezone.utc).isoformat(),
                      sha256=digest, text=text)
    raise SourceError("Source exceeded the redirect limit")


def collect_sources(event: Event, settings: Settings) -> tuple[list[Source], list[str]]:
    competitor = find_competitor(event.competitor, settings)
    # The event's primary source is mandatory. Failed references become explicit limitations.
    sources = [fetch_source(event.source_url, competitor, settings)]
    warnings = []
    urls = list(dict.fromkeys(competitor.reference_urls))
    for url in urls:
        if len(sources) >= settings.max_sources:
            break
        if url in {s.url for s in sources}:
            continue
        try:
            source = fetch_source(url, competitor, settings)
            if source.url not in {s.url for s in sources}:
                sources.append(source)
        except SourceError:
            warnings.append(f"Reference source unavailable: {url}")
    return sources, warnings
