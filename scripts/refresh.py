#!/usr/bin/env python3
"""Weekly rate-page watcher for Bulk Board.

For every buyer in data/buyers.json it downloads the store's rate page, pulls out every
money amount in the visible text ("$6.00", "8¢", "C$10") and compares that list with the
one saved last time in data/watch.json.

  * same amounts      -> the prices still stand; `last_confirmed` becomes today
  * different amounts -> `changed_on` is set and the site shows "page changed" until a
                         person re-checks the store and runs `--accept <id>`
  * download failed   -> `fetch_error` is recorded; nothing else changes

Comparing only the money amounts means a redesigned footer or a new blog post doesn't
raise a false alarm, while any price edit does.

Also refreshes data/fx.json (USD value of CAD/GBP/EUR/AUD) from the ECB via frankfurter.app.

Usage:
  scripts/refresh.py                 check every page
  scripts/refresh.py --only metatcg  check one buyer
  scripts/refresh.py --accept ID     after re-verifying a changed store: adopt its new prices as the baseline
  scripts/refresh.py --baseline      first run: record today's amounts for every page without flagging
Writes a Markdown summary of changes to --report (default: none).
"""
import argparse
import datetime as dt
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUYERS = ROOT / "data" / "buyers.json"
WATCH = ROOT / "data" / "watch.json"
FX = ROOT / "data" / "fx.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) BulkBoard/1.0 (+https://github.com/holdTheDoorHoid/bulk-board; weekly rate check)"
TODAY = dt.date.today().isoformat()

MONEY = re.compile(
    r"(?P<sym>US\$|CA?\$|AU?\$|NZ\$|\$|£|€)\s?(?P<a>\d{1,5}(?:,\d{3})*(?:\.\d{1,3})?)"
    r"|(?P<b>\d{1,3}(?:\.\d{1,2})?)\s?(?:¢|cents?\b)",
    re.I,
)


class TextOnly(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.out.append(data)


def visible_text(raw: str) -> str:
    p = TextOnly()
    p.feed(raw)
    return re.sub(r"\s+", " ", " ".join(p.out))


def amounts(text: str) -> list:
    found = []
    for m in MONEY.finditer(text):
        if m.group("a"):
            sym = m.group("sym").upper().replace("US$", "$").replace("CA$", "C$").replace("AU$", "A$")
            val = float(m.group("a").replace(",", ""))
            found.append(f"{sym}{val:.2f}")
        else:
            found.append(f"{float(m.group('b')):g}¢")
    return sorted(found)


JSON_PRICE = re.compile(r'"[A-Za-z_]*(?:price|rate|amount|cost|value|offer)[A-Za-z_]*"\s*:\s*"?(\d+(?:\.\d+)?)', re.I)


def json_amounts(raw: str) -> list:
    """Price-like numbers in a JSON feed (for stores whose rates live in a data file, e.g. Star City Games)."""
    return sorted(f"{float(v):.4f}" for v in JSON_PRICE.findall(raw))


def fetch(url: str) -> str:
    """Download a page, waiting and retrying when a host says "too many requests" (Shopify throttles
    GitHub's shared runners)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(min(int(wait) if wait and wait.isdigit() else 30 * (attempt + 1), 90))


def numeric(a: str) -> float:
    return float(re.sub(r"[^\d.]", "", a) or 0)


def real_changes(old: list, new: list) -> dict:
    """The price differences that matter: amounts that only drifted by under 1% (live totals,
    converted currencies) are paired off and ignored."""
    d = diff(old, new)
    added, removed = list(d["added"]), list(d["removed"])
    for r in list(removed):
        rv = numeric(r)
        for a in added:
            av = numeric(a)
            if rv and abs(av - rv) / rv < 0.01:
                removed.remove(r)
                added.remove(a)
                break
    return {"added": added, "removed": removed}


def diff(old: list, new: list) -> dict:
    o, n = Counter(old), Counter(new)
    return {"added": sorted((n - o).elements()), "removed": sorted((o - n).elements())}


def refresh_fx(report: list) -> None:
    try:
        req = urllib.request.Request("https://api.frankfurter.dev/v1/latest?base=USD&symbols=CAD,GBP,EUR,AUD,NZD,JPY", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        rates = {k: round(1 / v, 6) for k, v in data["rates"].items() if v}
        FX.write_text(json.dumps({"_about": "US dollars per one unit of each currency (ECB reference rates via frankfurter.app).", "date": data.get("date"), "rates": rates}, indent=2) + "\n")
    except Exception as e:  # keep last week's rates
        report.append(f"- Currency rates not refreshed: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--accept", action="append", default=[])
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--report")
    ap.add_argument("--no-fx", action="store_true")
    args = ap.parse_args()

    buyers = json.loads(BUYERS.read_text())["buyers"]
    watch = json.loads(WATCH.read_text()) if WATCH.exists() else {}
    w_all = watch.setdefault("buyers", {})
    changed, failed, confirmed = [], [], 0
    report = []

    for b in buyers:
        bid = b["id"]
        w = w_all.setdefault(bid, {})
        if args.accept and bid not in args.accept:
            continue
        if args.only and bid != args.only:
            continue
        if b.get("status") == "closed" or not b.get("rates_url"):
            continue
        if b.get("platform"):  # marketplace buyers are refreshed from the marketplace's data (fetch_tcgbulk.py)
            w.update({"mode": "api", "last_confirmed": b.get("checked_on")})
            continue
        if w.get("mode") == "manual" and not args.accept:
            continue
        try:
            url = b.get("watch_url") or b["rates_url"]
            raw = fetch(url)
            got = json_amounts(raw) if raw.lstrip()[:1] in "[{" else amounts(visible_text(raw))
            w.pop("fetch_error", None)
        except Exception as e:
            w["fetch_error"] = f"{TODAY}: {type(e).__name__}: {str(e)[:120]}"
            failed.append(b)
            time.sleep(1)
            continue
        time.sleep(3)  # be polite; many of these shops share Shopify's rate limits
        if not got:
            w["fetch_error"] = f"{TODAY}: no prices visible without a full browser"
            failed.append(b)
            continue
        if args.baseline or bid in args.accept or "fingerprint" not in w:
            w.update({"fingerprint": got, "last_confirmed": TODAY})
            for k in ("changed_on", "diff", "new_fingerprint"):
                w.pop(k, None)
            confirmed += 1
        elif got == w["fingerprint"] or not any(real_changes(w["fingerprint"], got).values()):
            w["fingerprint"] = got  # identical, or only drifted by pennies
            w["last_confirmed"] = TODAY
            for k in ("changed_on", "diff", "new_fingerprint"):
                w.pop(k, None)
            confirmed += 1
        else:
            if got != w.get("new_fingerprint"):
                w["changed_on"] = TODAY
            w["new_fingerprint"] = got
            w["diff"] = real_changes(w["fingerprint"], got)
            changed.append(b)

    watch["checked"] = TODAY
    WATCH.write_text(json.dumps(watch, indent=1, ensure_ascii=False) + "\n")
    if not args.no_fx and not args.only and not args.accept:
        refresh_fx(report)

    lines = [f"Weekly rate check {TODAY}: {confirmed} pages unchanged, {len(changed)} changed, {len(failed)} could not be read."]
    if changed:
        lines.append("\n### Rate pages that changed\nRe-check each store, update `data/buyers.json`, then run `scripts/refresh.py --accept <id>`.\n")
        for b in changed:
            d = w_all[b["id"]]["diff"]
            lines.append(f"- **{b['name']}** (`{b['id']}`) {b['rates_url']}\n  - new amounts: {', '.join(d['added']) or 'none'}\n  - gone: {', '.join(d['removed']) or 'none'}")
    if failed:
        lines.append("\n### Could not read\n")
        for b in failed:
            lines.append(f"- {b['name']} (`{b['id']}`): {w_all[b['id']].get('fetch_error')}")
    lines += report
    text = "\n".join(lines) + "\n"
    print(text)
    if args.report:
        Path(args.report).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
