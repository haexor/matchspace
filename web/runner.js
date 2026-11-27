// Laufanimation aus dem Zustand eines gesteuerten Spielers (web/movement.js): erzeugt die Gelenkpunkte, die der Avatar sonst aus den Körperposen der Szene bekommt
// (`avatar.setPose(P, JOINT_INDEX)`): Becken, Hals, Kopf, Nase, Schultern, Ellbogen, Handgelenke, Hüften, Knie, Knöchel, Fersen und Zehen in Weltkoordinaten (m, y oben).
// Die Haltung entsteht aus Schrittphase, Tempo und Luftanteil; das Becken sitzt so hoch, dass der tiefste Fußpunkt den Boden berührt (Auf und Ab des Laufens ergibt sich daraus).
import * as THREE from 'three';

export const BODY = { thigh: 0.42, shank: 0.41, torso: 0.52, head: 0.2, upperArm: 0.28, foreArm: 0.26, hipHalf: 0.095, shoulderHalf: 0.19 };
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Ein Bein in der Längsebene (y oben, z vorn): Phase des Beins, Schwungweite A, Kniebeugung K, Luftanteil; liefert Knie, Knöchel, Zehen, Ferse relativ zur Hüfte. */
function leg(phase, A, K, air, lean) {
  let theta = A * Math.sin(phase) + 0.25 * lean;                 // Oberschenkel nach vorn (+)
  let kappa = 0.1 + K * Math.max(0, Math.sin(phase - 0.7));      // Knie beugt vor allem in der Schwungphase
  theta = lerp(theta, 0.75, air);
  kappa = lerp(kappa, 1.25, air);
  const knee = [0, -BODY.thigh * Math.cos(theta), BODY.thigh * Math.sin(theta)];
  const shank = theta - kappa;
  const ankle = [0, knee[1] - BODY.shank * Math.cos(shank), knee[2] + BODY.shank * Math.sin(shank)];
  const pitch = clamp(0.35 - 0.9 * shank, -0.55, 0.9);           // Fuß: vorn Ferse zuerst, hinten Abdruck über die Zehen
  const toe = [0, ankle[1] - 0.15 * Math.sin(pitch), ankle[2] + 0.15 * Math.cos(pitch)];
  const heel = [0, ankle[1] - 0.03, ankle[2] - 0.07];
  return { knee, ankle, toe, heel, theta };
}

/**
 * Gelenke setzen. state: Zustand aus createMover (x, z, y, heading, phase, air, vx, vz, landed), sprintSpeed: Höchsttempo des Spielers (für die Tempostufe),
 * out: Array aus THREE.Vector3 (je Gelenk), J: Name -> Index (JOINT_INDEX der Szene).
 */
export function runnerPose(state, sprintSpeed, out, J) {
  const speed = Math.hypot(state.vx, state.vz), s = clamp(speed / sprintSpeed, 0, 1.15), air = state.air;
  const A = lerp(0.08, 0.7, Math.min(1, s)) * (1 - 0.3 * air), K = lerp(0.1, 1.5, Math.min(1, s));
  const lean = 0.06 + 0.26 * Math.min(1, s) + 0.2 * state.landed;
  const crouch = 0.07 * state.landed;                            // beim Landen kurz in die Knie
  const L = leg(state.phase, A, K, air, lean), R = leg(state.phase + Math.PI, A, K, air, lean);
  const local = {};
  const put = (name, x, y, z) => { local[name] = [x, y, z]; };
  // Becken: tiefster Fußpunkt auf den Boden
  const low = (l) => Math.min(l.ankle[1] - 0.06, l.toe[1], l.heel[1]);
  const pelvisY = -Math.min(low(L), low(R)) - crouch;
  put('pelvis', 0, pelvisY, 0);
  for (const [side, sign, l] of [['l', 1, L], ['r', -1, R]]) {
    const hip = [sign * BODY.hipHalf, pelvisY, 0];
    put(side + 'Hip', ...hip);
    put(side + 'Knee', hip[0], hip[1] + l.knee[1], hip[2] + l.knee[2]);
    put(side + 'Ankle', hip[0], hip[1] + l.ankle[1], hip[2] + l.ankle[2]);
    put(side + 'Toe', hip[0], hip[1] + l.toe[1], hip[2] + l.toe[2]);
    put(side + 'Heel', hip[0], hip[1] + l.heel[1], hip[2] + l.heel[2]);
  }
  // Oberkörper: nach vorn geneigt, gegen die Hüfte verdreht
  const neck = [0, pelvisY + BODY.torso * Math.cos(lean), BODY.torso * Math.sin(lean)];
  put('neck', ...neck);
  const headLean = lean * 0.5;
  const head = [0, neck[1] + BODY.head * Math.cos(headLean), neck[2] + BODY.head * Math.sin(headLean)];
  put('head', ...head);
  put('nose', 0, head[1] - 0.02, head[2] + 0.11);
  const twist = 0.22 * Math.min(1, s) * Math.sin(state.phase) * (1 - air);
  for (const [side, sign, l, phase] of [['l', 1, L, state.phase], ['r', -1, R, state.phase + Math.PI]]) {
    const sx = sign * BODY.shoulderHalf, shoulder = [sx * Math.cos(twist), neck[1] - 0.04, neck[2] - sx * Math.sin(twist) * 0.9];
    put(side + 'Shoulder', ...shoulder);
    const swing = -(0.12 + 0.6 * Math.min(1, s)) * Math.sin(phase) + 0.5 * air;   // Arm gegen das Bein derselben Seite (Oberarm höchstens etwa 40° vor und zurück)
    const flex = 0.2 + 0.85 * Math.min(1, s) + 0.2 * air;                      // Ellbogen: gehend fast gestreckt, im Sprint etwa 50° gebeugt
    const elbow = [shoulder[0] + sign * 0.03, shoulder[1] - BODY.upperArm * Math.cos(swing), shoulder[2] + BODY.upperArm * Math.sin(swing)];
    put(side + 'Elbow', ...elbow);
    put(side + 'Wrist', elbow[0] - sign * 0.02, elbow[1] - BODY.foreArm * Math.cos(swing + flex), elbow[2] + BODY.foreArm * Math.sin(swing + flex));
  }
  const c = Math.cos(state.heading), n = Math.sin(state.heading);       // Drehung um y: lokal +z (vorn) -> (sin, cos)
  for (const name of Object.keys(local)) {
    const [x, y, z] = local[name];
    out[J[name]].set(state.x + x * c + z * n, state.y + y, state.z - x * n + z * c);
  }
}
