// Modellaufbereitung: das erwachsene Grundmodell zum Jugendlichen umformen und anziehen (Teil von web/avatar.js).
import * as THREE from 'three';

// Umformen zum Jugendlichen: Breite und Tiefe des Rumpfs, Dicke der Glieder (Anteil des Erwachsenenmodells)
const SLIM = { torsoX: 0.84, torsoZ: 0.86, upperarm: 0.74, lowerarm: 0.8, hand: 0.9, thigh: 0.84, calf: 0.88, neck: 0.98, jaw: 0.9 };
// Kleidung trägt auf (Meter)
export const PAD = { shirt: 0.016, sleeve: 0.02, shorts: 0.014, shortsHem: 0.024, sock: 0.004, boot: 0.008 };

/** Zu welchem Körperteil ein Knochen des Modells gehört. */
export function partOf(name) {
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

/**
 * Formt das Modell in der Grundhaltung um: schmalerer Rumpf, dünnere Arme und Beine. Die Gelenke von Schulter
 * und Hüfte rücken mit nach innen. Danach gilt die neue Grundhaltung als Bindung von Netz und Skelett.
 */
export function reshape(template, meshes) {
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
export function dress(mesh, wear, extra) {
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
