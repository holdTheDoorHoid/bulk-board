#!/usr/bin/env python3
"""Expected value of a booster pack, per set: should you open it or sell it sealed?

Inputs
  cache/sealed_raw.json          card prices per set (fetch_sealed.py)
  research/pack_models/*.json    what's in a pack: slots and rarity odds, per game/era/set
  data/sealed/<game>.json        what a pack and a box cost (build_sealed.py)
  data/buyers.json               bulk buy rates, the floor for cards too cheap to sell one by one
Output
  data/ev/<game>.json, data/ev/index.json

Two values per pack:
  market   - every card at its TCGplayer market price
  if sold  - what you'd actually clear: price minus ~13% selling fees and a per-card handling cost,
             but never less than what a bulk buyer pays for that kind of card
Assumes every card of a rarity is equally likely within its slot (standard for EV estimates).
A 5,000-pack simulation gives the spread: the median pack, and how often a pack beats its price.
"""
import datetime as dt
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "cache" / "sealed_raw.json"
MODELS = ROOT / "research" / "pack_models"   # one JSON file per game (format: research/pack_models/README.md)
SEALED = ROOT / "data" / "sealed"
BUYERS = ROOT / "data" / "buyers.json"
OUT = ROOT / "data" / "ev"

SELL_FEE = 0.13        # TCGplayer: 10.75% commission + 2.5% payment processing (Oct 2026)
HANDLING = 0.50        # per card sold singly: share of the $0.30 order fee, sleeve, toploader, envelope
SIMS = 5000
# Card names that are separate printings, not drawn from the normal slots unless a model asks for them.
VARIANT = re.compile(r"\((?:[^)]*Pattern|Jumbo|Prerelease|Staff|Stamped|Code Card|Oversized|Display|Serial|Galaxy Foil|"
                     r"Borderless|Showcase|Extended Art|Retro Frame|Etched|Textured|Surge Foil|Halo Foil|Fracture Foil|"
                     r"Japanese|Alternate Art|Serialized)[^)]*\)", re.I)

# Printings that never come out of a booster pack: tournament prizes, promos, box toppers, event stamps.
NOT_IN_PACKS = re.compile(r"\([^)]*(?:Regionals|Top \d+|Champion|Tournament|Prize|Judge|Winner|Promo|Pre-?release|Dash Pack|"
                          r"Limited Foil|Box Topper|Release Event|Serial|Stamped|Store|Kickoff|Launch|Flagship|Treasure Cup|"
                          r"Sealed Battle|Premium Card|Bonus Pack|Gift|Collector'?s Edition|Regulation Battle|Finalist|"
                          r"Participant|Battle Pack|Exclusive)[^)]*\)", re.I)
# In "plain card" pools, a bracketed tag usually marks a special printing (event, promo, textured, box topper).
# These tags are allowed because they're part of ordinary card names: card numbers, "(X Antibody)", "(Ghetsis)"-style
# trainer names are rare enough in value terms to lose.
ALLOWED_TAG = re.compile(r"[A-Z]{1,5}\d{0,2}[-–]\d{2,3}[a-z]?|\d{2,3}|[A-Z]{2,5}\d{1,2}-\d{3}|X Antibody|"
                         r"[\w' ]{1,24} Mode|Showcase Leader|Leader|"
                         # variant names that do come out of packs (the model's own regex decides which pool they're in)
                         r"Foil|Cold Foil|Holo(?:foil)?|Enchanted|Epic|Iconic|Legendary|Showcase|Prestige|Hyperspace(?: Foil)?|"
                         r"S?R\*{1,3}|[CU]\*{1,3}|[A-Z]{1,3}\+{1,2}|Parallel|(?:Super )?Alternate Art|Manga|SP|Wanted Poster|"
                         r"Overnumbered|Signature|Extended Art|Full Art|Borderless|Alt Art|Starlight|Quarter Century", re.I)


def plain_ok(name):
    return all(ALLOWED_TAG.fullmatch(t.strip()) for t in re.findall(r"\(([^)]*)\)", name))


# Outcomes the research marked as placeholders aren't counted: an invented rate on a $2,000 card would decide the verdict.
PLACEHOLDER = re.compile(r"placeholder|unknown|guess", re.I)

# rarity label -> bulk column, per game (for the bulk floor)
BULK_COL = {
    "pokemon": [(r"^(common|uncommon)$", "pkm_cu"), (r"^rare$", "pkm_rare"), (r"holo rare", "pkm_holo"),
                (r"double rare", "pkm_ex"), (r"^ultra rare|full art", "pkm_fullart"), (r"^illustration rare", "pkm_ir"),
                (r"special illustration", "pkm_sir"), (r"hyper|gold|secret|rainbow|black white", "pkm_gold"),
                (r"ace spec|shiny|radiant|amazing", "pkm_ace")],
    "mtg": [(r"^[CU]$", "mtg_cu"), (r"^R$", "mtg_rare"), (r"^M$", "mtg_mythic"), (r"^L$", "mtg_land")],
    "lorcana": [(r"^(common|uncommon)$", "lor_cu"), (r"^rare$", "lor_rare"), (r"super rare", "lor_super"), (r"legendary", "lor_legendary")],
    "onepiece": [(r"^(C|UC)$", "op_cu"), (r"^R$", "op_rare"), (r"^SR$", "op_sr"), (r"^L$", "op_leader")],
    "yugioh": [(r"^common", "ygo_common"), (r"^rare$", "ygo_rare"), (r"^super", "ygo_super"), (r"^ultra", "ygo_ultra"), (r"secret", "ygo_secret")],
}
FOIL_COL = {"pokemon": "pkm_rh", "mtg": "mtg_foil_cu", "lorcana": "lor_foil_cu", "onepiece": "op_foil"}


def bulk_rates():
    """75th-percentile US cash bulk price per column (what a well-chosen buyer pays), $ per card."""
    if not BUYERS.exists():
        return {}
    data = json.loads(BUYERS.read_text())
    per = {}
    unit = {"per_card": 1, "per_100": 100, "per_1000": 1000}
    for b in data["buyers"]:
        if b.get("status") != "active" or b.get("country", "US") != "US" or b.get("source_type") == "second_hand":
            continue
        best = {}
        for r in b["rates"]:
            n = unit.get(r.get("unit")) or r.get("cards_per_unit")
            if not n or r.get("lang", "en") != "en" or r.get("paused") or r.get("payout") != "cash" or r.get("currency", "USD") != "USD":
                continue
            v = r["price"] / n * (1 - (b.get("fee_pct") or 0) / 100)
            for c in r.get("cats", []):
                best[c] = max(best.get(c, 0), v)
        for c, v in best.items():
            per.setdefault(c, []).append(v)
    out = {}
    for c, vals in per.items():
        vals.sort()
        out[c] = vals[min(len(vals) - 1, int(len(vals) * 0.75))]
    return out


def bulk_value(game, rarity, finish, rates):
    if finish and re.search(r"reverse|foil", finish, re.I) and FOIL_COL.get(game) and re.search(r"^(common|uncommon|rare|C|U|UC|R)$", rarity or "", re.I):
        return rates.get(FOIL_COL[game], 0.0)
    for pat, col in BULK_COL.get(game, []):
        if re.search(pat, rarity or "", re.I):
            return rates.get(col, 0.0)
    return 0.0


def sold_value(price, floor):
    return max(floor, price * (1 - SELL_FEE) - HANDLING) if price else floor


GAME_ALIAS = {"dbs_fusion_world": "dbs", "union_arena": "unionarena", "weiss_schwarz": "weiss"}


def code_matches(code, entries):
    for e in entries:
        if not code:
            return False
        if code == e or code.startswith(e + "-"):          # "OP15-EB04" belongs to OP15
            return True
        if "xx" in e.lower() and re.fullmatch(re.sub(r"xx", r"\\d+", re.escape(e), flags=re.I), code, re.I):
            return True
        if e.startswith("^") and re.search(e, code):        # an explicit regex
            return True
    return False


def model_for(game, s, kind, models):
    """Most specific model for this set and pack kind: by set name, then set code, then date range."""
    best, score = None, -1
    for m in models:
        if GAME_ALIAS.get(m.get("game"), m.get("game")) != game or m.get("pack", "booster") != kind:
            continue
        a = m.get("applies_to") or {}
        sc = -1
        names = a.get("set_names") or []
        if s["name"] in names:
            sc = 3
        elif any(n.endswith("*") and s["name"].startswith(n[:-1]) for n in names):
            sc = 1
        elif code_matches(s.get("code"), a.get("set_codes") or []):
            sc = 2
        elif (a.get("from") or a.get("to")) and not names and not a.get("set_codes"):
            if (not a.get("from") or s["released"] >= a["from"]) and (not a.get("to") or s["released"] <= a["to"]):
                sc = 1
        if sc > score:
            best, score = m, sc
    return best, score


CARD_LISTS = {}
BOOSTER_FUN = "Borderless|Showcase|Extended Art|Retro Frame"


def norm_name(n):
    return re.sub(r"\s*\([^)]*\)", "", n.split(" // ")[0]).strip().lower()


OUTLIER_X = 50    # a card listed at over 50x the median of its pool is usually a one-off printing or a bad listing
CAPPED = []


def pool(cards, outcome, game, rates):
    pl = _pool(cards, outcome, game, rates)
    if not pl and outcome.get("treatment") not in (None, "Regular") and outcome.get("name_regex"):
        pl = _pool(cards, {**outcome, "name_regex": BOOSTER_FUN}, game, rates)  # naming differs: any booster-fun version
    if len(pl) >= 5:
        med = statistics.median(x[1] for x in pl)
        cap = max(med * OUTLIER_X, 1.0)
        fixed = []
        for name, price, net, floor in pl:
            if price > cap:
                CAPPED.append(f"{name} (${price:,.0f}, counted as ${cap:,.0f})")
                price, net = cap, sold_value(cap, floor)
            fixed.append((name, price, net, floor))
        pl = fixed
    return pl


def _pool(cards, outcome, game, rates):
    rar = {x.lower() for x in outcome.get("rarity") or []}
    finish = outcome.get("finish")
    rx = re.compile(outcome["name_regex"], re.I) if outcome.get("name_regex") else None
    ex = re.compile(outcome["exclude_name_regex"], re.I) if outcome.get("exclude_name_regex") else None
    allow = {x.lower() for x in CARD_LISTS.get(outcome["card_list"], [])} if outcome.get("card_list") else None
    out = []
    for pid, name, number, rarity, fin in cards:
        if (rarity or "").lower() not in rar:
            continue
        if NOT_IN_PACKS.search(name):
            continue
        if allow is not None and norm_name(name) not in allow:
            continue
        if ex and ex.search(name):
            continue
        plain_pool = not rx or rx.pattern.startswith("^(?!")
        if rx and not rx.search(name):
            continue
        if not rx and VARIANT.search(name):
            continue
        if plain_pool and not plain_ok(name):
            continue
        pr = fin.get(finish) if finish else None
        if pr is None and finish is None:
            pr = next(iter(fin.values()))
        if pr is None:
            continue
        price = pr[0] if pr[0] is not None else pr[1]
        if price is None:
            continue
        floor = bulk_value(game, rarity, finish, rates)
        out.append((name, price, sold_value(price, floor), floor))
    return out


def evaluate(game, s, model, rates, by_name):
    cards = s.get("cards") or []
    slots, missing = [], []
    worst_gap = 0.0
    skipped = []
    ZERO = [("(nothing of value)", 0.0, 0.0, 0.0)]
    for slot in model["slots"]:
        outs, gap = [], 0.0
        total_p = sum(o.get("p", 0) for o in slot["outcomes"]) or 1
        for o in slot["outcomes"]:
            if o.get("p", 0) <= 0:
                continue
            if not o.get("rarity") or o.get("rarity") == ["Action Point"]:
                outs.append((o, o["p"] / total_p, ZERO))   # filler: a token, a basic rune, an action point card
                continue
            if PLACEHOLDER.search(str(o.get("basis", "")) + " " + str(o.get("note", ""))):
                skipped.append(f"{'/'.join(o['rarity'])} ({o['p']:.2%} per slot: odds not known yet, not counted)")
                outs.append((o, o["p"] / total_p, ZERO))
                continue
            if o.get("set_names"):
                src = [c for n in o["set_names"] for c in by_name.get(n, {}).get("cards", [])]
            elif o.get("cards_from_set"):
                src = by_name.get(o["cards_from_set"], {}).get("cards", [])
            else:
                src = cards
            pl = pool(src, o, game, rates)
            if not pl:
                # count it as worth nothing rather than spreading its odds over the rest (which would inflate the value)
                missing.append(f"{slot['name']}: {'/'.join(o.get('rarity') or [])} {o.get('finish') or ''} ({o['p']:.1%})".strip())
                gap += o["p"] / total_p
                outs.append((o, o["p"] / total_p, ZERO))
                continue
            outs.append((o, o["p"] / total_p, pl))
        worst_gap = max(worst_gap, gap)
        slots.append((slot, outs))
    if not slots or worst_gap > 0.5:
        return None  # too much of the pack can't be priced
    # exact expectation, and a per-rarity breakdown
    ev_gross = ev_net = ev_floor = 0.0
    breakdown = {}
    top_card = ("", 0.0)  # the single card that adds the most to an average pack
    for slot, outs in slots:
        for o, p, pl in outs:
            if pl is ZERO:
                continue
            cnt = slot.get("count", 1) * p
            g = statistics.fmean(x[1] for x in pl)
            n = statistics.fmean(x[2] for x in pl)
            f = statistics.fmean(x[3] for x in pl)
            ev_gross += cnt * g
            ev_net += cnt * n
            best = max(pl, key=lambda x: x[2])
            if cnt * best[2] / len(pl) > top_card[1]:
                top_card = (best[0], cnt * best[2] / len(pl))
            ev_floor += cnt * f
            key = ("/".join(o.get("rarity") or []) + (f" · {o['finish']}" if o.get("finish") and o["finish"] != "Normal" else "")
                   + (" · " + o["name_regex"] if o.get("name_regex") else ""))
            row = breakdown.setdefault(key, {"label": key, "per_pack": 0.0, "avg": g, "avg_sold": n, "gross": 0.0, "net": 0.0,
                                             "pool": len(pl), "top": sorted(((x[0], round(x[1], 2)) for x in pl), key=lambda t: -t[1])[:3]})
            row["per_pack"] += cnt
            row["gross"] += cnt * g
            row["net"] += cnt * n
    # simulation for the spread
    rnd = random.Random(s["id"] * 31 + len(model["id"]))
    sims = []
    for _ in range(SIMS):
        v = 0.0
        for slot, outs in slots:
            c = slot.get("count", 1)
            draws = int(c) + (1 if rnd.random() < c - int(c) else 0)  # fractional counts: an expected number of cards
            for _k in range(draws):
                r, acc = rnd.random(), 0.0
                for o, p, pl in outs:
                    acc += p
                    if r <= acc:
                        v += rnd.choice(pl)[2]
                        break
                else:
                    v += rnd.choice(outs[-1][2])[2]
        sims.append(v)
    sims.sort()
    q = lambda f: sims[min(len(sims) - 1, int(len(sims) * f))]
    rows = sorted(breakdown.values(), key=lambda r: -r["net"])
    for r in rows:
        for k in ("per_pack", "avg", "avg_sold", "gross", "net"):
            r[k] = round(r[k], 4)
    return {"ev_market": round(ev_gross, 2), "ev_sold": round(ev_net, 2), "bulk_floor": round(ev_floor, 3),
            "unpriced_share": round(worst_gap, 3), "not_counted": skipped,
            "top_card": top_card[0], "top_card_share": round(top_card[1] / ev_net, 3) if ev_net else 0,
            "median_sold": round(q(0.5), 2), "p10_sold": round(q(0.1), 2), "p90_sold": round(q(0.9), 2),
            "sims": sims, "breakdown": rows, "missing": missing}


def main():
    raw = json.loads(RAW.read_text())
    models = []
    for f in sorted(MODELS.glob("*.json")):
        doc = json.loads(f.read_text())
        models += doc.get("models", [])
        CARD_LISTS.update(doc.get("card_lists", {}))
    rates = bulk_rates()
    OUT.mkdir(parents=True, exist_ok=True)
    index = {"generated": dt.date.today().isoformat(), "prices_as_of": raw.get("prices_as_of"),
             "assumptions": {"sell_fee": SELL_FEE, "handling_per_card": HANDLING, "simulated_packs": SIMS,
                             "bulk_rates": {k: round(v, 4) for k, v in sorted(rates.items())}}, "games": {}}
    for game, gdata in raw["games"].items():
        sealed_path = SEALED / f"{game}.json"
        sealed = {s["id"]: s for s in json.loads(sealed_path.read_text())["sets"]} if sealed_path.exists() else {}
        out_sets = []
        by_name = {s["name"]: s for s in gdata["sets"]}
        for s in gdata["sets"]:
            if not s.get("cards"):
                continue
            sd = sealed.get(s["id"], {})
            kinds = sorted({k for p in sd.get("products", []) for k in p["contents"]} or {"booster"})
            for kind in kinds:
                model, score = model_for(game, s, kind, models)
                if not model:
                    continue
                CAPPED.clear()
                res = evaluate(game, s, model, rates, by_name)
                if not res:
                    continue
                pack_price = (sd.get("single_pack") or {}).get(kind)
                cheapest = None
                for p in sd.get("products", []):
                    if list(p["contents"]) == [kind] and p.get("per_pack") and "case" not in p["type"] and not p.get("presale"):
                        if not cheapest or p["per_pack"] < cheapest["per_pack"]:
                            cheapest = {"name": p["name"], "type": p["type"], "per_pack": p["per_pack"], "url": p["url"]}
                sims = res.pop("sims")
                res["capped"] = sorted(set(CAPPED))[:5]
                entry = {"id": s["id"], "name": s["name"], "code": s.get("code"), "released": s["released"], "kind": kind,
                         "model": model["id"], "match": ["era model", "era model", "set code", "this set"][score],
                         "confidence": model.get("confidence"), "sources": model.get("sources", [])[:4],
                         "pack_price": pack_price, "cheapest": cheapest, **res}
                for label, price in (("pack", pack_price), ("cheapest", cheapest and cheapest["per_pack"])):
                    if price:
                        entry[f"beats_{label}"] = round(sum(1 for v in sims if v >= price) / len(sims), 3)
                        entry[f"ratio_{label}"] = round(res["ev_sold"] / price, 3)
                # Opening rarely beats sealed by 2x for long: on thin pull-rate data that usually means a model or price problem.
                r = entry.get("ratio_pack") or 0
                entry["check"] = bool(r > 2 or (r > 1.3 and model.get("confidence") == "estimate"))
                out_sets.append(entry)
        out_sets.sort(key=lambda e: e["released"], reverse=True)
        (OUT / f"{game}.json").write_text(json.dumps({"game": game, "sets": out_sets}, ensure_ascii=False, separators=(",", ":")) + "\n")
        index["games"][game] = {"sets": len(out_sets)}
        print(f"{game}: EV for {len(out_sets)} set/pack combinations")
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
