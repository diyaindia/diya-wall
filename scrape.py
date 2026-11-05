#!/usr/bin/env python3
"""Collect Light a Diya share links into links.json.

Sources (each one is skipped when its keys are missing):
  GitHub issues   GITHUB_TOKEN + GITHUB_REPOSITORY (set automatically in Actions)
  Reddit          REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET  (free "script" app at reddit.com/prefs/apps)
  X               X_BEARER_TOKEN  (needs an X API plan with recent search)
"""

import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links.json")
KEEP = 600  # newest links kept on the wall
UA = "diya-wall/1.0 (link aggregator)"

# Strict: only this year's campaign share links, in exactly this shape.
CAMPAIGN = os.environ.get("DIYA_CAMPAIGN", "aWPhpVsRkD")
FIND_RE = re.compile(r"(?<![\w.\-@/])https://r\.swiggy\.com/light-diya/([A-Za-z0-9_\-]+)", re.IGNORECASE)
VALID_RE = re.compile(r"https://r\.swiggy\.com/light-diya/" + re.escape(CAMPAIGN) + r"-[A-Za-z0-9]{11}")


def canonical(url):
    """Return the canonical link if url is a valid share link, else None."""
    m = re.fullmatch(r"https://r\.swiggy\.com/light-diya/([A-Za-z0-9_\-]+)", (url or "").strip(), re.IGNORECASE)
    if not m:
        return None
    u = "https://r.swiggy.com/light-diya/" + m.group(1)  # host lowercased, code kept case-sensitive
    return u if VALID_RE.fullmatch(u) else None


def links_in(text):
    out = []
    for m in FIND_RE.finditer(text or ""):
        # the code must end the link: a letter, digit, - or _ right after a valid code means it is longer
        u = canonical("https://r.swiggy.com/light-diya/" + m.group(1))
        if u and u not in out:
            out.append(u)
    return out


def get(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------- sources

def from_github():
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (tok and repo):
        return []
    out, page = [], 1
    while page <= 10:
        items = get(f"https://api.github.com/repos/{repo}/issues?labels=diya-link&state=all&per_page=100&page={page}",
                    {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
        for it in items:
            for l in links_in((it.get("title") or "") + "\n" + (it.get("body") or "")):
                out.append({"url": l, "src": "submitted", "at": it["created_at"].replace("Z", "+00:00"),
                            "ref": it["html_url"]})
        if len(items) < 100:
            break
        page += 1
    return out


def from_form():
    """Links added on the page go to a Google Form; its response sheet is published as CSV."""
    url = os.environ.get("FORM_CSV_URL", "")
    if not url:
        return []
    import csv, io
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    out = []
    for row in list(csv.reader(io.StringIO(text)))[1:]:
        if len(row) < 2:
            continue
        try:  # Sheets writes form timestamps as M/D/YYYY H:MM:SS in the sheet's time zone (set to IST)
            at = datetime.strptime(row[0], "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            at = at.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for l in links_in(row[1]):
            out.append({"url": l, "src": "submitted", "at": at, "ref": ""})
    return out


def from_reddit():
    cid, sec = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and sec):
        return []
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    tok = get("https://www.reddit.com/api/v1/access_token", {"Authorization": f"Basic {basic}"},
              b"grant_type=client_credentials")["access_token"]
    out = []
    for q in ('"r.swiggy.com/light-diya"', '"light-diya" swiggy', "light a diya swiggy"):
        url = "https://oauth.reddit.com/search?" + urllib.parse.urlencode(
            {"q": q, "sort": "new", "t": "week", "limit": 100, "type": "link"})
        d = get(url, {"Authorization": f"Bearer {tok}"})
        for c in d["data"]["children"]:
            p = c["data"]
            for l in links_in(p.get("selftext", "") + "\n" + p.get("url", "") + "\n" + p.get("title", "")):
                out.append({"url": l, "src": "reddit", "at": iso(p["created_utc"]),
                            "ref": "https://www.reddit.com" + p["permalink"]})
            # links people drop in the comments of these threads
            try:
                com = get(f"https://oauth.reddit.com/comments/{p['id']}?limit=200&depth=2",
                          {"Authorization": f"Bearer {tok}"})
                stack = list(com[1]["data"]["children"])
                while stack:
                    k = stack.pop()
                    cd = k.get("data", {})
                    for l in links_in(cd.get("body", "")):
                        out.append({"url": l, "src": "reddit", "at": iso(cd.get("created_utc", p["created_utc"])),
                                    "ref": "https://www.reddit.com" + cd.get("permalink", p["permalink"])})
                    rep = cd.get("replies")
                    if isinstance(rep, dict):
                        stack.extend(rep["data"]["children"])
            except Exception as e:
                print("reddit comments:", e, file=sys.stderr)
        time.sleep(1)
    return out


def from_x():
    tok = os.environ.get("X_BEARER_TOKEN")
    if not tok:
        return []
    url = "https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode({
        "query": 'url:"r.swiggy.com/light-diya" -is:retweet',
        "max_results": 100,
        "tweet.fields": "created_at,entities",
    })
    d = get(url, {"Authorization": f"Bearer {tok}"})
    out = []
    for t in d.get("data", []):
        urls = [u.get("expanded_url", "") for u in t.get("entities", {}).get("urls", [])]
        for l in links_in("\n".join(urls) + "\n" + t.get("text", "")):
            out.append({"url": l, "src": "x", "at": t["created_at"].replace("Z", "+00:00"),
                        "ref": f"https://x.com/i/web/status/{t['id']}"})
    return out


# ------------------------------------------------------------- merge

def key(url):
    return url.split("://", 1)[1].lower().rstrip("/")


def main():
    try:
        old = json.load(open(OUT))["links"]
    except Exception:
        old = []
    old = [dict(l, url=canonical(l["url"])) for l in old if canonical(l["url"])]
    seen = {key(l["url"]): l for l in old}
    for name, fn in (("form", from_form), ("github", from_github), ("reddit", from_reddit), ("x", from_x)):
        try:
            got = fn()
        except Exception as e:  # one source failing must not wipe the wall
            print(f"{name}: {e}", file=sys.stderr)
            continue
        new = 0
        for l in got:
            k = key(l["url"])
            if k not in seen:
                seen[k] = l
                new += 1
            elif l["at"] < seen[k]["at"]:
                seen[k]["at"] = l["at"]  # keep the first time it was posted
        print(f"{name}: {len(got)} found, {new} new")
    links = sorted(seen.values(), key=lambda l: l["at"], reverse=True)[:KEEP]
    body = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "links": links}
    if links != old or not os.path.exists(OUT):
        json.dump(body, open(OUT, "w"), indent=1)
        print(f"wrote {len(links)} links")
    else:
        print("no change")


if __name__ == "__main__":
    main()
