"""Run the API and leased worker in one process on a small hosting instance."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn

from signalbrief.api import create_app
from signalbrief.config import Settings
from signalbrief.worker import Worker


def create_hosted_app(settings=None):
    if settings is None:
        if os.getenv("RENDER_EXTERNAL_URL"):
            os.environ.setdefault("PUBLIC_BASE_URL", os.environ["RENDER_EXTERNAL_URL"])
            os.environ.setdefault("SECURE_COOKIES", "true")
        settings = Settings()
    app = create_app(settings)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            task = asyncio.create_task(Worker(settings, app.state.store).run(), name="signalbrief-worker")
            app.state.worker_task = task
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app.router.lifespan_context = lifespan
    return app


def main():
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("signalbrief.hosted:create_hosted_app", factory=True, host="0.0.0.0",
                port=int(os.getenv("PORT", "8000")), proxy_headers=False)


if __name__ == "__main__":
    main()
