'use strict';
// Pack Value — price per pack for every sealed product in a set, from data/sealed/<game>.json.

const GAME_NAMES = {
  pokemon: 'Pokémon', mtg: 'Magic', lorcana: 'Lorcana', onepiece: 'One Piece', yugioh: 'Yu-Gi-Oh!',
  riftbound: 'Riftbound', swu: 'Star Wars: Unlimited', fab: 'Flesh and Blood', digimon: 'Digimon',
  dbs: 'Dragon Ball Super', gundam: 'Gundam', unionarena: 'Union Arena', weiss: 'Weiss Schwarz',
};
const KIND_NAMES = {
  booster: 'booster packs', play: 'Play Boosters', collector: 'Collector Boosters', set: 'Set Boosters',
  draft: 'Draft Boosters', jumpstart: 'Jumpstart packs', mega: 'Mega Packs', other: 'packs from other sets', carbonite: 'Carbonite packs', premium: 'Premium packs',
};
// columns in the all-sets overview, per game
const KEY_TYPES = {
  pokemon: ['Booster box', 'Half booster box', 'Elite Trainer Box', 'Booster bundle'],
  mtg: ['Play Booster box', 'Bundle', 'Collector Booster box'],
};

const S = { index: null, data: {}, game: 'pokemon', set: 'all', basis: 'market', cases: false, pre: true };
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => (v == null ? '—' : '$' + (v >= 100 ? v.toFixed(0) : v.toFixed(2)));

function prefs(save) {
  try {
    if (save) localStorage.setItem('bb.sealed', JSON.stringify({ basis: S.basis, cases: S.cases, pre: S.pre }));
    else Object.assign(S, JSON.parse(localStorage.getItem('bb.sealed') || '{}'));
  } catch (e) { /* private window: ignore */ }
}

async function load(game) {
  if (!S.data[game]) {
    const r = await fetch(`data/sealed/${game}.json`, { cache: 'no-cache' });
    S.data[game] = r.ok ? await r.json() : { sets: [] };
  }
  return S.data[game];
}

const price = (r) => (S.basis === 'low' ? r.low : r.market);
const isCase = (r) => /case/i.test(r.type);
const shown = (r) => (S.cases || !isCase(r)) && (S.pre || !r.presale) && price(r) != null;
const kinds = (r) => Object.keys(r.contents);
const single = (r) => kinds(r).length === 1;

// What one pack of each kind costs on its own in this set (median of single-pack listings).
function baseline(set) {
  const out = {};
  const by = {};
  for (const r of set.products) {
    if (!single(r) || r.packs !== 1 || /blister|sleeved|art bundle|sample/i.test(r.name) || price(r) == null) continue;
    (by[kinds(r)[0]] ||= []).push(price(r));
  }
  for (const [k, v] of Object.entries(by)) {
    v.sort((a, b) => a - b);
    out[k] = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
  }
  return out;
}
function perPack(r) { return single(r) && price(r) != null ? price(r) / r.packs : null; }
function vsSingles(r, base) {
  if (price(r) == null || !kinds(r).every((k) => base[k])) return null;
  const value = Object.entries(r.contents).reduce((s, [k, n]) => s + base[k] * n, 0);
  return price(r) / value - 1;
}
function pct(v) {
  if (v == null) return '<span class="muted">—</span>';
  const p = Math.round(v * 100);
  if (Math.abs(p) < 1) return '<span class="muted">same</span>';
  return p < 0 ? `<span class="good">${-p}% cheaper</span>` : `<span class="bad">${p}% more</span>`;
}
function inside(r) {
  return Object.entries(r.contents).map(([k, n]) => `${n} ${n === 1 ? KIND_NAMES[k].replace(/s$/, '').replace(/packs$/, 'pack') : KIND_NAMES[k]}`).join(' + ');
}
function mainKind(game, base) {
  for (const k of ['booster', 'play', 'draft', 'set', 'collector', 'jumpstart']) if (base[k]) return k;
  return Object.keys(base)[0];
}

// ---------------------------------------------------------------- rendering

function renderTabs() {
  const games = Object.keys(S.index.games).filter((g) => S.index.games[g].products);
  $('#tabs').innerHTML = games.map((g) => `<button role="tab" type="button" data-game="${g}" aria-selected="${g === S.game}">${esc(GAME_NAMES[g] || g)}<span class="n">${S.index.games[g].sets}</span></button>`).join('');
}

function renderSetSelect(data) {
  $('#set').innerHTML = '<option value="all">All sets: overview</option>' +
    data.sets.map((s) => `<option value="${s.id}"${String(s.id) === String(S.set) ? ' selected' : ''}>${esc(s.name)} (${s.released.slice(0, 7)})</option>`).join('');
  if (S.set === 'all') $('#set').value = 'all';
}

function renderLegend() {
  const basis = S.basis === 'low'
    ? 'Prices are the <b>cheapest listing</b> right now: one seller, maybe one copy, before shipping.'
    : 'Prices are TCGplayer <b>market prices</b>: what each product has recently sold for, before shipping.';
  $('#legend').innerHTML = `${basis} "vs one pack" compares the product with buying the same packs one at a time in that set. ` +
    'Promo cards, sleeves, dice and other extras are listed but <b>not counted</b>, so a product that costs a little more per pack may still be worth it for its promo.';
  const ix = S.index;
  $('#foot').innerHTML = `Prices as of ${esc(ix.prices_as_of || ix.generated)}. Pack counts come from each product's own description when it states one ("from listing"), otherwise from the usual contents for that kind of product ("usual count"). Product links go to TCGplayer.`;
}

function overview(data) {
  const types = KEY_TYPES[S.game] || ['Booster box'];
  let html = `<div class="table-wrap"><table class="rates sealed"><thead><tr><th class="store">Set</th><th>One pack</th><th>Cheapest per pack</th><th>vs one pack</th>` +
    types.map((t) => `<th>${esc(t)}<span class="u">per pack</span></th>`).join('') + '</tr></thead><tbody>';
  for (const s of data.sets) {
    const base = baseline(s);
    const mk = mainKind(S.game, base);
    const rows = s.products.filter((r) => shown(r) && single(r) && kinds(r)[0] === (mk || kinds(r)[0]));
    if (!rows.length) continue;
    const best = rows.reduce((a, b) => (perPack(b) < perPack(a) ? b : a));
    const cell = (t) => {
      const c = rows.filter((r) => r.type === t && perPack(r) != null).sort((a, b) => perPack(a) - perPack(b))[0];
      return c ? `<td class="v" title="${esc(c.name)}">${money(perPack(c))}<span class="fx">${pct(vsSingles(c, base))}</span></td>` : '<td class="v none">—</td>';
    };
    html += `<tr class="row" tabindex="0" data-set="${s.id}"><td class="store"><span class="nm">${esc(s.name)}</span><span class="meta">${esc(s.released)}</span></td>` +
      `<td class="v">${base[mk] ? money(base[mk]) : '—'}</td>` +
      `<td class="v r1" title="${esc(best.name)}">${money(perPack(best))}<span class="fx">${esc(best.type)}</span></td>` +
      `<td class="v">${pct(vsSingles(best, base))}</td>` + types.map(cell).join('') + '</tr>';
  }
  html += '</tbody></table></div><p class="hint">Click a set to see every product.</p>';
  return html;
}

function setView(s) {
  const base = baseline(s);
  const rows = s.products.filter(shown);
  const groups = {};
  for (const r of rows) {
    const key = single(r) ? kinds(r)[0] : 'mixed';
    (groups[key] ||= []).push(r);
  }
  const order = ['booster', 'play', 'collector', 'draft', 'set', 'jumpstart', 'mega', 'mixed'];
  let html = `<h2 class="set-h">${esc(s.name)} <small>released ${esc(s.released)}</small></h2>`;
  const bl = Object.entries(base).map(([k, v]) => `one ${KIND_NAMES[k].replace(/s$/, '').replace(/packs$/, 'pack')}: <b>${money(v)}</b>`).join(' · ');
  if (bl) html += `<p class="hint">On its own, ${bl}.</p>`;
  for (const key of order) {
    const g = groups[key];
    if (!g) continue;
    g.sort((a, b) => (perPack(a) ?? (vsSingles(a, base) ?? 9) + 1e6) - (perPack(b) ?? (vsSingles(b, base) ?? 9) + 1e6));
    const bestPP = Math.min(...g.map((r) => perPack(r) ?? Infinity));
    html += `<h3 class="grp-h">${key === 'mixed' ? 'Products with more than one kind of pack' : esc(KIND_NAMES[key][0].toUpperCase() + KIND_NAMES[key].slice(1))}</h3>`;
    html += '<div class="table-wrap"><table class="rates sealed"><thead><tr><th class="store">Product</th><th>Inside</th><th>Price</th><th>Per pack</th><th>vs one pack</th><th>Retail per pack</th></tr></thead><tbody>';
    for (const r of g) {
      const pp = perPack(r);
      const best = pp != null && pp === bestPP;
      const tags = [r.presale ? '<span class="tag">pre-order</span>' : '', `<span class="tag" title="${r.count_source === 'rule' ? 'The listing does not say; this is the usual count for this kind of product' : 'Pack count read from the product listing'}">${r.count_source === 'rule' ? 'usual count' : 'from listing'}</span>`].join('');
      html += `<tr><td class="store"><a class="nm" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a><span class="meta">${esc(r.type)} ${tags}</span></td>` +
        `<td class="v txt">${esc(inside(r))}${r.extras.length ? `<span class="fx">+ ${esc(r.extras.join(', '))}</span>` : ''}</td>` +
        `<td class="v">${money(price(r))}</td>` +
        `<td class="v${best ? ' r1' : ''}">${best ? '<span class="star" aria-label="cheapest per pack">★</span>' : ''}${money(pp)}</td>` +
        `<td class="v">${pct(vsSingles(r, base))}</td>` +
        `<td class="v">${r.msrp_per_pack ? money(r.msrp_per_pack) + `<span class="fx">MSRP ${money(r.msrp)}</span>` : '<span class="muted">—</span>'}</td></tr>`;
    }
    html += '</tbody></table></div>';
  }
  if (!rows.length) html += '<p class="empty">No products match these options.</p>';
  return html;
}

async function render() {
  renderTabs();
  const data = await load(S.game);
  if (S.set !== 'all' && !data.sets.some((s) => String(s.id) === String(S.set))) S.set = 'all';
  renderSetSelect(data);
  renderLegend();
  document.querySelectorAll('[data-basis]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.basis === S.basis)));
  $('#f-cases').checked = S.cases;
  $('#f-pre').checked = S.pre;
  $('#view').innerHTML = S.set === 'all' ? overview(data) : setView(data.sets.find((s) => String(s.id) === String(S.set)));
  history.replaceState(null, '', `#${S.game}${S.set === 'all' ? '' : '/' + S.set}`);
}

function bind() {
  $('#tabs').addEventListener('click', (e) => {
    const t = e.target.closest('[data-game]');
    if (t) { S.game = t.dataset.game; S.set = 'all'; render(); }
  });
  $('#set').addEventListener('change', (e) => { S.set = e.target.value; render(); window.scrollTo({ top: 0 }); });
  document.querySelectorAll('[data-basis]').forEach((b) => b.addEventListener('click', () => { S.basis = b.dataset.basis; prefs(true); render(); }));
  $('#f-cases').addEventListener('change', (e) => { S.cases = e.target.checked; prefs(true); render(); });
  $('#f-pre').addEventListener('change', (e) => { S.pre = e.target.checked; prefs(true); render(); });
  $('#view').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-set]');
    if (tr && !e.target.closest('a')) { S.set = tr.dataset.set; render(); window.scrollTo({ top: 0 }); }
  });
  $('#view').addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-set]')) { e.preventDefault(); e.target.click(); }
  });
}

async function init() {
  prefs(false);
  const r = await fetch('data/sealed/index.json', { cache: 'no-cache' });
  S.index = r.ok ? await r.json() : { games: {} };
  const [g, s] = location.hash.slice(1).split('/');
  if (g && S.index.games[g]) { S.game = g; if (s) S.set = s; }
  bind();
  render();
}

init();
