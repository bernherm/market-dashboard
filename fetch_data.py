#!/usr/bin/env python3
"""
Pulls corn, wheat, soybean (Yahoo Finance, CBOT futures) and the herbicide
cost index (FRED PCU32533253), and writes them to data.json.

Runs server-side (e.g. in a GitHub Action), so none of this is subject to
browser CORS restrictions — it just talks to the APIs directly.

Requires the FRED_API_KEY environment variable to be set.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_yahoo(symbol):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range=5y&interval=1d"
    )
    data = fetch_json(url)
    result = data["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    closes = result["indicators"]["quote"][0].get("close", [])
    points = []
    for t, c in zip(timestamps, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        points.append({"date": d, "value": round(float(c), 4)})
    return points


def fetch_fred(series_id):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY is not set")
    start = (datetime.now(timezone.utc) - timedelta(days=5 * 365 + 60)).strftime("%Y-%m-%d")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
        f"&sort_order=asc&observation_start={start}"
    )
    data = fetch_json(url)
    points = []
    for o in data.get("observations", []):
        if o.get("value") == ".":
            continue
        points.append({"date": o["date"], "value": float(o["value"])})
    return points


def main():
    series = {}
    errors = {}

    jobs = {
        "corn": lambda: fetch_yahoo("ZC=F"),
        "wheat": lambda: fetch_yahoo("ZW=F"),
        "soybean": lambda: fetch_yahoo("ZS=F"),
        "herbicide": lambda: fetch_fred("PCU32533253"),
    }

    for key, job in jobs.items():
        try:
            series[key] = job()
        except Exception as e:  # noqa: BLE001 - want to keep going on partial failure
            errors[key] = str(e)
            print(f"WARNING: failed to fetch {key}: {e}")

    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "series": series,
    }
    if errors:
        out["errors"] = errors

    with open("data.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote data.json with {len(series)} series" + (f", {len(errors)} errors" if errors else ""))

    # Fail the workflow only if EVERY series failed — a partial update still
    # keeps yesterday's good data for whichever series broke.
    if not series:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
