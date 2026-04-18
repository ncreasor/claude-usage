from curl_cffi import requests as curl_requests

API_BASE = "https://claude.ai/api"
HTTP_TIMEOUT_SECONDS = 20


class SubscriptionSource:
    def __init__(self, browser):
        self._browser = browser

    def fetch(self) -> dict:
        cookies = self._browser.read_cookies("claude.ai")
        if "sessionKey" not in cookies:
            raise RuntimeError("sessionKey cookie not found — log into claude.ai in the configured browser")
        org = cookies.get("lastActiveOrg")
        if not org:
            r = curl_requests.get(
                f"{API_BASE}/organizations",
                cookies=cookies,
                impersonate="chrome",
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            orgs = r.json()
            if not orgs:
                raise RuntimeError("no organizations returned")
            org = orgs[0]["uuid"]

        r = curl_requests.get(
            f"{API_BASE}/organizations/{org}/usage",
            cookies=cookies,
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        raw = r.json()
        return {
            "session_percent": round(raw.get("five_hour", {}).get("utilization", 0)),
            "session_resets_at": raw.get("five_hour", {}).get("resets_at"),
            "weekly_percent": round(raw.get("seven_day", {}).get("utilization", 0)),
            "weekly_resets_at": raw.get("seven_day", {}).get("resets_at"),
        }
