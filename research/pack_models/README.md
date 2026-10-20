# Pack model format (for expected-value calculations)

Goal: for a booster pack of a given set, the probability of each rarity in each slot, so a script can
compute expected value = sum over slots of P(rarity) x average market price of that set's cards of that
rarity (in the right finish). Rarity names MUST be the exact labels TCGplayer uses (see
research/rarity_labels.json in the scratchpad for samples; Pokemon uses full words like "Double Rare",
MTG uses letters C/U/R/M/L/T/S, One Piece uses C/UC/R/SR/SEC/L/SP etc.). Finish names are TCGplayer
price subtypes: "Normal", "Holofoil", "Reverse Holofoil", "Foil", "Cold Foil" (use what the game uses).

Write JSON: {"models": [ ... ], "notes": "..."}

Each model:
{
  "game": "pokemon",
  "id": "short-id",
  "applies_to": {"set_names": ["exact TCGplayer set names if per-set"], "set_codes": ["SVI", "PAL"],
                 "from": "2023-03-31", "to": null, "description": "which sets this covers"},
  "pack": "booster",                       // mtg: "play" | "collector" | "set" | "draft"
  "cards_per_pack": 10,
  "slots": [
    {"name": "commons", "count": 4,
     "outcomes": [{"rarity": ["Common"], "finish": "Normal", "p": 1.0}]},
    {"name": "rare slot", "count": 1,
     "outcomes": [
       {"rarity": ["Double Rare"], "finish": "Holofoil", "p": 0.2},
       {"rarity": ["Rare"], "finish": "Holofoil", "p": 0.8}
     ]},
    {"name": "pattern reverse", "count": 1,
     "outcomes": [{"rarity": ["Common", "Uncommon", "Rare"], "finish": "Holofoil", "name_regex": "Poke Ball Pattern", "p": 0.3}, ...]}
  ],
  "confidence": "official" | "large community sample" | "small community sample" | "estimate",
  "sources": ["url", ...],
  "notes": "assumptions, e.g. 'odds within a rarity assumed equal'"
}
Rules:
- Outcome probabilities within a slot must sum to 1 (put the leftover on the most common outcome).
- Convert "1 in 15 packs" to p = 0.0667. Convert per-box ratios ("4 per 36-pack box") to per-pack p.
- Prefer official odds (Wizards publishes MTG booster contents; Konami/Bandai sometimes publish box
  ratios); otherwise large community opening samples (TCGplayer articles, PokeBeach, large spreadsheets).
  Always cite. Never invent numbers; if you must estimate, set confidence "estimate" and explain.
- One model can cover many sets with the same structure; add per-set models where odds differ a lot.
