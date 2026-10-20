'use strict';
// Open or Sell — expected value of a pack per set, from data/ev/<game>.json (scripts/build_ev.py).

const GAME_NAMES = {
  pokemon: 'Pokémon', mtg: 'Magic', lorcana: 'Lorcana', onepiece: 'One Piece', yugioh: 'Yu-Gi-Oh!',
  riftbound: 'Riftbound', swu: 'Star Wars: Unlimited', fab: 'Flesh and Blood', digimon: 'Digimon',
  dbs: 'Dragon Ball Super', gundam: 'Gundam', unionarena: 'Union Arena', weiss: 'Weiss Schwarz',
};
const KIND = { booster: 'Booster pack', play: 'Play Booster', collector: 'Collector Booster', set: 'Set Booster', draft: 'Draft Booster', jumpstart: 'Jumpstart' };
const S = { index: null, data: {}, game: 'pokemon', set: 'all', vs: 'pack' };
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => (v == null ? '—' : '$' + (v >= 100 ? v.toFixed(0) : v.toFixed(2)));
const odds = (p) => (p >= 1 ? `${p.toFixed(p >= 10 ? 0 : 1)} per pack` : p > 0 ? `1 in ${Math.max(1, Math.round(1 / p)).toLocaleString()}` : '—');

function prefs(save) {
  try {
    if (save) localStorage.setItem('bb.open', JSON.stringify({ vs: S.vs }));
    else Object.assign(S, JSON.parse(localStorage.getItem('bb.open') || '{}'));
  } catch (e) { /* ignore */ }
}
async function load(game) {
  if (!S.data[game]) {
    const r = await fetch(`data/ev/${game}.json`, { cache: 'no-cache' });
    S.data[game] = r.ok ? await r.json() : { sets: [] };
  }
  return S.data[game];
}
const cost = (e) => (S.vs === 'pack' ? e.pack_price : e.cheapest && e.cheapest.per_pack);
const ratio = (e) => (S.vs === 'pack' ? e.ratio_pack : e.ratio_cheapest);
const beats = (e) => (S.vs === 'pack' ? e.beats_pack : e.beats_cheapest);

function verdict(e) {
  const r = ratio(e);
  if (r == null) return '<span class="muted">no price</span>';
  if (r >= 1.1) return `<span class="good">Open it</span>`;
  if (r >= 0.9) return `<span class="muted">Close call</span>`;
  return `<span class="bad">Sell it sealed</span>`;
}
function ret(r) {
  if (r == null) return '—';
  return `${Math.round(r * 100)}¢ <span class="u">per $1</span>`;
}

function renderTabs() {
  const games = Object.keys(S.index.games).filter((g) => S.index.games[g].sets);
  $('#tabs').innerHTML = games.map((g) => `<button role="tab" type="button" data-game="${g}" aria-selected="${g === S.game}">${esc(GAME_NAMES[g] || g)}<span class="n">${S.index.games[g].sets}</span></button>`).join('');
}
function key(e) { return `${e.id}-${e.kind}`; }

function renderSelect(data) {
  $('#set').innerHTML = '<option value="all">All sets: ranked</option>' +
    data.sets.map((e) => `<option value="${key(e)}"${key(e) === S.set ? ' selected' : ''}>${esc(e.name)}${e.kind !== 'booster' ? ' · ' + esc(KIND[e.kind] || e.kind) : ''}</option>`).join('');
  if (S.set === 'all') $('#set').value = 'all';
}

function renderLegend() {
  const a = S.index.assumptions || {};
  $('#legend').innerHTML = (S.vs === 'pack'
    ? 'Compared with what <b>one sealed pack</b> sells for: should you open the packs you have, or sell them sealed?'
    : 'Compared with the <b>cheapest way to buy packs</b> (usually a booster box): does buying sealed to open and sell the cards pay?')
    + ` <b>Return per $1</b>: what the cards would bring after selling costs, for every dollar the pack is worth sealed. Above 100¢ opening wins on average, but most single packs still come out below average; the <b>chance</b> column says how often one pack beats its price.`;
  $('#foot').innerHTML = `Card prices as of ${esc(S.index.prices_as_of || S.index.generated)}. Selling costs: ${Math.round((a.sell_fee || 0.13) * 100)}% fees plus $${(a.handling_per_card ?? 0.5).toFixed(2)} handling per card sold; cheaper cards counted at bulk-buyer rates. Every card of a rarity is assumed equally likely. Spread from ${(a.simulated_packs || 5000).toLocaleString()} simulated packs per set.`;
}

function ranked(data) {
  const rows = data.sets.filter((e) => cost(e) != null).sort((a, b) => (ratio(b) ?? -1) - (ratio(a) ?? -1));
  let html = '<div class="table-wrap"><table class="rates sealed"><thead><tr><th class="store">Set</th><th>Pack costs</th><th>Avg value opened<span class="u">market</span></th><th>If you sell the cards</th><th>Return per $1</th><th>Typical pack<span class="u">median, if sold</span></th><th>Chance a pack beats its cost</th><th>Verdict</th></tr></thead><tbody>';
  for (const e of rows) {
    const r = ratio(e);
    html += `<tr class="row" tabindex="0" data-key="${key(e)}"><td class="store"><span class="nm">${esc(e.name)}</span><span class="meta">${esc(KIND[e.kind] || e.kind)} · ${esc(e.released)} · ${esc(e.confidence || '')}</span></td>` +
      `<td class="v">${money(cost(e))}${S.vs === 'cheapest' && e.cheapest ? `<span class="fx">${esc(e.cheapest.type)}</span>` : ''}</td>` +
      `<td class="v">${money(e.ev_market)}</td><td class="v">${money(e.ev_sold)}</td>` +
      `<td class="v ${r >= 1.1 ? 'r1' : r >= 0.9 ? 'r2' : ''}">${ret(r)}</td>` +
      `<td class="v">${money(e.median_sold)}</td><td class="v">${beats(e) != null ? Math.round(beats(e) * 100) + '%' : '—'}</td><td class="v">${verdict(e)}</td></tr>`;
  }
  html += '</tbody></table></div><p class="hint">Click a set for what drives its value.</p>';
  const none = data.sets.filter((e) => cost(e) == null).length;
  if (none) html += `<p class="hint">${none} more set${none > 1 ? 's have' : ' has'} no sealed price to compare with.</p>`;
  return html;
}

function detail(e) {
  const c = cost(e);
  let html = `<h2 class="set-h">${esc(e.name)} <small>${esc(KIND[e.kind] || e.kind)} · released ${esc(e.released)}</small></h2>`;
  html += '<div class="kpis">' +
    `<div><span>${S.vs === 'pack' ? 'One sealed pack' : 'Cheapest per pack'}</span><b>${money(c)}</b>${S.vs === 'cheapest' && e.cheapest ? `<small>${esc(e.cheapest.name)}</small>` : ''}</div>` +
    `<div><span>Average pack, opened (market)</span><b>${money(e.ev_market)}</b></div>` +
    `<div><span>Average pack, if you sell the cards</span><b>${money(e.ev_sold)}</b><small>${verdict(e)}</small></div>` +
    `<div><span>Typical pack (median)</span><b>${money(e.median_sold)}</b><small>1 in 10 is worth over ${money(e.p90_sold)}</small></div>` +
    `<div><span>Chance one pack beats ${money(c)}</span><b>${beats(e) != null ? Math.round(beats(e) * 100) + '%' : '—'}</b></div>` +
    `<div><span>If you bulked every card</span><b>${money(e.bulk_floor)}</b><small>at bulk-buyer rates</small></div>` +
    '</div>';
  html += '<h3 class="grp-h">Where the value comes from</h3><div class="table-wrap"><table class="rates sealed"><thead><tr><th class="store">Pull</th><th>How often</th><th>Avg card<span class="u">market</span></th><th>Adds to a pack<span class="u">if sold</span></th><th>Share</th><th class="store">Top cards</th></tr></thead><tbody>';
  const tot = e.breakdown.reduce((s, r) => s + r.net, 0) || 1;
  for (const r of e.breakdown) {
    html += `<tr><td class="store">${esc(r.label)}<span class="meta">${r.pool} card${r.pool === 1 ? '' : 's'}</span></td><td class="v">${odds(r.per_pack)}</td><td class="v">${money(r.avg)}</td><td class="v">${money(r.net)}</td><td class="v">${Math.round((r.net / tot) * 100)}%</td>` +
      `<td class="v txt">${r.top.map(([n, p]) => `${esc(n)} <span class="muted">${money(p)}</span>`).join('<br>')}</td></tr>`;
  }
  html += '</tbody></table></div>';
  html += `<p class="hint">Pull rates: ${esc(e.confidence || 'unknown')} (${esc(e.match)})${e.sources.length ? ' — ' + e.sources.map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">source ${i + 1}</a>`).join(', ') : ''}.` +
    (e.missing && e.missing.length ? ` Not priced (no matching cards yet): ${esc(e.missing.join('; '))}.` : '') + '</p>';
  return html;
}

async function render() {
  renderTabs();
  const data = await load(S.game);
  if (S.set !== 'all' && !data.sets.some((e) => key(e) === S.set)) S.set = 'all';
  renderSelect(data);
  renderLegend();
  document.querySelectorAll('[data-vs]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.vs === S.vs)));
  $('#view').innerHTML = S.set === 'all' ? ranked(data) : detail(data.sets.find((e) => key(e) === S.set));
  history.replaceState(null, '', `#${S.game}${S.set === 'all' ? '' : '/' + S.set}`);
}

function bind() {
  $('#tabs').addEventListener('click', (e) => { const t = e.target.closest('[data-game]'); if (t) { S.game = t.dataset.game; S.set = 'all'; render(); } });
  $('#set').addEventListener('change', (e) => { S.set = e.target.value; render(); window.scrollTo({ top: 0 }); });
  document.querySelectorAll('[data-vs]').forEach((b) => b.addEventListener('click', () => { S.vs = b.dataset.vs; prefs(true); render(); }));
  $('#view').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-key]'); if (tr) { S.set = tr.dataset.key; render(); window.scrollTo({ top: 0 }); } });
  $('#view').addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-key]')) { e.preventDefault(); e.target.click(); } });
}

async function init() {
  prefs(false);
  const r = await fetch('data/ev/index.json', { cache: 'no-cache' });
  S.index = r.ok ? await r.json() : { games: {} };
  const [g, s] = location.hash.slice(1).split('/');
  if (g && S.index.games[g]) { S.game = g; if (s) S.set = s; }
  bind();
  render();
}
init();
