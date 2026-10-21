#!/usr/bin/env python3
"""Find money-making signals across every game: data/opportunities.json.

Reads data/sealed/<game>.json (pack value) and data/ev/<game>.json (expected value) and lists:
  open        packs worth more opened than sealed (on average, after selling costs)
  buy_to_open sets where buying the cheapest sealed product and selling the cards pays on average
  split       boxes that cost less than their packs would sell for one at a time, after fees
  flips       products selling far above MSRP: worth buying at retail when you can find them
  under_msrp  products selling below MSRP online: cheaper than the shelf price
"""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "data" / "sealed"
EV = ROOT / "data" / "ev"
OUT = ROOT / "data" / "opportunities.json"

SELL_FEE = 0.13     # TCGplayer fees on a sale
PACK_HANDLING = 1.00  # per pack sold singly: mailer and toploader-style protection; the buyer pays postage
BOX_TYPES = {"Booster box", "Half booster box", "Play Booster box", "Collector Booster box", "Set Booster box",
             "Draft Booster box", "Elite Trainer Box", "Booster bundle", "Bundle"}


def main():
    out = {"generated": dt.date.today().isoformat(), "assumptions": {"sell_fee": SELL_FEE, "pack_handling": PACK_HANDLING},
           "open": [], "buy_to_open": [], "split": [], "flips": [], "under_msrp": []}
    recent = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    recent2 = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    for f in sorted(SEALED.glob("*.json")):
        if f.name == "index.json":
            continue
        game = f.stem
        for s in json.loads(f.read_text())["sets"]:
            single = s.get("single_pack") or {}
            for p in s["products"]:
                base = {"game": game, "set": s["name"], "set_id": s["id"], "released": s["released"], "product": p["name"],
                        "type": p["type"], "url": p["url"], "market": p["market"], "presale": p.get("presale", False)}
                kinds = list(p["contents"])
                if p["type"] in BOX_TYPES and len(kinds) == 1 and (p.get("low") or p.get("market")) and single.get(kinds[0]) and not p.get("presale"):
                    buy = p.get("low") or p["market"]          # what the box costs right now
                    if p.get("market") and p.get("low") and p["low"] < 0.6 * p["market"]:
                        buy = p["market"]  # a listing that far below market is usually mislabeled or damaged
                    pack = single[kinds[0]]
                    lows = [x["low"] for x in s["products"] if x["contents"] == {kinds[0]: 1} and x.get("low")
                            and not any(w in x["name"].lower() for w in ("blister", "sleeved", "art bundle"))]
                    sell = min([pack] + lows)                  # you compete with the cheapest listing
                    net = sell * (1 - SELL_FEE) - PACK_HANDLING
                    profit = p["packs"] * net - buy
                    if profit > 0:
                        out["split"].append({**base, "packs": p["packs"], "box_cost": buy, "pack_price": round(sell, 2),
                                             "per_pack": round(buy / p["packs"], 2), "profit": round(profit, 2),
                                             "margin": round(profit / buy, 3),
                                             "thin": sell > 2 * buy / p["packs"]})
                if p.get("msrp") and p.get("market") and "case" not in p["type"]:
                    r = p["market"] / p["msrp"]
                    row = {**base, "msrp": p["msrp"], "ratio": round(r, 2)}
                    if r >= 1.5 and s["released"] >= recent:
                        out["flips"].append(row)       # in print: worth buying at retail when you find it
                    elif r <= 0.9 and not p.get("presale") and s["released"] >= recent2:
                        out["under_msrp"].append(row)
    for f in sorted(EV.glob("*.json")):
        if f.name == "index.json":
            continue
        game = f.stem
        for e in json.loads(f.read_text())["sets"]:
            base = {"game": game, "set": e["name"], "set_id": e["id"], "kind": e["kind"], "released": e["released"],
                    "ev_sold": e["ev_sold"], "ev_market": e["ev_market"], "median_sold": e["median_sold"],
                    "confidence": e.get("confidence")}
            if e.get("check"):
                out["suspect"] = out.get("suspect", 0) + 1
                continue  # too good on thin data: shown on Open or sell with a warning, not listed here
            base["lottery"] = e.get("top_card_share", 0) >= 0.4
            base["top_card"] = e.get("top_card")
            if e.get("ratio_pack") and e["ratio_pack"] >= 1.1:
                out["open"].append({**base, "cost": e["pack_price"], "ratio": e["ratio_pack"], "beats": e.get("beats_pack")})
            if e.get("ratio_cheapest") and e["ratio_cheapest"] >= 1.1 and e.get("cheapest"):
                out["buy_to_open"].append({**base, "cost": e["cheapest"]["per_pack"], "via": e["cheapest"]["name"],
                                           "url": e["cheapest"]["url"], "ratio": e["ratio_cheapest"], "beats": e.get("beats_cheapest")})
    out["open"].sort(key=lambda r: -r["ratio"])
    out["buy_to_open"].sort(key=lambda r: -r["ratio"])
    out["split"].sort(key=lambda r: -r["margin"])
    out["flips"].sort(key=lambda r: -r["ratio"])
    out["under_msrp"].sort(key=lambda r: r["ratio"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n")
    print(", ".join(f"{k}: {len(v)}" for k, v in out.items() if isinstance(v, list)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
