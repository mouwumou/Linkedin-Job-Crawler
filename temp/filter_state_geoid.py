import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote_plus

import requests
import pickle

STATE_LABELS = {
    "Alabama": "Alabama, United States",
    "Alaska": "Alaska, United States",
    "Arizona": "Arizona, United States",
    "Arkansas": "Arkansas, United States",
    "California": "California, United States",
    "Colorado": "Colorado, United States",
    "Connecticut": "Connecticut, United States",
    "Delaware": "Delaware, United States",
    "District of Columbia": "District of Columbia, United States",
    "Florida": "Florida, United States",
    "Georgia": "Georgia, United States",
    "Hawaii": "Hawaii, United States",
    "Idaho": "Idaho, United States",
    "Illinois": "Illinois, United States",
    "Indiana": "Indiana, United States",
    "Iowa": "Iowa, United States",
    "Kansas": "Kansas, United States",
    "Kentucky": "Kentucky, United States",
    "Louisiana": "Louisiana, United States",
    "Maine": "Maine, United States",
    "Maryland": "Maryland, United States",
    "Massachusetts": "Massachusetts, United States",
    "Michigan": "Michigan, United States",
    "Minnesota": "Minnesota, United States",
    "Mississippi": "Mississippi, United States",
    "Missouri": "Missouri, United States",
    "Montana": "Montana, United States",
    "Nebraska": "Nebraska, United States",
    "Nevada": "Nevada, United States",
    "New Hampshire": "New Hampshire, United States",
    "New Jersey": "New Jersey, United States",
    "New Mexico": "New Mexico, United States",
    "New York": "New York, United States",
    "North Carolina": "North Carolina, United States",
    "North Dakota": "North Dakota, United States",
    "Ohio": "Ohio, United States",
    "Oklahoma": "Oklahoma, United States",
    "Oregon": "Oregon, United States",
    "Pennsylvania": "Pennsylvania, United States",
    "Rhode Island": "Rhode Island, United States",
    "South Carolina": "South Carolina, United States",
    "South Dakota": "South Dakota, United States",
    "Tennessee": "Tennessee, United States",
    "Texas": "Texas, United States",
    "Utah": "Utah, United States",
    "Vermont": "Vermont, United States",
    "Virginia": "Virginia, United States",
    "Washington": "Washington, United States",
    "West Virginia": "West Virginia, United States",
    "Wisconsin": "Wisconsin, United States",
    "Wyoming": "Wyoming, United States",
}

def _resolve_geo_id(session: requests.Session, label: str) -> str:
    url = f"https://www.linkedin.com/jobs/search/?location={quote_plus(label)}"
    resp = session.get(url, allow_redirects=True)
    resp.raise_for_status()
    parsed = urlparse(resp.url)
    geo_id = parse_qs(parsed.query).get("geoId", [None])[0]
    if not geo_id:
        raise ValueError(f"未能在 {resp.url} 中解析 geoId")
    return geo_id

def state_filter(states=None,
                 cache_path=Path("state_geo_cache.json"),
                 cookie_path="cookies.pkl") -> dict[str, dict[str, str]]:
    states = states or STATE_LABELS.keys()
    cached = {}
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())

    session = requests.Session()
    # 把 selenium 登录后保存的 cookie 注入 requests 会话
    with open(cookie_path, "rb") as f:
        cookies = pickle.load(f)
    session.cookies.update(cookies[0])


    result = {}
    dirty = False
    for state in states:
        label = STATE_LABELS[state]
        print(f"解析 {state} 的 geoId... {label}")
        if label not in cached:
            cached[label] = _resolve_geo_id(session, label)
            dirty = True
        result[state] = {"location": label, "geoId": cached[label]}

    if dirty:
        cache_path.write_text(json.dumps(cached, indent=2, ensure_ascii=False))
    return result
