const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fx = (v, n) => v == null ? '–' : (+v).toFixed(n);
const spr = (who, ex) => `/static/characters/${who}/${who}_${ex}.png`;
const PLANS = [
  {key:'profit',   who:'queen',    name:'Queen of Ooo',    title:'Better profit'},
  {key:'health',   who:'bmo',      name:'BMO',             title:'Better land health'},
  {key:'balanced', who:'huntress', name:'Huntress Wizard', title:'Balanced: least loss between the two'},
];
const MON = ['J','F','M','A','M','J','J','A','S','O','N','D'];
let S = {cells: [], crops: [], other: []};
const show = id => ['intro','form','results'].forEach(x => $('#'+x).classList.toggle('hidden', x !== id));

async function api(path, opt) {
  const r = await fetch(path, opt), j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Please check the coordinates and history.');
  return j;
}

function line(el, labels, series) {
  const W = 440, H = 170, P = 26, all = series.flatMap(s => s.v).filter(v => v != null);
  const lo = Math.min(...all), hi = Math.max(...all), n = labels.length;
  const sx = i => P + i * (W - 2 * P) / ((n - 1) || 1), sy = v => H - P - (v - lo) / ((hi - lo) || 1) * (H - 2 * P);
  const step = Math.ceil(n / 7);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">` +
    series.map(s => `<polyline fill="none" stroke="${s.c}" stroke-width="2" points="${s.v.map((v, i) => v == null ? '' : `${sx(i)},${sy(v)}`).join(' ')}"/>`).join('') +
    labels.map((l, i) => i % step ? '' : `<text x="${sx(i)}" y="${H - 8}" fill="#9a93b5" font-size="10" text-anchor="middle">${l}</text>`).join('') +
    `<text x="2" y="12" fill="#9a93b5" font-size="10">${hi.toFixed(2)}</text><text x="2" y="${H - P}" fill="#9a93b5" font-size="10">${lo.toFixed(2)}</text></svg>` +
    `<div class="legend">${series.map(s => `<span style="color:${s.c}">■</span> ${s.n}`).join(' &nbsp; ')}</div>`;
}

function buildForm() {
  $('#chips').innerHTML = S.cells.slice(0, 14).map((c, i) => `<button class="chip" data-i="${i}">${c.lat.toFixed(2)}, ${c.lon.toFixed(2)}</button>`).join('');
  document.querySelectorAll('.chip').forEach(b => b.onclick = () => { const c = S.cells[b.dataset.i]; $('#lat').value = c.lat; $('#lon').value = c.lon; });
  const opts = '<option value="">nothing / unknown</option>' + [...S.crops, ...S.other].map(c => `<option>${esc(c)}</option>`).join('');
  let h = ''; for (let y = 2025; y <= new Date().getFullYear(); y++) h += `<label>${y}<select data-y="${y}">${opts}</select></label>`;
  $('#hist').innerHTML = h;
  if (S.cells[0]) { $('#lat').value = S.cells[0].lat; $('#lon').value = S.cells[0].lon; }
}

const mood = (k, d) => {
  const t = d.plans[k].picks[0];
  if (k === 'profit') return t.net >= 1000 ? 'excited' : t.net > 0 ? 'happy' : 'annoyed';
  if (k === 'health') return d.flags.low_om ? 'annoyed' : (t.legume ? 'excited' : 'happy');
  return t.score >= 0.8 ? 'happy' : 'neutral';
};

function render(d) {
  const far = d.flags.far, km = d.cell.distance_km.toFixed(0), L = d.land;
  $('#fernRes').src = spr('fern', far ? 'annoyed' : 'happy');
  $('#summary').innerHTML = far
    ? `Heads up: the closest cell in my data is <b>${km} km</b> from your pin, so treat this as a regional estimate.`
    : `Found data just <b>${km} km</b> from your pin. Here is your land and three plans for <b>${d.plan_year}</b>.`;
  const r = (k, v) => `<tr><td>${k}</td><td>${v}</td></tr>`;
  $('#landCard').innerHTML = `<h3>Your land (cell ${esc(d.cell.id)})</h3><table>` +
    r('Cell centre', `${d.cell.lat}, ${d.cell.lon}`) + r('Elevation / slope', `${fx(L.elevation_m,0)} m / ${fx(L.slope_deg,1)}°`) +
    r('Soil texture', `${L.texture} (clay ${fx(L.clay,0)}%, sand ${fx(L.sand,0)}%, silt ${fx(L.silt,0)}%)`) +
    r('Soil pH', fx(L.ph,1)) + r('Organic matter', fx(L.om,2) + (d.flags.low_om ? ' (low)' : '')) + r('Ksat', fx(L.ksat,1)) +
    r('Soil moisture (avg)', fx(L.soil_moisture,3)) + r('ET (avg, as stored)', fx(L.et,1)) + '</table>';
  $('#histCard').innerHTML = '<h3>What has been planted</h3><h4>You told me</h4>' +
    (d.history_user.length ? d.history_user.map(h => `<span class="pill">${h.year}: ${esc(h.crop)}</span>`).join('') : '<i>nothing entered</i>') +
    '<h4>My records for this cell</h4>' + d.history_db.map(h => `<div class="hrow"><b>${h.year}</b>${h.top.map(t => `${esc(t.crop)} ${(t.share*100).toFixed(0)}%`).join(' · ')}</div>`).join('');
  line($('#tempChart'), MON, [{n:'Mean', c:'#7dd3a8', v:d.climate.map(c => c.T2M)}, {n:'Max', c:'#f4a261', v:d.climate.map(c => c.T2M_MAX)}]);
  line($('#ndviChart'), d.ndvi.labels.map(l => l.slice(0,4)), [{n:'NDVI', c:'#9bd35a', v:d.ndvi.values}]);
  $('#plansTitle').textContent = `Three plans for ${d.plan_year}`;
  $('#plans').innerHTML = PLANS.map(p => `<article class="plan ${p.key}"><img src="${spr(p.who, mood(p.key, d))}" alt="${p.name}"><h3>${p.name}</h3><div class="sub">${p.title}</div>` +
    d.plans[p.key].picks.map((c, i) => `<div class="pick"><div class="ph"><b>${i+1}. ${esc(c.crop)}</b><span>${(c.score*100).toFixed(0)}/100</span></div><div class="bar"><i style="width:${c.score*100}%"></i></div><ul>${c.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul></div>`).join('') + '</article>').join('');
  $('#foot').textContent = `Profit uses placeholder prices and costs (edit crops.csv). ML model weight: ${(d.flags.model_weight*100).toFixed(0)}%${d.flags.model_used ? '' : ' (model not loaded, neutral score used)'}. Climate and soil values come from the NASA-derived dataset.`;
}

$('#start').onclick = () => show('form');
$('#again').onclick = () => show('form');
$('#go').onclick = async () => {
  $('#err').textContent = ''; $('#go').disabled = true; $('#go').textContent = 'Fern is looking…';
  const history = [...document.querySelectorAll('#hist select')].filter(s => s.value).map(s => ({year: +s.dataset.y, crop: s.value}));
  try {
    const d = await api('/api/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({lat: +$('#lat').value, lon: +$('#lon').value, history})});
    render(d); show('results'); window.scrollTo(0, 0);
  } catch (e) { $('#err').textContent = e.message; }
  $('#go').disabled = false; $('#go').textContent = 'Show me the plans';
};

(async () => {
  $('#fernImg').src = spr('fern', 'happy');
  try {
    const st = await api('/api/status');
    if (!st.ok) { $('#fernImg').src = spr('fern', 'annoyed'); $('#fernSay').textContent = st.error; $('#start').disabled = true; return; }
    const [c, k] = await Promise.all([api('/api/cells'), api('/api/crops')]);
    S = {cells: c.cells, crops: k.crops, other: k.other}; buildForm();
  } catch (e) { $('#fernImg').src = spr('fern', 'annoyed'); $('#fernSay').textContent = e.message; $('#start').disabled = true; }
})();
