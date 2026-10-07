"""At-least-once delivery to a configured Zapier Catch Hook."""
from urllib.parse import urlsplit

import httpx

from signalbrief.config import Settings
from signalbrief.store import Store


def valid_hook(url: str) -> bool:
    parts = urlsplit(url)
    try:
        return (parts.scheme == "https" and parts.hostname == "hooks.zapier.com" and
                parts.port in (None, 443) and not parts.username and not parts.password and
                parts.path.startswith("/hooks/catch/") and not parts.fragment and not parts.query)
    except ValueError:
        return False


async def deliver_one(store: Store, settings: Settings, transport=None) -> bool:
    url = settings.zapier_hook_url.get_secret_value()
    configured = bool(url and valid_hook(url))
    item = store.claim_delivery(90, configured)
    if item is None:
        return False
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False,
                                     transport=transport) as client:
            response = await client.post(url, json=item["payload"], headers={
                "X-SignalBrief-Delivery-ID": item["id"], "User-Agent": "SignalBrief/1.0",
            })
        if 200 <= response.status_code < 300:
            # A webhook receipt confirms Zapier acceptance, not successful downstream Slack delivery.
            store.delivery_result(item, "sent", None, {"http_status": response.status_code,
                                                       "accepted_by": "zapier"})
        else:
            retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
            outcome = "pending" if retryable and item["attempts"] < 5 else "failed"
            store.delivery_result(item, outcome, f"Zapier returned HTTP {response.status_code}")
    except httpx.HTTPError:
        outcome = "pending" if item["attempts"] < 5 else "failed"
        store.delivery_result(item, outcome, "Zapier request failed or timed out")
    return True
