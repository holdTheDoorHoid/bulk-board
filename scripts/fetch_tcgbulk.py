#!/usr/bin/env python3
"""Refresh the TCG Bulk marketplace buyers (research/sources/tcgbulk.json).

TCG Bulk (tcgbulk.com) is a marketplace where many small buyers post per-rarity bulk prices.
Its web app reads them from a public, unauthenticated JSON API; this script makes the same
GET requests the app makes, slowly, once a week.

Privacy: many of these buyers are individuals. The API also returns e-mail and shipping
addresses; this script keeps only the display name, country and state/province, and never
writes anything else about the person.

  python3 scripts/fetch_tcgbulk.py            then  python3 scripts/build_data.py
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research" / "sources" / "tcgbulk.json"
KNOWN = ROOT / "research" / "tcgbulk_known.json"
API = "https://api.tcgbulk.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) BulkBoard/1.0 (+https://github.com/holdTheDoorHoid/bulk-board; weekly rate check)"
TODAY = dt.date.today().isoformat()

GAMES = {"Pokemon": "pokemon", "Magic The Gathering": "mtg", "Yu-Gi-Oh": "yugioh", "Disney Lorcana": "lorcana",
         "One Piece": "onepiece", "Flesh and Blood": "fab", "Digimon": "digimon", "Star Wars Unlimited": "swu",
         "Dragonball Super": "dbs", "Weiss Schwarz": "weiss", "Riftbound": "riftbound", "Union Arena": "unionarena",
         "Final Fantasy": "fftcg", "Gundam": "gundam"}
US_STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
             "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
             "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
             "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
             "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
             "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
             "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
             "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
             "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
             "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC"}

SHIPPING = ("Seller pays shipping to the buyer; no prepaid label (TCG Bulk fees page). Optional insurance: 3.5% of "
            "order value, covers up to $200.")
CONDITION = ("Near Mint / Mint only for bulk (TCG Bulk card-condition rules); the buyer may adjust the order for lower "
             "condition, wrong quantity or wrong language.")
SORTING = ("You enter counts per rarity line on the buyer's list; the buyer checks them on arrival. Unsorted cards only "
           "pay if the buyer lists an 'Unsorted Bulk' line.")
PROCESS = ("Free seller account on tcgbulk.com (web or app): pick the buyer, enter quantities, ship, add tracking. "
           "The buyer's card is charged when tracking is entered; PayPal payout after the buyer marks it complete.")


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA, "Origin": "https://app.tcgbulk.com",
                                                      "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    # The public list returns a different subset from one request to the next, so remember every
    # account ever seen and look each one up directly.
    listing, page = [], 1
    while page <= 20:
        batch = get(f"/company/buyers-bulk/?page={page}&limit=100")
        listing += batch or []
        if not batch or len(batch) < 100:
            break
        page += 1
        time.sleep(0.7)
    listed = {x["url"]: x for x in listing}
    known = set(json.loads(KNOWN.read_text())["slugs"]) if KNOWN.exists() else set()
    known |= set(listed)
    KNOWN.write_text(json.dumps({"_about": json.loads(KNOWN.read_text())["_about"] if KNOWN.exists() else "",
                                 "slugs": sorted(known)}, indent=0) + "\n")
    buyers = []
    for slug in sorted(known):
        item = listed.get(slug, {})
        try:
            d = get(f"/company/{slug}")
        except Exception as e:
            print(f"  ! {slug}: {e}", file=sys.stderr)
            continue
        time.sleep(0.7)
        if not d or not d.get("onTheMarket") or d.get("banned") or d.get("closed") or item.get("banned") or item.get("closed"):
            continue
        addr = d.get("shippingAddress") or item.get("shippingAddress") or {}
        country = (addr.get("country") or {}).get("iso2") or ""
        state = addr.get("state") or ""
        region = US_STATES.get(state, state) if country == "US" else state
        cur = ((d.get("region") or {}).get("currency") or {}).get("code") or "USD"
        ship_ok = any(x.get("shippingEnabled") for x in d.get("shippingAddresses") or []) or bool(addr.get("shippingEnabled"))
        drop = bool(d.get("dropOff") and d.get("dropOffEnabled"))
        bud = item.get("budgets") or {}
        stats = d.get("stats") or {}
        rates = []
        for x in d.get("rarities") or []:
            if x.get("deleted"):
                continue
            gr = x["globalRarity"]
            gname = gr["game"]["name"]
            game = GAMES.get(gname, "other")
            lang = (gr.get("language") or {}).get("name") or "English"
            raw = (x.get("name") or gr["name"]).strip()
            notes = []
            if lang != "English":
                notes.append(f"Language: {lang}")
            if x.get("onTheMarket") is False:
                notes.append("paused")
            rates.append({"game": game, "category_raw": raw if game == "pokemon" else f"{gname}: {raw}",
                          "category_std": "", "price": float(x["rate"]), "currency": cur, "unit": "per_card",
                          "payout": "cash", "notes": "; ".join(notes)})
        minsub = d.get("minSubmissionPrice")
        left = bud.get("budget")
        status = "active"
        if left is not None and minsub is not None and left < minsub:
            status = "paused"
        notes = ["Buyer on the TCG Bulk marketplace; prices are the buyer's own, shown publicly on tcgbulk.com. "
                 "Sellers receive 90% after TCG Bulk's 10% service fee."]
        if left is not None:
            notes.append(f"Buyer budget remaining on TCG Bulk: {left} {cur} of {bud.get('budgetLimit') or item.get('monthlyBudgetReset')} monthly cap.")
        if status == "paused":
            notes.append("Remaining budget is below the buyer's minimum submission.")
        if slug not in listed:
            notes.append("Remaining budget unknown (TCG Bulk's buyer list didn't include this buyer when checked).")
        buyers.append({
            "name": d.get("displayName") or d.get("name"),
            "website": f"https://app.tcgbulk.com/buyer/{slug}", "rates_url": f"https://app.tcgbulk.com/buyer/{slug}",
            "country": country, "region": region,
            "mail_in": ship_ok, "in_person": drop,
            "payout_methods": ["paypal"],
            "minimum": f"Buyer minimum submission value: {minsub} {cur} (set by the buyer on TCG Bulk)" if minsub is not None else "",
            "shipping": SHIPPING, "condition_rules": CONDITION, "sorting_rules": SORTING, "process": PROCESS,
            "excluded": "Anything not on the buyer's list; TCG Bulk only shows sellers buyers in their own region.",
            "turnaround": "PayPal payout within about a day of the buyer completing the order.",
            "rates_last_updated": f"live from TCG Bulk on {TODAY} (buyer record updated {(d.get('updatedAt') or '')[:10]})",
            "status": status,
            "reputation": f"{stats.get('submissionsCompleted', 0)} submissions completed, {stats.get('numberOfReviews', 0)} reviews, "
                          f"average {stats.get('averageReview', 0)}/5; on TCG Bulk since {(d.get('createdAt') or '')[:10]}",
            "checked_on": TODAY, "source_type": "marketplace_listing", "notes": " ".join(notes), "rates": rates,
        })
    OUT.write_text(json.dumps({"source": "api.tcgbulk.com (public buyer listings)", "fetched": TODAY, "buyers": buyers},
                              indent=1, ensure_ascii=False) + "\n")
    print(f"TCG Bulk: {len(listing)} buyer accounts listed, {len(buyers)} on the market, "
          f"{sum(len(b['rates']) for b in buyers)} rate lines")


if __name__ == "__main__":
    sys.exit(main())
