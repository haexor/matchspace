// Videotextur der Spieler am Körpermodell: Koordinaten in der Textur je Punkt des Modells und der Shader, der daraus die
// Farbe liest (Teil von web/avatar.js; die Textur selbst macht tools/veo_looks.py).
import * as THREE from 'three';
import { partOf } from './avatar-body.js';

// Teile der Videotextur, in der Reihenfolge von meta.looks.segments (tools/veo_looks.py)
const LOOK_PARTS = ['torso', 'head', 'upperarm_l', 'upperarm_r', 'thigh_l', 'thigh_r', 'calf_l', 'calf_r', 'lowerarm_l', 'lowerarm_r', 'foot_l', 'foot_r'];
const X_AXIS = new THREE.Vector3(1, 0, 0), Y_AXIS = new THREE.Vector3(0, 1, 0), Z_AXIS = new THREE.Vector3(0, 0, 1);

/** Teil der Videotextur für einen Körperteil des Modells: Hals zum Rumpf (die Naht liegt dann unter dem Kinn statt am Kragen), Hand zum Unterarm. */
function lookPart(part) {
  if (part === 'neck') return 'torso';
  if (part.startsWith('hand')) return 'lowerarm' + part.slice(4);
  return part;
}

function across(v, axis) {
  return v.clone().addScaledVector(axis, -v.dot(axis)).normalize();
}

/**
 * Koordinaten in der Videotextur je Punkt der Grundhaltung, wie sie tools/veo_looks.py aus den Gelenken
 * rechnet: Körperteil, Lage t entlang seiner Achse und Richtung um die Achse (Kosinus, Sinus; 0 = vorn,
 * 90° = links). Ergebnis als Attribut look = (cos, sin, t, Teil) an jedem Netz.
 */
export function lookCoordinates(template, meshes, body, footLift) {
  const at = (name) => template.getObjectByName(name).getWorldPosition(new THREE.Vector3());
  const hipMid = at('thigh_l').add(at('thigh_r')).multiplyScalar(0.5);
  const shoulderMid = at('upperarm_l').add(at('upperarm_r')).multiplyScalar(0.5);
  const position = body.geometry.attributes.position, skinIndex = body.geometry.attributes.skinIndex, skinWeight = body.geometry.attributes.skinWeight;
  const bodyParts = body.skeleton.bones.map((b) => lookPart(partOf(b.name)));
  let crown = -Infinity;
  const foot = { l: { min: Infinity, max: -Infinity, ground: Infinity }, r: { min: Infinity, max: -Infinity, ground: Infinity } };
  for (let i = 0; i < position.count; i++) {
    let best = 0;
    for (let k = 1; k < 4; k++) if (skinWeight.getComponent(i, k) > skinWeight.getComponent(i, best)) best = k;
    const part = bodyParts[skinIndex.getComponent(i, best)], y = position.getY(i), z = position.getZ(i);
    if (part === 'head') crown = Math.max(crown, y);
    if (part.startsWith('foot')) {
      const f = foot[part.slice(-1)];
      f.min = Math.min(f.min, z); f.max = Math.max(f.max, z); f.ground = Math.min(f.ground, y);
    }
  }
  const axes = {};
  const limb = (name, A, B, arm) => {
    const axis = B.clone().sub(A), length = axis.length();
    axis.divideScalar(length);
    let F, S;
    if (arm) { F = across(Z_AXIS, axis); S = new THREE.Vector3().crossVectors(F, axis); }
    else { S = across(X_AXIS, axis); F = new THREE.Vector3().crossVectors(axis, S); }
    axes[name] = { A, axis, length, F, S };
  };
  {
    const axis = shoulderMid.clone().sub(hipMid), length = axis.length();
    axis.divideScalar(length);
    const F = across(Z_AXIS, axis);
    axes.torso = { A: hipMid, axis, length, F, S: new THREE.Vector3().crossVectors(axis, F) };
    axes.head = { A: shoulderMid, axis: Y_AXIS, length: crown - shoulderMid.y, F: Z_AXIS, S: X_AXIS };
  }
  for (const s of ['l', 'r']) {
    limb('upperarm_' + s, at('upperarm_' + s), at('lowerarm_' + s), true);
    limb('lowerarm_' + s, at('lowerarm_' + s), at('hand_' + s), true);
    limb('thigh_' + s, at('thigh_' + s), at('calf_' + s), false);
    limb('calf_' + s, at('calf_' + s), at('foot_' + s), false);
    const ankle = at('foot_' + s), f = foot[s];
    limb('foot_' + s, new THREE.Vector3(ankle.x, f.ground + footLift, f.min), new THREE.Vector3(ankle.x, f.ground + footLift, f.max), false);
  }
  const p = new THREE.Vector3(), r = new THREE.Vector3();
  for (const mesh of meshes) {
    const index = mesh.geometry.attributes.skinIndex, weight = mesh.geometry.attributes.skinWeight;
    const parts = mesh.skeleton.bones.map((b) => lookPart(partOf(b.name)));
    const own = [];
    for (let i = 0; i < mesh.geometry.attributes.position.count; i++) {
      let best = 0;
      for (let k = 1; k < 4; k++) if (weight.getComponent(i, k) > weight.getComponent(i, best)) best = k;
      own.push(parts[index.getComponent(i, best)]);
    }
    // Teilegrenzen an Gelenken sind Ebenen senkrecht zur Achse des oberen Teils (nicht nach dem Hautgewicht: das ergibt eine gezackte Linie um Knie und Ellbogen)
    const posAttr = mesh.geometry.attributes.position;
    const planes = [];
    for (const s of ['l', 'r']) {
      for (const [upper, lower] of [['upperarm_' + s, 'lowerarm_' + s], ['thigh_' + s, 'calf_' + s]]) {
        const a = axes[upper];
        const signed = (i) => { p.fromBufferAttribute(posAttr, i); return r.subVectors(p, a.A).dot(a.axis) - a.length; };
        planes.push({ upper, lower, signed });
        for (let i = 0; i < own.length; i++) if (own[i] === upper || own[i] === lower) own[i] = signed(i) > 0 ? lower : upper;
      }
    }
    const partOfVertex = splitSeams(mesh.geometry, own, planes);
    const pos = mesh.geometry.attributes.position;
    const look = new Float32Array(pos.count * 4);
    for (let i = 0; i < pos.count; i++) {
      const part = partOfVertex[i], a = axes[part];
      p.fromBufferAttribute(pos, i);
      const along = r.subVectors(p, a.A).dot(a.axis);
      r.addScaledVector(a.axis, -along);
      const c = r.dot(a.F), sn = r.dot(a.S), len = Math.hypot(c, sn) || 1;
      look.set([c / len, sn / len, along / a.length, LOOK_PARTS.indexOf(part)], i * 4);
    }
    mesh.geometry.setAttribute('look', new THREE.BufferAttribute(look, 4));
  }
}

/**
 * Jedes Dreieck gehört zu genau einem Teil der Textur. Der Shader bekommt Teil und Koordinaten (Winkel, t) der drei Punkte und interpoliert sie
 * über das Dreieck; hätte ein Punkt seine Koordinaten für den Nachbarteil, mischten sich zwei Achsen (Zacken an der Teilegrenze).
 * - An Gelenken (Oberarm/Unterarm, Oberschenkel/Unterschenkel) werden Dreiecke, die die Grenzebene schneiden, an der Ebene geteilt: die Grenze wird ein
 *   glatter Ring (neue Punkte je Seite, Hautgewichte vom näheren Punkt, Lage und Normale interpoliert).
 * - An den übrigen Teilegrenzen (Rumpf/Oberschenkel, Hals/Kopf) gehört das Dreieck zum Teil der Mehrheit seiner Punkte; die fremden Punkte bekommen
 *   Kopien (alle Attribute gleich), die ihre Koordinaten für dieses Teil rechnen.
 * Verändert die Geometrie (Punkte und Index) und liefert das Teil je Punkt (alte und neue).
 */
function splitSeams(geometry, own, planes) {
  const index = geometry.index;
  if (!index) return own;
  const tri = index.array, count = own.length;
  const parts = own.slice(), made = new Map(), extra = [];
  const out = [];
  const signs = new Map();
  const dist = (plane, v) => { const k = plane.upper + v; if (!signs.has(k)) signs.set(k, plane.signed(v)); return signs.get(k); };
  const copy = (v, part) => {
    const key = 'c' + v + '|' + part;
    let id = made.get(key);
    if (id === undefined) { id = count + extra.length; made.set(key, id); extra.push({ lo: v, hi: v, t: 0 }); parts.push(part); }
    return id;
  };
  const cut = (plane, a, b, part) => {
    const lo = Math.min(a, b), hi = Math.max(a, b), key = 'x' + lo + '|' + hi + '|' + part;
    let id = made.get(key);
    if (id === undefined) {
      const dl = dist(plane, lo), dh = dist(plane, hi);
      id = count + extra.length; made.set(key, id); extra.push({ lo, hi, t: dl / (dl - dh) }); parts.push(part);
    }
    return id;
  };
  for (let t = 0; t < tri.length; t += 3) {
    const v = [tri[t], tri[t + 1], tri[t + 2]], pt = v.map((i) => own[i]);
    if (pt[0] === pt[1] && pt[1] === pt[2]) { out.push(...v); continue; }
    const plane = planes.find((q) => pt.every((x) => x === q.upper || x === q.lower));
    if (plane) {
      const high = pt.map((x) => x === plane.lower);
      const lone = high.filter(Boolean).length === 1 ? high.indexOf(true) : high.indexOf(false);
      const [a, b, c] = [v[lone], v[(lone + 1) % 3], v[(lone + 2) % 3]];
      const own_a = own[a], other = own[b];
      const n1a = cut(plane, a, b, own_a), n2a = cut(plane, a, c, own_a), n1o = cut(plane, a, b, other), n2o = cut(plane, a, c, other);
      out.push(a, n1a, n2a, n1o, b, c, n1o, c, n2o);
      continue;
    }
    const part = pt[0] === pt[1] || pt[0] === pt[2] ? pt[0] : pt[1] === pt[2] ? pt[1] : pt[0];
    for (let k = 0; k < 3; k++) out.push(own[v[k]] === part ? v[k] : copy(v[k], part));
  }
  if (!extra.length) return own;
  const lerped = new Set(['position', 'normal']);
  const grow = (attr, interpolate) => {
    const size = attr.itemSize, arr = new attr.array.constructor((count + extra.length) * size);
    arr.set(attr.array);
    extra.forEach((e, j) => {
      for (let k = 0; k < size; k++) {
        const lo = attr.array[e.lo * size + k], hi = attr.array[e.hi * size + k];
        arr[(count + j) * size + k] = interpolate ? lo + (hi - lo) * e.t : (e.t < 0.5 ? lo : hi);
      }
    });
    return new THREE.BufferAttribute(arr, size, attr.normalized);
  };
  for (const name of Object.keys(geometry.attributes)) geometry.setAttribute(name, grow(geometry.attributes[name], lerped.has(name)));
  for (const name of Object.keys(geometry.morphAttributes)) geometry.morphAttributes[name] = geometry.morphAttributes[name].map((m) => grow(m, true));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(out), 1));
  return parts;
}

// Farbe aus der Videotextur: Kachel des Spielers, darin der Bereich des Körperteils (Winkel waagrecht, t senkrecht)
export const LOOK_GLSL = `
  uniform sampler2D lookMap; uniform vec4 lookTile; uniform vec4 lookRect[${LOOK_PARTS.length}]; uniform vec2 lookRange[${LOOK_PARTS.length}];
  varying vec2 vLookDir; varying float vLookT; flat varying float vLookPart;
  vec3 lookColour() {
    int part = int(vLookPart + 0.5);
    vec4 rect = lookRect[part];
    vec2 range = lookRange[part];
    float u = clamp((atan(vLookDir.y, vLookDir.x) + PI) / (2.0 * PI) * rect.z, 0.5, rect.z - 0.5);
    float v = clamp((vLookT - range.x) / (range.y - range.x) * rect.w, 0.5, rect.w - 0.5);
    return texture2D(lookMap, (lookTile.xy + rect.xy + vec2(u, v)) / lookTile.zw).rgb;
  }`;
export const LOOK_VERTEX = 'attribute vec4 look; varying vec2 vLookDir; varying float vLookT; flat varying float vLookPart;';
export const LOOK_PASS = 'vLookDir = look.xy; vLookT = look.z; vLookPart = look.w;';

export function lookUniforms(look) {
  return { lookMap: { value: look.map }, lookTile: { value: new THREE.Vector4(look.tile[0], look.tile[1], look.size[0], look.size[1]) },
    lookRect: { value: look.rects }, lookRange: { value: look.ranges } };
}
