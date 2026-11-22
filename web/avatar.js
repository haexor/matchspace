// Körpermodell: ein bewegliches Menschenmodell, das den 20 Gelenken eines Spielers folgt.
//
// Modell: models/player/player.glb, gebaut aus „Universal Base Characters“ von Quaternius (CC0, siehe
// models/player/LIZENZ.txt). Es ist ein erwachsener, sehr muskulöser Körper; hier wird er einmal beim Laden
// zu einem schmaleren Jugendlichen umgeformt und angezogen (Trikot, Hose, Stutzen, Schuhe als Auftrag auf
// der Oberfläche). Das Modell liefert nur die Form. Die Farben kommen, wo vorhanden, je Spieler aus dem
// Video (looks.png der Szene, tools/veo_looks.py); sonst aus den Mannschaftsfarben.
//
// Die Spieldaten liefern Gelenkpositionen, das Modell braucht Drehungen je Knochen. Jeder Knochen
// wird deshalb so gedreht, dass er vom eigenen Gelenk zum nächsten zeigt; die Verdrehung um die
// eigene Achse kommt vom Rumpf und bei gebeugtem Knie oder Ellbogen aus der Beugeebene. Die
// Knochenlängen des Modells werden auf die des Spielers gesetzt, damit Füße und Hände dort landen,
// wo die Daten sie haben.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';
import * as SkeletonUtils from './vendor/utils/SkeletonUtils.js';

// Name im Programm -> Knochen des Modells
const BONE = { Hips: 'pelvis', Spine: 'spine_01', Spine1: 'spine_02', Spine2: 'spine_03', Neck: 'neck_01', Head: 'Head',
  LeftShoulder: 'clavicle_l', LeftArm: 'upperarm_l', LeftForeArm: 'lowerarm_l', LeftHand: 'hand_l',
  RightShoulder: 'clavicle_r', RightArm: 'upperarm_r', RightForeArm: 'lowerarm_r', RightHand: 'hand_r',
  LeftUpLeg: 'thigh_l', LeftLeg: 'calf_l', LeftFoot: 'foot_l', LeftToeBase: 'ball_l',
  RightUpLeg: 'thigh_r', RightLeg: 'calf_r', RightFoot: 'foot_r', RightToeBase: 'ball_r' };
const DRIVEN = Object.keys(BONE);
const PARENT = { Hips: null, Spine: 'Hips', Spine1: 'Spine', Spine2: 'Spine1', Neck: 'Spine2', Head: 'Neck',
  LeftShoulder: 'Spine2', LeftArm: 'LeftShoulder', LeftForeArm: 'LeftArm', LeftHand: 'LeftForeArm',
  RightShoulder: 'Spine2', RightArm: 'RightShoulder', RightForeArm: 'RightArm', RightHand: 'RightForeArm',
  LeftUpLeg: 'Hips', LeftLeg: 'LeftUpLeg', LeftFoot: 'LeftLeg', LeftToeBase: 'LeftFoot',
  RightUpLeg: 'Hips', RightLeg: 'RightUpLeg', RightFoot: 'RightLeg', RightToeBase: 'RightFoot' };
const SKIN = new THREE.Color(0xd8a583), BOOT = new THREE.Color(0x141414);
const HAIR_COLOURS = [0x2a1c13, 0x3b2a1b, 0x4c3521, 0x6a4b2c, 0x8a6a3f, 0x1b1613].map((c) => new THREE.Color(c));
const HAIR_STYLES = ['Hair_SimpleParted', 'Hair_SimpleParted', 'Hair_Buzzed'];
const FINGERS = ['index', 'middle', 'ring', 'pinky'];
const CURL = [0.35, 0.8, 1.2];  // Beugung der drei Fingerglieder gegenüber der flachen Hand (Bogenmaß, aufsummiert)

// Umformen zum Jugendlichen: Breite und Tiefe des Rumpfs, Dicke der Glieder (Anteil des Erwachsenenmodells)
const SLIM = { torsoX: 0.84, torsoZ: 0.86, upperarm: 0.74, lowerarm: 0.8, hand: 0.9, thigh: 0.84, calf: 0.88, neck: 0.98, jaw: 0.9 };
// Kleidung trägt auf (Meter)
const PAD = { shirt: 0.016, sleeve: 0.02, shorts: 0.014, shortsHem: 0.024, sock: 0.004, boot: 0.008 };

// Teile der Videotextur, in der Reihenfolge von meta.looks.segments (tools/veo_looks.py)
const LOOK_PARTS = ['torso', 'head', 'upperarm_l', 'upperarm_r', 'thigh_l', 'thigh_r', 'calf_l', 'calf_r', 'lowerarm_l', 'lowerarm_r', 'foot_l', 'foot_r'];
const X_AXIS = new THREE.Vector3(1, 0, 0), Y_AXIS = new THREE.Vector3(0, 1, 0), Z_AXIS = new THREE.Vector3(0, 0, 1);

const v1 = new THREE.Vector3(), v2 = new THREE.Vector3(), v3 = new THREE.Vector3(), v4 = new THREE.Vector3();
const basis = new THREE.Matrix4(), q1 = new THREE.Quaternion();
const FORWARD = new THREE.Vector3(0, 0, 1), BACK = new THREE.Vector3(0, 0, -1);

/** Drehung, die die Modellachsen (x links, y oben, z vorn) auf einen Körperteil legt. keep: 'left' oder 'up' bleibt exakt. */
function frame(left, up, keep, out) {
  if (keep === 'left') {
    v1.copy(left).normalize();
    v2.copy(up).addScaledVector(v1, -up.dot(v1)).normalize();
  } else {
    v2.copy(up).normalize();
    v1.copy(left).addScaledVector(v2, -left.dot(v2)).normalize();
  }
  v3.crossVectors(v1, v2);
  return out.setFromRotationMatrix(basis.makeBasis(v1, v2, v3));
}

/** out = kürzeste Drehung, die die mitgedrehte Ruherichtung auf target legt, nach der Drehung des Vorgängers. */
function swing(parentDelta, restDir, target, out) {
  v1.copy(restDir).applyQuaternion(parentDelta);
  return out.setFromUnitVectors(v1, target).multiply(parentDelta);
}

/** Dreht delta um axis, bis die Modellachse ref in Richtung bend zeigt (Beugeebene von Knie oder Ellbogen). */
function twist(delta, axis, ref, joint, a, b) {
  v2.addVectors(a, b).multiplyScalar(0.5).subVectors(joint, v2);  // wohin das Gelenk aus der Geraden ragt
  v2.addScaledVector(axis, -v2.dot(axis));
  const bend = v2.length();
  if (bend < 0.02) return;
  v2.divideScalar(bend);
  v1.copy(ref).applyQuaternion(delta);
  v1.addScaledVector(axis, -v1.dot(axis)).normalize();
  const angle = Math.atan2(v3.crossVectors(v1, v2).dot(axis), v1.dot(v2));
  const w = Math.min(1, (bend - 0.02) / 0.06);
  delta.premultiply(q1.setFromAxisAngle(axis, angle * w * w * (3 - 2 * w)));
}

function hash(text) {
  let h = 2166136261;
  for (const c of String(text)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

/** Zu welchem Körperteil ein Knochen des Modells gehört. */
function partOf(name) {
  if (name === 'Head') return 'head';
  if (name === 'neck_01') return 'neck';
  if (name === 'pelvis' || name.startsWith('spine') || name.startsWith('clavicle')) return 'torso';
  const side = name.endsWith('_l') ? 'l' : 'r';
  if (name.startsWith('upperarm')) return 'upperarm_' + side;
  if (name.startsWith('lowerarm')) return 'lowerarm_' + side;
  if (name.startsWith('thigh')) return 'thigh_' + side;
  if (name.startsWith('calf')) return 'calf_' + side;
  if (name.startsWith('foot') || name.startsWith('ball')) return 'foot_' + side;
  return 'hand_' + side;  // Hand und Finger
}

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
function lookCoordinates(template, meshes, body, footLift) {
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
    const pos = mesh.geometry.attributes.position, index = mesh.geometry.attributes.skinIndex, weight = mesh.geometry.attributes.skinWeight;
    const parts = mesh.skeleton.bones.map((b) => lookPart(partOf(b.name)));
    const look = new Float32Array(pos.count * 4);
    for (let i = 0; i < pos.count; i++) {
      let best = 0;
      for (let k = 1; k < 4; k++) if (weight.getComponent(i, k) > weight.getComponent(i, best)) best = k;
      const part = parts[index.getComponent(i, best)], a = axes[part];
      p.fromBufferAttribute(pos, i);
      const along = r.subVectors(p, a.A).dot(a.axis);
      r.addScaledVector(a.axis, -along);
      const c = r.dot(a.F), sn = r.dot(a.S), len = Math.hypot(c, sn) || 1;
      look.set([c / len, sn / len, along / a.length, LOOK_PARTS.indexOf(part)], i * 4);
    }
    mesh.geometry.setAttribute('look', new THREE.BufferAttribute(look, 4));
  }
}

// Farbe aus der Videotextur: Kachel des Spielers, darin der Bereich des Körperteils (Winkel waagrecht, t senkrecht)
const LOOK_GLSL = `
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
const LOOK_VERTEX = 'attribute vec4 look; varying vec2 vLookDir; varying float vLookT; flat varying float vLookPart;';
const LOOK_PASS = 'vLookDir = look.xy; vLookT = look.z; vLookPart = look.w;';

function lookUniforms(look) {
  return { lookMap: { value: look.map }, lookTile: { value: new THREE.Vector4(look.tile[0], look.tile[1], look.size[0], look.size[1]) },
    lookRect: { value: look.rects }, lookRange: { value: look.ranges } };
}

/**
 * Formt das Modell in der Grundhaltung um: schmalerer Rumpf, dünnere Arme und Beine. Die Gelenke von Schulter
 * und Hüfte rücken mit nach innen. Danach gilt die neue Grundhaltung als Bindung von Netz und Skelett.
 */
function reshape(template, meshes) {
  const pos = (name) => template.getObjectByName(name).getWorldPosition(new THREE.Vector3());
  const centreZ = pos('spine_02').z;
  const shift = {}, axis = {};
  for (const side of ['l', 'r']) {
    const shoulder = pos('upperarm_' + side), hip = pos('thigh_' + side);
    shift['arm_' + side] = new THREE.Vector3((SLIM.torsoX - 1) * shoulder.x, 0, (SLIM.torsoZ - 1) * (shoulder.z - centreZ));
    shift['leg_' + side] = new THREE.Vector3((SLIM.torsoX - 1) * hip.x, 0, (SLIM.torsoZ - 1) * (hip.z - centreZ));
    for (const [part, a, b, f] of [['upperarm', 'upperarm', 'lowerarm', SLIM.upperarm], ['lowerarm', 'lowerarm', 'hand', SLIM.lowerarm],
      ['thigh', 'thigh', 'calf', SLIM.thigh], ['calf', 'calf', 'foot', SLIM.calf]]) {
      const from = pos(`${a}_${side}`), dir = pos(`${b}_${side}`).sub(from).normalize();
      axis[`${part}_${side}`] = { from, dir, f };
    }
    axis['hand_' + side] = { from: pos('hand_' + side), dir: pos('middle_01_' + side).sub(pos('hand_' + side)).normalize(), f: SLIM.hand };
  }
  // Gesicht: Das Modell hat das kantige Kinn eines Erwachsenen; unterhalb der Nase wird der Kopf schmaler.
  const head = pos('Head'), nose = head.y + 0.075, chin = head.y + 0.005;
  const d = new THREE.Vector3(), r = new THREE.Vector3(), p = new THREE.Vector3();
  for (const mesh of meshes) {
    const position = mesh.geometry.attributes.position, index = mesh.geometry.attributes.skinIndex, weight = mesh.geometry.attributes.skinWeight;
    const parts = mesh.skeleton.bones.map((b) => partOf(b.name));
    for (let i = 0; i < position.count; i++) {
      p.fromBufferAttribute(position, i);
      d.set(0, 0, 0);
      for (let k = 0; k < 4; k++) {
        const w = weight.getComponent(i, k);
        if (w <= 0) continue;
        const part = parts[index.getComponent(i, k)];
        if (part === 'head') {
          const low = Math.min(1, Math.max(0, (nose - p.y) / (nose - chin)));
          d.x += w * (SLIM.jaw - 1) * low * p.x;
          d.z += w * (SLIM.jaw - 1) * 0.5 * low * (p.z - head.z);
          continue;
        }
        if (part === 'torso' || part === 'neck') {
          const f = part === 'neck' ? SLIM.neck : 1;
          d.x += w * (SLIM.torsoX * f - 1) * p.x;
          d.z += w * (SLIM.torsoZ * f - 1) * (p.z - centreZ);
          continue;
        }
        const side = part.slice(-1), limb = part.startsWith('upperarm') || part.startsWith('lowerarm') || part.startsWith('hand') ? 'arm_' : 'leg_';
        d.addScaledVector(shift[limb + side], w);
        const a = axis[part];
        if (a) {
          r.subVectors(p, a.from);
          r.addScaledVector(a.dir, -r.dot(a.dir));
          d.addScaledVector(r, w * (a.f - 1));
        }
      }
      position.setXYZ(i, p.x + d.x, p.y + d.y, p.z + d.z);
    }
    position.needsUpdate = true;
  }
  for (const side of ['l', 'r']) {
    for (const [name, key] of [['upperarm_', 'arm_'], ['thigh_', 'leg_']]) {
      const bone = template.getObjectByName(name + side);
      bone.position.copy(bone.parent.worldToLocal(bone.getWorldPosition(new THREE.Vector3()).add(shift[key + side])));
    }
  }
  template.updateMatrixWorld(true);
  for (const skeleton of new Set(meshes.map((m) => m.skeleton))) skeleton.calculateInverses();
}

/**
 * Zieht das Körpernetz an: Unter Trikot und Hose wird das Muskelrelief geglättet, dann trägt die Kleidung auf.
 * Punkte, die im Netz doppelt vorkommen (Nähte der Textur), werden gemeinsam bewegt; die Normalen entstehen neu.
 */
function dress(mesh, wear, extra) {
  const geometry = mesh.geometry, position = geometry.attributes.position, n = position.count;
  const group = new Int32Array(n), keys = new Map();
  for (let i = 0; i < n; i++) {
    const key = `${Math.round(position.getX(i) * 2e4)},${Math.round(position.getY(i) * 2e4)},${Math.round(position.getZ(i) * 2e4)}`;
    if (!keys.has(key)) keys.set(key, keys.size);
    group[i] = keys.get(key);
  }
  const g = keys.size, P = new Float32Array(g * 3), cloth = new Float32Array(g), pad = new Float32Array(g);
  for (let i = 0; i < n; i++) {
    const k = group[i], shirt = wear[i * 4], shorts = wear[i * 4 + 1], sock = wear[i * 4 + 2], boot = wear[i * 4 + 3];
    P[k * 3] = position.getX(i); P[k * 3 + 1] = position.getY(i); P[k * 3 + 2] = position.getZ(i);
    cloth[k] = Math.max(cloth[k], Math.min(1, Math.max(shirt, shorts, 0) / 0.04), Math.min(1, Math.max(boot, 0) / 0.02));   // zum Saum hin läuft die Glättung aus; im Schuh verschwinden die Zehen
    pad[k] = Math.max(pad[k], shirt > 0 ? PAD.shirt + extra[i] : shorts > 0 ? PAD.shorts + extra[i] : boot > 0 ? PAD.boot : sock > 0 ? PAD.sock : 0);
  }
  const index = geometry.index.array, near = Array.from({ length: g }, () => new Set());
  for (let t = 0; t < index.length; t += 3) {
    const a = group[index[t]], b = group[index[t + 1]], c = group[index[t + 2]];
    near[a].add(b).add(c); near[b].add(a).add(c); near[c].add(a).add(b);
  }
  const Q = new Float32Array(g * 3);
  for (let pass = 0; pass < 24; pass++) {
    for (let k = 0; k < g; k++) {
      let x = 0, y = 0, z = 0;
      for (const m of near[k]) { x += P[m * 3]; y += P[m * 3 + 1]; z += P[m * 3 + 2]; }
      const w = 0.5 * cloth[k], c = near[k].size || 1;
      Q[k * 3] = P[k * 3] + w * (x / c - P[k * 3]); Q[k * 3 + 1] = P[k * 3 + 1] + w * (y / c - P[k * 3 + 1]); Q[k * 3 + 2] = P[k * 3 + 2] + w * (z / c - P[k * 3 + 2]);
    }
    P.set(Q);
  }
  const normals = () => {
    const N = new Float32Array(g * 3), a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    for (let t = 0; t < index.length; t += 3) {
      const ia = group[index[t]], ib = group[index[t + 1]], ic = group[index[t + 2]];
      a.fromArray(P, ia * 3); b.fromArray(P, ib * 3); c.fromArray(P, ic * 3);
      b.sub(a); c.sub(a); b.cross(c);
      for (const k of [ia, ib, ic]) { N[k * 3] += b.x; N[k * 3 + 1] += b.y; N[k * 3 + 2] += b.z; }
    }
    for (let k = 0; k < g; k++) {
      const len = Math.hypot(N[k * 3], N[k * 3 + 1], N[k * 3 + 2]) || 1;
      N[k * 3] /= len; N[k * 3 + 1] /= len; N[k * 3 + 2] /= len;
    }
    return N;
  };
  let N = normals();
  for (let k = 0; k < g; k++) for (let c = 0; c < 3; c++) P[k * 3 + c] += N[k * 3 + c] * pad[k];
  N = normals();
  const normal = geometry.attributes.normal;
  for (let i = 0; i < n; i++) {
    const k = group[i];
    position.setXYZ(i, P[k * 3], P[k * 3 + 1], P[k * 3 + 2]);
    normal.setXYZ(i, N[k * 3], N[k * 3 + 1], N[k * 3 + 2]);
  }
  position.needsUpdate = true;
  normal.needsUpdate = true;
}

export async function loadAvatars(url) {
  const gltf = await new GLTFLoader().loadAsync(url);
  const template = gltf.scene;
  template.updateMatrixWorld(true);
  const all = [];
  template.traverse((o) => { if (o.isSkinnedMesh) all.push(o); });
  const hairs = all.filter((m) => m.name.startsWith('Hair_'));
  const body = all.find((m) => m.geometry.attributes.position.count > 4000 && !m.name.startsWith('Hair_'));
  const brows = all.find((m) => m.name.startsWith('Eyebrows')), eyes = all.find((m) => m.name.startsWith('Eyes'));
  reshape(template, all);

  const rest = {};
  for (const name of DRIVEN) {
    const bone = template.getObjectByName(BONE[name]);
    rest[name] = { q: bone.getWorldQuaternion(new THREE.Quaternion()), p: bone.getWorldPosition(new THREE.Vector3()), local: bone.position.clone() };
  }
  for (const name of DRIVEN) rest[name].inverse = rest[name].q.clone().invert();
  const hipsParent = template.getObjectByName(BONE.Hips).parent;
  const hipsParentQ = hipsParent.getWorldQuaternion(new THREE.Quaternion());
  const hipsParentInverse = hipsParent.matrixWorld.clone().invert();
  const dir = (a, b) => rest[b].p.clone().sub(rest[a].p).normalize();
  const restDir = {};
  for (const side of ['Left', 'Right']) {
    restDir[side + 'UpLeg'] = dir(side + 'UpLeg', side + 'Leg');
    restDir[side + 'Leg'] = dir(side + 'Leg', side + 'Foot');
    restDir[side + 'Arm'] = dir(side + 'Arm', side + 'ForeArm');
    restDir[side + 'ForeArm'] = dir(side + 'ForeArm', side + 'Hand');
    restDir[side + 'Foot'] = dir(side + 'Foot', side + 'ToeBase').setY(0).normalize();
  }
  const restLeg = rest.LeftLeg.p.distanceTo(rest.LeftUpLeg.p) + rest.LeftFoot.p.distanceTo(rest.LeftLeg.p);
  const hipMid = rest.LeftUpLeg.p.clone().add(rest.RightUpLeg.p).multiplyScalar(0.5);
  const hipDrop = hipMid.clone().sub(rest.Hips.p);                       // vom Beckenknochen zur Mitte der Hüftgelenke
  const shoulderY = (rest.LeftArm.p.y + rest.RightArm.p.y) / 2, shoulderHalf = Math.abs(rest.LeftArm.p.x - rest.RightArm.p.x) / 2;
  // Der Punkt „neck“ der Daten liegt über der Schulterlinie (Schultern hängen rund 18°); der Halsknochen des Modells noch etwas höher.
  const neckLift = rest.Neck.p.y - (shoulderY + 0.31 * shoulderHalf);
  const restSpine = rest.Neck.p.y - rest.Hips.p.y;

  // Ausrüstung als vier Felder je Punkt der Oberfläche (Meter, positiv = bedeckt): Trikot, Hose, Stutzen, Schuh.
  // Sie hängen an der Lage in der Grundhaltung und verlaufen über Gelenke hinweg stetig; die Säume liegen dort,
  // wo ein Feld durch null geht, und werden je Bildpunkt gerechnet. Reihenfolge: Trikot über Hose über Schuh über Stutzen.
  const kneeY = rest.LeftLeg.p.y, thigh = rest.LeftUpLeg.p.y - kneeY;
  const shortsHem = kneeY + 0.33 * thigh, sockTop = kneeY - 0.075, bootTop = rest.LeftFoot.p.y + 0.03, waist = rest.Hips.p.y + 0.005, collar = rest.Neck.p.y + 0.018;
  const sleeve = {};
  for (const [side, s] of [['Left', 'l'], ['Right', 'r']]) sleeve[s] = { from: rest[side + 'Arm'].p, dir: restDir[side + 'Arm'], length: 0.52 * rest[side + 'ForeArm'].p.distanceTo(rest[side + 'Arm'].p) };
  function fields(bone, x, y, z, out, o) {
    const part = partOf(bone), side = part.slice(-1);
    let shirt = -1, shorts = -1, more = 0;
    if (part === 'neck' || part === 'torso') {
      const neckline = collar + 0.55 * Math.abs(x) + 0.3 * Math.min(0.06, Math.max(0, rest.Neck.p.z - z)) - y;   // hinten höher geschlossen
      shirt = Math.min(neckline, y - waist);
      shorts = waist + 0.1 - y;
    } else if (part.startsWith('upperarm')) {
      shirt = sleeve[side].length - v1.set(x, y, z).sub(sleeve[side].from).dot(sleeve[side].dir);
      more = PAD.sleeve - PAD.shirt;
    } else if (part.startsWith('thigh')) {
      shorts = y - shortsHem;
      shirt = y - waist;
      more = (PAD.shortsHem - PAD.shorts) * Math.min(1, Math.max(0, (waist - y) / (waist - shortsHem)));
    }
    const leg = part.startsWith('thigh') || part.startsWith('calf') || part.startsWith('foot');
    out[o] = shirt; out[o + 1] = shorts; out[o + 2] = leg ? sockTop - y : -1; out[o + 3] = leg ? bootTop - y : -1;
    return more;
  }
  const position = body.geometry.attributes.position, skinIndex = body.geometry.attributes.skinIndex, skinWeight = body.geometry.attributes.skinWeight;
  const wear = new Float32Array(position.count * 4), extra = new Float32Array(position.count);
  for (let i = 0; i < position.count; i++) {
    let best = 0;
    for (let k = 1; k < 4; k++) if (skinWeight.getComponent(i, k) > skinWeight.getComponent(i, best)) best = k;
    extra[i] = fields(body.skeleton.bones[skinIndex.getComponent(i, best)].name, position.getX(i), position.getY(i), position.getZ(i), wear, i * 4);
  }
  // Wo die Rückennummer sitzt (Grundhaltung): halbe Breite, Mitte in der Höhe, halbe Höhe
  const plate = new THREE.Vector4(0.13, (shoulderY + rest.Hips.p.y) / 2 + 0.05, 0.13, 1);
  dress(body, wear, extra);
  body.geometry.setAttribute('wear', new THREE.BufferAttribute(wear, 4));
  lookCoordinates(template, [body, ...hairs], body, 0.035);

  // Entspannte Hände: Finger leicht gebeugt statt gestreckt wie in der Grundhaltung.
  for (const s of ['l', 'r']) {
    const at = (name) => template.getObjectByName(`${name}_${s}`).getWorldPosition(new THREE.Vector3());
    const hand = at('hand'), palm = new THREE.Vector3().crossVectors(at('index_01').sub(hand), at('pinky_01').sub(hand)).normalize();
    if (palm.dot(new THREE.Vector3(-Math.sign(hand.x), -1, 0)) < 0) palm.negate();   // Handfläche zeigt zum Körper
    for (const finger of FINGERS) {
      const joints = [1, 2, 3].map((i) => template.getObjectByName(`${finger}_0${i}_${s}`));
      if (joints.some((b) => !b)) continue;
      const along = joints[1].getWorldPosition(new THREE.Vector3()).sub(joints[0].getWorldPosition(new THREE.Vector3())).normalize();
      const bend = new THREE.Vector3().crossVectors(along, palm).normalize();
      let parentWorld = joints[0].parent.getWorldQuaternion(new THREE.Quaternion());
      const restWorld = joints.map((b) => b.getWorldQuaternion(new THREE.Quaternion()));
      joints.forEach((bone, i) => {
        const world = new THREE.Quaternion().setFromAxisAngle(bend, CURL[i]).multiply(restWorld[i]);
        bone.quaternion.copy(parentWorld).invert().multiply(world);
        parentWorld = world;
      });
    }
  }
  template.updateMatrixWorld(true);

  const blank = new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1);
  blank.needsUpdate = true;
  function numberTexture(text) {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 256;
    const g = cv.getContext('2d');
    g.fillStyle = '#fff';
    g.strokeStyle = 'rgba(0,0,0,0.5)';
    g.lineWidth = 10;
    g.lineJoin = 'round';
    g.font = `bold ${text.length > 1 ? 180 : 210}px system-ui, sans-serif`;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.strokeText(text, 128, 138);
    g.fillText(text, 128, 138);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return tex;
  }
  // Körper: Haut und Ausrüstung nach den Feldern gefärbt; die Rückennummer ist auf das Trikot gedruckt.
  function bodyMaterial(kit, number, look) {
    const material = new THREE.MeshStandardMaterial({ roughness: 0.78, metalness: 0 });
    const uniforms = { numberMap: { value: number === null ? blank : numberTexture(String(number)) }, plate: { value: number === null ? new THREE.Vector4(1, 0, 1, 0) : plate },
      kitSkin: { value: kit.skin ?? SKIN }, kitShirt: { value: kit.shirt }, kitShorts: { value: kit.shorts }, kitSock: { value: kit.socks }, kitBoot: { value: BOOT },
      ...(look ? lookUniforms(look) : {}) };
    // Mit Videotextur: Farbe von dort (Licht des Spieltags steckt schon darin, deshalb etwas aufgehellt); sonst Mannschaftsfarben je Kleidungsstück
    const colour = look ? 'vec3 kitColour = lookColour() * 1.15;' : `vec3 kitColour = mix(kitSkin, kitSock, covered(vWear.z));
          kitColour = mix(kitColour, kitBoot, covered(vWear.w));
          kitColour = mix(kitColour, kitShorts, covered(vWear.y));
          kitColour = mix(kitColour, kitShirt, covered(vWear.x));`;
    material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>\nattribute vec4 wear; varying vec4 vWear; varying vec3 vRest; varying float vBack;\n${look ? LOOK_VERTEX : ''}`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>\nvWear = wear; vRest = position; vBack = normal.z;\n${look ? LOOK_PASS : ''}`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
          varying vec4 vWear; varying vec3 vRest; varying float vBack;
          uniform sampler2D numberMap; uniform vec4 plate; uniform vec3 kitSkin, kitShirt, kitShorts, kitSock, kitBoot;
          float covered(float d) { return smoothstep(-0.5, 0.5, d / max(fwidth(d), 1e-5)); }
          ${look ? LOOK_GLSL : ''}`)
        .replace('#include <color_fragment>', `${colour}
          vec2 plateUv = vec2(0.5 - vRest.x / (2.0 * plate.x), 0.5 + (vRest.y - plate.y) / (2.0 * plate.z));
          if (plate.w > 0.5 && vBack < -0.25 && vWear.x > 0.0 && plateUv.x > 0.0 && plateUv.x < 1.0 && plateUv.y > 0.0 && plateUv.y < 1.0) {
            vec4 digit = texture2D(numberMap, plateUv);
            kitColour = mix(kitColour, digit.rgb, digit.a);
          }
          diffuseColor.rgb *= kitColour;`);
    };
    material.customProgramCacheKey = () => (look ? 'matchspace-player-body-look' : 'matchspace-player-body');
    return material;
  }
  // Haare mit Videotextur: Strähnen aus der Haartextur des Modells, Farbe vom Oberkopf im Video
  function hairLookMaterial(look) {
    const material = new THREE.MeshStandardMaterial({ map: hairMap, roughness: 0.9, metalness: 0, side: THREE.DoubleSide });
    const uniforms = lookUniforms(look);
    material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>\n${LOOK_VERTEX}`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>\n${LOOK_PASS}`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>\n${LOOK_GLSL}`)
        .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb *= lookColour() * 1.6;');
    };
    material.customProgramCacheKey = () => 'matchspace-player-hair-look';
    return material;
  }
  const hairMap = brows?.material.map ?? hairs[0]?.material.map ?? null;
  const hairMaterials = new Map();
  function hairMaterial(colour) {
    const key = colour.getHexString();
    if (!hairMaterials.has(key)) {
      hairMaterials.set(key, new THREE.MeshStandardMaterial({ map: hairMap, color: colour.clone().multiplyScalar(1.5), roughness: 0.9, metalness: 0, side: THREE.DoubleSide }));
    }
    return hairMaterials.get(key);
  }
  if (eyes) { eyes.material.roughness = 0.35; eyes.material.metalness = 0; }

  /**
   * kit: { shirt, shorts, socks } als THREE.Color, optional skin und hair; number: Rückennummer oder null; seed: wählt die Frisur
   * (und ohne Videotextur die Haarfarbe). look: Videotextur des Spielers { map, tile: [x, y], size: [Breite, Höhe], rects, ranges } oder null.
   */
  function create(kit, number, seed = number ?? 0, look = null) {
    const root = new THREE.Group();
    const model = SkeletonUtils.clone(template);
    root.add(model);
    const pick = hash(seed);
    const style = HAIR_STYLES[pick % HAIR_STYLES.length], hairColour = kit.hair ?? HAIR_COLOURS[(pick >>> 8) % HAIR_COLOURS.length];
    const drop = [];
    model.traverse((o) => {
      if (!o.isSkinnedMesh) return;
      o.frustumCulled = false;
      o.castShadow = true;
      if (o.name.startsWith('Hair_')) {
        if (o.name === style) o.material = look ? hairLookMaterial(look) : hairMaterial(hairColour); else drop.push(o);
      } else if (o.name.startsWith('Eyebrows')) {
        o.material = hairMaterial(hairColour.clone().lerp(kit.skin ?? SKIN, 0.45));   // heller als das Haar, sonst wirkt der Blick finster
        o.castShadow = false;
      } else if (o.name.startsWith('Eyes')) {
        o.castShadow = false;
      } else {
        o.material = bodyMaterial(kit, number ?? null, look);
      }
    });
    for (const o of drop) o.removeFromParent();
    const bones = {};
    for (const name of DRIVEN) bones[name] = model.getObjectByName(BONE[name]);
    const delta = Object.fromEntries(DRIVEN.map((n) => [n, new THREE.Quaternion()]));
    const world = Object.fromEntries(DRIVEN.map((n) => [n, new THREE.Quaternion()]));
    const hipsQ = new THREE.Quaternion(), chestQ = new THREE.Quaternion(), headQ = new THREE.Quaternion();
    const left = new THREE.Vector3(), up = new THREE.Vector3(), target = new THREE.Vector3(), origin = new THREE.Vector3();
    let k = 1, fitted = false;

    // Einmal je Spieler: Größe und Knochenlängen des Modells auf die des Spielers setzen.
    function fit(P, J) {
      const len = (a, b) => P[J[a]].distanceTo(P[J[b]]);
      const thighLength = len('lHip', 'lKnee'), shank = len('lKnee', 'lAnkle');
      k = (thighLength + shank) / restLeg;
      root.scale.setScalar(k);
      // Das Modell hat den Kopf eines Erwachsenen. Kleinere Spieler bekommen einen im Verhältnis größeren Kopf.
      bones.Head.scale.setScalar(Math.min(1.2, Math.max(1.04, Math.pow(1 / k, 0.75))));
      const half = len('lHip', 'rHip') / 2, shoulder = Math.min(shoulderHalf + 0.03, Math.max(shoulderHalf - 0.03, len('lShoulder', 'rShoulder') / 2 / k));
      for (const [side, sign] of [['Left', 1], ['Right', -1]]) {
        v1.subVectors(rest[side + 'UpLeg'].p, rest.Hips.p).setX(sign * half / k);
        bones[side + 'UpLeg'].position.copy(v1).applyQuaternion(rest.Hips.inverse);
        v1.subVectors(rest[side + 'Arm'].p, rest[side + 'Shoulder'].p);
        v1.x += sign * shoulder - rest[side + 'Arm'].p.x;
        bones[side + 'Arm'].position.copy(v1).applyQuaternion(rest[side + 'Shoulder'].inverse);
        bones[side + 'Leg'].position.copy(rest[side + 'Leg'].local).setLength(thighLength / k);
        bones[side + 'Foot'].position.copy(rest[side + 'Foot'].local).setLength(shank / k);
        bones[side + 'ForeArm'].position.copy(rest[side + 'ForeArm'].local).setLength(len('lShoulder', 'lElbow') / k);
        bones[side + 'Hand'].position.copy(rest[side + 'Hand'].local).setLength(len('lElbow', 'lWrist') / k);
      }
      // Wirbelsäule: vom Beckenknochen bis zum Halsknochen
      const spine = (len('pelvis', 'neck') / k + hipDrop.y + neckLift) / restSpine;
      for (const n of ['Spine', 'Spine1', 'Spine2', 'Neck']) bones[n].position.copy(rest[n].local).multiplyScalar(spine);
      fitted = true;
    }

    /** P: Gelenkpositionen (THREE.Vector3, Weltkoordinaten), J: Name -> Index. */
    function setPose(P, J) {
      if (!fitted) fit(P, J);
      up.subVectors(P[J.neck], P[J.pelvis]);
      frame(left.subVectors(P[J.lHip], P[J.rHip]), up, 'left', hipsQ);
      frame(left.subVectors(P[J.lShoulder], P[J.rShoulder]), up, 'up', chestQ);
      up.subVectors(P[J.head], P[J.neck]);
      target.subVectors(P[J.nose], P[J.head]);
      frame(left.crossVectors(up, target), up, 'up', headQ);

      delta.Hips.copy(hipsQ);
      delta.Spine.copy(hipsQ).slerp(chestQ, 1 / 3);
      delta.Spine1.copy(hipsQ).slerp(chestQ, 2 / 3);
      delta.Spine2.copy(chestQ);
      delta.Neck.copy(chestQ).slerp(headQ, 0.5);
      delta.Head.copy(headQ);
      for (const [side, s] of [['Left', 'l'], ['Right', 'r']]) {
        const hip = P[J[s + 'Hip']], knee = P[J[s + 'Knee']], ankle = P[J[s + 'Ankle']];
        target.subVectors(knee, hip).normalize();
        swing(hipsQ, restDir[side + 'UpLeg'], target, delta[side + 'UpLeg']);
        twist(delta[side + 'UpLeg'], v4.copy(target), FORWARD, knee, hip, ankle);
        target.subVectors(ankle, knee).normalize();
        swing(delta[side + 'UpLeg'], restDir[side + 'Leg'], target, delta[side + 'Leg']);
        target.subVectors(P[J[s + 'Toe']], P[J[s + 'Heel']]).normalize();
        swing(delta[side + 'Leg'], restDir[side + 'Foot'], target, delta[side + 'Foot']);
        delta[side + 'ToeBase'].copy(delta[side + 'Foot']);

        const shoulder = P[J[s + 'Shoulder']], elbow = P[J[s + 'Elbow']], wrist = P[J[s + 'Wrist']];
        delta[side + 'Shoulder'].copy(chestQ);
        target.subVectors(elbow, shoulder).normalize();
        swing(chestQ, restDir[side + 'Arm'], target, delta[side + 'Arm']);
        twist(delta[side + 'Arm'], v4.copy(target), BACK, elbow, shoulder, wrist);
        target.subVectors(wrist, elbow).normalize();
        swing(delta[side + 'Arm'], restDir[side + 'ForeArm'], target, delta[side + 'ForeArm']);
        delta[side + 'Hand'].copy(delta[side + 'ForeArm']);
      }
      for (const name of DRIVEN) {
        world[name].multiplyQuaternions(delta[name], rest[name].q);
        const parent = PARENT[name];
        bones[name].quaternion.copy(parent ? world[parent] : hipsParentQ).invert().multiply(world[name]);
      }
      // Becken so setzen, dass die Hüftgelenke des Modells auf denen des Spielers liegen
      origin.addVectors(P[J.lHip], P[J.rHip]).multiplyScalar(0.5);
      origin.sub(v1.copy(hipDrop).multiplyScalar(k).applyQuaternion(delta.Hips));
      bones.Hips.position.copy(origin).divideScalar(k).applyMatrix4(hipsParentInverse);
    }
    return { root, setPose };
  }
  return { create };
}
