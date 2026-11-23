// Markierwerkzeug: strittige Stellen einer Szene entscheiden (specs/003-eigene-referenz/contracts/review-api.md).
// Läuft nur gegen den lokalen Server (tools/review_server.py); lädt nichts von außen.
'use strict';

const COLORS = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4', '#f032e6', '#bfef45'];
const KIND = {
  occlusion: 'Verdeckung', end: 'Spurende', start: 'Spurbeginn', split: 'Trennung', link: 'Verbindung',
  number: 'Nummer prüfen', 'number-unsure': 'Nummer unsicher', veo: 'Veo sieht anders', control: 'Kontrolle',
};
const $ = (id) => document.getElementById(id);
const video = $('video');
const canvas = $('view');
const ctx = canvas.getContext('2d');

let data = null;          // {scene, fps, lensSize, spots, answers, open}
let index = 0;            // aktuelle Stelle
let slow = false;
let zoom = 1;             // 1 = vorgeschlagener Ausschnitt; > 1 näher heran, < 1 weiter weg
const VIEW_W = 1600;      // Breite der Zeichenfläche in Pixeln; die Seite skaliert sie auf die verfügbare Größe

// Ausschnitt der Stelle mit Zoom um seine Mitte, im Linsenbild gehalten
function view(s) {
  const [x, y, w, h] = s.crop;
  const [lw, lh] = data.lensSize || [2048, 1024];
  const k = Math.min(1 / zoom, lw / w, lh / h);
  const vw = w * k, vh = h * k;
  return [Math.min(Math.max(x + (w - vw) / 2, 0), lw - vw), Math.min(Math.max(y + (h - vh) / 2, 0), lh - vh), vw, vh];
}

function fit() {
  const [, , w, h] = view(spot());
  canvas.width = VIEW_W;
  canvas.height = Math.round(VIEW_W * h / w);
}

const spot = () => data.spots[index];
const color = (letter) => COLORS[(letter.charCodeAt(0) - 65) % COLORS.length];
const isNumber = (s) => s.kinds.some((k) => k === 'number' || k === 'number-unsure');

async function load() {
  data = await (await fetch('/spots')).json();
  $('scene').textContent = data.scene;
  const asked = parseInt(new URLSearchParams(location.search).get('stelle'), 10);   // ?stelle=6 öffnet Stelle 6
  const first = data.spots.findIndex((s) => !data.answers[s.id]);
  show(asked >= 1 && asked <= data.spots.length ? asked - 1 : first >= 0 ? first : 0);
  requestAnimationFrame(loop);
  if ('requestVideoFrameCallback' in video) video.requestVideoFrameCallback(onFrame);
}

function list() {
  const ol = $('list');
  ol.replaceChildren();
  data.spots.forEach((s, i) => {
    const li = document.createElement('li');
    const a = data.answers[s.id];
    li.className = (i === index ? 'current ' : '') + (a ? (a.choice === 'unclear' ? 'unclear' : 'done') : '');
    const t = document.createElement('span');
    t.innerHTML = `<b>${i + 1}</b> · ${(s.frame / data.fps).toFixed(1)} s <span class="kinds">${s.kinds.map((k) => KIND[k] || k).join(', ')}</span>`;
    const state = document.createElement('span');
    state.className = 'state';
    state.textContent = a ? (a.choice === 'unclear' ? '?' : '✓') : '';
    li.append(t, state);
    li.onclick = () => show(i);
    ol.append(li);
  });
  ol.children[index]?.scrollIntoView({ block: 'nearest' });
  history.replaceState(null, '', `?stelle=${index + 1}`);
  document.title = `Stelle ${index + 1} von ${data.spots.length} – ${data.scene}`;
  $('progress').textContent = `Stelle ${index + 1} von ${data.spots.length} · ${data.spots.length - data.open} von ${data.spots.length} entschieden, offen ${data.open}`;
}

function participants(s) {
  const byLetter = new Map();
  for (const p of [...s.before, ...s.after]) byLetter.set(p.letter, p);
  return [...byLetter.values()];
}

function show(i) {
  index = Math.max(0, Math.min(data.spots.length - 1, i));
  const s = spot();
  fit();
  video.currentTime = s.from / data.fps;
  video.playbackRate = slow ? 0.5 : 1;
  video.play().catch(() => {});
  $('message').textContent = '';
  list();
  question(s);
}

function chip(letter) {
  const c = document.createElement('span');
  c.className = 'letter';
  c.style.background = color(letter);
  c.textContent = letter;
  return c;
}

function button(text, action) {
  const b = document.createElement('button');
  b.textContent = text;
  b.onclick = action;
  return b;
}

function question(s) {
  const q = $('question');
  const choices = $('choices');
  const mapping = $('mapping');
  const numbers = $('numbers');
  choices.replaceChildren();
  mapping.replaceChildren();
  numbers.replaceChildren();
  const prev = data.answers[s.id];
  const kinds = s.kinds.map((k) => KIND[k] || k).join(', ');
  if (isNumber(s)) {
    q.textContent = s.number != null ? `${kinds}: Trägt ${s.after[0].letter} die Nummer ${s.number}?`
      : `${kinds}: Welche Nummer trägt ${s.after[0].letter}? (leer lassen, wenn nicht lesbar)`;
    const input = document.createElement('input');
    input.type = 'number'; input.min = 1; input.max = 99; input.id = 'num';
    input.value = prev?.numbers?.[s.after[0].letter] ?? '';
    numbers.append(chip(s.after[0].letter), input);
    if (s.number != null) choices.append(button(`Stimmt (Enter)`, () => send('proposed', {}, { [s.after[0].letter]: s.number })));
    choices.append(button('Nummer speichern', () => saveNumber(s)), button('Nicht lesbar (U)', () => send('unclear')));
    return;
  }
  if (s.kinds.includes('control')) q.textContent = `Kontrolle: Ist ${s.after[0].letter} nach der Marke dieselbe Person wie davor?`;
  else q.textContent = `${kinds}: Wer ist nach der Marke wer?`;
  for (const p of s.after) {
    const to = s.proposal[p.letter];
    const line = document.createElement('label');
    line.append(chip(p.letter), document.createTextNode(' nachher ist '));
    const sel = document.createElement('select');
    sel.dataset.letter = p.letter;
    for (const b of s.before) sel.add(new Option(`${b.letter} von vorher`, b.letter));
    sel.add(new Option('eine andere Person', 'other'));
    sel.add(new Option('unklar', 'unclear'));
    sel.value = prev?.mapping?.[p.letter] ?? (to ?? 'other');
    line.append(sel);
    mapping.append(line);
  }
  mapping.append(button('Zuordnung speichern', () => {
    const m = {};
    mapping.querySelectorAll('select').forEach((sel) => { m[sel.dataset.letter] = sel.value; });
    send('mapped', m);
  }));
  const text = s.after.map((p) => `${p.letter} → ${s.proposal[p.letter] ?? 'neu'}`).join(', ');
  choices.append(button(`Stimmt: ${text} (Enter)`, () => send('proposed')));
  if (s.before.length === 2) choices.append(button('Vertauscht (V)', () => send('swapped')));
  if (s.after.length === 1 && s.before.length >= 1) choices.append(button('Andere Person (N)', () => send('mapped', { [s.after[0].letter]: 'other' })));
  choices.append(button('Unklar (U)', () => send('unclear')));
}

function saveNumber(s) {
  const n = parseInt($('num').value, 10);
  if (Number.isInteger(n) && n >= 1 && n <= 99) send('proposed', {}, { [s.after[0].letter]: n });
  else send('unclear');
}

async function send(choice, mapping = {}, numbers = {}) {
  const s = spot();
  const body = { spot: s.id, choice, mapping, numbers, repeat: $('repeat').checked };
  const r = await fetch('/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const res = await r.json();
  if (!res.ok) { $('message').textContent = res.error; return; }
  if (!body.repeat) data.answers[s.id] = { ...body, choice };
  data.open = res.open;
  const next = data.spots.findIndex((x, i) => i > index && !data.answers[x.id]);
  show(next >= 0 ? next : index);
  $('message').textContent = res.warnings.length ? `Hinweis: ${res.warnings.join(' · ')}` : '';
}

let shownTime = 0;   // Zeit des angezeigten Videobilds (genau über requestVideoFrameCallback)

function loop() {
  requestAnimationFrame(loop);
  if (!data || video.readyState < 2) return;
  const s = spot();
  if (video.currentTime >= s.to / data.fps || video.currentTime < s.from / data.fps - 0.2) video.currentTime = s.from / data.fps;
  if (!('requestVideoFrameCallback' in video)) { shownTime = video.currentTime; render(); }
}

function onFrame(_now, meta) {
  shownTime = meta.mediaTime;
  render();
  video.requestVideoFrameCallback(onFrame);
}

function render() {
  if (!data || video.readyState < 2) return;
  const s = spot();
  const fps = data.fps;
  const f = Math.round(shownTime * fps);
  const [x, y, w, h] = view(s);
  const lensH = data.lensSize ? data.lensSize[1] : video.videoHeight / 2;
  const k = canvas.width / w;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(video, x, y + s.lens * lensH, w, h, 0, 0, canvas.width, canvas.height);
  const after = f >= s.frame;
  $('phase').textContent = after ? 'nachher' : 'vorher';
  for (const p of participants(s)) {      // Laufspur (Boxunterkante): bis jetzt kräftig, danach blass; Lücken werden überbrückt
    const pts = Object.keys(p.boxes).map(Number).sort((a, b) => a - b).map((g) => [g, p.boxes[g]]);
    ctx.lineWidth = 5;
    for (const [from, to, alpha] of [[0, f, 0.9], [f, Infinity, 0.35]]) {
      const part = pts.filter(([g]) => g >= from && g <= to);
      if (part.length < 2) continue;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color(p.letter);
      ctx.beginPath();
      part.forEach(([, b], i) => ctx[i ? 'lineTo' : 'moveTo'](((b[0] + b[2]) / 2 - x) * k, (b[3] - y) * k));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  for (const p of participants(s)) {
    const side = after ? s.after : s.before;
    if (!side.some((q) => q.letter === p.letter)) continue;
    let box = p.boxes[f] ?? p.boxes[String(f)];
    let guessed = false;
    if (!box) {   // Lücke: Box zwischen dem letzten und dem nächsten Bild schätzen (höchstens 2 s)
      const have = Object.keys(p.boxes).map(Number).sort((a, b) => a - b);
      const lo = have.filter((g) => g < f).pop();
      const hi = have.find((g) => g > f);
      if (lo === undefined || hi === undefined || hi - lo > 2 * fps) continue;
      const t = (f - lo) / (hi - lo);
      box = p.boxes[lo].map((v, i) => v + (p.boxes[hi][i] - v) * t);
      guessed = true;
    }
    ctx.strokeStyle = color(p.letter);
    ctx.lineWidth = 3;
    ctx.globalAlpha = guessed ? 0.55 : 1;
    ctx.setLineDash(guessed ? [3, 7] : after ? [] : [10, 6]);
    ctx.strokeRect((box[0] - x) * k, (box[1] - y) * k, (box[2] - box[0]) * k, (box[3] - box[1]) * k);
    ctx.setLineDash([]);
    ctx.fillStyle = color(p.letter);
    ctx.font = 'bold 28px system-ui, sans-serif';
    ctx.fillText(guessed ? `${p.letter} (geschätzt)` : p.letter, (box[0] - x) * k, (box[1] - y) * k - 6);
    ctx.globalAlpha = 1;
  }
  const span = s.to - s.from || 1;
  $('mark').style.left = `${((s.frame - s.from) / span) * 100}%`;
  $('head').style.left = `${Math.min(100, Math.max(0, ((f - s.from) / span) * 100))}%`;
}

document.addEventListener('keydown', (e) => {
  if (!data || e.target.tagName === 'SELECT' || (e.target.tagName === 'INPUT' && e.key !== 'Enter')) return;
  const s = spot();
  if (e.key === 'Enter') {
    e.preventDefault();
    if (isNumber(s)) {
      if ($('num').value) saveNumber(s);
      else if (s.number != null) send('proposed', {}, { [s.after[0].letter]: s.number });
    } else send('proposed');
  } else if (e.key === 'v' || e.key === 'V') { if (s.before.length === 2 && !isNumber(s)) send('swapped'); }
  else if (e.key === 'n' || e.key === 'N') { if (s.after.length === 1 && !isNumber(s)) send('mapped', { [s.after[0].letter]: 'other' }); }
  else if (e.key === 'u' || e.key === 'U') send('unclear');
  else if (e.key === 'ArrowRight') show(index + 1);
  else if (e.key === 'ArrowLeft') show(index - 1);
  else if (e.key === ' ') { e.preventDefault(); if (video.paused) video.play(); else video.pause(); }
  else if (e.key === '+' || e.key === '=') { zoom = Math.min(3, zoom * 1.25); fit(); }
  else if (e.key === '-') { zoom = Math.max(0.4, zoom / 1.25); fit(); }
  else if (e.key === ',' || e.key === '.') { video.pause(); video.currentTime += (e.key === '.' ? 1 : -1) / data.fps; }
  else if (e.key === 's' || e.key === 'S') { slow = !slow; video.playbackRate = slow ? 0.5 : 1; }
});

video.addEventListener('ended', () => { video.currentTime = spot().from / data.fps; video.play(); });
load();
