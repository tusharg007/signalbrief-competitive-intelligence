"""Send exactly one operator-authorized, labelled verification notification."""
import asyncio
import json
import uuid
from pathlib import Path

import httpx

from signalbrief.config import Settings
from signalbrief.delivery import valid_hook


async def main():
    settings = Settings()
    url = settings.zapier_hook_url.get_secret_value()
    if not valid_hook(url):
        raise SystemExit("Save a valid ZAPIER_HOOK_URL in .env")
    payload = {
        "event_type": "verification", "delivery_id": uuid.uuid4().hex,
        "title": "[SignalBrief verification] Live webhook connectivity check",
        "message": "This is the single operator-authorized SignalBrief verification notification. "
                   "It confirms webhook connectivity and does not contain an approved strategic report.",
        "competitor": "Verification", "version": 0,
        "review_url": settings.public_base_url, "report_url": settings.public_base_url,
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        response = await client.post(url, json=payload, headers={"X-SignalBrief-Delivery-ID": payload["delivery_id"]})
    result = {"delivery_id": payload["delivery_id"], "http_status": response.status_code,
              "accepted_by_zapier": 200 <= response.status_code < 300,
              "downstream_slack_delivery": "Verify the final action in Zap History", "notifications_sent": 1}
    Path("data").mkdir(exist_ok=True)
    Path("data/zapier-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["accepted_by_zapier"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
