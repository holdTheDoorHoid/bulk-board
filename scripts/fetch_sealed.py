#!/usr/bin/env python3
"""Download sealed-product prices (booster boxes, ETBs, bundles, blisters...) from TCGCSV.

TCGCSV (tcgcsv.com) republishes TCGplayer's catalog and daily prices as plain JSON. Its usage
guidelines: sync at most once a day, send a descriptive User-Agent, pause ~100 ms between
requests, stay well under 10,000 requests a day. A full run here is about 1,000 requests.

Writes cache/sealed_raw.json: every sealed product, plus (for sets sold in booster packs) every
card's rarity and price so scripts/build_ev.py can work out what a pack is worth on average.
scripts/build_sealed.py turns the sealed products into data/sealed/<game>.json.

  python3 scripts/fetch_sealed.py [--games pokemon,mtg] [--booster-sets-only]
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cache" / "sealed_raw.json"
BASE = "https://tcgcsv.com/tcgplayer"
UA = "BulkBoard/1.0 (+https://github.com/holdTheDoorHoid/bulk-board; daily sealed-price sync)"

# game id -> (TCGplayer category id, earliest set release to include)
GAMES = {
    "pokemon": (3, "2020-01-01"),
    "mtg": (1, "2020-01-01"),
    "yugioh": (2, "2021-01-01"),
    "lorcana": (71, "2023-01-01"),
    "onepiece": (68, "2022-01-01"),
    "swu": (79, "2024-01-01"),
    "riftbound": (89, "2025-01-01"),
    "fab": (62, "2022-01-01"),
    "digimon": (63, "2022-01-01"),
    "dbs": (80, "2024-01-01"),
    "gundam": (86, "2025-01-01"),
    "unionarena": (81, "2024-01-01"),
    "weiss": (20, "2023-01-01"),
}


def get(path):
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
        finally:
            time.sleep(0.15)


def text_of(ext):
    t = ext.get("CardText") or ext.get("Description") or ""
    t = re.sub(r"<br\s*/?>|</li>|</p>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", html.unescape(t)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=",".join(GAMES))
    ap.add_argument("--booster-sets-only", action="store_true",
                    help="skip sets whose cached products include no booster pack (saves requests)")
    args = ap.parse_args()
    today = dt.date.today()
    horizon = (today + dt.timedelta(days=120)).isoformat()
    old = json.loads(OUT.read_text()) if OUT.exists() else {"games": {}}
    out = {"fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "games": dict(old.get("games", {}))}
    try:
        with urllib.request.urlopen(urllib.request.Request("https://tcgcsv.com/last-updated.txt", headers={"User-Agent": UA}), timeout=30) as r:
            out["prices_as_of"] = r.read().decode().strip()
    except Exception:
        pass
    n_req = 0
    for game in args.games.split(","):
        cat, since = GAMES[game]
        groups = get(f"{cat}/groups")["results"]
        n_req += 1
        sets = []
        cached = {s["id"]: s for s in (old.get("games", {}).get(game) or {}).get("sets", [])}
        for g in groups:
            rel = (g.get("publishedOn") or "")[:10]
            if g.get("isSupplemental") or not rel or rel < since or rel > horizon:
                continue
            if args.booster_sets_only and g["groupId"] in cached and not any(
                    re.search(r"booster", p["name"], re.I) for p in cached[g["groupId"]]["products"]):
                continue
            products = get(f"{cat}/{g['groupId']}/products")["results"]
            prices = get(f"{cat}/{g['groupId']}/prices")["results"]
            n_req += 2
            pm = {}
            for p in prices:
                pm.setdefault(p["productId"], []).append(p)
            sealed, cards = [], []
            for p in products:
                ext = {e["name"]: e["value"] for e in p.get("extendedData") or []}
                if "Number" in ext or "Rarity" in ext:
                    fin = {x["subTypeName"]: [x.get("marketPrice"), x.get("lowPrice")] for x in pm.get(p["productId"], [])}
                    if fin:
                        cards.append([p["productId"], p["name"], ext.get("Number"), ext.get("Rarity"), fin])
                    continue
                pr = next((x for x in pm.get(p["productId"], []) if x.get("subTypeName") in (None, "Normal")), None) \
                    or (pm.get(p["productId"]) or [None])[0]
                sealed.append({
                    "id": p["productId"], "name": p["name"], "url": p.get("url"),
                    "image": p.get("imageUrl"),
                    "presale": (p.get("presaleInfo") or {}).get("isPresale") or False,
                    "market": pr and pr.get("marketPrice"), "low": pr and pr.get("lowPrice"),
                    "text": text_of(ext)[:1500],
                })
            if sealed:
                has_booster = any(re.search(r"booster", x["name"], re.I) for x in sealed)
                sets.append({"id": g["groupId"], "name": g["name"], "code": g.get("abbreviation"),
                             "released": rel, "products": sealed, "cards": cards if has_booster else []})
        out["games"][game] = {"category": cat, "sets": sorted(sets, key=lambda s: s["released"], reverse=True)}
        print(f"{game}: {len(sets)} sets with sealed products, {sum(len(s['products']) for s in sets)} products", flush=True)
    out["requests"] = n_req
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False) + "\n")
    print(f"{n_req} requests; prices as of {out.get('prices_as_of')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
