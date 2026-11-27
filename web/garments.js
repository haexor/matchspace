// Kleidungsstücke als eigene Hüllen über dem Körper (Trikot, Hose, Stutzen mit der Textur des Mannschaftsblatts der Bild-KI, tools/kit_sheet.py; Unterhemd, Handschuhe, Schuhe
// einfarbig nach dem, was der Spieler laut tools/kit_player.py trägt).
// Statt Körper und Kleidung in einer Textur zu mischen (Zacken am Saum, Stutzen laufen in die Schuhe) ist jedes Stück ein Netz mit eigener Kante: Die Hülle liegt dort, wo das
// Kleidungsfeld des Avatars (Trikot, Hose, Stutzen, Schuh; Meter, positiv = bedeckt, `fields` in avatar.js) ≥ 0 ist, die Kante wird an der Nulllinie sauber geschnitten.
import * as THREE from 'three';

const HEM_FLARE = { height: 0.05, out: 0.012 };   // Saum des Trikots: Höhe der Aufweitung und Abstand am unteren Rand (m)
const HEM_SHADOW = { shorts: 0.06, rim: 0.012, strength: 0.4 };   // Schatten der Hose unter dem Trikotsaum (Höhe m, Stärke) und Breite der Saumkante
const SOLE = { height: 0.02, lip: 0.008, studs: 0.007 };   // Schuhsohle: Höhe, Überstand, Höhe der Stollenplatte (m)
const PAD = { shirt: 0.018, under: 0.009, shorts: 0.016, socks: 0.007, boots: 0.012, gloves: 0.006 };   // Abstand der Hülle vom Körper (m)
// Ein Stück liegt dort, wo sein Feld ≥ 0 ist und kein darüber getragenes Stück liegt (Trikot über Hose über Schuh über Stutzen)
const EDGE_SMOOTHING = 12;   // Durchgänge, mit denen die Kleidungsfelder vor dem Schneiden geglättet werden (glatte Kanten)
const BOOT_DROP = 0.025;   // Der Schuh endet so viel tiefer als das Schuhfeld des Avatars (m): ein flacher Fußballschuh, kein Stiefel; der Stutzen läuft entsprechend tiefer
const FIELD = {
  shirt: (w) => w[0],
  shorts: (w) => Math.min(w[1], -w[0]),
  socks: (w) => Math.min(w[2], -(w[3] - BOOT_DROP), -w[1], -w[0]),
  boots: (w) => w[3] - BOOT_DROP,
};

/** Glättet ein Feld über die Nachbarn im Netz (Punkte an derselben Stelle, etwa an Nähten der Textur, zählen als einer): Das Netz des Körpers ist grob, die Nulllinie des Feldes folgt sonst
 *  den Dreieckskanten und läuft als Zickzack um Saum, Stutzenrand und Schuhkante. */
function smoothField(geometry, field, passes) {
  const p = geometry.attributes.position, n = p.count, group = new Int32Array(n), keys = new Map();
  for (let i = 0; i < n; i++) {
    const key = `${Math.round(p.getX(i) * 2e4)},${Math.round(p.getY(i) * 2e4)},${Math.round(p.getZ(i) * 2e4)}`;
    if (!keys.has(key)) keys.set(key, keys.size);
    group[i] = keys.get(key);
  }
  const g = keys.size, value = new Float64Array(g), count = new Uint32Array(g), near = Array.from({ length: g }, () => new Set());
  for (let i = 0; i < n; i++) { value[group[i]] += field[i]; count[group[i]]++; }
  for (let k = 0; k < g; k++) value[k] /= count[k];
  const index = geometry.index.array;
  for (let t = 0; t < index.length; t += 3) {
    const a = group[index[t]], b = group[index[t + 1]], c = group[index[t + 2]];
    near[a].add(b).add(c); near[b].add(a).add(c); near[c].add(a).add(b);
  }
  let next = new Float64Array(g);
  for (let pass = 0; pass < passes; pass++) {
    for (let k = 0; k < g; k++) {
      let sum = 0;
      for (const m of near[k]) sum += value[m];
      next[k] = near[k].size ? 0.5 * value[k] + 0.5 * sum / near[k].size : value[k];
    }
    value.set(next);
  }
  return Float32Array.from({ length: n }, (_, i) => value[group[i]]);
}

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
  for (const [name, fn] of Object.entries(FIELD)) {
    const field = smoothField(body.geometry, Float32Array.from({ length: pos.count }, (_, i) => fn(w4(i))), EDGE_SMOOTHING);
    bases[name] = clip(body.geometry, (i) => field[i]);
  }
  // Unterhemd: lange Ärmel vom Schulteransatz bis zum Handgelenk (rein nach der Lage: der Avatar steht in T-Haltung, die Arme liegen entlang ±x)
  const sx = Math.abs(ctx.sleeve.l.from.x), wrist = Math.abs(ctx.wristX);
  bases.under = clip(body.geometry, (i) => Math.min(Math.abs(pos.getX(i)) - (sx - 0.015), wrist - Math.abs(pos.getX(i))));
  // Handschuhe: alles jenseits des Handgelenks (T-Haltung: die Hände liegen außen auf ±x)
  bases.gloves = clip(body.geometry, (i) => Math.abs(pos.getX(i)) - (wrist - 0.012));
  for (const [name, g] of Object.entries(bases)) {
    const p = g.attributes.position, nrm = g.attributes.normal, pad = PAD[name];
    for (let i = 0; i < p.count; i++) p.setXYZ(i, p.getX(i) + nrm.getX(i) * pad, p.getY(i) + nrm.getY(i) * pad, p.getZ(i) + nrm.getZ(i) * pad);
    g.computeBoundingBox();
  }
  // Saum des Trikots: Es fällt über die Hose und steht dort etwas ab (die Hose ist dieselbe Farbe, ohne den Überhang verschwimmen beide)
  {
    const g = bases.shirt, p = g.attributes.position, nrm = g.attributes.normal, edge = Math.abs(ctx.sleeve.l.from.x) * 0.95;
    let yBot = 1e9;
    for (let i = 0; i < p.count; i++) if (Math.abs(p.getX(i)) < edge) yBot = Math.min(yBot, p.getY(i));
    for (let i = 0; i < p.count; i++) {
      if (Math.abs(p.getX(i)) >= edge) continue;
      const t = Math.min(1, Math.max(0, (yBot + HEM_FLARE.height - p.getY(i)) / HEM_FLARE.height)), push = HEM_FLARE.out * t * t * (3 - 2 * t), len = Math.hypot(nrm.getX(i), nrm.getZ(i)) || 1;
      p.setXYZ(i, p.getX(i) + nrm.getX(i) / len * push, p.getY(i), p.getZ(i) + nrm.getZ(i) / len * push);
    }
    g.computeBoundingBox();
  }
  // Schuhsohle: unten steht sie etwas über den Schuh (sonst ist der Schuh eine Röhre wie ein Strumpf)
  {
    const g = bases.boots, p = g.attributes.position, nrm = g.attributes.normal;
    for (let i = 0; i < p.count; i++) {
      const t = Math.min(1, Math.max(0, (SOLE.height - p.getY(i)) / (SOLE.height * 0.5))), push = SOLE.lip * t * t * (3 - 2 * t), len = Math.hypot(nrm.getX(i), nrm.getZ(i)) || 1;
      p.setXYZ(i, p.getX(i) + nrm.getX(i) / len * push, p.getY(i), p.getZ(i) + nrm.getZ(i) / len * push);
    }
    g.computeBoundingBox();
  }
  bases.ctx = ctx;
  return bases;
}

const box = (g) => g.boundingBox ?? (g.computeBoundingBox(), g.boundingBox);

/** Texturkoordinaten einer Hülle aus der Lage in der Grundhaltung und den Rechtecken des Kit-Blatts (Pixel, `kit.boxes`, Bildgröße `kit.size`). Vorn/hinten je Dreieck nach der Normale. */
export function garmentUv(name, geometry, kit, ctx) {
  const p = geometry.attributes.position, nrm = geometry.attributes.normal, n = p.count, uv = new Float32Array(n * 2);
  const [W, H] = kit.size, B = kit.boxes, b = box(geometry);
  const put = (i, x, y) => { uv[i * 2] = x / W; uv[i * 2 + 1] = y / H; };
  const at = (r, fx, fy) => [r[0] + fx * r[2], r[1] + fy * r[3]];
  // Vorder- oder Rückseite des Blatts wird je Dreieck gewählt (Geometrie ist nicht indiziert): sonst spannte ein Dreieck an der Seitennaht
  // mit einer vorderen und einer hinteren Ecke das ganze Blatt auf und es zog sich ein Streifen übers Trikot.
  const facing = new Uint8Array(n);
  for (let t = 0; t + 2 < n; t += 3) facing[t] = facing[t + 1] = facing[t + 2] = nrm.getZ(t) + nrm.getZ(t + 1) + nrm.getZ(t + 2) >= 0 ? 1 : 0;
  if (name === 'shirt') {
    const sx = Math.abs(ctx.sleeve.l.from.x), length = ctx.sleeve.l.length, sy = ctx.sleeve.l.from.y;
    let hemHalf = 0.1, yTop = -1e9, yBot = 1e9;
    for (let i = 0; i < n; i++) {
      const ax = Math.abs(p.getX(i)), y = p.getY(i);
      if (ax < sx * 0.95) { yTop = Math.max(yTop, y); yBot = Math.min(yBot, y); }
    }
    for (let i = 0; i < n; i++) if (Math.abs(p.getX(i)) < sx * 0.95 && p.getY(i) < yBot + 0.05) hemHalf = Math.max(hemHalf, Math.abs(p.getX(i)));
    const SLEEVE = { s: kit.shape.sleeveS, c: kit.shape.sleeveC, w: kit.shape.sleeveW };      // Ärmel im Kit-Blatt (Anteil des Trikotrechtecks, gemessen in tools/kit_sheet.py): Ansatz und Bündchen des linken Ärmels (Bildseite links)
    const BODY = kit.shape.body;                                         // Rumpf im Kit-Blatt: linker und rechter Rand, Oberkante (Anteil)
    const inBody = new Uint8Array(n);      // Rumpf- oder Ärmelabbildung je Dreieck (nach der Mitte): ein Dreieck an der Ärmelnaht mit beiden Abbildungen spannte Teile des Blatts auf und zog helle Splitter über die Schulter
    for (let t = 0; t + 2 < n; t += 3) inBody[t] = inBody[t + 1] = inBody[t + 2] = (Math.abs(p.getX(t)) + Math.abs(p.getX(t + 1)) + Math.abs(p.getX(t + 2))) / 3 <= sx ? 1 : 0;
    for (let i = 0; i < n; i++) {
      const x = p.getX(i), y = p.getY(i), front = facing[i] === 1, r = front ? B.shirtFront : B.shirtBack;
      const side = x >= 0 ? 1 : -1;      // +x = links des Spielers: vorn im Bild rechts, hinten (Ansicht von hinten) im Bild links
      const imgSide = front ? side : -side;          // +1 = rechte Bildhälfte
      if (inBody[i] === 1) {
        const fx = 0.5 + imgSide * Math.min(1, Math.abs(x) / hemHalf) * 0.96 * (BODY[1] - BODY[0]) / 2, fy = BODY[2] + (yTop - y) / (yTop - yBot) * (1 - BODY[2]);
        put(i, ...at(r, fx, 0.02 + 0.94 * fy));
      } else {
        const a = Math.min(1.15, Math.max(0, (Math.abs(x) - sx) / length)), mirror = imgSide;
        const S = at(r, mirror > 0 ? 1 - SLEEVE.s[0] : SLEEVE.s[0], SLEEVE.s[1]), C = at(r, mirror > 0 ? 1 - SLEEVE.c[0] : SLEEVE.c[0], SLEEVE.c[1]);
        const dx = C[0] - S[0], dy = C[1] - S[1], len = Math.hypot(dx, dy);
        let px = dy / len, py = -dx / len;
        if (py > 0) { px = -px; py = -py; }      // senkrecht zur Ärmelachse, nach oben im Bild
        const ky = r[3] * (1 - BODY[2]) / (yTop - yBot), half = SLEEVE.w ? 0.3 * r[3] * (SLEEVE.w[0] + Math.min(1, a) * (SLEEVE.w[1] - SLEEVE.w[0])) : Infinity;
        const w = Math.max(-half, Math.min(half, (y - sy) * ky));      // der Ärmel liegt nicht flach: Punkte unter der Achsel liegen sonst außerhalb der Ärmelfläche des Blatts
        put(i, S[0] + a * dx + w * px, S[1] + a * dy + w * py);
      }
    }
  } else if (name === 'shorts') {
    for (let i = 0; i < n; i++) {
      const front = facing[i] === 1, r = front ? B.shortsFront : B.shortsBack, edge = front ? kit.shape.shortsFront : kit.shape.shortsBack;
      let fx = (p.getX(i) - b.min.x) / (b.max.x - b.min.x);      // vorn steht +x (links des Spielers) im Bild rechts, von hinten links
      if (!front) fx = 1 - fx;
      const fy = (b.max.y - p.getY(i)) / (b.max.y - b.min.y);
      fx = fx < 0.5 ? 0.04 + fx * 0.8 : 0.96 - (1 - fx) * 0.8;      // weder den Spalt zwischen den Hosenbeinen noch den hellen Rand des Blatts abtasten
      if (edge) {      // Bund schmaler als Saum: innerhalb des Umrisses der Hose in dieser Höhe (Zeilen des Blatts, dazwischen gemischt)
        const q = Math.min(edge.length - 1, Math.max(0, fy * edge.length - 0.5)), k = Math.min(edge.length - 2, Math.floor(q)), t = q - k;
        const lo = edge[k][0] + t * (edge[k + 1][0] - edge[k][0]), hi = edge[k][1] + t * (edge[k + 1][1] - edge[k][1]);
        fx = lo + fx * (hi - lo);
      }
      put(i, ...at(r, fx, 0.02 + 0.94 * fy));
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
  }
  return uv;
}

const flat = (colour, roughness = 0.85) => new THREE.MeshStandardMaterial({ color: new THREE.Color(colour).convertSRGBToLinear(), roughness, metalness: 0, side: THREE.DoubleSide });

/** Netze der Kleidungsstücke für eine Figur: `base` aus garmentBases, `skeletonMesh` der geklonte Körper (gleiches Skelett),
 *  `kit` { texture, boxes, shape, size, variant: { baseLayer, gloves, boots } } (Mannschaftsblatt samt aufgedruckter Nummer, was der Spieler zusätzlich trägt). */
/** Schatten und Saumkante als Eckpunktfarbe: unter dem Trikotsaum ist die Hose dunkler (Schattenwurf des Überhangs), der Saum selbst ist ein schmales dunkleres Band. */
export function shade(name, geometry) {
  const p = geometry.attributes.position, n = p.count, out = new Float32Array(n * 3).fill(1), b = box(geometry);
  for (let i = 0; i < n; i++) {
    let f = 1;
    if (name === 'shorts') {
      const t = Math.min(1, Math.max(0, 1 - (b.max.y - p.getY(i)) / HEM_SHADOW.shorts)); f = 1 - HEM_SHADOW.strength * t * t * (3 - 2 * t);
    } else if (name === 'shirt') {
      if (p.getY(i) < b.min.y + HEM_SHADOW.rim) f = 1 - HEM_SHADOW.strength * 0.5;
    }
    out[i * 3] = out[i * 3 + 1] = out[i * 3 + 2] = f;
  }
  return out;
}

/** Material eines Schuhs: Obermaterial in der Farbe des Spielers, Sohle hell (bei hellem Schuh dunkel), Stollenplatte dunkel, Schnürung etwas heller.
 *  Die Zonen entstehen im Fragmentshader aus Höhe und Normale der Grundhaltung (je Pixel, nicht je Eckpunkt: das Netz des Fußes ist grob, Farbwechsel je Eckpunkt zackten). */
export function bootMaterial(colour) {
  const upper = new THREE.Color(colour).convertSRGBToLinear(), luma = 0.2126 * upper.r + 0.7152 * upper.g + 0.0722 * upper.b;
  const sole = new THREE.Color(luma > 0.35 ? '#2a2a2a' : '#e6e6e6').convertSRGBToLinear(), studs = new THREE.Color('#1b1b1b').convertSRGBToLinear();
  const laces = upper.clone().lerp(new THREE.Color(luma > 0.35 ? '#000000' : '#ffffff').convertSRGBToLinear(), 0.28);
  const material = new THREE.MeshStandardMaterial({ color: upper, roughness: 0.55, metalness: 0, side: THREE.DoubleSide });
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, { uSole: { value: sole }, uStuds: { value: studs }, uLaces: { value: laces }, uZones: { value: new THREE.Vector3(SOLE.studs, SOLE.height, 0.06) } });
    shader.vertexShader = shader.vertexShader.replace('#include <common>', '#include <common>\nvarying float vRestY;\nvarying float vRestNy;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvRestY = position.y;\nvRestNy = normal.y;');
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vRestY;\nvarying float vRestNy;\nuniform vec3 uSole;\nuniform vec3 uStuds;\nuniform vec3 uLaces;\nuniform vec3 uZones;')
      .replace('#include <color_fragment>', `#include <color_fragment>
      float e = 0.0015;
      diffuseColor.rgb = mix(diffuseColor.rgb, uLaces, 0.5 * smoothstep(0.55, 0.8, vRestNy) * smoothstep(uZones.z - 0.01, uZones.z + 0.01, vRestY));
      diffuseColor.rgb = mix(uSole, diffuseColor.rgb, smoothstep(uZones.y - e, uZones.y + e, vRestY));
      diffuseColor.rgb = mix(uStuds, diffuseColor.rgb, smoothstep(uZones.x - e, uZones.x + e, vRestY));`);
  };
  return material;
}

export function dressUp(base, skeletonMesh, kit) {
  const meshes = [], v = kit.variant ?? {};
  // Mit Blatt: Textur der Mannschaft. Ohne Blatt (kit.flat = { shirt, shorts, socks } als Farben, z. B. Schiedsrichter, Torwart, Szene ohne Blatt): einfarbige Stücke, sonst gleiche Form und Saumschatten.
  const cloth = (colour) => new THREE.MeshStandardMaterial({ ...(kit.flat ? { color: colour } : { map: kit.texture }), vertexColors: true, roughness: 0.85, metalness: 0, side: THREE.DoubleSide });
  const textured = kit.flat ? null : cloth();
  const parts = [['shirt', textured ?? cloth(kit.flat.shirt)], ['shorts', textured ?? cloth(kit.flat.shorts)], ['socks', textured ?? cloth(kit.flat.socks)], ['boots', bootMaterial(v.boots ?? '#202020')]];
  if (v.baseLayer) parts.push(['under', flat(v.baseLayer)]);
  if (v.gloves) parts.push(['gloves', flat(v.gloves, 0.7)]);
  for (const [name, material] of parts) {
    let g = base[name].clone();
    if (name === 'shirt' || name === 'shorts' || name === 'socks') {
      g = g.index ? g.toNonIndexed() : g;
      if (!kit.flat) g.setAttribute('uv', new THREE.BufferAttribute(garmentUv(name, g, kit, base.ctx), 2));
      g.setAttribute('color', new THREE.BufferAttribute(shade(name, g), 3));
    }
    const mesh = new THREE.SkinnedMesh(g, material);
    mesh.name = `Kit_${name}`;
    mesh.frustumCulled = false;
    mesh.castShadow = true;
    mesh.bind(skeletonMesh.skeleton, skeletonMesh.bindMatrix);
    meshes.push(mesh);
  }
  return meshes;
}
