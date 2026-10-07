# Render + Neon deployment

## Live access

- Public portfolio: https://signalbrief-dncb.onrender.com/showcase
- Operator login: https://signalbrief-dncb.onrender.com
- Readiness: https://signalbrief-dncb.onrender.com/ready
- Zapier ingress: https://signalbrief-dncb.onrender.com/events

The full FastAPI API and leased worker run together in one hosted process. The dedicated Neon PostgreSQL database stores evidence, report versions, audit history, leases and the delivery outbox. Local SQLite records remain intact. Two selected approved live runs were imported without replaying their completed notifications.

## RSS cutover

The operator confirmed this change on 8 October 2026:

1. Open **Linear RSS to SignalBrief** → **Edit Zap** → **2. POST** → **Configure**.
2. URL: `https://signalbrief-dncb.onrender.com/events`.
3. Keep JSON Data: event_id = `linear:` + RSS Guid, competitor = literal `Linear`, title = RSS Title, source_url = RSS Link.
4. Keep `X-API-Key` unchanged. Delete `ngrok-skip-browser-warning`.
5. Test the same previously imported event. An identical payload returns `status: duplicate`, `created: false`; it does not rerun inference or resend Slack notifications.
6. Publish. New feed items are subject to the five-new-runs-per-day admission limit.

The outbound Slack Zap keeps its Catch Hook and mappings. New notifications use Render public links automatically. Historical Slack messages retain their original ngrok links.

## Runtime secrets

Render's private environment contains DATABASE_URL, GROQ_API_KEY, ZAPIER_HOOK_URL, ADMIN_PASSWORD, WEBHOOK_API_KEY and SESSION_SECRET. The dashboard uses the existing local administrator password. Public visitors use `/showcase` without credentials.

SHOWCASE_RUN_IDS explicitly selects which approved runs are public. Approval alone does not publish future research. Public responses omit delivery payloads and receipts. Avoid publishing confidential records.

Account setup files under `data/hosting.env` and `data/neon.env` are ignored by Git and excluded from Docker. Deployment did not rewrite `.env`.

## Reproduction

Connect the GitHub repository to Render and use the free Docker web service described by `render.yaml`, supplying the secret values and a Neon PostgreSQL URL. Start command:

```text
.venv/bin/python -m signalbrief.hosted
```

Render supplies PORT and RENDER_EXTERNAL_URL. The launcher sets public notification links and enables secure cookies. `/ready` checks a recent heartbeat and hosted worker task health.

With a PostgreSQL DATABASE_URL set in your process, preserve a selected completed SQLite run with:

```powershell
uv run python scripts/import_approved.py --source data/signalbrief.sqlite3 --run-id APPROVED_RUN_ID
```

The import requires approval and completed/cancelled deliveries. It is selective preservation, not a general backup tool.

## Operating limits

Free Render sleeps after 15 minutes without inbound traffic and takes about a minute to wake. External PostgreSQL state survives restarts. Requests can wake the service; caller timeouts and provider quotas still apply. See [Render's free-service limits](https://render.com/docs/free).

The hosted admission cap is five new runs per day, with ten-second idle polling. Groq, Neon, Render and Zapier have finite quotas. Webhook automation needs an eligible Zapier plan after the trial. No paid compute upgrade was performed. This portfolio deployment has no always-on production SLA.

## Maintenance

Check `/ready`, Render logs, dashboard status and Zap History. A webhook receipt proves acceptance; check Slack separately. Back up Neon with a PostgreSQL dump or supported database export/branch workflow, retaining frozen evidence and audit history. Deploy application code after CI passes; the same test suite exercises SQLite and PostgreSQL.

Vercel is not used here: the existing full backend and worker stay together on Render, keeping one authentication origin.
