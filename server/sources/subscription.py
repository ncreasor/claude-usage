from curl_cffi import requests as curl_requests

API_BASE = "https://claude.ai/api"
HTTP_TIMEOUT_SECONDS = 20


class SubscriptionSource:
    def __init__(self, browser):
        self._browser = browser

    def _get_cookies_and_org(self) -> tuple[dict, str]:
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
        return cookies, org

    def fetch(self) -> dict:
        cookies, org = self._get_cookies_and_org()

        r = curl_requests.get(
            f"{API_BASE}/organizations/{org}/usage",
            cookies=cookies,
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        raw = r.json()
        omelette = raw.get("seven_day_omelette") or {}
        extra = raw.get("extra_usage") or {}

        result = {
            "session_percent": round(raw.get("five_hour", {}).get("utilization", 0)),
            "session_resets_at": raw.get("five_hour", {}).get("resets_at"),
            "weekly_percent": round(raw.get("seven_day", {}).get("utilization", 0)),
            "weekly_resets_at": raw.get("seven_day", {}).get("resets_at"),
        }

        if omelette.get("utilization") is not None:
            result["claude_design_percent"] = round(omelette["utilization"])

        result["extra_usage_enabled"] = extra.get("is_enabled", False)
        used = extra.get("used_credits")
        limit = extra.get("monthly_limit")
        util = extra.get("utilization")
        result["extra_usage_percent"] = round(util) if util is not None else None
        result["extra_usage_spent"] = used / 100 if used is not None else None
        result["extra_usage_limit"] = limit / 100 if limit is not None else None

        try:
            cr = curl_requests.get(
                f"{API_BASE}/organizations/{org}/prepaid/credits",
                cookies=cookies,
                impersonate="chrome",
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            cr.raise_for_status()
            result["account_balance"] = cr.json().get("amount", 0) / 100
        except Exception:
            pass

        return result

    def toggle_extra_usage(self, enabled: bool) -> None:
        cookies, org = self._get_cookies_and_org()

        r = curl_requests.get(
            f"{API_BASE}/organizations/{org}/overage_spend_limit",
            cookies=cookies,
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        current = r.json()

        payload = {
            "is_enabled": enabled,
            "monthly_credit_limit": current.get("monthly_credit_limit", 5000),
            "currency": current.get("currency", "USD"),
        }
        r = curl_requests.put(
            f"{API_BASE}/organizations/{org}/overage_spend_limit",
            cookies=cookies,
            impersonate="chrome",
            timeout=HTTP_TIMEOUT_SECONDS,
            json=payload,
        )
        r.raise_for_status()
