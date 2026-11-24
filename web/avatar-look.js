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
