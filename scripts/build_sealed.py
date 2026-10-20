#!/usr/bin/env python3
"""Turn cache/sealed_raw.json (from fetch_sealed.py) into data/sealed/<game>.json.

For every sealed product it works out what's inside (how many packs, of which kind), then the
price per pack and how that compares with buying the same packs one at a time.

How the pack count is decided, in order:
  1. research/sealed_overrides.json, by TCGplayer product id (hand fixes);
  2. the product's own description ("includes 9 ... booster packs");
  3. the usual count for that kind of product (research/sealed_configs.json, else built-in).
Products whose contents can't be worked out are left out rather than guessed.

  python3 scripts/build_sealed.py
"""
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "cache" / "sealed_raw.json"
OVERRIDES = ROOT / "research" / "sealed_overrides.json"
MSRP = ROOT / "research" / "sealed_msrp.json"
OUTDIR = ROOT / "data" / "sealed"

NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
       "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "sixteen": 16, "eighteen": 18, "twenty": 20,
       "twenty-four": 24, "thirty": 30, "thirty-six": 36}
NUMWORD = r"\d{1,3}|" + "|".join(sorted(NUM, key=len, reverse=True))

PACK_NAMES = {  # pack kind -> label shown on the site
    "booster": "booster packs", "play": "Play Boosters", "collector": "Collector Boosters", "set": "Set Boosters",
    "draft": "Draft Boosters", "jumpstart": "Jumpstart packs", "mega": "Mega Packs", "other": "packs from other sets",
    "carbonite": "Carbonite packs", "premium": "Premium packs",
}


def num(s):
    s = s.lower()
    return int(s) if s.isdigit() else NUM.get(s)


def has(p, s):
    return re.search(p, s, re.I) is not None


# ------------------------------------------------------------------ reading the description

PACKS_IN_TEXT = re.compile(
    rf"(?:\((?P<n1>\d{{1,3}})\)|(?<![\w$.,])(?P<n2>{NUMWORD})(?![\w.,]))\s*(?:x\s+)?"
    r"(?P<mid>[^\n•;!?]{0,90}?)"
    r"\b(?P<kind>play|collector|set|draft|jumpstart|mega)?[- ]?(?:booster|pack)(?:s\b| packs?\b|\b)",
    re.I)


def packs_from_text(text, game):
    """{'booster': 9} from 'includes: • 9 Pokémon TCG: ... booster packs'. Empty dict if unclear."""
    found = {}
    for m in PACKS_IN_TEXT.finditer(text or ""):
        n = int(m.group("n1")) if m.group("n1") else num(m.group("n2"))
        mid = m.group("mid") or ""
        whole = m.group(0).lower()
        if not n or n > 60 or "booster" not in whole and not re.search(r"\bpacks?\b", whole):
            continue
        if re.search(r"\b(?:cards?|copies|cases?|displays?|boxes|bundles|tins|kits|days?|years?|reasons?|each|every|as|"
                     r"per|with|this|that|from|than|up to|over|more|times?|ways?|variations?|unique)\b|%", mid, re.I):
            continue  # "10 cards per booster", "6 copies of ...", "30 reasons ... as each booster pack"
        if re.search(r"each|per|in every", text[max(0, m.start() - 25):m.start()], re.I) and n >= 9:
            continue  # "each booster pack contains 10 cards"
        kind = (m.group("kind") or "").lower() or "booster"
        if re.search(r"additional pok[eé]mon tcg booster", whole):
            kind = "other"  # random packs from other sets: can't be valued
        if game != "mtg" and kind in ("play", "collector", "set", "draft", "jumpstart"):
            kind = "booster"
        if game == "yugioh" and kind != "mega":
            kind = "booster"
        found[kind] = max(found.get(kind, 0), n)
    return found


def units_from_text(name, text):
    """How many retail units are in a case/display, when the listing says."""
    m = re.search(r"\((\d{1,3})\s*(?:ct|count|pcs?|units?)\)|\b(\d{1,3})\s*(?:ct|count)\b|\bx\s?(\d{1,3})\b", name, re.I)
    if m:
        return int(next(g for g in m.groups() if g))
    for pat in (r"contains?\s+(\d{1,3})\s+(?:copies|units|sealed|individual)",
                r"(?:case|display)\s+(?:of|contains|includes|with)\s+(\d{1,3})\b",
                rf"contains?\s+({NUMWORD})(?![\w.])\s+[\w'’&:.\- ]{{0,60}}?(?:boxes|bundles|tins|blisters|kits|collections|displays)\b",
                r"\b(\d{1,3})\s+(?:booster boxes|elite trainer boxes|booster bundles|bundles|mini tins|blisters|build & battle (?:boxes|kits)|displays)\b"):
        m = re.search(pat, text or "", re.I)
        if m:
            n = num(m.group(1))
            if n and 2 <= n <= 60:
                return n
    return None


# ------------------------------------------------------------------ product kinds by name

def era(released, cutoff):
    return released >= cutoff


def kind_pokemon(n, released):
    """(type label, default contents or None to rely on the description)."""
    sv = era(released, "2023-03-31")
    if has(r"pok[eé]mon center elite trainer box", n):
        return "Pokémon Center ETB", {"booster": 11 if sv else 10}
    if has(r"elite trainer box", n):
        return "Elite Trainer Box", {"booster": 9 if sv else 8}
    if has(r"sleeved booster pack art bundle|booster pack art bundle", n):
        return "Pack art bundle", {"booster": 1}  # x4 from its "[Set of 4]"
    if has(r"half booster box", n):
        return "Half booster box", {"booster": 18}
    if has(r"enhanced booster box", n):
        return "Enhanced booster box", None
    if has(r"booster box", n):
        return "Booster box", {"booster": 36}
    if has(r"booster bundle", n):
        return "Booster bundle", {"booster": 6}
    if has(r"sleeved booster", n):
        return "Sleeved booster", {"booster": 1}
    if has(r"booster pack\b", n):
        return "Booster pack", {"booster": 1}
    if has(r"3[- ]pack blister|three[- ]pack blister", n):
        return "3-pack blister", {"booster": 3}
    if has(r"premium checklane blister", n):
        return "Premium checklane blister", None
    if has(r"single pack blister|checklane blister|1[- ]pack blister", n):
        return "1-pack blister", {"booster": 1}
    if has(r"build (?:&|and) battle stadium", n):
        return "Build & Battle Stadium", None
    if has(r"build (?:&|and) battle box", n):
        return "Build & Battle Box", {"booster": 4}
    if has(r"mini tin", n):
        return "Mini tin", {"booster": 2}
    if has(r"ultra[- ]premium collection", n):
        return "Ultra-Premium Collection", None
    if has(r"premium collection|premium figure|special collection", n):
        return "Premium collection", None
    if has(r"\btin\b", n):
        return "Tin", None
    if has(r"collection|\bex box\b|\bv box\b|surprise box|binder|poster|sticker|bundle", n):
        return "Collection", None
    return None, None


FOUR_PACK_COLLECTOR = re.compile(r"^(?:Double Masters(?: 2022)?|Commander Masters)$", re.I)  # 4-pack collector displays
DRAFT_24 = re.compile(r"Commander Legends|Commander Masters|Double Masters", re.I)  # 20-card draft packs, 24 per box
SET_BOX_UNKNOWN = re.compile(r"Battle for Baldur", re.I)


def kind_mtg(n, released, set_name=""):
    play_era = era(released, "2024-02-09")  # Murders at Karlov Manor: Play Boosters replace Draft/Set
    if has(r"collector booster (?:box|display)", n):
        return "Collector Booster box", {"collector": 4 if FOUR_PACK_COLLECTOR.match(set_name) else 12}
    if has(r"collector booster pack|collector booster$|collector booster \[", n):
        return "Collector Booster pack", {"collector": 1}
    if has(r"play booster (?:box|display)", n):
        return "Play Booster box", {"play": 30 if era(released, "2025-02-14") else 36}  # Aetherdrift onward: 30
    if has(r"play booster pack|play booster$|play booster \[", n):
        return "Play Booster pack", {"play": 1}
    if has(r"set booster (?:box|display)", n):
        return "Set Booster box", None if SET_BOX_UNKNOWN.search(set_name) else {"set": 30}
    if has(r"set booster pack|set booster$", n):
        return "Set Booster pack", {"set": 1}
    if has(r"draft booster (?:box|display)", n):
        return "Draft Booster box", {"draft": 24 if DRAFT_24.search(set_name) else 36}
    if has(r"draft booster pack|draft booster$", n):
        return "Draft Booster pack", {"draft": 1}
    if has(r"jumpstart.*booster (?:box|display)", n):
        return "Jumpstart box", {"jumpstart": 24}
    if has(r"jumpstart.*booster pack|jumpstart.*booster$", n):
        return "Jumpstart pack", {"jumpstart": 1}
    if has(r"gift bundle$|bundle:? gift edition", n):
        return "Gift Bundle", {"play": 9, "collector": 1} if play_era else None
    if has(r"(?:^|- )bundle$", n) and not has(r"commander|secret lair|deck", n):
        if play_era:
            return "Bundle", {"play": 9}
        return "Bundle", {"set": 8} if era(released, "2021-09-24") else {"draft": 10}  # Midnight Hunt to Lost Caverns: 8 Set
    if has(r"prerelease (?:pack|kit)", n):
        return "Prerelease pack", {"play": 6} if play_era else None
    if has(r"beginner box|starter kit|foundations starter", n):
        return "Starter product", None
    return None, None


def kind_generic(n, released, game):
    if has(r"premium booster (?:box|display)", n):
        return "Premium booster box", None
    if game == "swu" and has(r"carbonite", n) and has(r"booster (?:box|display)", n):
        return "Booster box", {"booster": 12}  # Carbonite displays hold 12 packs
    if has(r"booster (?:box|display)|\bbooster case\b(?!.*\bof\b)", n) and not has(r"\bcase\b", n):
        if game == "weiss":
            return "Booster box", None  # 10- or 12-pack displays now, older 16; rely on the listing
        return "Booster box", {"booster": 16 if game == "unionarena" else 24}
    if has(r"booster pack|booster$|booster \[", n):
        return "Booster pack", {"booster": 1}
    if has(r"illumineer'?s trove", n):
        return "Illumineer's Trove", {"booster": 8}
    if has(r"double pack", n):
        return "Double pack set", {"booster": 2}
    if has(r"gift set", n) and game == "lorcana":
        return "Gift set", {"booster": 4}
    if has(r"\bvault\b", n) and game == "riftbound":
        return "Vault", {"booster": 6}
    if has(r"gift set|gift box|collection|bundle|tin\b|carbonite|starter set|prerelease", n):
        return "Other bundle", None
    return None, None


JUNK = (r"code card|fun pack|trick or trade|mini booster|omega pack|\bdeck\b(?!.*build (?:&|and) battle)|sleeves?\b(?!d)|playmat|\bpin\b|\bjumbo\b|"
        r"single card|\bpromo\b(?!.*collection)|empty|box only|no packs|figure only|deck box|binder only|"
        r"portfolio|card sleeves|dice\b|token|life counter|art card|storage|\bmat\b|\bsurprise box display|"
        r"secret lair|commander (?:deck|collection)|precon|structure deck|starter deck|battle deck|league battle|"
        r"theme deck|trainer'?s toolkit|world championship|championship deck|slab|graded|psa|cgc|bgs")

EXTRAS = [("promo", r"promo"), ("sleeves", r"sleeves"), ("dice", r"\bdice\b|\bdie\b"), ("coin", r"\bcoin\b"),
          ("oversize card", r"oversize|jumbo"), ("binder", r"binder"), ("poster", r"poster"), ("pin", r"\bpins?\b"),
          ("figure", r"figure"), ("stickers", r"sticker"), ("playmat", r"playmat"), ("storage box", r"storage box|deck box"),
          ("collector box", r"collector'?s? box")]


def classify(game, prod, released, set_name=""):
    n, text = prod["name"], prod.get("text") or ""
    if has(JUNK, n):
        return None
    multi = has(r"\bcase\b|\bcarton\b", n) or (has(r"\bdisplay\b", n) and not has(r"booster display", n))
    base = re.sub(r"\s*\b(?:display|case|master carton|carton)\b.*$", "", n, flags=re.I) if multi else n
    m_set = re.search(r"[\[(]\s*set of (\d{1,2})\s*[\])]", n, re.I) or \
        re.search(r"\b(?:tins?|collections?|bundles?|boxes)\s+(\d{1,2})-pack\b", n, re.I)
    set_of = int(m_set.group(1)) if m_set else 1
    if game == "pokemon":
        label, default = kind_pokemon(base, released)
    elif game == "mtg":
        label, default = kind_mtg(base, released, set_name)
    else:
        label, default = kind_generic(base, released, game)
    if not label:
        return None
    if multi and label in ("Booster pack", "Sleeved booster", "Play Booster pack", "Collector Booster pack", "Set Booster pack",
                           "Draft Booster pack", "Jumpstart pack") and has(r"booster (?:box|display)", n):
        pass
    parsed = packs_from_text(text, game)
    if label == "Build & Battle Stadium" and parsed.get("booster") and has(r"additional", text):
        parsed["booster"] += 8  # plus two Build & Battle Boxes of 4 packs each
    total_hint = re.search(r"\((\d{2,4})\s*packs? total\)|(\d{2,4})\s+(?:booster )?packs total", text, re.I)
    source = "rule"
    contents = default
    if parsed and not multi:
        if default is None:
            contents, source = parsed, "description"
        elif sum(parsed.values()) != sum(default.values()):
            # trust the listing when it disagrees with the usual count, within reason
            if 0.5 <= sum(parsed.values()) / sum(default.values()) <= 2:
                contents, source = parsed, "description"
    if multi:
        units = units_from_text(n, text)
        if has(r"\bdisplay\b", n) and has(r"\bcase\b", n) and not total_hint:
            return None  # a case of displays: two unknown multipliers
        if total_hint:
            contents, source = {next(iter(default or parsed or {"booster": 1})): int(next(g for g in total_hint.groups() if g))}, "description"
            label = f"{label} case"
        elif units and (default or parsed):
            per = parsed if (parsed and default is None) else default
            contents = {k: v * units for k, v in per.items()}
            label, source = f"{label} case ({units}×)", "description"
        else:
            return None  # case size unknown
    if not contents:
        return None
    if set_of > 1 and not multi and source != "description":
        contents = {k: v * set_of for k, v in contents.items()}
        if label != "Pack art bundle":
            label = f"{label} (set of {set_of})"
    if game == "swu" and has(r"carbonite", n):
        contents = {"carbonite" if k == "booster" else k: v for k, v in contents.items()}
    if has(r"premium booster", n) and game in ("onepiece", "weiss", "digimon", "dbs", "unionarena"):
        contents = {"premium" if k == "booster" else k: v for k, v in contents.items()}
    extras = [name for name, pat in EXTRAS if has(pat, text) or has(pat, n)]
    return {"type": label, "contents": contents, "count_source": source, "extras": extras}


# ------------------------------------------------------------------ build

def msrp_for(game, label, released, table, set_name="", packs=None):
    best = None
    for row in table.get(game, []):
        if row["type"].lower() != label.lower():
            continue
        if row.get("from") and released < row["from"]:
            continue
        if row.get("set_regex") and not re.search(row["set_regex"], set_name, re.I):
            continue
        if row.get("not_set_regex") and re.search(row["not_set_regex"], set_name, re.I):
            continue
        if row.get("packs") and packs != row["packs"]:
            continue
        if not best or (row.get("from") or "") > (best.get("from") or ""):
            best = row
    return best


HISTORY = ROOT / "data" / "history"
TRACKED = {"Booster pack", "Booster box", "Half booster box", "Elite Trainer Box", "Pokémon Center ETB", "Booster bundle",
           "Play Booster pack", "Play Booster box", "Collector Booster pack", "Collector Booster box", "Bundle"}


def record_history(game, sets_out):
    """Keep a weekly market-price point for the main products, so trends can be shown later."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    path = HISTORY / f"{game}.json"
    hist = json.loads(path.read_text()) if path.exists() else {}
    today = dt.date.today()
    for s in sets_out:
        for r in s["products"]:
            if r["type"] not in TRACKED or not r.get("market"):
                continue
            h = hist.setdefault(str(r["id"]), {"name": r["name"], "set": s["name"], "pts": []})
            last = h["pts"][-1] if h["pts"] else None
            if not last or (today - dt.date.fromisoformat(last[0])).days >= 7:
                h["pts"].append([today.isoformat(), r["market"]])
                h["pts"] = h["pts"][-104:]  # two years of weekly points
    path.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")) + "\n")


def main():
    raw = json.loads(RAW.read_text())
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    msrp = json.loads(MSRP.read_text()).get("games", {}) if MSRP.exists() else {}
    OUTDIR.mkdir(parents=True, exist_ok=True)
    index = {"generated": dt.date.today().isoformat(), "prices_as_of": raw.get("prices_as_of"),
             "source": "TCGplayer market prices via TCGCSV", "games": {}}
    for game, gdata in raw["games"].items():
        sets_out = []
        for s in gdata["sets"]:
            rows = []
            for p in s["products"]:
                ov = overrides.get(str(p["id"]))
                if ov and ov.get("skip"):
                    continue
                c = classify(game, p, s["released"], s["name"])
                if ov and ov.get("contents"):
                    c = c or {"type": ov.get("type", "Other"), "extras": []}
                    c.update({"contents": ov["contents"], "count_source": "checked by hand"})
                    if ov.get("type"):
                        c["type"] = ov["type"]
                if not c:
                    continue
                price = p.get("market") or None
                if price is None and p.get("low") is None:
                    continue
                packs = sum(c["contents"].values())
                row = {"id": p["id"], "name": p["name"], "url": p["url"], "image": p.get("image"),
                       "type": c["type"], "contents": c["contents"], "packs": packs,
                       "count_source": c["count_source"], "extras": c["extras"],
                       "market": price, "low": p.get("low"), "presale": p.get("presale") or False}
                m = msrp_for(game, c["type"], s["released"], msrp, s["name"], sum(c["contents"].values()))
                if m and list(c["contents"]) not in (["booster"], ["play"], ["collector"]):
                    m = None  # MSRP rows describe standard packs only
                if m and m.get("price"):
                    row["msrp"] = m["price"]
                rows.append(row)
            if not rows:
                continue
            # what one pack of each kind costs on its own (median of the single-pack listings)
            single = {}
            for kind in {k for r in rows for k in r["contents"]}:
                vals = [r["market"] for r in rows if r["contents"] == {kind: 1} and r["market"]
                        and not re.search(r"blister|sleeved|art bundle|sample", r["name"], re.I)]
                if vals:
                    single[kind] = round(statistics.median(vals), 2)
            for r in rows:
                kinds = list(r["contents"])
                if r["market"] and len(kinds) == 1:
                    r["per_pack"] = round(r["market"] / r["packs"], 3)
                if r["low"] and len(kinds) == 1:
                    r["per_pack_low"] = round(r["low"] / r["packs"], 3)
                if all(k in single for k in kinds):
                    value = sum(single[k] * v for k, v in r["contents"].items())
                    r["singles_value"] = round(value, 2)
                    if r["market"]:
                        r["vs_singles"] = round(r["market"] / value - 1, 4)
                if r.get("msrp") and len(kinds) == 1:
                    r["msrp_per_pack"] = round(r["msrp"] / r["packs"], 3)
            rows.sort(key=lambda r: (list(r["contents"])[0], r.get("per_pack") or 1e9))
            sets_out.append({"id": s["id"], "name": s["name"], "code": s.get("code"), "released": s["released"],
                             "single_pack": single, "products": rows})
        (OUTDIR / f"{game}.json").write_text(json.dumps({"game": game, "sets": sets_out}, ensure_ascii=False, separators=(",", ":")) + "\n")
        record_history(game, sets_out)
        index["games"][game] = {"sets": len(sets_out), "products": sum(len(s["products"]) for s in sets_out)}
        print(f"{game}: {len(sets_out)} sets, {index['games'][game]['products']} products")
    (OUTDIR / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
