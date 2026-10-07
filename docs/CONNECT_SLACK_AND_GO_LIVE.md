# Connect Slack and receive real Zapier signals

The application and real Groq pipeline are verified. Both the outbound Slack Zap and inbound Linear RSS Zap are published and on. The operator's screenshots confirm the real RSS test run, manual approval, and both review and approved-report Slack notifications with public ngrok links. Public dashboard login and worker-online status are also observed. The steps below document how to reproduce the integration. The free tunnel route does not require a hosting account or domain purchase. Your computer must remain awake with both the application and tunnel running.

## 1. Connect Slack to your existing Catch Hook Zap

1. In Slack, create a channel such as `#signalbrief`.
2. In Zapier, open **Apps → Add connection → Slack**, sign in and authorize the intended workspace. Managed workspaces might require administrator approval.
3. Open the Zap whose Catch Hook URL you already saved. In its trigger's **Test** tab, select the previously received **SignalBrief verification** record.
4. Add **Slack → Send Channel Message**, select your connection and channel, and map the fields shown below using Zapier's field picker.
5. Click **Test action**, check the channel, and then publish the Zap.

Official instructions: [Connect Slack](https://help.zapier.com/hc/en-us/articles/8495993391629-How-to-get-started-with-Slack-on-Zapier).

```text
SignalBrief · {{event_type}}
{{title}}
Competitor: {{competitor}} · Version: {{version}}
{{message}}
Review: {{review_url}}
Report: {{report_url}}
Delivery: {{delivery_id}}
```

The braces represent mapped fields, not text to type literally. The verification record's old localhost links are only connectivity-test values. Future real signals use the public address configured below. For review messages `report_url` is absent; for approved messages `review_url` is absent. A blank line is harmless, or use Paths to format each event kind separately.

If the old test record is unavailable, test the action with a label you enter manually, then use a new real signal after the tunnel is running. No additional notification has been sent automatically during setup. See [ZAPIER.md](ZAPIER.md) for delivery-ID duplicate suppression. Catch Hook requires a Zapier plan that supports Webhooks; a free plan alone does not support this trigger. [Current webhook plan requirements](https://help.zapier.com/hc/en-us/articles/8496288690317-Trigger-Zap-workflows-from-webhooks).

## 2. Install and authenticate ngrok

Create a free account at [ngrok](https://dashboard.ngrok.com/signup). Follow its [Windows installation instructions](https://ngrok.com/download/windows). In PowerShell:

```powershell
winget install ngrok -s msstore
```

Open a new terminal after installation. Copy the authentication command from your ngrok dashboard and run it locally:

```powershell
ngrok config add-authtoken "YOUR_NGROK_AUTHTOKEN"
ngrok http 8007
```

Keep that terminal running. Copy the displayed HTTPS forwarding address, such as `https://YOUR-ASSIGNED-DOMAIN.ngrok-free.app`. The free plan provides an assigned development domain and HTTPS within usage quotas. Browser visitors may see ngrok's **Visit Site** screen first. [Official free-plan details](https://ngrok.com/docs/pricing-limits/free-plan-limits).

## 3. Start SignalBrief with that public address

The existing review preview uses port **8008**. Use **8007** here to avoid that port conflict. In a second PowerShell terminal:

```powershell
Set-Location -LiteralPath 'E:\AI-Powered Competitive Intelligence Pipeline'
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Port 8007 -Model openai/gpt-oss-120b -PublicUrl https://YOUR-ASSIGNED-DOMAIN.ngrok-free.app
```

Replace the hostname with the actual forwarding address. This launcher supplies the tested Groq model, public links and secure cookies through **process environment values only**. It does not rewrite `.env`, its API key or its hook URL. It starts the real worker, so new signals and reviewed reports now schedule normal Zapier notifications.

If the saved key or hook is missing, the launcher asks for it with hidden input and holds it only in the process environment for this session. This also lets you operate without storing provider credentials in `.env`. Never paste secrets into chat. If an editor repeatedly restores an older blank file, close other `.env` tabs before saving; the project's setup command uses exclusive creation and preserves an existing file.

You can protect a correctly saved `.env` with `(Get-Item -LiteralPath '.env').IsReadOnly=$true`; the app can still read it. Before intentionally rotating a credential, unlock it with `(Get-Item -LiteralPath '.env').IsReadOnly=$false`, make your changes locally, and lock it again. Model and public-URL launcher options do not require unlocking the file. The attempted handoff lock was not applied because the terminal still saw empty values despite editor-save confirmations. The already-running review API retained its working configuration. Use the launcher's hidden prompts if that editor/file synchronization issue persists.

Open the **public HTTPS address**, pass the ngrok interstitial if shown, and sign in using `ADMIN_PASSWORD` from local `.env`. Use the HTTPS page for reviews; secure cookies are intentionally not sent to an HTTP localhost page in this mode. Keep both terminals open. Ctrl+C in the app terminal stops its worker; Ctrl+C in the ngrok terminal closes the tunnel.

## 4. Create the inbound RSS Zap

Create a separate Zap named `Linear RSS to SignalBrief`:

| Setting | Value |
| --- | --- |
| Trigger app/event | RSS by Zapier → New Item in Feed |
| Feed URL | `https://linear.app/rss/changelog.xml` |
| Action app/event | Webhooks by Zapier → POST |
| URL | `https://YOUR-ASSIGNED-DOMAIN.ngrok-free.app/events` |
| Payload type | JSON |
| Header | `X-API-Key`: your local `WEBHOOK_API_KEY` |
| Header | `ngrok-skip-browser-warning`: `1` |
| Data `event_id` | Prefix `linear:` plus the mapped feed GUID |
| Data `competitor` | `Linear` |
| Data `title` | Mapped feed title |
| Data `source_url` | Mapped feed link |

The actual feed was fetched successfully during setup preparation. Its current GUID is a normal Linear URL accepted by the application's event-ID character rules. If using another feed, normalize GUIDs containing unsupported characters and keep them stable. Leave `published_at` out rather than guessing it. Do not wrap the JSON object in a list, and do not enable nested wrapping/unflattening. The endpoint accepts one event object.

Click **Test action** once. A successful first call returns HTTP 202 and `run_id`. Repeating the identical payload returns HTTP 200 with `created: false`. Inspect the new signal in the public dashboard and then publish the Zap. Polling cadence and publication features depend on your Zapier plan.

## 5. Check the full working flow

1. The RSS test creates a run in the dashboard.
2. The worker stores actual sources, CrewAI output and AutoGen messages.
3. The Slack channel receives `review_requested` with a working public review link.
4. You inspect the current report and approve it.
5. Slack receives `approved_report`. Check Zap History if the final action fails.

HTTP 200 from the outbound Catch Hook is only its acceptance receipt. The operator has observed both the review request and approved report from a real RSS sample in Slack with public links and confirmed that the inbound Zap is published and on. Continued polling depends on the operator's Zapier plan and the app/ngrok sessions remaining available. The saved initial live report was manually approved; its earlier test review notification was suppressed so startup did not post an obsolete localhost link.

## Optional: continuous operation on a server

The free tunnel route depends on your laptop. For continuous operation, use one paid Linux server with Docker Compose and a domain whose DNS points to that server. Start with 2 GB RAM as a practical initial allocation and inspect memory usage under your workload; this is a sizing suggestion, not a measured capacity guarantee. Costs depend on the provider.

1. Put the source in your own GitHub repository, keeping `.env`, `data/` and `.venv/` excluded. Clone it on the server.
2. Install Docker with its [official instructions](https://docs.docker.com/engine/install/ubuntu/).
3. Transfer `.env` securely to the server separately and restrict it to the operator account (`chmod 600 .env`). Do not put credentials in GitHub. Keep the configured Groq key and actual Zapier Catch Hook.
4. Point a domain's A record to the server. Allow inbound ports 80 and 443 for certificate issuance and HTTPS. The API itself stays bound to host loopback.
5. From the project directory on the server, run:

```bash
export SIGNALBRIEF_DOMAIN=your.real.domain
export SIGNALBRIEF_MODEL=openai/gpt-oss-120b
docker compose -f compose.yaml -f compose.hosted.yaml up -d --build
```

The included Caddy proxy forwards HTTPS to the API, while API and worker share one persistent SQLite volume. Caddy automatically manages certificates when the domain and reachability requirements are satisfied. [Caddy HTTPS documentation](https://caddyserver.com/docs/automatic-https).

Check `https://your.real.domain/health`, sign in, inspect worker health, and change the inbound Zap's endpoint to this domain. The hosted override sets public report links and secure cookies without editing your secrets. Use filesystem backups of the local SQLite volume, keep one host/instance, and update dependencies deliberately. The hosted configuration is prepared and Compose-validated; a public server deployment has not been performed.
