import hashlib
import hmac
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.middleware.sessions import SessionMiddleware

from signalbrief.config import Settings, get_settings
from signalbrief.delivery import valid_hook
from signalbrief.render import markdown_report
from signalbrief.schemas import Event, Review
from signalbrief.sources import SourceError, allowed_url, find_competitor, load_competitors
from signalbrief.store import BudgetExceeded, Conflict, Store


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.require_auth()
    store = Store(settings.database_path)
    static = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        with store.transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
                client TEXT NOT NULL, at REAL NOT NULL
            )""")
        load_competitors(settings)
        yield

    app = FastAPI(title="SignalBrief", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret.get_secret_value(),
                       session_cookie="signalbrief_session", max_age=28800, same_site="strict",
                       https_only=settings.secure_cookies)
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 65536:
                    return JSONResponse({"detail": "Request exceeds 64 KiB"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        # The ingestion endpoint uses its own header credential; browser mutations require CSRF.
        if request.method in {"POST", "PUT", "DELETE", "PATCH"} and request.url.path != "/events":
            origin = request.headers.get("origin")
            expected = urlsplit(settings.public_base_url)
            allowed_origins = {f"{expected.scheme}://{expected.netloc}",
                               f"{request.url.scheme}://{request.url.netloc}"}
            if origin and origin not in allowed_origins:
                return JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def authenticated(request: Request):
        if request.session.get("authenticated") is not True:
            raise HTTPException(401, "Sign in to the dashboard")

    def mutation(request: Request, _=Depends(authenticated)):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(csrf, request.session.get("csrf", "")):
            raise HTTPException(403, "Missing or invalid CSRF token")

    def run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    @app.exception_handler(Conflict)
    async def conflict_handler(request: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static / "index.html")

    @app.get("/health")
    def health():
        status = store.health()
        # Public health intentionally omits run details, credentials, and integration URLs.
        return {"status": "ok", "version": "1.0.0", "database": status["database"],
                "worker_online": status["worker_online"]}

    @app.get("/api/session")
    def session(request: Request):
        request.session.setdefault("csrf", secrets.token_urlsafe(32))
        return {"authenticated": request.session.get("authenticated") is True, "csrf": request.session["csrf"]}

    @app.post("/api/login")
    def login(body: Login, request: Request):
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), request.session.get("csrf", "!")):
            raise HTTPException(403, "Refresh the login page")
        client = hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()
        now = time.time()
        with store.transaction() as conn:
            conn.execute("DELETE FROM login_attempts WHERE at<?", (now - 300,))
            count = conn.execute("SELECT COUNT(*) FROM login_attempts WHERE client=?", (client,)).fetchone()[0]
            if count >= 5:
                raise HTTPException(429, "Too many login attempts; wait five minutes")
            conn.execute("INSERT INTO login_attempts VALUES(?,?)", (client, now))
        if not hmac.compare_digest(body.password.encode(), settings.admin_password.get_secret_value().encode()):
            raise HTTPException(401, "Invalid password")
        request.session.clear()
        request.session.update(authenticated=True, csrf=secrets.token_urlsafe(32))
        return {"authenticated": True, "csrf": request.session["csrf"]}

    @app.post("/api/logout", dependencies=[Depends(mutation)])
    def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    def enqueue(event: Event):
        try:
            competitor = find_competitor(event.competitor, settings)
            allowed_url(event.source_url, competitor.domains)
            run_id, created = store.enqueue(event, settings.max_daily_runs)
        except (ValueError, SourceError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except BudgetExceeded as exc:
            raise HTTPException(429, str(exc)) from exc
        return JSONResponse({"run_id": run_id, "status": "queued" if created else "duplicate",
                             "created": created}, status_code=202 if created else 200)

    @app.post("/events", summary="Ingest a real Zapier event using X-API-Key")
    async def events(request: Request):
        key = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(key.encode(), settings.webhook_api_key.get_secret_value().encode()):
            raise HTTPException(401, "Invalid webhook credential")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 65536:
                raise HTTPException(413, "Request exceeds 64 KiB")
        try:
            event = Event.model_validate_json(data)
        except ValidationError:
            raise HTTPException(422, "Invalid event schema; see /docs") from None
        return enqueue(event)

    @app.post("/api/events", dependencies=[Depends(mutation)])
    def manual_event(event: Event):
        return enqueue(event)

    @app.get("/api/status", dependencies=[Depends(authenticated)])
    def status():
        result = store.health()
        result.update(model_configured=bool(settings.model_key), provider=settings.llm_provider,
                      model=settings.llm_model, zapier_configured=valid_hook(settings.zapier_hook_url.get_secret_value()),
                      daily_run_limit=settings.max_daily_runs)
        return result

    @app.get("/api/competitors", dependencies=[Depends(authenticated)])
    def competitors():
        return [c.model_dump() for c in load_competitors(settings)]

    @app.get("/api/runs", dependencies=[Depends(authenticated)])
    def runs():
        return store.list_runs()

    @app.get("/api/runs/{run_id}", dependencies=[Depends(authenticated)])
    def get_run(run_id: str):
        return run_or_404(run_id)

    @app.get("/api/runs/{run_id}/report.md", dependencies=[Depends(authenticated)])
    def report_file(run_id: str):
        run = run_or_404(run_id)
        if not run["report"]:
            raise HTTPException(409, "Report is not ready")
        return PlainTextResponse(markdown_report(run), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="signalbrief-{run_id}.md"'})

    @app.post("/api/runs/{run_id}/review", dependencies=[Depends(mutation)])
    def review(run_id: str, body: Review):
        run_or_404(run_id)
        try:
            store.review(run_id, body.version, body.decision, body.feedback, settings.public_base_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return run_or_404(run_id)

    @app.post("/api/runs/{run_id}/retry", dependencies=[Depends(mutation)])
    def retry(run_id: str):
        run_or_404(run_id)
        store.retry_run(run_id)
        return {"ok": True}

    @app.post("/api/deliveries/{delivery_id}/retry", dependencies=[Depends(mutation)])
    def retry_delivery(delivery_id: str):
        try:
            store.retry_delivery(delivery_id)
        except KeyError as exc:
            raise HTTPException(404, "Delivery not found") from exc
        return {"ok": True}

    @app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(mutation)])
    def cancel(run_id: str):
        run_or_404(run_id)
        store.cancel_run(run_id)
        return {"ok": True}

    return app
