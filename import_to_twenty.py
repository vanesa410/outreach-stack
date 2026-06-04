#!/usr/bin/env python3
"""
Bulk-import influencers.xlsx into Twenty CRM (People) via the REST API.

Maps each row to a Twenty Person and sets the cadence custom fields so the
n8n outreach workflow can pick them up.

Usage:
    export TWENTY_API_KEY="eyJ..."          # Twenty → Settings → Developers → API keys
    python3 import_to_twenty.py             # DRY RUN (prints, writes nothing)
    python3 import_to_twenty.py --commit    # actually create the contacts
    python3 import_to_twenty.py --commit --file influencers_small.xlsx

Cadence rules:
  - Contacts WITH an email  -> cadenceStatus=ACTIVE, cadenceStep=0  (enter outreach)
  - Contacts WITHOUT an email -> imported but no status (skipped by the workflow)
Re-running is safe for emailed contacts: existing primaryEmail matches are skipped.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

import openpyxl

BASE_URL = os.environ.get("TWENTY_BASE_URL", "http://localhost:3100/rest")
API_KEY = os.environ.get("TWENTY_API_KEY", "")


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
                wait = 12 * (attempt + 1)        # back off: Twenty limit is per-60s window
                print(f"    …rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            return e.code, json.loads(e.read().decode() or "{}")
    return 429, {"messages": ["rate limit: gave up"]}


def fetch_existing():
    """Page through all People once; return (emails set, 'first|last' name set)."""
    emails, names = set(), set()
    cursor = ""
    while True:
        q = "/people?limit=60" + (f"&starting_after={cursor}" if cursor else "")
        status, body = api("GET", q)
        data = body.get("data") or {}
        people = data.get("people") or []
        for p in people:
            em = ((p.get("emails") or {}).get("primaryEmail") or "").strip().lower()
            if em:
                emails.add(em)
            nm = p.get("name") or {}
            names.add(f"{(nm.get('firstName') or '').strip().lower()}|{(nm.get('lastName') or '').strip().lower()}")
        info = body.get("pageInfo") or {}
        if not info.get("hasNextPage") or not people:
            break
        cursor = info.get("endCursor") or ""
    return emails, names


def split_name(full):
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def parse_count(val):
    """Parse follower strings like '5.5M', '125K', '2,300', 262000 -> int."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().upper().replace(",", "").replace("+", "")
    if not s:
        return 0
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    elif s.endswith("B"):
        mult, s = 1_000_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


FOLLOWER_COLS = ["X Followers", "IG Followers", "YT Subscribers",
                 "Telegram Members", "TikTok Followers"]


def build_person(row, hdr):
    g = lambda k: row[hdr[k]] if k in hdr and hdr[k] < len(row) else None
    first, last = split_name(g("Name"))
    if not first:
        return None
    if str(g("Tier") or "").strip().upper() == "SKIP":
        return None                                # skip retired/placeholder rows
    email = (g("Email") or "").strip() if g("Email") else ""
    max_followers = max((parse_count(g(c)) for c in FOLLOWER_COLS), default=0)
    person = {
        "name": {"firstName": first, "lastName": last},
        "jobTitle": (g("Type") or "") or "",
        "fundSize": str(max_followers) if max_followers else "",  # exact max reach
        "timezone": "",                            # blank = workflow sends any hour
        "cadenceStep": 0,
    }
    if email:
        person["emails"] = {"primaryEmail": email}
        person["cadenceStatus"] = "ACTIVE"
    x_url = g("X URL")
    x_handle = g("X Handle")
    if x_url:
        person["xLink"] = {"primaryLinkUrl": x_url, "primaryLinkLabel": x_handle or ""}
    return person, email


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="actually create contacts")
    ap.add_argument("--file", default="influencers.xlsx")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit("ERROR: set TWENTY_API_KEY env var first.")

    wb = openpyxl.load_workbook(args.file, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = {name: i for i, name in enumerate(rows[0])}

    mode = "COMMIT" if args.commit else "DRY RUN"
    print(f"[{mode}] {args.file}: {len(rows)-1} rows -> {BASE_URL}\n")

    # Dedup against what's already in Twenty (safe re-runs for both emailed and
    # email-less contacts). Skipped during dry run to avoid needless calls.
    emails_seen, names_seen = (fetch_existing() if args.commit else (set(), set()))

    created = skipped_dup = no_email = errors = would = 0
    for row in rows[1:]:
        built = build_person(row, hdr)
        if not built:
            continue
        person, email = built
        first = person["name"]["firstName"]
        last = person["name"]["lastName"]
        label = f"{first} {last}".strip()
        em = email.lower()
        name_key = f"{first.strip().lower()}|{last.strip().lower()}"
        tag = "ACTIVE" if person.get("cadenceStatus") == "ACTIVE" else "no-email"
        if not email:
            no_email += 1

        if not args.commit:
            would += 1
            print(f"  [{tag:8}] {label}  <{email or '—'}>  reach={person['fundSize']}")
            continue

        # dedup: by email if present, else by name
        if (em and em in emails_seen) or (not em and name_key in names_seen):
            print(f"  [skip-dup] {label} <{email or '—'}>")
            skipped_dup += 1
            continue

        status, body = api("POST", "/people", person)
        if status in (200, 201):
            created += 1
            if em:
                emails_seen.add(em)
            names_seen.add(name_key)
            print(f"  [created ] {label}  <{email or '—'}>  ({tag})")
        else:
            errors += 1
            print(f"  [ERROR {status}] {label}: {body.get('messages', body)}")
        time.sleep(0.7)   # stay under Twenty's ~100 req / 60s limit

    print()
    if args.commit:
        print(f"Done. created={created} skipped_dup={skipped_dup} errors={errors} (of which no-email so far={no_email})")
    else:
        print(f"Dry run complete. {would} contacts would be imported "
              f"({no_email} without email = imported but not entered into cadence).")
        print("Re-run with --commit to create them.")


if __name__ == "__main__":
    main()
