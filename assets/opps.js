'use strict';
// Opportunities — renders data/opportunities.json (scripts/build_opportunities.py).

const GAME_NAMES = {
  pokemon: 'Pokémon', mtg: 'Magic', lorcana: 'Lorcana', onepiece: 'One Piece', yugioh: 'Yu-Gi-Oh!',
  riftbound: 'Riftbound', swu: 'Star Wars: Unlimited', fab: 'Flesh and Blood', digimon: 'Digimon',
  dbs: 'Dragon Ball Super', gundam: 'Gundam', unionarena: 'Union Arena', weiss: 'Weiss Schwarz',
};
const KIND = { booster: '', play: 'Play Booster', collector: 'Collector Booster', set: 'Set Booster', draft: 'Draft Booster' };
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => (v == null ? '—' : '$' + (v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(2)));
const S = { data: null, games: null, limit: 15 };

function prefs(save) {
  try {
    if (save) localStorage.setItem('bb.opps', JSON.stringify([...S.games]));
    else { const g = JSON.parse(localStorage.getItem('bb.opps') || 'null'); if (g) S.games = new Set(g); }
  } catch (e) { /* ignore */ }
}

function conf(c) {
  const map = { official: ['official', 'good'], 'large community sample': ['large sample', 'good'], 'small community sample': ['small sample', 'muted'], estimate: ['estimate', 'bad'] };
  const [t, cls] = map[c] || [c || 'unknown', 'muted'];
  return `<span class="${cls}" title="How the pack odds were measured">${esc(t)}</span>`;
}

function section(id, title, blurb, rows, head, cells) {
  const list = rows.filter((r) => S.games.has(r.game));
  let html = `<section id="${id}"><h2>${title} <small class="muted">${list.length}</small></h2><p class="hint">${blurb}</p>`;
  if (!list.length) return html + '<p class="empty">Nothing right now for the games selected.</p></section>';
  html += `<div class="table-wrap"><table class="rates sealed"><thead><tr><th class="store">What</th>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>`;
  for (const r of list.slice(0, S.limit)) {
    const what = r.url ? `<a class="nm" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.product || r.set)}</a>` : `<span class="nm">${esc(r.product || r.set)}</span>`;
    html += `<tr><td class="store">${what}<span class="meta">${esc(GAME_NAMES[r.game] || r.game)} · ${esc(r.set)}${r.kind && KIND[r.kind] ? ' · ' + KIND[r.kind] : ''}${r.presale ? ' <span class="tag">pre-order</span>' : ''}${r.thin ? ' <span class="tag" title="The pack price is more than double what packs cost in the box: it may rest on a few sales or listings. Check sold listings first.">thin market?</span>' : ''}</span></td>${cells(r).map((c) => `<td class="v">${c}</td>`).join('')}</tr>`;
  }
  html += '</tbody></table></div>';
  if (list.length > S.limit) html += `<p class="hint">${list.length - S.limit} more not shown.</p>`;
  return html + '</section>';
}

function render() {
  const d = S.data;
  const a = d.assumptions || {};
  const fee = Math.round((a.sell_fee || 0.13) * 100);
  let html = '';
  html += section('open', 'Packs worth more opened than sealed',
    `On average, the cards in one of these packs sell for at least 10% more than the sealed pack, after ${fee}% fees and handling, with cheap cards counted at bulk prices. Most individual packs still land below the average; "chance" is how often one pack beats its price. Details on <a href="open.html">Open or sell</a>.`,
    d.open, ['Sealed pack', 'Avg if sold', 'Return per $1', 'Typical pack', 'Chance', 'Pull-rate data'],
    (r) => [money(r.cost), money(r.ev_sold), `<span class="good">${Math.round(r.ratio * 100)}¢</span>`, money(r.median_sold) + (r.lottery ? `<span class="fx" title="${esc(r.top_card)}">lottery: one card carries it</span>` : ''), r.beats != null ? Math.round(r.beats * 100) + '%' : '—', conf(r.confidence)]);
  if (d.suspect) html += `<p class="hint">${d.suspect} more set${d.suspect > 1 ? 's look' : ' looks'} far better opened than sealed, but on thin pull-rate data or a single huge card. They're on <a href="open.html">Open or sell</a> marked "check".</p>`;
  html += section('buy', 'Sealed worth buying to open',
    'Buying the cheapest way to get packs (usually a box) and selling the cards pays more than it costs, on average. A long run of boxes evens out the luck; one box may not.',
    d.buy_to_open, ['Cost per pack', 'Bought as', 'Avg if sold', 'Return per $1', 'Chance per pack', 'Pull-rate data'],
    (r) => [money(r.cost), esc(r.via), money(r.ev_sold), `<span class="good">${Math.round(r.ratio * 100)}¢</span>` + (r.lottery ? `<span class="fx" title="${esc(r.top_card)}">lottery</span>` : ''), r.beats != null ? Math.round(r.beats * 100) + '%' : '—', conf(r.confidence)]);
  html += section('split', 'Boxes worth more as single packs',
    `The box costs less than its packs sell for one at a time, after ${fee}% fees and $${(a.pack_handling ?? 1).toFixed(2)} handling per pack. Box cost is the cheapest listing; pack price is the lower of the market price and the cheapest listing, because that's what you'd be competing with.`,
    d.split, ['Box costs', 'Packs', 'Per pack in box', 'Pack sells for', 'Profit if all sell', 'Margin'],
    (r) => [money(r.box_cost), r.packs, money(r.per_pack), money(r.pack_price), `<span class="good">${money(r.profit)}</span>`, Math.round(r.margin * 100) + '%']);
  html += section('flips', 'Selling far above retail',
    'Products from the last 12 months selling for 1.5× their MSRP or more. If you can buy at the shelf price (stores, preorders), these resell at a profit, but supply is limited and prices fall as print runs catch up.',
    d.flips, ['Market', 'MSRP', 'Market ÷ MSRP'],
    (r) => [money(r.market), money(r.msrp), `<span class="good">${r.ratio}×</span>`]);
  html += section('under', 'Cheaper online than in stores',
    'Products from the last two years selling below their MSRP. If you want to play or open these, the secondary market beats the shelf.',
    d.under_msrp, ['Market', 'MSRP', 'Market ÷ MSRP'],
    (r) => [money(r.market), money(r.msrp), `<span class="bad">${r.ratio}×</span>`]);
  html += `<p class="hint">Built ${esc(d.generated)} from daily prices. MSRPs are official US prices where published (Yu-Gi-Oh! and Star Wars: Unlimited publish none).</p>`;
  $('#view').innerHTML = html;
}

function renderGames() {
  const games = [...new Set(['open', 'buy_to_open', 'split', 'flips', 'under_msrp'].flatMap((k) => S.data[k].map((r) => r.game)))];
  games.sort((a, b) => Object.keys(GAME_NAMES).indexOf(a) - Object.keys(GAME_NAMES).indexOf(b));
  if (!S.games) S.games = new Set(games);
  $('#games').innerHTML = '<span class="seg-label">Games</span>' + games.map((g) => `<label><input type="checkbox" data-g="${g}"${S.games.has(g) ? ' checked' : ''}> ${esc(GAME_NAMES[g] || g)}</label>`).join('');
  $('#games').addEventListener('change', (e) => {
    const g = e.target.dataset.g;
    if (!g) return;
    if (e.target.checked) S.games.add(g); else S.games.delete(g);
    prefs(true);
    render();
  });
}

async function init() {
  const r = await fetch('data/opportunities.json', { cache: 'no-cache' });
  S.data = r.ok ? await r.json() : { open: [], buy_to_open: [], split: [], flips: [], under_msrp: [] };
  prefs(false);
  renderGames();
  render();
}
init();
