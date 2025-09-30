import pickle
import os
from datetime import datetime

def save_cookies(driver, filename="cookies.pkl"):
    cookies = driver.get_cookies()
    with open(filename, "wb") as f:
        pickle.dump(cookies, f)
    print(f"Cookies saved to {filename}")

def load_cookies(driver, filename="cookies.pkl"):
    if not os.path.exists(filename):
        print("Cookie file not found")
        return False

    with open(filename, "rb") as f:
        cookies = pickle.load(f)

    linkedin_cookies: list[dict] = []
    skipped_domains = 0

    for cookie in cookies:
        domain = (cookie.get("domain") or "").lower()
        if "linkedin.com" not in domain:
            skipped_domains += 1
            continue
        normalized = dict(cookie)
        expiry = normalized.get("expiry")
        if isinstance(expiry, float):
            normalized["expiry"] = int(expiry)
        linkedin_cookies.append(normalized)

    if skipped_domains:
        print(f"Skipped {skipped_domains} non-LinkedIn cookies")

    if not linkedin_cookies:
        print("Cookie file exists but no LinkedIn cookies were found")
        return False

    added = 0
    failed = 0

    for cookie in linkedin_cookies:
        try:
            driver.add_cookie(cookie)
            added += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"Failed to add cookie {cookie.get('name')}: {exc}")

    if failed:
        print(f"{failed} LinkedIn cookies could not be added")

    if added == 0:
        print("No LinkedIn cookies could be loaded")
        return False

    print(f"Cookies loaded ({added} LinkedIn entries)")
    return True
