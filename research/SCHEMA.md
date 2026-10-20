# Bulk buyer record format (shared by all research agents)

Write a single JSON file: `{"buyers": [ ... ], "leads_unchecked": [ ... ], "notes": "..."}`

Each buyer:

```json
{
  "name": "Store name as it brands itself",
  "website": "https://homepage",
  "rates_url": "https://the exact page the rates came from",
  "other_urls": ["terms/faq/shipping pages you read"],
  "country": "US",            // ISO-2
  "region": "PA",             // state/province, if known
  "city": "",
  "mail_in": true,            // accepts shipped bulk
  "in_person": false,         // physical store that buys over the counter
  "games": ["pokemon", "mtg", "yugioh", "lorcana", "onepiece", "fab", "digimon", "swu", "dbs", "weiss", "sports", "other"],
  "payout_methods": ["paypal", "check", "venmo", "zelle", "ach", "cash", "store_credit", "gift_card"],
  "store_credit_bonus": "e.g. '+25% in store credit' or null",
  "minimum": "minimum quantity / value to submit, verbatim-ish",
  "shipping": "who pays shipping; prepaid label threshold; drop-off options",
  "volume_bonus": "any tiered bonus for large submissions, or null",
  "condition_rules": "condition requirements (e.g. NM-LP only, no water damage)",
  "sorting_rules": "how cards must be sorted/counted; what is rejected; what happens to rejects",
  "excluded": "what they do NOT buy (e.g. energy, basic lands, pre-2010, Japanese)",
  "turnaround": "processing time / payout time",
  "process": "how to submit (form, email, app, account needed?)",
  "rates_last_updated": "date shown on the page, if any",
  "status": "active | paused | closed | unclear",
  "reputation": "anything notable (Reddit complaints, BBB, years in business) — optional",
  "checked_on": "2026-10-20",
  "rates": [
    {
      "game": "pokemon",
      "category_raw": "exact label the store uses",
      "category_std": "one of the codes below (best fit) or 'other'",
      "price": 6.00,           // number, USD unless 'currency' says otherwise
      "currency": "USD",
      "unit": "per_1000",      // per_card | per_100 | per_1000 | per_lb | per_box | flat
      "unit_note": "if per_box/per_lb, how many cards/what box",
      "payout": "cash",        // cash | credit  (cash = any money payout: PayPal/check/etc.)
      "notes": "conditions on this line, e.g. 'English only', 'must be sorted by set', 'min 500'"
    }
  ]
}
```

If a store quotes both cash and store credit for a line, write two rate entries.
If a store quotes a range ("$5-8/1000"), use the LOW number in `price` and put the range in `notes`.
Never invent a number. If a page says "contact us for pricing", record the buyer with `rates: []` and say so in `notes`.

## Standard category codes (`category_std`)

Pokemon
- `pkm_cu` commons & uncommons (non-holo, non-reverse)
- `pkm_energy` basic energy
- `pkm_rh` reverse holos
- `pkm_rare` non-holo rares
- `pkm_holo` holo rares
- `pkm_ex` double rares / V / VMAX / VSTAR / GX / EX / ex (regular, non-full-art)
- `pkm_fullart` full arts / ultra rares / trainer gallery / full-art trainers
- `pkm_ir` illustration rares
- `pkm_sir` special illustration / hyper / gold / secret rares
- `pkm_ace` ACE SPEC / radiant / amazing rares / shiny
- `pkm_japanese` Japanese / non-English bulk
- `pkm_code` code cards
- `pkm_mixed` mixed / unsorted bulk
- `pkm_other`

Magic: The Gathering
- `mtg_cu` commons & uncommons
- `mtg_rare` rares & mythics (bulk rares)
- `mtg_mythic` mythics only (if priced separately from rares)
- `mtg_foil_cu` foil commons & uncommons
- `mtg_foil_rare` foil rares & mythics
- `mtg_land` basic lands
- `mtg_token` tokens / art cards / emblems
- `mtg_foreign` non-English
- `mtg_mixed` mixed / unsorted bulk
- `mtg_other`

Yu-Gi-Oh: `ygo_common`, `ygo_rare`, `ygo_super`, `ygo_ultra`, `ygo_secret`, `ygo_mixed`, `ygo_other`
Lorcana: `lor_cu`, `lor_rare`, `lor_super`, `lor_legendary`, `lor_foil`, `lor_mixed`, `lor_other`
One Piece: `op_cu`, `op_rare`, `op_sr`, `op_leader`, `op_mixed`, `op_other`
Any other TCG (fab, digimon, swu, dbs, weiss, other): `<game>_cu`, `<game>_rare`, `<game>_foil`, `<game>_mixed`, `<game>_other`
Sports: `sports_base` (base cards), `sports_rookie`, `sports_insert` (inserts/parallels), `sports_mixed`, `sports_other`
