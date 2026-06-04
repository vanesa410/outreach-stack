#!/usr/bin/env python3
"""
Provision all custom fields on the Twenty **Person** object that the n8n outreach
workflow depends on. Idempotent — safe to re-run (existing fields are skipped).

Usage:
    export TWENTY_API_KEY="eyJ..."          # Twenty → Settings → Developers → API keys
    # export TWENTY_BASE_URL="http://localhost:3100/rest"   # default
    python3 setup_twenty_fields.py
"""
import os, sys, json, urllib.request, urllib.error

BASE = os.environ.get("TWENTY_BASE_URL", "http://localhost:3100/rest")
KEY = os.environ.get("TWENTY_API_KEY", "")


def api(method, path, body=None):
    r = urllib.request.Request(BASE + path,
                               data=(json.dumps(body).encode() if body is not None else None),
                               method=method)
    r.add_header("Authorization", "Bearer " + KEY)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "{}")


def person_object_id():
    cur = ""
    while True:
        s, d = api("GET", "/metadata/objects?limit=100" + (f"&starting_after={cur}" if cur else ""))
        data = d.get("data", [])
        objs = data if isinstance(data, list) else data.get("objects", [])
        for o in objs:
            if o.get("nameSingular") == "person":
                return o["id"]
        pi = d.get("pageInfo", {})
        if not pi.get("hasNextPage") or not objs:
            return None
        cur = pi.get("endCursor", "")


# stage = the Kanban pipeline. Two "lead" states: awaiting approval / awaiting client reply.
STAGE_OPTS = [
    {"label": "Cold lead",                 "value": "COLD_LEAD",    "color": "gray",   "position": 0},
    {"label": "Email 1 sent",              "value": "EMAIL_1_SENT", "color": "yellow", "position": 1},
    {"label": "Email 2 sent",              "value": "EMAIL_2_SENT", "color": "orange", "position": 2},
    {"label": "Lead · awaiting my approval","value": "LEAD",        "color": "green",  "position": 3},
    {"label": "Lead · awaiting client reply","value": "NEGOTIATION","color": "sky",    "position": 4},
    {"label": "Deal",                      "value": "DEAL",         "color": "purple", "position": 5},
    {"label": "Done",                      "value": "DONE",         "color": "red",    "position": 6},
]
SIZE_OPTS = [
    {"label": "Nano (<50K)",       "value": "NANO",  "color": "gray",   "position": 0},
    {"label": "Micro (50K-250K)",  "value": "MICRO", "color": "blue",   "position": 1},
    {"label": "Mid (250K-1M)",     "value": "MID",   "color": "green",  "position": 2},
    {"label": "Macro (1M-5M)",     "value": "MACRO", "color": "orange", "position": 3},
    {"label": "Mega (5M+)",        "value": "MEGA",  "color": "red",    "position": 4},
]
CAD_STATUS = [
    {"label": "Active", "value": "ACTIVE", "color": "green", "position": 0},
    {"label": "Replied", "value": "REPLIED", "color": "blue", "position": 1},
    {"label": "Bounced", "value": "BOUNCED", "color": "red", "position": 2},
    {"label": "Done", "value": "DONE", "color": "gray", "position": 3},
]

# (name, label, type, options)
FIELDS = [
    ("stage", "Stage", "SELECT", STAGE_OPTS),
    ("cadenceStep", "Cadence Step", "NUMBER", None),
    ("cadenceStatus", "Cadence Status", "SELECT", CAD_STATUS),   # legacy, kept for import script
    ("lastEmailSent", "Last Email Sent", "DATE", None),
    ("timezone", "Timezone", "TEXT", None),
    ("fundSize", "Size (followers)", "TEXT", None),
    ("replyApproved", "Reply Approved", "BOOLEAN", None),
    ("aiDraftSubject", "AI Draft Subject", "TEXT", None),
    ("aiDraftBody", "AI Draft Body", "TEXT", None),
    ("dealPriceRequested", "Deal Price Requested", "NUMBER", None),
    ("dealOurOffer", "Deal Our Offer", "NUMBER", None),
    ("dealSummary", "Deal Summary", "TEXT", None),
    ("dealAnalyzed", "Deal Analyzed", "BOOLEAN", None),
    ("youtubeUrl", "YouTube", "LINKS", None),
    ("instagramUrl", "Instagram", "LINKS", None),
    ("tiktokUrl", "TikTok", "LINKS", None),
    ("websiteUrl", "Website", "LINKS", None),
    ("niche", "Niche", "TEXT", None),
    ("preferredChannel", "Preferred Channel", "TEXT", None),
    ("size", "Size", "SELECT", SIZE_OPTS),
]


def main():
    if not KEY:
        sys.exit("ERROR: set TWENTY_API_KEY first.")
    obj = person_object_id()
    if not obj:
        sys.exit("ERROR: could not find the Person object via the metadata API.")
    print(f"Person object: {obj}\nCreating {len(FIELDS)} custom fields...\n")
    created = skipped = 0
    for name, label, ftype, opts in FIELDS:
        spec = {"objectMetadataId": obj, "type": ftype, "name": name, "label": label, "isNullable": True}
        if opts:
            spec["options"] = opts
        if ftype == "BOOLEAN":
            spec["defaultValue"] = False
        s, d = api("POST", "/metadata/fields", spec)
        if s in (200, 201):
            created += 1; print(f"  + {name} ({ftype})")
        else:
            msg = str(d.get("messages", d))
            if "already" in msg.lower() or "duplicate" in msg.lower() or s == 409:
                skipped += 1; print(f"  = {name} already exists")
            else:
                print(f"  ! {name} -> {s}: {msg}")
    print(f"\nDone. created={created} skipped={skipped}")
    print("Next: import the n8n workflow, set your sending email in the code nodes, "
          "and create your Twenty/Gmail credentials. See README.md.")


if __name__ == "__main__":
    main()
