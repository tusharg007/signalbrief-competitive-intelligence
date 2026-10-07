# Connect real Zapier workflows

The backend must be reachable over public HTTPS for the inbound Zap. An outbound Catch Hook alone does not make a localhost API reachable. This repository includes the running application and webhook contracts; account-owned Zaps must be configured in the authenticated Zapier workspace.

## Zap 1: RSS → SignalBrief

1. Trigger: **RSS by Zapier → New Item in Feed**. Use the actual competitor's official feed, and test it with a genuine entry. Verify that the source URL hostname is registered in `competitors.json`.
2. Optional Filter: continue only for the relevant product or pricing topic.
3. Action: **Webhooks by Zapier → Custom Request**.
4. Method: `POST`; URL: `https://YOUR_PUBLIC_HOST/events`.
5. Headers: `Content-Type: application/json` and `X-API-Key: the WEBHOOK_API_KEY from your local environment`.
6. Send the following JSON with mapped RSS values. Leave `published_at` null if the feed has no trustworthy timestamp.

```json
{
  "event_id": "linear-feed-STABLE-RSS-GUID",
  "competitor": "Linear",
  "title": "Mapped RSS item title",
  "source_url": "https://linear.app/changelog/a-real-entry",
  "published_at": null
}
```

Use a stable GUID, not the Zap's execution timestamp. The permitted event-ID characters are letters, digits, `_`, `.`, `:`, `/`, and `-`; normalize feed GUIDs if necessary. The same ID and payload returns `created: false`; reuse with different content returns HTTP 409. A new run returns HTTP 202 with `run_id`.

Do not send an AI-generated summary as the source. SignalBrief fetches the actual URL and preserves its readable text. A feed redirect to an unregistered hostname fails explicitly.

## Zap 2: SignalBrief → Slack

1. Trigger: **Webhooks by Zapier → Catch Hook**.
2. Copy its actual URL into local `ZAPIER_HOOK_URL`; restart the worker after changing environment values.
3. For deduplication, use **Storage by Zapier** to look up `delivery_id`. If already present, stop. Store the ID after the Slack action succeeds. This reduces duplicates but does not provide a transaction across Storage and Slack; strict exactly-once posting needs a downstream service with atomic idempotency support.
4. Action: **Slack → Send Channel Message**. Connect your own account and select the intended channel.
5. Map a message such as:

```text
{{title}}
Competitor: {{competitor}} · Version: {{version}}
{{message}}
Review: {{review_url}}
Report: {{report_url}}
Delivery: {{delivery_id}}
```

`review_requested` events contain the title, competitor, version and authenticated review link. They contain no strategic report text. `approved_report` events contain the reviewed summary, actions and report link. Use Paths or Filters if the two kinds should go to different channels. A `verification` event is a clearly labelled connectivity check and should reach the chosen test channel.

Example review notification:

```json
{
  "event_type": "review_requested",
  "delivery_id": "stable-generated-delivery-id",
  "run_id": "generated-run-id",
  "version": 1,
  "competitor": "Linear",
  "title": "A source-backed launch brief",
  "review_url": "https://YOUR_PUBLIC_HOST/?run=generated-run-id",
  "message": "A new brief is ready. Open the review dashboard to approve, reject, or revise."
}
```

Example approved notification:

```json
{
  "event_type": "approved_report",
  "delivery_id": "stable-generated-delivery-id",
  "run_id": "generated-run-id",
  "version": 1,
  "competitor": "Linear",
  "title": "A source-backed launch brief",
  "summary": "The human-reviewed strategic interpretation.",
  "message": "The human-reviewed strategic interpretation.",
  "report_url": "https://YOUR_PUBLIC_HOST/?run=generated-run-id",
  "actions": []
}
```

The examples document the contract; they are not runtime seeded reports.

## Approval

Slack links open the authenticated dashboard. Approve/reject/revise use session authentication, CSRF protection and an explicit report version. Native Slack interaction callbacks and unauthenticated approval URLs are not used.

## Verify the complete flow

1. Start the API and worker with a saved model key, hook URL and public base URL.
2. Test Zap 1 with an actual feed item. Confirm the returned run appears in the dashboard.
3. Inspect fetched evidence and both framework transcripts.
4. Confirm a review notification appears in Zap History and Slack.
5. Approve the current version in the dashboard. Check the approved delivery row and the final Slack message.
6. Replay the same feed payload and confirm no duplicate run. Reject a separate run and verify no approved report is emitted.

A Catch Hook HTTP 200 confirms acceptance only. If the final Slack action fails after the hook accepts, the backend cannot observe that failure without a separate Zapier completion callback. Inspect Zap History and replay failed Zap runs there. Backend retries apply to the Catch Hook HTTP exchange.

## Local verification without deploying

The dashboard's New Signal form exercises the same validated ingestion service. `scripts/live_verify.py` exercises the actual collector and models while saving an unapproved draft. `scripts/verify_delivery.py` sends one explicit connectivity notification and saves the HTTP receipt. These checks do not verify that a public inbound Zap is configured, nor do they independently confirm the final Slack action.

Official references: [Catch Hook triggers](https://help.zapier.com/hc/en-us/articles/8496288690317-Trigger-Zap-workflows-from-webhooks), [Zapier webhooks overview](https://help.zapier.com/hc/en-us/articles/8496061300365-How-to-get-started-with-Webhooks-by-Zapier).
