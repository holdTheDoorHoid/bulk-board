#!/usr/bin/env python3
"""Build data/buyers.json from the research files.

  research/sources/*.json      what research found (format: research/SCHEMA.md)
  research/corrections.json    hand corrections, applied last (see the file for the format)
  -> data/buyers.json          what the site reads

Every store words its categories differently ("V/VMAX/VSTAR", "Bulk Magic Rare", "Cold Foil
C/U"...). classify() maps each store's own label onto the site's columns with ordered rules;
the store's wording is kept as `category_raw` and shown on hover. Lines that fit no column
(graded cards, playmats, set-specific lines...) keep `cats: []` and appear only in the store's
details panel.

Run:  python3 scripts/build_data.py
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "research" / "sources"
CORRECTIONS = ROOT / "research" / "corrections.json"
OUT = ROOT / "data" / "buyers.json"

# Research files in priority order: a store's own page beats a comparison page.
SOURCE_RANK = {"first_party": 0, "marketplace_listing": 1, None: 2, "second_hand": 3}
PLATFORMS = {"app.tcgbulk.com": ("tcgbulk", "TCG Bulk", 10.0)}  # host -> (id, name, seller fee %)

LANGS = {"japanese": "ja", "korean": "ko", "chinese": "zh", "french": "fr", "german": "de", "italian": "it",
         "spanish": "es", "portuguese": "pt", "thai": "th", "indonesian": "id", "russian": "ru", "dutch": "nl"}

# Smaller games that share the "Other games" tab. Label prefixes on mixed "other" lines.
OTHER_PREFIX = {"final fantasy": "fftcg", "gundam": "gundam", "riftbound": "riftbound", "union arena": "unionarena"}

FIELDS = ["name", "website", "rates_url", "watch_url", "other_urls", "country", "region", "city", "mail_in", "in_person", "games",
          "payout_methods", "store_credit_bonus", "minimum", "min_cards", "min_usd", "shipping", "pays_shipping",
          "ship_free_over_cards", "ship_free_over_usd", "volume_bonus", "condition_rules", "sorting_rules", "excluded",
          "turnaround", "process", "rates_last_updated", "status", "reputation", "checked_on", "notes"]


# ---------------------------------------------------------------- classification

def clean_label(s):
    s = re.sub(r"\((?:[^)]*\b(?:excluded|exclude|excludes|excluding|no|not|except|without)\b[^)]*)\)", " ", s, flags=re.I)
    s = re.sub(r"\b(?:no|without|excluding|except)\b\s+[^,;()/]*", " ", s, flags=re.I)
    s = re.sub(r"[-–]\s*(?:promos?|[\w ]+)\s+excluded\b.*$", " ", s, flags=re.I)
    s = re.sub(r"\bexclude[sd]?\b.*$", " ", s, flags=re.I)
    s = re.sub(r"READ DESCRIPT\w*.*$", " ", s, flags=re.I)
    s = re.sub(r"\(\s*\$[^)]*\)|\$\s?\d[\d.,]*\s*(?:each|per card|/card)?", " ", s, flags=re.I)  # prices repeated inside labels
    return re.sub(r"\s+", " ", s).strip()


def has(pat, s, flags=re.I):
    return re.search(pat, s, flags) is not None


PKM_SETS = r"\b(151|prismatic|phantasmal|ascended|hidden fates|shining fates|celebrations|crown zenith|paldean fates|destined rivals|journey together|surging sparks|stellar crown|black bolt|white flare|perfect order|chaos rising|evolving skies|wotc|vintage|base set|jungle|fossil|e-?reader|1st edition|neo )"
PKM_JUNK = r"alternate art|graded|\bpsa\b|\bcgc\b|\bbgs\b|\bpins?\b|\bcoins?\b|playmat|\bmats?\b|sleeve|dice|divider|oversized|jumbo|big card|metal|gold card|sealed|booster|\betb\b|binder|deck box|black star|promos?\b|prism star|gem pack|figures?\b|prebuilt|above holo"
PKM_NAMED = r"charizard|eevee|pikachu ultra|numbered 1-30"


def classify_pokemon(raw, s):
    """Return the Pokémon column codes one store label covers.

    Comma-separated lists are classified item by item. Inside an item, a line that names several
    kinds ("Holo / Reverse Holo / Poké Ball Pattern") counts toward each of them, while words that
    only qualify a kind ("Reverse Holo C/U", "Rainbow VMAX/VSTAR") don't add a column of their own.
    """
    t = re.sub(r"\bS ?& ?V\b", "SandV", s)
    t = re.sub(r"\bV (MAX|STAR)\b", r"V\1", t, flags=re.I)
    # whole-label checks first, so a comma list can't escape them
    t = re.sub(r"non[- ]?(holo|foil)", r"non\1", t, flags=re.I)
    if (has(PKM_JUNK, t) and "," not in t and not has(r"reverse|holo rare|common|uncommon|\bc ?/ ?u", t)) or has(PKM_NAMED, t) or has(r"vintage|wotc|1st edition|\(\d{4} & prior\)|topps|topsun", t):
        return []
    if has(r"^(?:english:? |bulk )?nonholo$|nonholo \(", t):
        return ["pkm_cu", "pkm_rare"]  # "non-holo" with no rarity named = every non-holo card
    if has(r"unsorted|mixed|all cards|any rarity|any non-?foil", t):
        return ["pkm_mixed"]
    if has(r"before sandv|pre-?2016|\(old\)", t) and not has(r"gx|break", t):
        return ["pkm_gx"]
    if "," in t:
        parts = [p for p in (x.strip() for x in t.split(",")) if p]
        if len(parts) > 1:
            got = [classify_pokemon(raw, p) for p in parts]
            if all(g is None for g in got):
                return None
            return sorted({c for g in got if g for c in g})
    return _pkm_item(t)


def _pkm_item(t):
    if (has(PKM_JUNK, t) and not has(r"reverse|holo rare|common|uncommon|\bc ?/ ?u", t)) or has(PKM_NAMED, t):
        return []
    if has(r"\bcodes?\b", t):
        return ["pkm_code"]
    if has(PKM_SETS, t):
        return []
    if has(r"energ", t):
        rest = re.sub(r"(?:(?:holo|foil|reverse|special|basic|gold)\s+)*energ\w*(?:\s+cards?)?", " ", t, flags=re.I)
        if has(r"reverse|holo|rare|full ?art|gold|rainbow|gallery|common|uncommon|\bc ?/ ?u|trainers?|\bex\b|\bV\b|gx", rest):
            t = rest  # energy is one item in a list; classify the rest
        else:
            return [] if has(r"reverse|holo|foil|special", t) else ["pkm_energy"]
    if has(r"unsorted|mixed|all cards|any rarity|any non-?foil", t):
        return ["pkm_mixed"]
    acc = set()
    if has(r"master ?ball", t):
        acc.add("pkm_mbrh")
    if has(r"pok[eé] ?ball", t):
        acc.add("pkm_pbrh")
    if has(r"special illustration|\bSIR\b|special art|\bSAR\b", t):
        acc.add("pkm_sir")
    if has(r"hyper|\bgold\b|rainbow|secret", t):
        acc.add("pkm_gold")
    if has(r"(?<!special )illu\w*ation rares?|^illustration|\bIR\b|(?<!full )(?<!alternate )\bart rare|character rare|\bCHR\b", t):
        acc.add("pkm_ir")
    if has(r"trainer gallery|galarian gallery|gallerian gallery|\bTG\b|\bGG\b|full ?-?art|alternate art|^gallery|\bgallery\b", t):
        acc.add("pkm_fullart")
    if has(r"ace ?spec|radiant|amazing|shiny|shining", t):
        acc.add("pkm_ace")
    # the ex / V family
    fam = set()
    if has(r"v ?max|v ?star|v-?union", t):
        fam.add("pkm_vmax")
    if re.search(r"(?:^|[\s/,&(-])V(?:$|[\s/,&):])", t):
        fam.add("pkm_v")
    if has(r"\bgx\b|\bLV\.? ?X\b", t) or (has(r"\bbreaks?\b", t) and has(r"\bgx\b|\bEX\b|\bV\b", t)):
        fam.add("pkm_gx")
    elif has(r"\bbreaks?\b", t) and not has(r"amazing|character|radiant|full|holo|ace", t):
        return []  # BREAK on its own pays more than GX; it stays in the details
    if re.search(r"\bex\b", t) or has(r"mega ex|double rare|\bRR\b", t):
        fam.add("pkm_ex")
    if re.search(r"\bEX\b", t):
        fam.add("pkm_gx")
        if not re.search(r"mega ex|\(old\)|pre-?2016", t, re.I):
            fam.add("pkm_ex")  # many lists write EX for every ex; count it for both
    if re.search(r"\bEx\b", t):
        fam |= {"pkm_ex", "pkm_gx"}
    if has(r"ultra rares?", t) and not fam and not has(r"full ?-?art|SandV|\bsv\b", t):
        acc.add("pkm_fullart")
    elif has(r"ultra rares?", t) and has(r"SandV|\bsv\b", t):
        acc.add("pkm_fullart")
    family_is_modifier = ("pkm_gold" in acc or "pkm_sir" in acc
                          or has(r"full ?-?art\s+(?:gx|v|ex|vmax|vstar)\b|\b(?:gx|v|ex|vmax|vstar)\s+full ?-?art", t))
    if fam and not family_is_modifier:
        acc |= fam
    # reverse holos, holos, plain rares, commons
    noball = re.sub(r"(?:pok[eé]|master) ?ball(?: pattern)?(?: (?:holos?|reverse(?: holos?)?|foils?))?", " ", t, flags=re.I)
    rh = has(r"reverse|\brev\b", noball)
    if rh:
        acc.add("pkm_rh")
    rest = re.sub(r"reverse[- ](?:holo|foil)s?|foil reverse|\brev\b|reverse", " ", noball, flags=re.I)
    special = acc & {"pkm_gold", "pkm_sir", "pkm_ir", "pkm_fullart", "pkm_ace"}
    if has(r"\bholos?\b|\bfoils?\b", rest) and not has(r"nonholo|nonfoil", t) and not special:
        acc.add("pkm_holo")
    if "pkm_gold" in acc and not has(r"full ?-?art", t):
        acc.discard("pkm_fullart")
    plain = re.sub(r"(?:holo|foil|ultra|secret|rainbow|amazing|illustrat\w*|art|radiant|double|hyper|shiny(?: vault)?|character|gold|special|alternate art) rares?", " ", rest, flags=re.I)
    if (has(r"\brares?\b|\bR\)", plain) or has(r"nonholo$|nonholo rare|nonfoil rare", t)) and not rh and not acc - {"pkm_holo"}:
        acc.add("pkm_rare")
    elif has(r"nonholo rares?|nonfoil rares?", t) or (has(r"\brares?\b", plain) and has(r"common|uncommon|c ?/ ?u", t) and not rh):
        acc.add("pkm_rare")
    if has(r"common|uncommon|\bc ?/ ?u|\bc ?/ ?uc|\buc ?/ ?c|com ?/ ?unc|trainers?$", t) and not rh and not (acc - {"pkm_rare"}):
        acc.add("pkm_cu")
    return sorted(acc) if acc else None


def classify_mtg(raw, s):
    t = s
    if has(r"promo|playmat|dice|spindown|un-?set|unstable|unfinity|unsanctioned|unhinged|unglued|acorn|oversized|sealed|\bjumbo\b|serialized|graded|sleeve", t):
        return []
    if has(r"full[- ]?art", t) or (has(r"foil", t) and has(r"\bland", t) and not has(r"common|uncommon", t)):
        return []
    if has(r"token|art cards?|art series|emblem", t):
        return ["mtg_token"]
    if has(r"\blands?\b", t) and not has(r"common|uncommon|rare", t):
        return ["mtg_land"]
    foil = has(r"foil|etched", re.sub(r"non-?foil", "", t, flags=re.I))
    out = []
    if has(r"mythic", t):
        out.append("mtg_foil_rare" if foil else "mtg_mythic")
    if re.search(r"\brares?\b", re.sub(r"mythic rares?", "", t, flags=re.I), re.I):
        out.append("mtg_foil_rare" if foil else "mtg_rare")
    if out:
        return sorted(set(out))
    if has(r"common|uncommon|\bc ?/ ?u|\bc ?/ ?uc|com ?/ ?unc", t):
        return ["mtg_foil_cu" if foil else "mtg_cu"]
    if has(r"unsorted|mixed|all cards|magic cards|any rarity|^bulk$", t):
        return ["mtg_mixed"]
    return None


def classify_yugioh(raw, s):
    t = s
    if has(r"ultimate|ghost|starlight|collector|quarter century|prismatic|platinum|gold rare|starfoil|mosaic|shatterfoil|short print|graded|sealed|vintage|pre-?200\d", t):
        return []
    acc = set()
    if has(r"secret", t):
        acc.add("ygo_secret")
    if has(r"ultra", t):
        acc.add("ygo_ultra")
    if has(r"super", t):
        acc.add("ygo_super")
    if has(r"\brares?\b|silver letter", re.sub(r"(?:secret|super|ultra) ?(?:/ ?)?rares?", " ", t, flags=re.I)) and not has(r"common", t):
        acc.add("ygo_rare")
    if acc:
        return sorted(acc)
    if has(r"common", t):
        return ["ygo_common"]
    if has(r"unsorted|mixed|all cards|yu-?gi-?oh cards|any rarity|^bulk$", t):
        return ["ygo_mixed"]
    return None


def classify_lorcana(raw, s):
    t = s
    if has(r"enchanted|iconic|epic|promo|sealed|graded", t):
        return []
    if has(r"foil ?/ ?non-?foil|unsorted|mixed|all cards", t):
        return ["lor_mixed"]
    foil = has(r"foil", no_nonfoil(t))
    out = []
    if has(r"legendar", t):
        out.append("lor_foil_legendary" if foil else "lor_legendary")
    if has(r"super rare", t):
        out.append("lor_foil_super" if foil else "lor_super")
    if re.search(r"(?<!super )\brares?\b", t, re.I) and not re.fullmatch(r".*super rares?", t, re.I):
        out.append("lor_foil_rare" if foil else "lor_rare")
    elif has(r"rare ?/ ?super", t):
        out.append("lor_foil_rare" if foil else "lor_rare")
    if out:
        return sorted(set(out))
    if has(r"common|uncommon|\bc ?/ ?u|com ?/ ?unc|c ?/ ?unc", t):
        return ["lor_foil_cu" if foil else "lor_cu"]
    if foil:
        return ["lor_foil_cu"] if has(r"bulk", t) else []
    return None


def classify_onepiece(raw, s):
    t = s
    if has(r"\bdon\b|alt(?:ernate|ernative)? art|\bAA\b|manga|secret|\bSEC\b|treasure|sealed|graded|promo|special|\bSP\b", t):
        return []
    if has(r"unsorted|mixed|all cards", t):
        return ["op_mixed"]
    if has(r"foil|parallel", no_nonfoil(t)):
        return ["op_foil"]
    if has(r"leader", t):
        return ["op_leader"]
    if has(r"super rare|\bSR\b", t):
        return ["op_sr"]
    if has(r"\brares?\b", t) and not has(r"common", t):
        return ["op_rare"]
    if has(r"common|uncommon|\bc ?/ ?u", t):
        return ["op_cu"]
    return None


def classify_small(game, raw, s):
    """Flesh and Blood, Digimon, Star Wars Unlimited, Dragon Ball, Weiss, Gundam, Riftbound..."""
    t = s
    if has(r"unsorted|mixed|all cards|any rarity", t):
        return [game + "_mixed"]
    if has(r"foil", no_nonfoil(t)):
        return [game + "_foil"] if has(r"common|uncommon|\bc ?/ ?u|\bc ?/ ?t|c ?/ ?uc", t) and not has(r"rare|legend|majestic", t) else []
    if has(r"super|secret|special|ultra|legend|majestic|epic|hyperspace|parallel|alt|showcase|double|triple|\bsp\b|\bssp\b|\bsec\b", t):
        return []
    if has(r"\brares?\b", t) and not has(r"common", t):
        return [game + "_rare"]
    if has(r"trial deck|\bTD\b", t):
        return []
    if has(r"common|uncommon|\bc ?/ ?u|\bc ?/ ?t|c ?/ ?uc|com ?/ ?unc", t):
        return [game + "_cu"]
    return None


def classify_sports(raw, s):
    t = s
    if has(r"junk wax|graded|sealed|autograph|relic|patch|game-used|minimum per|19[5-7]0s|& earlier|1979|vintage", t):
        return []
    if has(r"rookie", t):
        return ["sports_rookie"]
    if has(r"insert|parallel|refractor|numbered", t):
        return ["sports_insert"]
    if has(r"any sport|unsorted|mixed", t):
        return ["sports_mixed"]
    if has(r"common|base|baseball|basketball|football|hockey|soccer|golf|ufc|wnba|wrestling|bulk", t):
        return ["sports_base"]
    return None


def lang_of(rate):
    blob = f"{rate.get('category_raw', '')} {rate.get('notes', '')}"
    m = re.search(r"Language:\s*([A-Za-z]+)", blob)
    if m:
        name = m.group(1).lower()
        return "en" if name == "english" else LANGS.get(name, name[:2])
    for name, code in LANGS.items():
        if re.search(rf"\b{name}\b", rate.get("category_raw", ""), re.I) and not re.search(rf"no {name}|{name} excluded|non-{name}", blob, re.I):
            return code
    if rate.get("category_std") in ("pkm_japanese", "mtg_foreign"):
        return "xx"  # "non-English" without a named language
    if re.search(r"\bnon-?english|foreign", rate.get("category_raw", ""), re.I):
        return "xx"
    return "en"


GAME_ALIASES = {"magic": "mtg", "pkmn": "pokemon"}
GAME_WORDS = (r"\b(?:dragon ?ball(?: super)?(?: fusion world)?|fusion world|digimon|flesh and blood|star wars(?: unlimited)?|"
              r"weiss schwarz|riftbound|gundam(?: tcg)?|union arena|final fantasy|yu-?gi-?oh!?|disney lorcana|lorcana|one piece)\b:?")
OTHER_NAMES = {"riftbound": "riftbound", "gundam": "gundam", "union arena": "unionarena", "final fantasy": "fftcg"}


def valid_codes():
    g = json.loads((ROOT / "data" / "games.json").read_text())["games"]
    out = set()
    for x in g:
        for c in x["columns"]:
            out |= {m + c["code"] for m in x["multi"]} if x.get("multi") else {c["code"]}
    return out


CODES = valid_codes()


def no_nonfoil(t):
    return re.sub(r"non-?foil", " ", t, flags=re.I)


def classify(game, rate):
    raw = rate.get("category_raw") or ""
    s = clean_label(raw)
    s = re.sub(r"^(pok[eé]mon|magic(?: the gathering)?:?|mtg:?|disney lorcana:?|lorcana:?|one piece:?)\s*:?\s*", "", s, flags=re.I)
    s = re.sub(GAME_WORDS, " ", s, flags=re.I).strip(" :-")
    if game == "pokemon":
        cats = classify_pokemon(raw, s)
    elif game == "mtg":
        cats = classify_mtg(raw, s)
    elif game == "yugioh":
        cats = classify_yugioh(raw, s)
    elif game == "lorcana":
        cats = classify_lorcana(raw, s)
    elif game == "onepiece":
        cats = classify_onepiece(raw, s)
    elif game == "sports":
        cats = classify_sports(raw, s)
    else:
        cats = classify_small(game, raw, s)
    if cats is None:
        std = rate.get("category_std") or ""
        cats = [std] if std in CODES else []
        if std == "pkm_japanese":
            cats = ["pkm_mixed"]
    return cats


# ---------------------------------------------------------------- merge

def host(url):
    h = urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


def key_for(b):
    url = b.get("rates_url") or b.get("website") or ""
    h = host(url)
    if h in PLATFORMS:
        return h + urlparse(url).path.rstrip("/").lower()
    return host(b.get("website") or url)


def make_id(b, taken):
    url = b.get("rates_url") or b.get("website") or ""
    h = host(url)
    if h in PLATFORMS:
        base = PLATFORMS[h][0] + "-" + urlparse(url).path.rstrip("/").split("/")[-1]
    elif host(url) in ("form.jotform.com", "docs.google.com", "forms.gle", "jotform.com") and host(b.get("website") or "") in ("", host(url)):
        base = b["name"]
    else:
        parts = host(b.get("website") or url).split(".")
        base = parts[0] if len(parts) > 2 and parts[-2] in ("co", "com") and len(parts[-1]) == 2 else (parts[-2] if len(parts) >= 2 else b["name"])
        if parts and parts[-2:-1] == ["google"]:
            base = b["name"]
    s = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "store"
    out, n = s, 2
    while out in taken:
        out, n = f"{s}-{n}", n + 1
    taken.add(out)
    return out


def parse_int(s):
    try:
        return int(re.sub(r"[^\d]", "", s))
    except ValueError:
        return None


def structure(b):
    """Pull numbers the calculator needs out of the free-text fields (only when obvious)."""
    mi = b.get("minimum") or ""
    if b.get("min_usd") is None:
        m = re.search(r"\$\s?(\d+(?:\.\d+)?)", mi) or re.search(r"(\d+(?:\.\d+)?)\s?USD", mi)
        if m and not re.search(r"no minimum|none", mi, re.I):
            b["min_usd"] = float(m.group(1))
    if b.get("min_cards") is None:
        m = re.search(r"(\d[\d,]{2,})\s*(?:cards|ct|count)", mi, re.I)
        if m:
            b["min_cards"] = parse_int(m.group(1))
    sh = b.get("shipping") or ""
    if not b.get("pays_shipping"):
        if re.search(r"seller pays (?:all )?shipping|no prepaid|you pay (?:for )?shipping|responsible for (?:covering )?(?:the )?shipping|at your (?:own )?(?:cost|expense)", sh, re.I) \
                and not re.search(r"over \$?\d|above \$?\d", sh, re.I):
            b["pays_shipping"] = "no"
        elif re.search(r"prepaid|free (?:insured )?(?:shipping|label)|we (?:pay|cover)|label (?:provided|included)|reimburs", sh, re.I):
            m = re.search(r"(?:over|above|exceed\w*|more than|at least|\$)\s*\$?\s?(\d+(?:\.\d+)?)", sh, re.I)
            if re.search(r"\b(?:over|above|exceed|more than|at least|minimum|orders? of)\b", sh, re.I) and m:
                b["pays_shipping"] = "over_threshold"
                b["ship_free_over_usd"] = float(m.group(1))
            else:
                b["pays_shipping"] = "yes"
        elif re.search(r"seller pays|you pay|responsible for|buyer does not pay|not reimburs", sh, re.I):
            b["pays_shipping"] = "no"


def main():
    taken, by_key, rank = set(), {}, {}
    problems = []
    files = sorted(SOURCES.glob("*.json"))
    for f in files:
        doc = json.loads(f.read_text())
        if "buyers" not in doc:
            continue
        for raw in doc["buyers"]:
            if not raw.get("name") or not (raw.get("website") or raw.get("rates_url")):
                continue
            k = key_for(raw)
            st = raw.get("source_type")
            if not st and "second-hand" in (raw.get("notes") or "").lower():
                st = "second_hand"
            b = by_key.get(k)
            if b is None:
                b = {"id": make_id(raw, taken), "rates": [], "_src": st, "_files": []}
                by_key[k] = b
            b["_files"].append(f.name)
            better = SOURCE_RANK.get(st, 2) < SOURCE_RANK.get(b["_src"], 2)
            if better:  # first-hand data replaces second-hand rates
                b["rates"], b["_src"] = [], st
            elif SOURCE_RANK.get(st, 2) > SOURCE_RANK.get(b["_src"], 2) and b["rates"]:
                for fld in FIELDS:
                    if b.get(fld) in (None, "", []) and raw.get(fld) not in (None, "", []):
                        b[fld] = raw[fld]
                continue
            for fld in FIELDS:
                v = raw.get(fld)
                if v in (None, "", []):
                    continue
                if better or b.get(fld) in (None, "", []):
                    b[fld] = v
                elif fld in ("games", "payout_methods", "other_urls") and isinstance(v, list):
                    b[fld] = sorted(set(b[fld]) | set(v))
            have = {(r["game"], r["category_raw"].lower(), r["payout"], r["price"], r["unit"], r.get("lang")) for r in b["rates"]}
            local = set()
            b.setdefault("_cross", set())
            for r in raw.get("rates", []):
                r = dict(r)
                g = GAME_ALIASES.get(r.get("game"), r.get("game"))
                if g == "other":
                    lab = (r.get("category_raw") or "").lower()
                    g = next((v for k, v in OTHER_NAMES.items() if k in lab), "other")
                r["game"] = g
                if not isinstance(r.get("price"), (int, float)):
                    problems.append(f"{raw['name']}: non-numeric price {r.get('price')!r} ({r.get('category_raw')})")
                    continue
                pay = str(r.get("payout") or "cash").lower()
                if pay not in ("cash", "credit"):
                    r["notes"] = ((r.get("notes") or "") + "; page doesn't say cash or store credit").strip("; ")
                    pay = "cash"
                r["payout"] = pay
                r["lang"] = lang_of(r)
                r["cats"] = classify(g, r)
                if re.search(r"\[PAUSED\]|currently not buying|not currently buying|\bpaused\b", (r.get("notes") or "") + " " + r.get("category_raw", ""), re.I):
                    r["paused"] = True
                if r.get("unit") == "per_box" and not r.get("cards_per_unit"):
                    m = re.search(r"(\d[\d,]{2,})", r.get("unit_note") or "")
                    if m:
                        r["cards_per_unit"] = parse_int(m.group(1))
                n = {"per_card": 1, "per_100": 100, "per_1000": 1000}.get(r.get("unit")) or r.get("cards_per_unit")
                same_value = (g, tuple(r["cats"]), pay, r["lang"], round(r["price"] / n, 6) if n else r["price"], r.get("currency", "USD"))
                key = (g, (r.get("category_raw") or "").lower(), pay, r["price"], r.get("unit"), r["lang"])
                if key in have or (r["cats"] and same_value in b["_cross"]):
                    continue  # the same price recorded by two research passes, maybe in different units
                have.add(key)
                local.add(same_value)
                keep = ["game", "category_raw", "cats", "lang", "price", "currency", "unit", "unit_note", "cards_per_unit", "payout", "paused", "notes"]
                b["rates"].append({k2: r[k2] for k2 in keep if r.get(k2) not in (None, "")})
            b["_cross"] |= local

    buyers = list(by_key.values())

    # corrections: {"<id>": {"field": value, ..., "drop_rates": ["label", ...], "add_rates": [...]}}
    corr = json.loads(CORRECTIONS.read_text()) if CORRECTIONS.exists() else {}
    ids = {b["id"]: b for b in buyers}
    for bid, c in corr.items():
        if bid.startswith("_"):
            continue
        b = ids.get(bid)
        if not b:
            problems.append(f"corrections.json: no buyer with id {bid}")
            continue
        for k, v in c.items():
            if k == "drop_rates":
                b["rates"] = [r for r in b["rates"] if r.get("category_raw") not in v]
            elif k == "add_rates":
                for r in v:
                    r.setdefault("lang", "en")
                    r.setdefault("cats", classify(r["game"], r))
                    b["rates"].append(r)
            elif k == "recat":  # {"label": ["code", ...]}
                for r in b["rates"]:
                    if r.get("category_raw") in v:
                        r["cats"] = v[r["category_raw"]]
            else:
                b[k] = v

    for b in buyers:
        h = host(b.get("rates_url") or b.get("website"))
        if h in PLATFORMS:
            pid, pname, fee = PLATFORMS[h]
            b["platform"], b["platform_name"], b["fee_pct"] = pid, pname, fee
            b["name"] = re.sub(r"\s*\(via [^)]*\)\s*$", "", b["name"]).strip()
            b.setdefault("mail_in", True)
        b["source_type"] = b.pop("_src") or "first_party"
        b.pop("_files", None)
        b.pop("_cross", None)
        structure(b)
        b["games"] = sorted(set(b.get("games") or []) | {r["game"] for r in b["rates"]})
        m = re.search(r"(\d+) submissions? completed", b.get("reputation") or "")
        if m:
            b["completed_orders"] = int(m.group(1))
        m = re.search(r"budget remaining[^:]*:\s*([\d,.]+)\s*([A-Z]{3})?", b.get("notes") or "", re.I)
        if m:
            b["budget_left"] = float(m.group(1).replace(",", ""))
            b["budget_currency"] = m.group(2) or "USD"

    buyers.sort(key=lambda b: b["name"].lower())
    order = ["id"] + FIELDS + ["platform", "platform_name", "fee_pct", "completed_orders", "budget_left", "budget_currency", "source_type", "rates"]
    out = [{k: b[k] for k in order if k in b} for b in buyers]
    OUT.write_text(json.dumps({"generated": dt.date.today().isoformat(), "buyers": out}, indent=1, ensure_ascii=False) + "\n")

    # report
    n_rates = sum(len(b["rates"]) for b in out)
    unmapped = sum(1 for b in out for r in b["rates"] if not r["cats"])
    print(f"{len(out)} buyers, {n_rates} rate lines ({unmapped} kept for details only) from {len(files)} files")
    for p in problems:
        print("  !", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
