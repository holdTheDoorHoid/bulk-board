'use strict';
// Bulk Board — renders data/buyers.json as one comparison table per game.
// No build step, no dependencies. All prices are compared as US dollars per card.

const DEFAULT_SHIP_PER_K = 4.0; // fallback; data/meta.json overrides it
const STALE_DAYS = 45;
const UNIT_CARDS = { per_card: 1, per_100: 100, per_1000: 1000 };
const CUR = { USD: '$', CAD: 'C$', GBP: '£', EUR: '€', AUD: 'A$', NZD: 'NZ$', JPY: '¥' };
const LANG_NAMES = { en: 'English', ja: 'Japanese', ko: 'Korean', zh: 'Chinese', fr: 'French', de: 'German', it: 'Italian', es: 'Spanish', pt: 'Portuguese', th: 'Thai', id: 'Indonesian', ru: 'Russian', nl: 'Dutch', xx: 'Non-English (any language)' };

const S = {
  games: [], buyers: [], watch: {}, fx: { USD: 1 }, meta: {},
  game: 'pokemon', payout: 'cash',
  show: { mail: true, local: true, intl: false, market: true },
  lang: 'en',
  q: '', sort: { col: null, dir: -1 }, open: null,
  counts: {}, shipPerK: null,
};

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const today = () => new Date().toISOString().slice(0, 10);
const daysSince = (d) => (d ? Math.floor((Date.now() - Date.parse(d + 'T00:00:00Z')) / 864e5) : Infinity);

function store(key, val) {
  try {
    if (val === undefined) return JSON.parse(localStorage.getItem('bb.' + key));
    localStorage.setItem('bb.' + key, JSON.stringify(val));
  } catch (e) { return null; }
}

async function getJSON(url, fallback) {
  try { const r = await fetch(url, { cache: 'no-cache' }); return r.ok ? await r.json() : fallback; }
  catch (e) { return fallback; }
}

// ---------- money ----------

function cardsPerUnit(rate) {
  if (UNIT_CARDS[rate.unit]) return UNIT_CARDS[rate.unit];
  if ((rate.unit === 'per_box' || rate.unit === 'per_lb') && rate.cards_per_unit > 0) return rate.cards_per_unit;
  return null; // flat fees and unknown box sizes can't be compared per card
}
function usdPerCard(rate) {
  const n = cardsPerUnit(rate);
  const fx = S.fx[rate.currency || 'USD'];
  if (!n || !fx || typeof rate.price !== 'number') return null;
  return (rate.price / n) * fx;
}
function fmtMoney(v, cur = 'USD') {
  if (v == null) return '';
  const sym = CUR[cur] ?? cur + ' ';
  let s = v.toFixed(v < 1 && v > 0 ? 3 : 2);
  if (v < 1 && s.endsWith('0')) s = s.slice(0, -1); // $0.450 -> $0.45, but keep $0.675
  return sym + s;
}
// the value as displayed, so two prices that look equal rank equal
function shown(usdCard, unit) {
  if (usdCard == null) return null;
  const v = inUnit(usdCard, unit);
  return Math.round(v * (v < 1 ? 1000 : 100)) / (v < 1 ? 1000 : 100);
}
// value in the column's display unit
function inUnit(usdCard, unit) { return unit === 'per_1000' ? usdCard * 1000 : usdCard; }
function unitLabel(unit) { return unit === 'per_1000' ? 'per 1,000' : 'each'; }
function nativeInUnit(rate, unit) {
  const n = cardsPerUnit(rate);
  if (!n) return null;
  const per = rate.price / n;
  return unit === 'per_1000' ? per * 1000 : per;
}
function rawPrice(rate) {
  const u = { per_card: 'each', per_100: 'per 100', per_1000: 'per 1,000', per_lb: 'per lb', per_box: 'per box', flat: 'flat' }[rate.unit] || rate.unit;
  return `${fmtMoney(rate.price, rate.currency || 'USD')} ${u}${rate.unit_note ? ` (${rate.unit_note})` : ''}`;
}

// ---------- data shaping ----------

function gameDef(id = S.game) { return S.games.find((g) => g.id === id); }

// Rows for a game tab. A multi-game tab ("Other games") gets one row per store per game.
const buying = (b) => b.status !== 'closed' && b.status !== 'paused';
const subsOf = (g) => (g.multi ? g.multi : [g.id]);

// Rows for a game tab. A multi-game tab ("Other games") gets one row per store per game.
// `rates` holds the lines that count (chosen language, not paused); `all` every line for the game.
function rowsFor(g, lang = S.lang) {
  const rows = [];
  for (const b of S.buyers) {
    if (!buying(b)) continue;
    for (const sub of subsOf(g)) {
      const all = (b.rates || []).filter((r) => r.game === sub);
      const rates = all.filter((r) => (r.lang || 'en') === lang && !r.paused);
      if (!rates.length) continue;
      rows.push({ b, sub, rates, all, label: g.multi ? (g.game_names[sub] || sub) : null });
    }
  }
  return rows;
}
function unpublishedFor(g) {
  const subs = subsOf(g);
  return S.buyers.filter((b) => buying(b)
    && (b.games || []).some((x) => subs.includes(x))
    && !(b.rates || []).some((r) => subs.includes(r.game)));
}
function pausedFor(g) {
  const subs = subsOf(g);
  return S.buyers.filter((b) => {
    const mine = (b.rates || []).filter((r) => subs.includes(r.game));
    const inGame = (b.games || []).some((x) => subs.includes(x)) || mine.length;
    return inGame && (b.status === 'paused' || (b.status !== 'closed' && mine.length && mine.every((r) => r.paused)));
  });
}
function langsFor(g) {
  const subs = subsOf(g);
  const n = {};
  for (const b of S.buyers) {
    if (!buying(b)) continue;
    const seen = new Set((b.rates || []).filter((r) => subs.includes(r.game) && !r.paused).map((r) => r.lang || 'en'));
    for (const l of seen) n[l] = (n[l] || 0) + 1;
  }
  return Object.entries(n).sort((a, b) => (a[0] === 'en' ? -1 : b[0] === 'en' ? 1 : b[1] - a[1]));
}

function visible(b) {
  if (b.country && b.country !== 'US' && !S.show.intl) return false;
  if (b.platform && !S.show.market) return false;
  const mail = !!b.mail_in, local = !!b.in_person;
  if (!((mail && S.show.mail) || (local && S.show.local) || (!mail && !local))) return false;
  if (S.q) {
    const hay = `${b.name} ${b.city || ''} ${b.region || ''} ${b.country || ''}`.toLowerCase();
    if (!hay.includes(S.q.toLowerCase())) return false;
  }
  return true;
}

// Best rate a store offers for one column under the current payout setting.
// Marketplace prices are shown after the marketplace's seller fee, so they compare fairly with direct buyers.
function cell(row, code) {
  const full = row.sub && gameDef().multi ? row.sub + code : code;
  const lines = row.rates.filter((r) => (r.cats || []).includes(full));
  const usable = lines.filter((r) => S.payout === 'credit' || r.payout !== 'credit');
  const keep = 1 - (row.b.fee_pct || 0) / 100;
  let best = null;
  for (const r of usable) {
    const v = usdPerCard(r);
    if (v == null) continue;
    if (!best || v * keep > best.usd) best = { usd: v * keep, rate: r };
  }
  return { best, lines };
}

// ---------- rendering ----------

function renderTabs() {
  const counts = Object.fromEntries(S.games.map((g) => [g.id, new Set(rowsFor(g).filter((r) => visible(r.b)).map((r) => r.b.id)).size]));
  $('#tabs').innerHTML = S.games
    .filter((g) => rowsFor(g).length || unpublishedFor(g).length)
    .map((g) => `<button role="tab" type="button" data-game="${g.id}" aria-selected="${g.id === S.game}">${esc(g.short)}<span class="n">${counts[g.id]}</span></button>`)
    .join('');
}

function renderLegend(g) {
  const conf = S.meta.generated ? ` Data assembled ${esc(S.meta.generated)}.` : '';
  $('#legend').innerHTML =
    `<span class="sw r1">★ $6.00</span> = highest payer in that column, <span class="sw r2">shaded</span> = 2nd and 3rd. ` +
    `Bulk columns are dollars per 1,000 cards; the rest are dollars per card. Click a column to sort, click a store for its rules, minimums and shipping.` +
    (S.payout === 'credit' ? ' <b>Store credit is included</b> — a <span class="tag">credit</span> tag marks prices only paid as credit.' : '') +
    ' Marketplace buyers are shown after the marketplace\'s seller fee. <i>Unconfirmed</i> prices come from comparison sites and are never marked as the top payer.' + conf;
}

function freshness(b) {
  const w = S.watch[b.id] || {};
  if (w.changed_on) return `<span class="fresh changed" title="The store's rate page changed on ${esc(w.changed_on)}; these numbers may be out of date until re-checked.">⚠ page changed ${esc(w.changed_on)}</span>`;
  const d = w.last_confirmed || b.checked_on;
  if (!d) return '';
  const old = daysSince(d) > STALE_DAYS;
  const how = w.last_confirmed ? 'Prices on the store page last matched on' : 'Checked by hand on';
  return `<span class="fresh${old ? ' old' : ''}" title="${how} ${esc(d)}">${old ? '⚠ ' : '✓ '}${esc(d)}</span>`;
}

function renderTable() {
  const g = gameDef();
  const rows = rowsFor(g).filter((r) => visible(r.b));
  const cols = g.columns;

  // Only keep columns somebody prices (among all stores, not just visible ones, so columns don't jump around).
  const all = rowsFor(g);
  const live = cols.filter((c) => all.some((r) => cell(r, c.code).lines.length));

  // compute cells + per-column ranks
  const grid = rows.map((r) => ({ r, cells: Object.fromEntries(live.map((c) => [c.code, cell(r, c.code)])) }));
  const rank = {};
  for (const c of live) {
    // second-hand (unconfirmed) prices are shown but never crowned
    const vals = [...new Set(grid.filter((x) => x.r.b.source_type !== 'second_hand').map((x) => shown(x.cells[c.code].best?.usd, c.unit)).filter((v) => v != null))].sort((a, b) => b - a);
    rank[c.code] = vals;
  }

  // sort
  const sc = S.sort.col && live.some((c) => c.code === S.sort.col) ? S.sort.col : live[0]?.code;
  grid.sort((x, y) => {
    if (S.sort.col === '_name') return S.sort.dir * x.r.b.name.localeCompare(y.r.b.name);
    const a = x.cells[sc]?.best?.usd, b = y.cells[sc]?.best?.usd;
    if (a == null && b == null) return x.r.b.name.localeCompare(y.r.b.name);
    if (a == null) return 1; // stores that don't buy this always sink to the bottom
    if (b == null) return -1;
    return S.sort.dir * (a - b) || x.r.b.name.localeCompare(y.r.b.name);
  });
  const activeCol = S.sort.col === '_name' ? '_name' : sc;
  S.sort.eff = activeCol;
  const arrow = (code) => (activeCol === code ? `<span class="arrow" aria-hidden="true">${S.sort.dir < 0 ? ' ▼' : ' ▲'}</span>` : '');
  const ariaSort = (code) => (activeCol === code ? (S.sort.dir < 0 ? 'descending' : 'ascending') : 'none');

  let html = '<thead><tr>' +
    `<th class="store" scope="col" aria-sort="${ariaSort('_name')}"><button type="button" data-sort="_name">Store${arrow('_name')}</button></th>` +
    live.map((c) => `<th scope="col" aria-sort="${ariaSort(c.code)}" title="${esc(c.label)}"><button type="button" data-sort="${c.code}">${esc(c.short)}${arrow(c.code)}<span class="u">${unitLabel(c.unit)}</span></button></th>`).join('') +
    '</tr></thead><tbody>';

  for (const { r, cells } of grid) {
    const b = r.b;
    const key = b.id + '|' + r.sub;
    const where = [b.city, b.region, b.country !== 'US' ? b.country : ''].filter(Boolean).join(', ');
    const how = [b.platform ? `via ${b.platform_name} (${b.completed_orders ?? '?'} orders done${b.budget_left != null ? `, ${fmtMoney(b.budget_left, b.budget_currency)} budget left` : ''})` : (b.mail_in ? 'mail-in' : ''), b.in_person ? 'in person' : ''].filter(Boolean).join(' · ');
    const flags = (b.source_type === 'second_hand' ? '<span class="fresh changed" title="These prices come from a comparison page, not the store\'s own site. They may be out of date.">unconfirmed</span> ' : '')
      + (b.status === 'unclear' ? '<span class="fresh changed" title="It is not clear the store is buying right now.">status unclear</span> ' : '');
    html += `<tr class="row" tabindex="0" data-key="${esc(key)}" aria-expanded="${S.open === key}">` +
      `<td class="store"><span class="nm">${esc(b.name)}</span>${r.label ? ` — ${esc(r.label)}` : ''}` +
      `<span class="meta">${esc([how, where].filter(Boolean).join(' · '))} ${flags}${freshness(b)}</span></td>`;
    for (const c of live) {
      const x = cells[c.code];
      if (!x.best) {
        const t = x.lines.length ? 'Priced, but not comparable here (see store details)' : 'Not bought / not listed';
        html += `<td class="v none" title="${t}">${x.lines.length ? '·' : '—'}</td>`;
        continue;
      }
      const sh = b.source_type === 'second_hand';
      const pos = sh ? -1 : rank[c.code].indexOf(shown(x.best.usd, c.unit));
      const cls = sh ? 'sh' : pos === 0 ? 'r1' : pos === 1 ? 'r2' : pos === 2 ? 'r3' : '';
      const rate = x.best.rate;
      const cur = rate.currency || 'USD';
      const txt = cur === 'USD' ? fmtMoney(inUnit(x.best.usd, c.unit)) : fmtMoney(nativeInUnit(rate, c.unit), cur);
      const tip = x.lines.map((l) => `${l.category_raw}: ${rawPrice(l)}${l.payout === 'credit' ? ' (store credit)' : ''}${l.notes ? ' — ' + l.notes : ''}`).join('\n')
        + (b.fee_pct ? `\nShown after ${b.platform_name}'s ${b.fee_pct}% seller fee.` : '');
      html += `<td class="v ${cls}" title="${esc(tip)}">` +
        (pos === 0 ? '<span class="star" aria-label="top payer">★</span>' : '') + esc(txt) +
        (rate.payout === 'credit' ? '<span class="tag">credit</span>' : '') +
        (x.lines.length > 1 ? '<span class="tag" title="More than one price line; hover for all">+</span>' : '') +
        (cur !== 'USD' ? `<span class="fx">≈ ${esc(fmtMoney(inUnit(x.best.usd, c.unit)))}</span>` : '') +
        '</td>';
    }
    html += '</tr>';
    if (S.open === key) html += `<tr class="detail"><td colspan="${live.length + 1}">${detail(b, r)}</td></tr>`;
  }
  html += '</tbody>';
  $('#rates').innerHTML = html;

  const empty = $('#empty');
  empty.hidden = grid.length > 0;
  empty.textContent = grid.length ? '' : 'No stores match these filters. Try ticking more boxes above, or clear the search.';

  const un = unpublishedFor(g).filter(visible);
  const pa = pausedFor(g).filter(visible);
  const lk = (b) => `<a href="${esc(b.rates_url || b.website)}" target="_blank" rel="noopener">${esc(b.name)}</a>`;
  const up = $('#unpublished');
  up.hidden = !un.length && !pa.length;
  up.innerHTML = (un.length ? `<b>Also buys ${esc(g.short)} bulk but doesn't publish rates:</b> ${un.map(lk).join(', ')}.<br>` : '')
    + (pa.length ? `<b>Not buying ${esc(g.short)} bulk right now (paused):</b> ${pa.map(lk).join(', ')}.` : '');
}

function dl(label, val) { return val ? `<div><dt>${esc(label)}</dt><dd>${val}</dd></div>` : ''; }
function link(u, text) { return u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(text || u.replace(/^https?:\/\//, ''))}</a>` : ''; }

function detail(b, row) {
  const w = S.watch[b.id] || {};
  const pay = (b.payout_methods || []).join(', ');
  const other = [...new Set((b.rates || []).map((r) => r.game))].filter((x) => x !== row.sub);
  let watch = '';
  if (w.changed_on) watch = `The rate page changed on ${esc(w.changed_on)} and hasn't been re-checked yet.` + (w.diff ? ` Prices that appeared: ${esc((w.diff.added || []).join(', ') || 'none')}; disappeared: ${esc((w.diff.removed || []).join(', ') || 'none')}.` : '');
  else if (w.last_confirmed) watch = `Prices on the page last matched on ${esc(w.last_confirmed)}.`;
  else if (w.mode === 'manual') watch = 'This page can only be checked by hand (it needs a full browser).';
  if (w.fetch_error) watch += ` Last automatic check failed: ${esc(w.fetch_error)}.`;
  return `<dl class="detail-grid">` +
    (b.platform ? dl('Marketplace', `Sold through ${esc(b.platform_name)}: you need a free ${esc(b.platform_name)} seller account, prices in the table are after its ${b.fee_pct}% seller fee, and you pay shipping.` + (b.completed_orders != null ? ` This buyer has completed ${b.completed_orders} orders there.` : '')) : '') +
    (b.source_type === 'second_hand' ? dl('Source', 'These prices were copied from another site comparing buyers, not from the store itself, and may be out of date. Check the store before relying on them.') : '') +
    dl('Rates page', link(b.rates_url) + (b.website && b.website !== b.rates_url ? ` · ${link(b.website, 'home')}` : '')) +
    dl('Checked', esc(b.checked_on) + (b.rates_last_updated ? ` (store says rates updated ${esc(b.rates_last_updated)})` : '') + (watch ? `<br><small>${watch}</small>` : '')) +
    dl('How to sell', esc(b.process)) +
    dl('Minimum', esc(b.minimum)) +
    dl('Shipping', esc(b.shipping)) +
    dl('Payout', esc(pay) + (b.store_credit_bonus ? ` · store credit: ${esc(b.store_credit_bonus)}` : '') + (b.turnaround ? ` · ${esc(b.turnaround)}` : '')) +
    dl('Volume bonus', esc(b.volume_bonus)) +
    dl('Condition', esc(b.condition_rules)) +
    dl('Sorting', esc(b.sorting_rules)) +
    dl("Doesn't buy", esc(b.excluded)) +
    dl('Notes', esc(b.notes)) +
    dl('Reputation', esc(b.reputation)) +
    dl('Also buys', esc(other.map((x) => (gameDef(x) || {}).short || x).join(', '))) +
    `</dl>` +
    `<table class="raw"><thead><tr><th>Their category</th><th>Price as listed</th><th>Paid as</th><th>Notes</th></tr></thead><tbody>` +
    row.all.map((r) => `<tr><td>${esc(r.category_raw)}${(r.lang || 'en') !== 'en' ? ` <span class="tag">${esc(LANG_NAMES[r.lang] || r.lang)}</span>` : ''}${r.paused ? ' <span class="tag">paused</span>' : ''}${(r.cats || []).length ? '' : ' <span class="tag" title="Doesn\'t fit a column in the table">not in table</span>'}</td><td>${esc(rawPrice(r))}</td><td>${r.payout === 'credit' ? 'store credit' : 'cash'}</td><td>${esc(r.notes)}</td></tr>`).join('') +
    `</tbody></table>`;
}

// ---------- calculator ----------

function shipCost(b, cards, gross) {
  if (!b.mail_in) return { cost: 0, note: 'in-person drop-off' };
  const perK = S.shipPerK ?? DEFAULT_SHIP_PER_K;
  const est = (cards / 1000) * perK;
  switch (b.pays_shipping) {
    case 'yes': return { cost: 0, note: 'they pay shipping' };
    case 'over_threshold': {
      const ok = (b.ship_free_over_cards && cards >= b.ship_free_over_cards) || (b.ship_free_over_usd && gross >= b.ship_free_over_usd);
      return ok ? { cost: 0, note: 'free label (over their threshold)' } : { cost: est, note: 'below their free-label threshold' };
    }
    default: return { cost: est, note: '' };
  }
}
function minNote(b, cards, gross) {
  const out = [];
  if (b.min_cards && cards < b.min_cards) out.push(`below their ${b.min_cards.toLocaleString()}-card minimum`);
  if (b.min_usd && gross < b.min_usd) out.push(`below their $${b.min_usd} minimum`);
  return out;
}

function renderCalcInputs() {
  const g = gameDef();
  const sec = $('#calc');
  sec.hidden = !!g.multi;
  if (g.multi) return;
  const all = rowsFor(g);
  const live = g.columns.filter((c) => all.some((r) => cell(r, c.code).lines.length));
  const counts = S.counts[g.id] || {};
  $('#calc-inputs').innerHTML = live.map((c) =>
    `<label>${esc(c.label)}<input type="number" min="0" step="1" inputmode="numeric" data-count="${c.code}" value="${counts[c.code] ?? ''}" placeholder="0"></label>`).join('');
  const ship = $('#ship-per-k');
  ship.value = (S.shipPerK ?? DEFAULT_SHIP_PER_K).toFixed(2);
  $('#ship-hint').textContent = S.meta.ship_hint || '';
}

function calc() {
  const g = gameDef();
  if (g.multi) return;
  const counts = S.counts[g.id] || {};
  const codes = Object.keys(counts).filter((k) => counts[k] > 0);
  const out = $('#calc-out');
  if (!codes.length) { out.innerHTML = ''; return; }
  const totalCards = codes.reduce((s, k) => s + counts[k], 0);
  const rows = rowsFor(g).filter((r) => visible(r.b));

  const results = rows.map((r) => {
    let gross = 0, sent = 0, unbought = 0;
    const per = {};
    for (const k of codes) {
      const c = cell(r, k).best;
      if (c) { gross += c.usd * counts[k]; sent += counts[k]; per[k] = c.usd; }
      else unbought += counts[k];
    }
    const warn = minNote(r.b, sent, gross);
    if (r.b.platform && r.b.budget_left == null) warn.push('budget left unknown');
    if (r.b.budget_left != null) {
      const cap = r.b.budget_left * (S.fx[r.b.budget_currency || 'USD'] || 1);
      if (gross > cap) { warn.push(`their budget only covers ${fmtMoney(cap)} right now`); gross = cap; }
    }
    const ship = shipCost(r.b, sent, gross);
    if (unbought) warn.push(`doesn't buy ${unbought.toLocaleString()} of your cards`);
    if (r.b.source_type === 'second_hand') warn.push('unconfirmed prices');
    if (r.b.status === 'unclear') warn.push('may not be buying right now');
    if (r.b.platform) warn.push(`via ${r.b.platform_name}, after fee`);
    if (ship.note) warn.push(ship.note);
    return { b: r.b, gross, ship: ship.cost, net: gross - ship.cost, sent, warn, per };
  }).filter((x) => x.sent > 0).sort((a, b) => b.net - a.net);

  if (!results.length) { out.innerHTML = '<p class="hint">None of the stores shown buys those categories.</p>'; return; }

  // Recommendations only use confirmed, currently-buying stores; the table below still lists everyone.
  const solid = results.filter((x) => x.b.source_type !== 'second_hand' && x.b.status === 'active');
  // Split plan: every category goes to whoever pays most for it; shipping counted once per store.
  const plan = new Map();
  for (const k of codes) {
    let best = null;
    for (const x of solid) if (x.per[k] != null && (!best || x.per[k] > best.per[k])) best = x;
    if (!best) continue;
    const p = plan.get(best.b.id) || { b: best.b, gross: 0, sent: 0, cats: [] };
    p.gross += best.per[k] * counts[k]; p.sent += counts[k]; p.cats.push(k);
    plan.set(best.b.id, p);
  }
  let splitNet = 0;
  const splitWarn = [];
  for (const p of plan.values()) {
    const s = shipCost(p.b, p.sent, p.gross);
    p.ship = s.cost; splitNet += p.gross - s.cost;
    const m = minNote(p.b, p.sent, p.gross);
    if (m.length) splitWarn.push(`${p.b.name}: ${m.join(', ')}`);
  }
  const top = solid[0] || results[0];
  const label = (k) => (g.columns.find((c) => c.code === k) || {}).short || k;
  let summary = `<div class="calc-summary">Best single store: <b>${esc(top.b.name)}</b>, about <b>${fmtMoney(top.net)}</b> after shipping for ${top.sent.toLocaleString()} of your ${totalCards.toLocaleString()} cards.`;
  if (plan.size > 1) {
    const gain = splitNet - top.net;
    summary += gain > 0.5
      ? `<br>Splitting across ${plan.size} stores would pay about <b>${fmtMoney(splitNet)}</b> (${fmtMoney(gain)} more): ` +
        [...plan.values()].map((p) => `${esc(p.b.name)} (${p.cats.map(label).join(', ')})`).join('; ') + '.'
      : `<br>Splitting across ${plan.size} stores isn't worth it — the extra shipping eats the difference.`;
    if (gain > 0.5 && splitWarn.length) summary += `<br><small>Check minimums: ${esc(splitWarn.join('; '))}.</small>`;
  }
  summary += '</div>';

  out.innerHTML = summary + '<div class="calc-wrap"><table class="calc-t"><thead><tr><th>Store</th><th>Payout</th><th>Your shipping</th><th>You keep</th><th>Watch out for</th></tr></thead><tbody>' +
    results.slice(0, 20).map((x, i) => `<tr class="${i === 0 ? 'top' : ''}"><td>${esc(x.b.name)}</td><td>${fmtMoney(x.gross)}</td><td>${x.ship ? '−' + fmtMoney(x.ship) : '$0'}</td><td>${fmtMoney(x.net)}</td><td class="warn">${esc(x.warn.join('; '))}</td></tr>`).join('') +
    '</tbody></table></div><p class="hint">Estimates only: stores grade condition and count on arrival, and payout can come in lower. Shipping is your cost per 1,000 cards times the cards each store would take.</p>';
}

// ---------- wiring ----------

function renderLang() {
  const ls = langsFor(gameDef());
  if (!ls.some(([l]) => l === S.lang)) S.lang = 'en';
  const sel = $('#lang');
  sel.innerHTML = ls.map(([l, n]) => `<option value="${l}"${l === S.lang ? ' selected' : ''}>${esc(LANG_NAMES[l] || l)} (${n})</option>`).join('');
  sel.closest('label').hidden = ls.length < 2;
}

function render() {
  renderLang();
  renderTabs();
  renderLegend(gameDef());
  renderTable();
  renderCalcInputs();
  calc();
  document.querySelectorAll('[data-payout]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.payout === S.payout)));
}

function saveFilters() { store('prefs', { payout: S.payout, show: S.show, shipPerK: S.shipPerK, counts: S.counts }); }

function bind() {
  $('#tabs').addEventListener('click', (e) => {
    const t = e.target.closest('[data-game]');
    if (!t) return;
    S.game = t.dataset.game; S.sort = { col: null, dir: -1 }; S.open = null; S.lang = 'en';
    history.replaceState(null, '', '#' + S.game);
    render();
  });
  $('#tabs').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const tabs = [...document.querySelectorAll('#tabs [data-game]')];
    const i = tabs.findIndex((t) => t.dataset.game === S.game);
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    n.click(); $(`#tabs [data-game="${n.dataset.game}"]`).focus();
  });
  document.querySelectorAll('[data-payout]').forEach((b) => b.addEventListener('click', () => { S.payout = b.dataset.payout; saveFilters(); render(); }));
  $('#lang').addEventListener('change', (e) => { S.lang = e.target.value; S.open = null; render(); });
  for (const [id, k] of [['f-mail', 'mail'], ['f-local', 'local'], ['f-market', 'market'], ['f-intl', 'intl']]) {
    const el = $('#' + id);
    el.checked = S.show[k];
    el.addEventListener('change', () => { S.show[k] = el.checked; saveFilters(); render(); });
  }
  $('#q').addEventListener('input', (e) => { S.q = e.target.value.trim(); renderTable(); renderTabs(); calc(); });
  $('#rates').addEventListener('click', (e) => {
    const s = e.target.closest('[data-sort]');
    if (s) {
      const col = s.dataset.sort;
      S.sort = S.sort.eff === col ? { col, dir: -S.sort.dir } : { col, dir: col === '_name' ? 1 : -1 };
      renderTable();
      return;
    }
    if (e.target.closest('a')) return;
    const tr = e.target.closest('tr.row');
    if (tr) { S.open = S.open === tr.dataset.key ? null : tr.dataset.key; renderTable(); }
  });
  $('#rates').addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr.row')) { e.preventDefault(); e.target.click(); }
  });
  $('#calc-inputs').addEventListener('input', (e) => {
    const k = e.target.dataset.count;
    if (!k) return;
    const v = Math.max(0, Math.floor(Number(e.target.value) || 0));
    (S.counts[S.game] ||= {})[k] = v;
    saveFilters(); calc();
  });
  $('#ship-per-k').addEventListener('input', (e) => {
    const v = Number(e.target.value);
    S.shipPerK = Number.isFinite(v) && v >= 0 ? v : null;
    saveFilters(); calc();
  });
}

async function init() {
  const [games, buyers, watch, fx, meta] = await Promise.all([
    getJSON('data/games.json', { games: [] }),
    getJSON('data/buyers.json', { buyers: [] }),
    getJSON('data/watch.json', {}),
    getJSON('data/fx.json', { rates: {} }),
    getJSON('data/meta.json', {}),
  ]);
  S.games = games.games || [];
  S.buyers = buyers.buyers || [];
  S.watch = watch.buyers || {};
  S.fx = Object.assign({ USD: 1 }, fx.rates || {});
  S.meta = Object.assign({}, meta, { generated: buyers.generated });
  const p = store('prefs');
  if (p) {
    if (p.payout) S.payout = p.payout;
    if (p.show) Object.assign(S.show, p.show);
    if (typeof p.shipPerK === 'number') S.shipPerK = p.shipPerK;
    if (p.counts) S.counts = p.counts;
  }
  if (S.shipPerK == null && typeof S.meta.ship_per_1000_usd === 'number') S.shipPerK = S.meta.ship_per_1000_usd;
  const h = location.hash.slice(1);
  if (S.games.some((g) => g.id === h)) S.game = h;
  bind();
  render();
}

init();
