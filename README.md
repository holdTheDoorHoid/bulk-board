# Bulk Board

**Who pays the most for your bulk trading cards?** Bulk Board compares the published bulk buy
rates of card shops and mail-in bulk buyers for Pokémon, Magic: The Gathering, Yu-Gi-Oh!,
Lorcana, One Piece, sports cards and more — one tab per game, stores down the side, card types
across the top, the top payer in each column highlighted.

Site: https://holdthedoorhoid.github.io/bulk-board/

- Sort any column; filter mail-in vs. local stores; include or exclude store credit.
- Click a store for its minimums, shipping rules, payout methods, condition and sorting rules.
- **Where should I send my bulk?** — enter your counts and the calculator prices your lot at every
  store, subtracts the shipping you'd pay, flags unmet minimums, and says whether splitting the lot
  across stores is worth the extra postage.
- Every price links to the store page it came from and shows when it was last confirmed.

**Pack value** (`sealed.html`): every sealed product of a set (booster box, ETB, bundle, blister, tin,
collection, case) priced per pack and compared with buying single packs and with MSRP.

**Open or sell** (`open.html`): the expected value of a pack for every set, from pull rates and current
card prices, before and after selling costs, with the chance a single pack beats its price.

**Opportunities** (`opportunities.html`): packs worth opening, sealed worth buying to open, boxes worth
more as single packs, products selling far above MSRP (retail flips) and below it.

## How the data works

| File | What it is |
| --- | --- |
| `data/buyers.json` | What the site reads: every buyer and rate, built by `scripts/build_data.py`. |
| `data/games.json` | The columns shown for each game. |
| `data/watch.json` | Written by the weekly check: when each page last matched, and which changed. |
| `data/fx.json` | Exchange rates for non-US stores (ECB, weekly). |
| `research/sources/` | The research files the table is built from (one per research pass). |
| `research/corrections.json` | Hand fixes applied on top of the research. |

`scripts/refresh.py` runs every Monday from `.github/workflows/refresh.yml`. It re-downloads each
store's rate page and compares every money amount on it with last week's. Unchanged pages get a
new "confirmed" date; changed pages are flagged on the site and listed in a `rate-check` issue
until someone re-checks them and runs `scripts/refresh.py --accept <store-id>`.

`scripts/fetch_tcgbulk.py` refreshes the ~150 TCG Bulk marketplace buyers from the public data
the TCG Bulk app reads (display name, country/state and prices only — nothing personal).

`scripts/fetch_sealed.py` downloads sealed-product and card prices from TCGCSV (daily, ~1,900
requests); `scripts/build_sealed.py` works out pack contents (`research/sealed_msrp.json`,
`research/sealed_overrides.json`); `scripts/build_ev.py` applies the pull-rate models in
`research/pack_models.json`; `scripts/build_opportunities.py` writes `data/opportunities.json`.
All four run every evening from `.github/workflows/sealed.yml`.

`scripts/build_data.py` rebuilds `data/buyers.json` from `research/sources/*.json` and
`research/corrections.json`. It maps every store's own category wording onto the site's columns;
the store's wording is kept and shown on hover. To add a store, drop a research file in the
format of `research/SCHEMA.md` into `research/sources/` and re-run it.

No build step: it's plain HTML, CSS and JavaScript. Preview locally with
`python3 -m http.server 8796` in this folder and open http://localhost:8796.

## Contributing

Missing a store, or a rate is wrong? Open an issue with the
[suggest a store](../../issues/new?template=suggest-store.yml) or
[wrong rate](../../issues/new?template=wrong-rate.yml) form.

Not affiliated with any store listed. Rates are facts copied from each store's public page;
always confirm with the store before shipping. MIT licensed — maintained by LSOH.
