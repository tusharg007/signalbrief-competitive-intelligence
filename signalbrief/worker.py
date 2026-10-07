import asyncio
import logging
import os
import time
import uuid

# Disable third-party framework telemetry before importing framework packages.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TELEMETRY_DISABLED", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from signalbrief import agents
from signalbrief.config import Settings, get_settings
from signalbrief.delivery import deliver_one
from signalbrief.schemas import Event, ResearchDossier, Source, validate_dossier
from signalbrief.sources import SourceError, collect_sources, find_competitor
from signalbrief.store import Conflict, Store

log = logging.getLogger("signalbrief.worker")


class Worker:
    def __init__(self, settings: Settings, store: Store | None = None):
        self.settings = settings
        self.store = store or Store(settings.database_path, settings.database_url.get_secret_value())
        self.worker_id = uuid.uuid4().hex

    async def process(self, item: dict) -> None:
        token, run_id = item["lease_token"], item["id"]
        lease_lost = asyncio.Event()
        started = time.monotonic()

        async def keep_alive():
            while True:
                await asyncio.sleep(min(10, max(1, self.settings.lease_seconds / 3)))
                if not self.store.heartbeat(run_id, token, self.settings.lease_seconds):
                    lease_lost.set()
                    return
                self.store.worker_seen(self.worker_id)

        heartbeat = asyncio.create_task(keep_alive())
        try:
            if not self.settings.model_key:
                raise ValueError("Configure GROQ_API_KEY or LLM_API_KEY; no model key is available")
            event = Event.model_validate(item["event"])
            competitor = find_competitor(event.competitor, self.settings)
            metrics = item.get("metrics") or {}
            if item.get("sources"):
                sources = [Source.model_validate(s) for s in item["sources"]]
            else:
                sources, warnings = await asyncio.to_thread(collect_sources, event, self.settings)
                metrics["source_warnings"] = warnings
                self.store.checkpoint(run_id, token, "evidence_collected", "sources_json",
                                      [s.model_dump() for s in sources], {"messages": [], "metrics": metrics})
            if lease_lost.is_set():
                raise Conflict("Worker lease lost")
            if item.get("research"):
                dossier = ResearchDossier.model_validate(item["research"])
                validate_dossier(dossier, sources)
                research_messages = [m for m in item.get("messages") or [] if m["framework"] == "CrewAI"]
            else:
                dossier, research_messages, research_metrics = await asyncio.to_thread(
                    agents.research, event, competitor, sources, self.settings)
                metrics.update(research_metrics)
                self.store.checkpoint(run_id, token, "research_completed", "research_json",
                    dossier.model_dump(), {"messages": research_messages, "metrics": metrics})
            if lease_lost.is_set():
                raise Conflict("Worker lease lost")
            report, council_messages, analysis_metrics = await agents.council(
                dossier, competitor, self.settings, item.get("feedback", ""))
            metrics.update(analysis_metrics)
            metrics["attempt_seconds"] = round(time.monotonic() - started, 3)
            metrics["source_count"] = len(sources)
            metrics["quoted_citations"] = sum(len(f.citations) for f in dossier.findings)
            metrics["model"] = self.settings.llm_model
            metrics["provider"] = self.settings.llm_provider
            self.store.finish(run_id, token, dossier.model_dump(), report.model_dump(),
                              research_messages + council_messages, metrics, self.settings.public_base_url)
            log.info("Run %s completed and awaits approval", run_id)
        except Conflict:
            log.warning("Run %s stopped because worker ownership changed", run_id)
        except asyncio.CancelledError:
            # The lease expires and a subsequent worker resumes from stored checkpoints.
            raise
        except Exception as exc:
            error, retryable = classify_failure(exc)
            try:
                self.store.fail(run_id, token, error, retryable, self.settings.max_attempts)
            except Conflict:
                pass
            log.warning("Run %s: %s", run_id, error)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def run_once(self) -> bool:
        self.store.worker_seen(self.worker_id)
        item = self.store.claim(self.settings.lease_seconds, self.settings.max_attempts)
        if item:
            await self.process(item)
        delivered = await deliver_one(self.store, self.settings)
        return bool(item or delivered)

    async def run(self) -> None:
        self.store.initialize()
        log.info("Worker ready; provider=%s model=%s", self.settings.llm_provider, self.settings.llm_model)
        while True:
            try:
                worked = await self.run_once()
            except Exception as exc:
                # Never print provider exception bodies, credential-bearing URLs, or prompts.
                log.error("Worker operation failed (%s)", type(exc).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(self.settings.worker_poll_seconds)


def classify_failure(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, agents.AgentOutputError):
        return str(exc), True
    if isinstance(exc, SourceError):
        return str(exc), "timed out" in str(exc) or "HTTP 5" in str(exc) or "HTTP 429" in str(exc)
    if isinstance(exc, ValueError):
        return "Invalid configuration or unsupported model output; check local settings and run evidence", False
    code = getattr(exc, "status_code", None)
    if code in {401, 403}:
        return "Model authentication failed; check the configured API key", False
    if code == 404:
        return "Configured model is unavailable to this provider account; check LLM_MODEL", False
    if code == 429:
        return "Model rate limit reached", True
    return f"Model or pipeline operation failed ({type(exc).__name__}); no report was published", True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in ("httpx", "openai", "crewai", "autogen_core.events"):
        logging.getLogger(name).setLevel(logging.ERROR)
    settings = get_settings()
    settings.require_auth()
    try:
        asyncio.run(Worker(settings).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
