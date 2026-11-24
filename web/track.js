// Spieldaten der Szene (Format matchspace-track): Bahnen aller Figuren und Körperposen in Blöcken.
// Die Daten werden beim Import geladen; ohne sie bricht die Seite mit einer Meldung ab.

const $ = (id) => document.getElementById(id);
export const query = new URLSearchParams(location.search);
export const base = `data/${query.get('match') || 'game1'}/`;

// ---------- Daten laden (Format: matchspace-track v0) ----------
export let meta, data;
try {
  meta = await (await fetch(base + 'meta.json')).json();
  data = new Int16Array(await (await fetch(base + meta.tracks.file)).arrayBuffer());
} catch (err) {
  $('status').textContent = `Spieldaten unter ${base} nicht gefunden. Siehe README.`;
  throw err;
}
export const N = meta.frames;
export const ENTITIES = meta.entities;
const STRIDE = ENTITIES.length * 3;
const { scale: SCALE, missing: MISSING } = meta.tracks;
export const L = meta.pitch.length, W = meta.pitch.width;

// ---------- Körperposen (optional, in Blöcken nachgeladen) ----------
export const POSES = meta.poses ?? null;
export const PLAYER_SLOTS = ENTITIES.map((e) => e.kind === 'player').reduce((acc, isPlayer, i) => {
  if (isPlayer) acc.set(i, acc.size);
  return acc;
}, new Map());
export const JOINTS = POSES ? POSES.skeleton.joints : [];
export const BONES = POSES ? POSES.skeleton.bones : [];
export const J = JOINTS.length;
export const JOINT_INDEX = Object.fromEntries(JOINTS.map((j, i) => [j.name, i]));
const chunkCache = new Map(); // Blocknummer -> Int16Array | null (lädt) | false (fehlt)

export function poseChunk(frame) {
  const c = Math.floor(frame / POSES.chunkFrames);
  if (c < 0 || c >= POSES.chunks) return null;
  const cached = chunkCache.get(c);
  if (cached !== undefined) return cached || null;
  chunkCache.set(c, null);
  fetch(base + POSES.path.replace('{chunk}', String(c).padStart(3, '0')))
    .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.statusText))))
    .then((buf) => {
      chunkCache.set(c, new Int16Array(buf));
      for (const key of chunkCache.keys()) if (Math.abs(key - c) > 4) chunkCache.delete(key);
    })
    .catch(() => chunkCache.set(c, false));
  return null;
}

/** Gelenkpositionen eines Spielers zum Frame t in Three-Koordinaten; root = Position am Boden. */
export function samplePose(slot, t, root, out) {
  const f0 = Math.min(N - 1, Math.max(0, Math.floor(t)));
  const f1 = Math.min(N - 1, f0 + 1);
  const c0 = poseChunk(f0);
  if (!c0) return false;
  const perFrame = PLAYER_SLOTS.size * J * 3;
  const o0 = (f0 % POSES.chunkFrames) * perFrame + slot * J * 3;
  if (c0[o0] === POSES.missing) return false;
  let c1 = poseChunk(f1);
  let o1 = (f1 % POSES.chunkFrames) * perFrame + slot * J * 3;
  if (!c1 || c1[o1] === POSES.missing) { c1 = c0; o1 = o0; }
  const a = t - f0, k = POSES.scale;
  for (let j = 0; j < J; j++) {
    const i0 = o0 + j * 3, i1 = o1 + j * 3;
    const x = c0[i0] + (c1[i1] - c0[i0]) * a;
    const y = c0[i0 + 1] + (c1[i1 + 1] - c0[i0 + 1]) * a;
    const z = c0[i0 + 2] + (c1[i1 + 2] - c0[i0 + 2]) * a;
    out[j].set(root.x + x * k, z * k, root.z - y * k);
  }
  return true;
}

/** Position eines Objekts zum (gebrochenen) Frame t, in Three-Koordinaten. */
export function sample(entity, t, out) {
  const f0 = Math.min(N - 1, Math.max(0, Math.floor(t)));
  const f1 = Math.min(N - 1, f0 + 1);
  const i0 = f0 * STRIDE + entity * 3, i1 = f1 * STRIDE + entity * 3;
  if (data[i0] === MISSING) return false;
  const a = data[i1] === MISSING ? 0 : t - f0;
  const x = data[i0] + (data[i1] - data[i0]) * a;
  const y = data[i0 + 1] + (data[i1 + 1] - data[i0 + 1]) * a;
  const z = data[i0 + 2] + (data[i1 + 2] - data[i0 + 2]) * a;
  out.set(x * SCALE, z * SCALE, -y * SCALE); // Feld: x Länge, y Breite, z hoch
  return true;
}
