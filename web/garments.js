// Kleidungsstücke als eigene Hüllen über dem Körper (Trikot, Unterhemd, Hose, Stutzen, Schuhe), mit der Textur des Kit-Blatts der Bild-KI (tools/kit_sheet.py).
// Statt Körper und Kleidung in einer Textur zu mischen (Zacken am Saum, Stutzen laufen in die Schuhe) ist jedes Stück ein Netz mit eigener Kante: Die Hülle liegt dort, wo das
// Kleidungsfeld des Avatars (Trikot, Hose, Stutzen, Schuh; Meter, positiv = bedeckt, `fields` in avatar.js) ≥ 0 ist, die Kante wird an der Nulllinie sauber geschnitten.
import * as THREE from 'three';

const PAD = { shirt: 0.018, under: 0.009, shorts: 0.016, socks: 0.007, boots: 0.012 };   // Abstand der Hülle vom Körper (m)
// Ein Stück liegt dort, wo sein Feld ≥ 0 ist und kein darüber getragenes Stück liegt (Trikot über Hose über Schuh über Stutzen)
const FIELD = {
  shirt: (w) => w[0],
  shorts: (w) => Math.min(w[1], -w[0]),
  socks: (w) => Math.min(w[2], -w[3], -w[1], -w[0]),
  boots: (w) => w[3],
};

/** Schneidet die Dreiecke von `geometry` an der Linie field = 0 und behält den Teil mit field ≥ 0. Rückgabe: neue BufferGeometry mit Lage, Normale, Haut und Hautgewichten. */
function clip(geometry, field) {
  const pos = geometry.attributes.position, nor = geometry.attributes.normal, si = geometry.attributes.skinIndex, sw = geometry.attributes.skinWeight;
  const index = geometry.index.array, n = pos.count;
  const f = new Float32Array(n);
  for (let i = 0; i < n; i++) f[i] = field(i);
  const P = [], N = [], SI = [], SW = [], out = [], known = new Map();
  const copy = (i, p, q) => { P.push(pos.getX(i), pos.getY(i), pos.getZ(i)); N.push(nor.getX(i), nor.getY(i), nor.getZ(i)); SI.push(si.getX(i), si.getY(i), si.getZ(i), si.getW(i)); SW.push(sw.getX(i), sw.getY(i), sw.getZ(i), sw.getW(i)); };
  const vertex = (i) => {
    const key = `v${i}`;
    if (!known.has(key)) { known.set(key, P.length / 3); copy(i); }
    return known.get(key);
  };
  const edge = (a, b) => {
    const lo = Math.min(a, b), hi = Math.max(a, b), key = `e${lo},${hi}`;
    if (!known.has(key)) {
      const t = f[lo] / (f[lo] - f[hi]);
      known.set(key, P.length / 3);
      const near = t < 0.5 ? lo : hi;
      P.push(pos.getX(lo) + t * (pos.getX(hi) - pos.getX(lo)), pos.getY(lo) + t * (pos.getY(hi) - pos.getY(lo)), pos.getZ(lo) + t * (pos.getZ(hi) - pos.getZ(lo)));
      const nx = nor.getX(lo) + t * (nor.getX(hi) - nor.getX(lo)), ny = nor.getY(lo) + t * (nor.getY(hi) - nor.getY(lo)), nz = nor.getZ(lo) + t * (nor.getZ(hi) - nor.getZ(lo));
      const len = Math.hypot(nx, ny, nz) || 1;
      N.push(nx / len, ny / len, nz / len);
      SI.push(si.getX(near), si.getY(near), si.getZ(near), si.getW(near)); SW.push(sw.getX(near), sw.getY(near), sw.getZ(near), sw.getW(near));
    }
    return known.get(key);
  };
  for (let t = 0; t < index.length; t += 3) {
    const tri = [index[t], index[t + 1], index[t + 2]], poly = [];
    for (let k = 0; k < 3; k++) {
      const a = tri[k], b = tri[(k + 1) % 3];
      if (f[a] >= 0) poly.push(vertex(a));
      if ((f[a] >= 0) !== (f[b] >= 0)) poly.push(edge(a, b));
    }
    for (let k = 1; k + 1 < poly.length; k++) out.push(poly[0], poly[k], poly[k + 1]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(P), 3));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(N), 3));
  g.setAttribute('skinIndex', new THREE.BufferAttribute(new si.array.constructor(SI), 4));
  g.setAttribute('skinWeight', new THREE.BufferAttribute(new Float32Array(SW), 4));
  g.setIndex(out);
  return g;
}

/** Hüllen der Kleidungsstücke einmal je Modell (unabhängig vom Spieler): { shirt, under, shorts, socks, boots } als BufferGeometry in der Grundhaltung, samt Maßen für die Abbildung. */
export function garmentBases(body, ctx) {
  const wear = body.geometry.attributes.wear, pos = body.geometry.attributes.position;
  const w4 = (i) => [wear.getX(i), wear.getY(i), wear.getZ(i), wear.getW(i)];
  const bases = {};
  for (const [name, fn] of Object.entries(FIELD)) bases[name] = clip(body.geometry, (i) => fn(w4(i)));
  // Unterhemd: lange Ärmel vom Schulteransatz bis zum Handgelenk (rein nach der Lage: der Avatar steht in T-Haltung, die Arme liegen entlang ±x)
  const sx = Math.abs(ctx.sleeve.l.from.x), wrist = Math.abs(ctx.wristX);
  bases.under = clip(body.geometry, (i) => Math.min(Math.abs(pos.getX(i)) - (sx - 0.015), wrist - Math.abs(pos.getX(i))));
  for (const [name, g] of Object.entries(bases)) {
    const p = g.attributes.position, nrm = g.attributes.normal, pad = PAD[name];
    for (let i = 0; i < p.count; i++) p.setXYZ(i, p.getX(i) + nrm.getX(i) * pad, p.getY(i) + nrm.getY(i) * pad, p.getZ(i) + nrm.getZ(i) * pad);
    g.computeBoundingBox();
  }
  bases.ctx = ctx;
  return bases;
}

const box = (g) => g.boundingBox;

/** Texturkoordinaten einer Hülle aus der Lage in der Grundhaltung und den Rechtecken des Kit-Blatts (Pixel, `kit.boxes`, Bildgröße `kit.size`). Vorn/hinten nach der Normale. */
export function garmentUv(name, geometry, kit, ctx) {
  const p = geometry.attributes.position, nrm = geometry.attributes.normal, n = p.count, uv = new Float32Array(n * 2);
  const [W, H] = kit.size, B = kit.boxes, b = box(geometry);
  const put = (i, x, y) => { uv[i * 2] = x / W; uv[i * 2 + 1] = y / H; };
  const at = (r, fx, fy) => [r[0] + fx * r[2], r[1] + fy * r[3]];
  if (name === 'under') {
    const [x, y] = at(B.underFront, 0.5, 0.5);
    for (let i = 0; i < n; i++) put(i, x, y);      // einfarbig schwarz: ein Punkt in der Mitte des Stücks
  } else if (name === 'shirt') {
    const sx = Math.abs(ctx.sleeve.l.from.x), length = ctx.sleeve.l.length, sy = ctx.sleeve.l.from.y;
    let hemHalf = 0.1, yTop = -1e9, yBot = 1e9;
    for (let i = 0; i < n; i++) {
      const ax = Math.abs(p.getX(i)), y = p.getY(i);
      if (ax < sx * 0.95) { yTop = Math.max(yTop, y); yBot = Math.min(yBot, y); }
    }
    for (let i = 0; i < n; i++) if (Math.abs(p.getX(i)) < sx * 0.95 && p.getY(i) < yBot + 0.05) hemHalf = Math.max(hemHalf, Math.abs(p.getX(i)));
    const SLEEVE = { s: [0.234, 0.19], c: [0.044, 0.372] };      // Ärmel im Kit-Blatt (Anteil des Trikotrechtecks): Ansatz und Bündchen des linken Ärmels (Bildseite links)
    const BODY = [0.215, 0.785, 0.044];                          // Rumpf im Kit-Blatt: linker und rechter Rand, Oberkante (Anteil)
    for (let i = 0; i < n; i++) {
      const x = p.getX(i), y = p.getY(i), front = nrm.getZ(i) >= 0, r = front ? B.shirtFront : B.shirtBack;
      const side = x >= 0 ? 1 : -1;      // +x = links des Spielers: vorn im Bild rechts, hinten (Ansicht von hinten) im Bild links
      const imgSide = front ? side : -side;          // +1 = rechte Bildhälfte
      if (Math.abs(x) <= sx) {
        const fx = 0.5 + imgSide * Math.min(1, Math.abs(x) / hemHalf) * (BODY[1] - BODY[0]) / 2, fy = BODY[2] + (yTop - y) / (yTop - yBot) * (1 - BODY[2]);
        put(i, ...at(r, fx, fy));
      } else {
        const a = Math.min(1.15, (Math.abs(x) - sx) / length), mirror = imgSide;
        const S = at(r, mirror > 0 ? 1 - SLEEVE.s[0] : SLEEVE.s[0], SLEEVE.s[1]), C = at(r, mirror > 0 ? 1 - SLEEVE.c[0] : SLEEVE.c[0], SLEEVE.c[1]);
        const dx = C[0] - S[0], dy = C[1] - S[1], len = Math.hypot(dx, dy);
        let px = dy / len, py = -dx / len;
        if (py > 0) { px = -px; py = -py; }      // senkrecht zur Ärmelachse, nach oben im Bild
        const ky = r[3] * (1 - BODY[2]) / (yTop - yBot), w = (y - sy) * ky;
        put(i, S[0] + a * dx + w * px, S[1] + a * dy + w * py);
      }
    }
  } else if (name === 'shorts') {
    for (let i = 0; i < n; i++) {
      const front = nrm.getZ(i) >= 0, r = front ? B.shortsFront : B.shortsBack;
      let fx = (p.getX(i) - b.min.x) / (b.max.x - b.min.x);      // vorn steht +x (links des Spielers) im Bild rechts, von hinten links
      if (!front) fx = 1 - fx;
      put(i, ...at(r, fx, (b.max.y - p.getY(i)) / (b.max.y - b.min.y)));
    }
  } else if (name === 'socks') {
    const half = (b.max.x + b.min.x) / 2;
    for (let i = 0; i < n; i++) {
      const x = p.getX(i), side = x >= half ? 1 : -1, r = side > 0 ? B.sockR : B.sockL;
      const xs = side > 0 ? [half, b.max.x] : [b.min.x, half];
      const fx = (x - xs[0]) / Math.max(1e-6, xs[1] - xs[0]);
      const tube = r === B.sockL ? [0.5, 0.98] : [0.02, 0.5];      // das Bein des flachen Strumpfs liegt in der linken Strumpf rechts, im rechten links (Paar spiegelbildlich), der Fuß daneben
      put(i, ...at(r, tube[0] + fx * (tube[1] - tube[0]), 0.62 * (b.max.y - p.getY(i)) / (b.max.y - b.min.y)));
    }
  } else if (name === 'boots') {
    const half = (b.max.x + b.min.x) / 2;
    for (let i = 0; i < n; i++) {
      const side = p.getX(i) >= half ? 1 : -1, r = side > 0 ? B.bootR : B.bootL;
      const fz = (p.getZ(i) - b.min.z) / Math.max(1e-6, b.max.z - b.min.z);      // 0 = hinten (Ferse), 1 = vorn (Spitze)
      put(i, ...at(r, side > 0 ? fz : 1 - fz, (b.max.y - p.getY(i)) / (b.max.y - b.min.y)));
    }
  }
  return uv;
}

/** Netze der Kleidungsstücke für eine Figur: `base` aus garmentBases, `skeletonMesh` der geklonte Körper (gleiches Skelett), `kit` { texture, boxes, size }. */
export function dressUp(base, skeletonMesh, kit) {
  const meshes = [];
  const material = new THREE.MeshStandardMaterial({ map: kit.texture, roughness: 0.85, metalness: 0, side: THREE.DoubleSide });
  for (const name of ['shirt', 'under', 'shorts', 'socks', 'boots']) {
    const g = base[name].clone();
    g.setAttribute('uv', new THREE.BufferAttribute(garmentUv(name, g, kit, base.ctx), 2));
    const mesh = new THREE.SkinnedMesh(g, material);
    mesh.name = `Kit_${name}`;
    mesh.frustumCulled = false;
    mesh.castShadow = true;
    mesh.bind(skeletonMesh.skeleton, skeletonMesh.bindMatrix);
    meshes.push(mesh);
  }
  return meshes;
}
