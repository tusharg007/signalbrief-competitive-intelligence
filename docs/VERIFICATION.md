# Verification record

Verified locally on 8 October 2026. This record distinguishes actual external execution from isolated regression tests.

## Actual model execution

Run `1764a413980b4e7aabc2af41f8adfb8c` fetched two public sources:

- [Linear's dated coding-agent announcement](https://linear.app/changelog/2026-09-24-new-controls-for-linear-coding-agent)
- [Linear product features](https://linear.app/features)

The real CrewAI researcher and verifier produced a validated dossier. The real AutoGen strategist, critic and editor produced a validated strategy report through Groq using `openai/gpt-oss-120b`. No canned report, fixture response or mock model was used. The business context in `competitors.json` is synthetic. The operator subsequently approved this report; their 8 October screenshot shows the real brief delivered to Slack with a public report link for this run.

| Recorded measure | Value |
| --- | ---: |
| Frozen sources | 2 |
| Research findings / checked quotes | 6 / 6 |
| CrewAI stage duration | 31.719 seconds |
| CrewAI recorded prompt / completion tokens | 13,394 / 8,422 |
| AutoGen council turns | 3 |
| AutoGen stage duration | 32.171 seconds |
| AutoGen prompt / completion tokens | 7,962 / 4,521 |
| Research-only proposed actions | 3 |
| Post-critique proposed actions | 4 |
| Critic objections recorded | 5 |
| Valid action source IDs / owners / validation steps | 100% in both sets |

These are successful-stage measurements. They exclude earlier failed attempts, queue delay and source-collection latency; they are not a total project token or billing estimate. More actions and objections do not establish better strategy. Quote matching verifies traceability, not factual entailment. The evaluation includes a human-review rubric instead of an invented accuracy score.

### Failures exercised against real services

An oversized source page failed explicitly. CrewAI's provider auto-detection required explicit compatible routing. An unavailable configured Llama model returned HTTP 404. Model quote typography required canonicalizing equivalent punctuation back to a literal source span; substantive missing words still fail validation. A Groq HTTP 429 interrupted the council; bounded per-request pacing allowed the editor to recover. Research checkpoints were reused on subsequent analysis attempts. Nine obsolete verification attempts were cancelled with their evidence and audit records retained.

The configured `.env` was left untouched during final verification. An available model was selected through process environment overrides.

## Actual Zapier request

Exactly one authorized, clearly labelled verification notification was sent to the configured Catch Hook. Zapier returned HTTP **200**. The saved delivery ID is `221fccc5fdd04f90a6a93a81f2c4fbdb`.

This original receipt confirms real outbound webhook connectivity. During account setup, the operator sent a fresh verification request and tested the Slack action. Their screenshots show Slack's `Ok: true` result, the actual mapped verification title/message in `#signalbrief`, and successful publication of **SignalBrief — Review & Report Notifications to Slack**. After starting the application through ngrok and manually approving the saved live report, the operator provided a screenshot of its actual title, strategic summary and public run link in that channel. No draft was automatically approved. A subsequent RSS sample created run `d1434228a9ad4f92acc120d45af1c437`; both its public review request and approved report were observed in Slack. The local delivery records show `review_requested: sent` and `approved_report: sent`, each on one attempt. This verifies the real RSS-sample → research → human approval → Slack loop.

## Local application and packaging

- **46 tests passed**: immutable event deduplication, concurrent claims, lease ownership, checkpoints, version-bound reviews, rejection, revision, cancellation, outbox retry, permanent/temporary provider failures, bounded rate-limit recovery, URL/IP boundaries, quote validation, authentication, CSRF and preservation of an existing credential file.
- Ruff passed. External services are substituted only inside isolated regression tests.
- A real Chrome/Edge browser passed dashboard sign-in, signal dialog, evidence/agent/activity tabs, mobile layout, mobile sign-out and JavaScript error checks. It displayed the actual live report without changing its approval status.
- Authenticated Markdown export of the actual draft returned HTTP 200 and included its execution record.
- Screenshots in `docs/assets/` show the real dashboard and report.
- The Docker image built successfully. Both frameworks imported inside Linux. An isolated API container with synthetic credentials returned HTTP 200 from `/health`. It performed no external calls and was stopped after verification.
- Compose configuration validated. Normal API-plus-worker Compose execution with production credentials was not started during verification.

Credential-free machine records remain under ignored `data/`: `live-verification.json`, `evaluation.json`, `zapier-verification.json`, `ui-verification.json` and `docker-verification.json`. The actual source texts, transcripts, history and draft are in the local SQLite database.

## Account setup and hosting state

The implemented application runs locally with public HTTPS access through an operator-run ngrok tunnel. Screenshots show successful public dashboard login, worker-online status, and the approved real report in Slack. The operator configured **Linear RSS to SignalBrief** and its POST test returned `created: true` for run `d1434228a9ad4f92acc120d45af1c437`. The new run completed and was manually approved; its review request and final report both appeared in Slack with the correct public links. A later Zapier screenshot confirms the inbound Zap is published and on, with a displayed two-minute polling interval. Native Slack button approvals are outside the implemented scope; Slack messages link to the authenticated dashboard. See [ZAPIER.md](ZAPIER.md) for the concrete setup and payload mapping.

The operator completed Slack, tunnel and RSS setup following the walkthrough. [CONNECT_SLACK_AND_GO_LIVE.md](CONNECT_SLACK_AND_GO_LIVE.md) records the setup and flow checks. The advertised Linear RSS feed was separately verified with HTTP 200. An optional Caddy/Compose hosting configuration is included; the later Render + Neon deployment is documented below. The publication screen reports premium-app access during a 14-day Zapier trial, so continued webhook operation depends on retaining an eligible plan afterward.

The operator's latest screenshots show the API running on port **8007**, exposed through ngrok, with the normal worker online. Both the application and tunnel must stay running for this local hosting route. The earlier review preview used port 8008.

An earlier raw-file check found both integration values empty in `.env`, while the already-running API still reported its successfully loaded model/hook configuration. Editor-save confirmations did not change the file observed by the terminal; the source of that synchronization issue was not established. The application does not overwrite existing `.env` files. The Windows launcher accepts hidden session-only credentials, so account setup can proceed without repeatedly editing that file.

## Render + Neon verification — 8 October 2026

The full API and worker were deployed to https://signalbrief-dncb.onrender.com on Render free compute. A dedicated Neon PostgreSQL 17 database stores workflow state. Both approved real runs were imported with source packets, messages, metrics, audits, report versions and completed deliveries. No pending notification was imported or replayed.

Checks against the public deployment returned:

| Check | Observed result |
| --- | --- |
| `/health` and `/ready` | HTTP 200; database ok; worker online |
| `/showcase` and selected published run | HTTP 200 without an operator session |
| `/api/runs` without login | HTTP 401 |
| Administrator login and authenticated run list | HTTP 200 |
| Identical RSS payload posted to `/events` | Existing run ID, `status: duplicate`, `created: false` |
| Unselected/draft showcase boundaries | Covered by regression tests |
| SQLite suite | 49 passed locally |
| PostgreSQL 17 suite | The same 49 tests passed locally |

The operator confirmed the published inbound Zap URL was changed from ngrok to Render. The duplicate cloud probe validates ingress and deduplication without initiating inference or Slack delivery. The gallery's Slack captures document original real deliveries before cloud deployment; they do not claim a fresh cloud model run.

App screenshots are reproduced from the actual deployed read-only workspace using `scripts/capture_proof.cjs`. Zapier and Slack screenshots are unmodified operator captures. Provider token usage and stage durations in the README belong to the original RSS run, not to mocked regression calls. Free Render sleeps on idle; see the deployment guide for operating limits.

### Fresh hosted inference and delivery

With operator authorization, run `357d68840b1a43e0afb44834b1b64c05` executed on Render against the same public Linear evidence. It completed on attempt 1, producing two CrewAI task outputs and three AutoGen messages. Neon stored two sources and nine checked citation excerpts. Research took 33.415 seconds; analysis took 132.1 seconds. The recorded attempt took 187.558 seconds. Groq reported 14,072 research input tokens / 8,716 output tokens and 8,355 analysis input tokens / 4,698 output tokens.

The report remains `awaiting_approval`. Its single `review_requested` outbox delivery is `sent`, attempt 1, proving Zapier accepted the request. Final Slack appearance for this cloud notification is not independently verified. No approval or approved-report delivery was performed by the assistant. The screenshot `cloud-execution.png` was captured through authenticated read-only inspection of the actual new report.
