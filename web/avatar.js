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
import { PAD, partOf, reshape, dress } from './avatar-body.js';
import { garmentBases, dressUp } from './garments.js';
import { lookCoordinates, LOOK_GLSL, LOOK_VERTEX, LOOK_PASS, lookUniforms } from './avatar-look.js';

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
// Schichten ansehen (Hilfsansicht): ?layer=skin zeigt den Körper ohne Kleidung (Hautfarbe, ohne Stoffaufpolsterung), ?layer=cloth nur die Kleidungsstücke (Trikot, Hose, Stutzen, Schuhe)
const LAYER = typeof location === 'undefined' ? null : new URLSearchParams(location.search).get('layer');
// Kleidung als eigene Hüllen ist Standard; ?kit=0 zeigt die alte Körpertextur statt des Kit-Blatts (web/garments.js).
const KIT_PARAM = typeof location === 'undefined' ? true : new URLSearchParams(location.search).get('kit') !== '0';      // Kleidung als Hüllen ist Standard; `?kit=0` zeigt die alte Körpertextur
const HAIR_COLOURS = [0x2a1c13, 0x3b2a1b, 0x4c3521, 0x6a4b2c, 0x8a6a3f, 0x1b1613].map((c) => new THREE.Color(c));
const HAIR_STYLES = ['Hair_SimpleParted', 'Hair_SimpleParted', 'Hair_Buzzed'];
const FINGERS = ['index', 'middle', 'ring', 'pinky'];
const CURL = [0.35, 0.8, 1.2];  // Beugung der drei Fingerglieder gegenüber der flachen Hand (Bogenmaß, aufsummiert)

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

// Die Frisuren des Modells stehen am Scheitel bis zu 4 cm vom Schädel ab und wirken wie ein Bienenkorb. Jeder Haarpunkt, der weiter als HAIR_THICKNESS
// vom Kopf des Körpernetzes entfernt liegt, wird auf diese Dicke an den Kopf herangezogen: die Frisur liegt am Schädel an, ihre Form (Ansatz, Seiten) bleibt.
const HAIR_THICKNESS = 0.012;   // m
const HAIR_BOTTOM = 1.675;   // m: tiefste Haarkante im Nacken; die Zacken der Frisur darunter werden gerade abgeschnitten (sonst dunkle Zackenlinie auf dem Nacken)
const HEAD_FROM = 1.6;   // m: ab dieser Höhe (Grundhaltung) zählen Körperpunkte zum Kopf
// Die Frisur reicht an den Seiten über das Ohr (Strähnen am Ohr, im Netz ein zweites ohrförmiges Gebilde): Dreiecke mit einem Punkt im Ohrbereich entfallen,
// das Ohr des Kopfes bleibt frei. Maße in m, Grundhaltung: Abstand von der Mittelebene ab, Höhe von bis, z von bis.
const EAR_CLEAR = { x: 0.062, y: [1.64, 1.735], z: [-0.055, 0.045] };
function clearEars(geometry) {
  const position = geometry.attributes.position, index = geometry.index;
  if (!index) return;
  const keep = [];
  for (let t = 0; t < index.count; t += 3) {
    let inEar = false;
    for (let k = 0; k < 3; k++) {
      const v = index.getX(t + k), x = Math.abs(position.getX(v)), y = position.getY(v), z = position.getZ(v);
      if (x > EAR_CLEAR.x && y > EAR_CLEAR.y[0] && y < EAR_CLEAR.y[1] && z > EAR_CLEAR.z[0] && z < EAR_CLEAR.z[1]) inEar = true;
    }
    if (!inEar) keep.push(index.getX(t), index.getX(t + 1), index.getX(t + 2));
  }
  geometry.setIndex(keep);
}

function hugHead(hair, body) {
  clearEars(hair.geometry);
  const bp = body.geometry.attributes.position, head = [];
  for (let i = 0; i < bp.count; i++) if (bp.getY(i) > HEAD_FROM && Math.abs(bp.getX(i)) < 0.13) head.push(new THREE.Vector3().fromBufferAttribute(bp, i));
  const position = hair.geometry.attributes.position, p = new THREE.Vector3(), d = new THREE.Vector3();
  for (let i = 0; i < position.count; i++) {
    p.fromBufferAttribute(position, i);
    let best = Infinity, near = null;
    for (const q of head) { const l = p.distanceToSquared(q); if (l < best) { best = l; near = q; } }
    const dist = Math.sqrt(best);
    if (dist > HAIR_THICKNESS) { d.subVectors(p, near).multiplyScalar(HAIR_THICKNESS / dist); position.setXYZ(i, near.x + d.x, near.y + d.y, near.z + d.z); }
    if (position.getY(i) < HAIR_BOTTOM) position.setY(i, HAIR_BOTTOM);
  }
  position.needsUpdate = true;
  hair.geometry.computeVertexNormals();
  hair.geometry.computeBoundingBox();
  hair.geometry.computeBoundingSphere();
}

export async function loadAvatars(url, options = {}) {
  const KIT = options.kit ?? KIT_PARAM;
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
  if (LAYER !== 'skin') dress(body, wear, extra, !KIT);      // Kit-Hüllen tragen selbst auf: unter ihnen wird das Muskelrelief nur geglättet; nackt: ohne Aufpolsterung und Glättung unter dem Stoff
  body.geometry.setAttribute('wear', new THREE.BufferAttribute(wear, 4));
  for (const h of hairs) hugHead(h, body);
  lookCoordinates(template, [body, ...hairs], body, 0.035);
  const kitBases = KIT ? garmentBases(body, { sleeve, wristX: rest.LeftHand.p.x }) : null;

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
      backMap: { value: look?.back?.map ?? blank }, backCell: { value: look?.back?.cell ?? new THREE.Vector4(0, 0, 1, 1) }, backY: { value: look?.back?.y ?? 0 }, backSize: { value: look?.back?.size ?? new THREE.Vector2(1, 1) },
      ...(look ? lookUniforms(look) : {}) };
    // Mit Videotextur: Farbe von dort (Licht des Spieltags steckt schon darin, deshalb etwas aufgehellt); sonst Mannschaftsfarben je Kleidungsstück
    const colour = LAYER === 'skin' ? 'vec3 kitColour = kitSkin;' : look ? 'vec3 kitColour = lookColour() * 1.15;' : `vec3 kitColour = mix(kitSkin, kitSock, covered(vWear.z));
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
          uniform sampler2D numberMap, backMap; uniform vec4 plate, backCell; uniform float backY; uniform vec2 backSize; uniform vec3 kitSkin, kitShirt, kitShorts, kitSock, kitBoot;
          float covered(float d) { return smoothstep(-0.5, 0.5, d / max(fwidth(d), 1e-5)); }
          ${look ? LOOK_GLSL : ''}`)
        .replace('#include <color_fragment>', `${colour}
          vec2 plateUv = vec2(0.5 - vRest.x / (2.0 * plate.x), 0.5 + (vRest.y - plate.y) / (2.0 * plate.z));
          if (plate.w > 0.5 && vBack < -0.25 && vWear.x > 0.0 && plateUv.x > 0.0 && plateUv.x < 1.0 && plateUv.y > 0.0 && plateUv.y < 1.0) {
            vec4 digit = texture2D(numberMap, plateUv);
            kitColour = mix(kitColour, digit.rgb, digit.a);
          }
          ${LAYER === 'cloth' ? 'if (max(max(vWear.x, vWear.y), max(vWear.z, vWear.w)) <= 0.0) discard;' : ''}
          ${look?.back && LAYER !== 'skin' ? `
          // Rückenpartie aus dem Foto (Nummer scharf): derselbe Rückenausschnitt wie das Foto, weicher Rand, nur auf der Rückseite des Trikots
          vec2 bu = vec2(0.5 - vRest.x / (2.0 * backCell.w), 0.5 + (vRest.y - backY) / (2.0 * backCell.w));
          if (bu.x > 0.0 && bu.x < 1.0 && bu.y > 0.0 && bu.y < 1.0) {
            float edge = min(min(bu.x, 1.0 - bu.x), min(bu.y, 1.0 - bu.y));
            float on = smoothstep(0.0, 0.1, edge) * smoothstep(0.25, 0.6, -vBack) * covered(vWear.x);
            kitColour = mix(kitColour, texture2D(backMap, (backCell.xy + vec2(bu.x, 1.0 - bu.y) * backCell.z) / backSize).rgb * 1.15, on);
          }` : ''}
          diffuseColor.rgb *= kitColour;`);
    };
    material.customProgramCacheKey = () => (look ? (look.back ? 'matchspace-player-body-look-back' : 'matchspace-player-body-look') : 'matchspace-player-body');
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
   * (und ohne Videotextur die Haarfarbe). look: Videotextur des Spielers { map, tile: [x, y], size: [Breite, Höhe], rects, ranges, photo } oder null (photo: Gesicht aus dem Foto statt vom Modell, trägt Augen und Brauen selbst; Szenen mit faceFromModel zeigen die Teile des Modells).
   */
  function create(kit, number, seed = number ?? 0, look = null, outfit = null) {
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
        o.visible = !look?.photo;      // Gesicht aus Fotos: Brauen und Augen sind schon in der Textur, die des Modells gäben vier Augen
      } else if (o.name.startsWith('Eyes')) {
        o.castShadow = false;
        o.visible = !look?.photo;
      } else {
        o.material = bodyMaterial(kit, look?.printKept ? null : (number ?? null), look);   // die Videotextur trägt den echten Aufdruck: keine zweite Nummer darüber
      }
    });
    for (const o of drop) o.removeFromParent();
    if (kitBases && outfit) {
      let bodyMesh = null;
      model.traverse((o) => { if (o.isSkinnedMesh && o.name === body.name) bodyMesh = o; });
      if (LAYER !== 'skin') for (const m of dressUp(kitBases, bodyMesh, outfit)) {
        if (m.name === 'Kit_shirt' && outfit.flat && number != null) {
          const numberMap = numberTexture(String(number));
          m.material.onBeforeCompile = (shader) => {
            Object.assign(shader.uniforms, { flatNumberMap: { value: numberMap }, flatNumberPlate: { value: plate } });
            shader.vertexShader = shader.vertexShader
              .replace('#include <common>', '#include <common>\nvarying vec3 vFlatRest;\nvarying float vFlatBack;')
              .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFlatRest = position;\nvFlatBack = normal.z;');
            shader.fragmentShader = shader.fragmentShader
              .replace('#include <common>', '#include <common>\nvarying vec3 vFlatRest;\nvarying float vFlatBack;\nuniform sampler2D flatNumberMap;\nuniform vec4 flatNumberPlate;')
              .replace('#include <color_fragment>', `#include <color_fragment>
                vec2 flatPlateUv = vec2(0.5 - vFlatRest.x / (2.0 * flatNumberPlate.x), 0.5 + (vFlatRest.y - flatNumberPlate.y) / (2.0 * flatNumberPlate.z));
                if (vFlatBack < -0.25 && flatPlateUv.x > 0.0 && flatPlateUv.x < 1.0 && flatPlateUv.y > 0.0 && flatPlateUv.y < 1.0) {
                  vec4 digit = texture2D(flatNumberMap, flatPlateUv);
                  diffuseColor.rgb = mix(diffuseColor.rgb, digit.rgb, digit.a);
                }`);
          };
          m.material.customProgramCacheKey = () => 'matchspace-flat-shirt-number';
        }
        bodyMesh.parent.add(m);
      }
      if (LAYER === 'cloth') bodyMesh.visible = false;
    }
    if (LAYER === 'cloth') model.traverse((o) => { if (o.isSkinnedMesh && /^(Hair_|Eyebrows|Eyes)/.test(o.name)) o.visible = false; });
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
