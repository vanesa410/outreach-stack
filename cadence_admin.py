#!/usr/bin/env python3
"""
Cadence test helpers for Twenty.

    export TWENTY_API_KEY="eyJ..."

    python3 cadence_admin.py status                 # how many ACTIVE / paused
    python3 cadence_admin.py add-test               # create the test contact (ACTIVE)
    python3 cadence_admin.py pause-others           # pause every ACTIVE contact except the test one
    python3 cadence_admin.py restore                # set all emailed, paused contacts back to ACTIVE

The test contact uses YOUR email so the cadence emails land in your inbox.
"pause" sets cadenceStatus = null (so the workflow's ACTIVE filter skips them);
REPLIED / BOUNCED contacts are never touched. "restore" only re-activates
contacts that have an email and are currently un-set.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE_URL = os.environ.get("TWENTY_BASE_URL", "http://localhost:3100/rest")
API_KEY = os.environ.get("TWENTY_API_KEY", "")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "test@example.com")


def api(method, path, body=None, _tries=6):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(_tries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {API_KEY}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _tries - 1:
                time.sleep(12 * (attempt + 1))
                continue
            return e.code, json.loads(e.read().decode() or "{}")
    return 429, {"messages": ["rate limit"]}


def all_people():
    out, cursor = [], ""
    while True:
        q = "/people?limit=60" + (f"&starting_after={cursor}" if cursor else "")
        _, body = api("GET", q)
        people = (body.get("data") or {}).get("people") or []
        out.extend(people)
        info = body.get("pageInfo") or {}
        if not info.get("hasNextPage") or not people:
            break
        cursor = info.get("endCursor") or ""
    return out


def email_of(p):
    return ((p.get("emails") or {}).get("primaryEmail") or "").strip().lower()


def cmd_status():
    people = all_people()
    from collections import Counter
    c = Counter((p.get("cadenceStatus") or "—") for p in people)
    print(f"total people: {len(people)}")
    for k, v in c.items():
        print(f"  {k}: {v}")


def cmd_add_test():
    people = all_people()
    if any(email_of(p) == TEST_EMAIL for p in people):
        print(f"Test contact <{TEST_EMAIL}> already exists — skipping create.")
        return
    person = {
        "name": {"firstName": "Test", "lastName": "Influencer"},
        "emails": {"primaryEmail": TEST_EMAIL},
        "jobTitle": "Test",
        "fundSize": "50000",
        "timezone": "",          # blank => passes the timezone window any hour
        "cadenceStep": 0,
        "cadenceStatus": "ACTIVE",
    }
    status, body = api("POST", "/people", person)
    if status in (200, 201):
        print(f"Created test contact: Test Influencer <{TEST_EMAIL}> (ACTIVE, step 0)")
    else:
        print(f"ERROR {status}: {body.get('messages', body)}")


def cmd_pause_others():
    people = all_people()
    targets = [p for p in people if p.get("cadenceStatus") == "ACTIVE" and email_of(p) != TEST_EMAIL]
    print(f"Pausing {len(targets)} ACTIVE contacts (keeping <{TEST_EMAIL}>)…")
    n = 0
    for p in targets:
        status, _ = api("PATCH", f"/people/{p['id']}", {"cadenceStatus": None})
        if status in (200, 201):
            n += 1
        time.sleep(0.7)
    print(f"Paused {n}. Run 'restore' later to re-activate them.")


def cmd_restore():
    people = all_people()
    targets = [p for p in people if email_of(p) and not p.get("cadenceStatus")]
    print(f"Re-activating {len(targets)} paused, emailed contacts…")
    n = 0
    for p in targets:
        status, _ = api("PATCH", f"/people/{p['id']}", {"cadenceStatus": "ACTIVE"})
        if status in (200, 201):
            n += 1
        time.sleep(0.7)
    print(f"Restored {n} to ACTIVE.")


def main():
    if not API_KEY:
        sys.exit("ERROR: set TWENTY_API_KEY env var first.")
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["status", "add-test", "pause-others", "restore"])
    args = ap.parse_args()
    {
        "status": cmd_status,
        "add-test": cmd_add_test,
        "pause-others": cmd_pause_others,
        "restore": cmd_restore,
    }[args.command]()


if __name__ == "__main__":
    main()
