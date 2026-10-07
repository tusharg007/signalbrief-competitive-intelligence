FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY signalbrief ./signalbrief
RUN uv sync --frozen --no-dev --python /usr/local/bin/python
COPY competitors.json ./competitors.json
RUN useradd --create-home --uid 10001 signalbrief && mkdir -p data && chown signalbrief:signalbrief /app/data
USER signalbrief
EXPOSE 8000
CMD [".venv/bin/uvicorn", "signalbrief.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
