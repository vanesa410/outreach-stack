#!/usr/bin/env python3
"""Enrich existing Twenty People with social URLs, size, niche, channel from the spreadsheets.
Usage: TWENTY_API_KEY=... python3 enrich_twenty.py [--commit]
Matches contacts by full name. Dry-run by default.
"""
import os, sys, json, time, urllib.request, urllib.error
import openpyxl

BASE = os.environ.get("TWENTY_BASE_URL", "http://localhost:3100/rest")
KEY = os.environ.get("TWENTY_API_KEY", "")
COMMIT = "--commit" in sys.argv
FILES = ["contacts.xlsx"]   # your spreadsheet(s) — add more to merge
FOLLOWER_COLS = ["X Followers", "IG Followers", "YT Subscribers", "Telegram Members", "TikTok Followers"]


def api(m, p, b=None, _t=6):
    for a in range(_t):
        r = urllib.request.Request(BASE + p, data=(json.dumps(b).encode() if b is not None else None), method=m)
        r.add_header("Authorization", "Bearer " + KEY); r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=30) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < _t - 1: time.sleep(10 * (a + 1)); continue
            return e.code, json.loads(e.read() or "{}")
    return 429, {}


def num(v):
    if v is None: return 0
    if isinstance(v, (int, float)): return int(v)
    s = str(v).strip().upper().replace(",", "").replace("+", "")
    if not s: return 0
    mult = 1
    if s.endswith("K"): mult, s = 1_000, s[:-1]
    elif s.endswith("M"): mult, s = 1_000_000, s[:-1]
    elif s.endswith("B"): mult, s = 1_000_000_000, s[:-1]
    try: return int(float(s) * mult)
    except ValueError: return 0


def size_bucket(n):
    if n <= 0: return None
    if n < 50_000: return "NANO"
    if n < 250_000: return "MICRO"
    if n < 1_000_000: return "MID"
    if n < 5_000_000: return "MACRO"
    return "MEGA"


def link(url, label):
    url = (url or "").strip()
    return {"primaryLinkUrl": url, "primaryLinkLabel": (label or "").strip()} if url else None


def load_rows():
    merged = {}
    for f in FILES:
        if not os.path.exists(f): continue
        ws = openpyxl.load_workbook(f, read_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        h = {n: i for i, n in enumerate(rows[0])}
        g = lambda r, k: r[h[k]] if k in h and h[k] < len(r) else None
        for r in rows[1:]:
            name = (g(r, "Name") or "").strip()
            if not name: continue
            merged[name.lower()] = {
                "youtube": (g(r, "YouTube URL"), g(r, "YouTube Channel")),
                "instagram": (g(r, "IG URL"), g(r, "IG Handle")),
                "tiktok": (g(r, "TikTok URL"), g(r, "TikTok Handle")),
                "website": (g(r, "Website") or g(r, "Contact Form / Website"), name),
                "niche": g(r, "Niche"),
                "channel": g(r, "Preferred Channel"),
                "size": size_bucket(max((num(g(r, c)) for c in FOLLOWER_COLS), default=0)),
            }
    return merged


def all_people():
    out, cur = [], ""
    while True:
        _, b = api("GET", "/people?limit=60" + (f"&starting_after={cur}" if cur else ""))
        ppl = (b.get("data") or {}).get("people") or []
        out += ppl
        pi = b.get("pageInfo", {})
        if not pi.get("hasNextPage") or not ppl: break
        cur = pi.get("endCursor", "")
    return out


def main():
    if not KEY: sys.exit("set TWENTY_API_KEY")
    rows = load_rows()
    people = all_people()
    print(f"[{'COMMIT' if COMMIT else 'DRY RUN'}] {len(rows)} spreadsheet rows, {len(people)} Twenty contacts\n")
    matched = updated = 0
    for p in people:
        nm = p.get("name") or {}
        full = f"{(nm.get('firstName') or '').strip()} {(nm.get('lastName') or '').strip()}".strip().lower()
        d = rows.get(full)
        if not d: continue
        matched += 1
        body = {}
        for fld, key in [("youtubeUrl", "youtube"), ("instagramUrl", "instagram"), ("tiktokUrl", "tiktok"), ("websiteUrl", "website")]:
            lk = link(*d[key])
            if lk: body[fld] = lk
        if d["niche"]: body["niche"] = str(d["niche"])
        if d["channel"]: body["preferredChannel"] = str(d["channel"])
        if d["size"]: body["size"] = d["size"]
        if not body: continue
        if not COMMIT:
            print(f"  {full:34} {list(body.keys())}  size={d['size']}")
            continue
        s, _ = api("PATCH", f"/people/{p['id']}", body)
        if s in (200, 201): updated += 1; print(f"  updated {full}")
        else: print(f"  ERROR {s} {full}")
        time.sleep(0.35)
    print(f"\nmatched {matched} contacts" + (f", updated {updated}" if COMMIT else " (dry run — add --commit)"))


if __name__ == "__main__":
    main()
