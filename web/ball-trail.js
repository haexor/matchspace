// Halbtransparente Spur hinter dem Ball: Der Zuschauer sieht, woher der Ball kam und wohin er fliegt, auch bei hohen Bällen.
// Ohne eigenen Zustand: Die Spur wird je Bild aus den Spieldaten der letzten Sekunden gelesen, springt man in der Zeit, stimmt sie sofort.
// In der Luft (Höhe über dem Boden) gelb und kräftiger, am Boden weiß und blasser; wo der Ball unbekannt war (versteckt), reißt sie ab.
import * as THREE from 'three';

const SECONDS = 1.6;      // so weit zurück reicht die Spur
const SEGMENTS = 56;      // Stützstellen der Spur
const WIDTH_HEAD = 0.16;  // m Breite am Ball
const WIDTH_TAIL = 0.025; // m Breite am Ende
const ALPHA_AIR = 0.62, ALPHA_GROUND = 0.34;
const AIR = new THREE.Color('#ffe600'), GROUND = new THREE.Color('#ffffff');
const LIFT = 0.11;        // Mittelpunkt des Balls über dem Boden

export function createBallTrail({ scene, sample, ballIndex, fps, enabled = true }) {
  if (!enabled || ballIndex < 0) return { update() {} };
  const verts = (SEGMENTS + 1) * 2;
  const position = new THREE.BufferAttribute(new Float32Array(verts * 3), 3);
  const color = new THREE.BufferAttribute(new Float32Array(verts * 4), 4);
  const index = [];
  for (let i = 0; i < SEGMENTS; i++) {
    const a = i * 2;
    index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', position);
  geometry.setAttribute('color', color);
  geometry.setIndex(index);
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
    vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
  }));
  mesh.frustumCulled = false;
  mesh.renderOrder = 5;
  mesh.visible = false;
  scene.add(mesh);

  const pts = Array.from({ length: SEGMENTS + 1 }, () => new THREE.Vector3());
  const known = new Array(SEGMENTS + 1).fill(false);
  const dir = new THREE.Vector3(), view = new THREE.Vector3(), side = new THREE.Vector3(), c = new THREE.Color();
  const span = SECONDS * fps;   // Frames

  /** t: Zeit in Frames, camera: für die Ausrichtung des Bandes zum Betrachter. */
  function update(t, camera) {
    if (!sample(ballIndex, t, pts[0])) { mesh.visible = false; return; }
    let run = true;      // zusammenhängend bekannt ab dem Ball: ab der ersten Lücke reißt die Spur ab
    known[0] = true;
    for (let i = 1; i <= SEGMENTS; i++) {
      run = run && sample(ballIndex, t - (i / SEGMENTS) * span, pts[i]);
      known[i] = run;
      if (!run) pts[i].copy(pts[i - 1]);
    }
    for (const p of pts) p.y += LIFT;
    let any = false;
    for (let i = 0; i <= SEGMENTS; i++) {
      const next = Math.min(SEGMENTS, i + 1), prev = Math.max(0, i - 1);
      let fade = known[i] ? 1 - i / SEGMENTS : 0;
      fade = Math.pow(fade, 1.25);
      dir.subVectors(pts[prev], pts[next]);
      if (dir.lengthSq() < 1e-8) dir.set(1, 0, 0);
      view.subVectors(camera.position, pts[i]);
      side.crossVectors(dir, view).normalize().multiplyScalar((WIDTH_HEAD + (WIDTH_TAIL - WIDTH_HEAD) * (i / SEGMENTS)) / 2);
      const air = Math.min(1, Math.max(0, (pts[i].y - LIFT) / 0.8));
      c.copy(GROUND).lerp(AIR, air);
      const alpha = fade * (ALPHA_GROUND + (ALPHA_AIR - ALPHA_GROUND) * air);
      for (const [k, sign] of [[0, 1], [1, -1]]) {
        const v = i * 2 + k;
        position.setXYZ(v, pts[i].x + sign * side.x, pts[i].y + sign * side.y, pts[i].z + sign * side.z);
        color.setXYZW(v, c.r, c.g, c.b, alpha);
      }
      any ||= fade > 0;
    }
    position.needsUpdate = true;
    color.needsUpdate = true;
    mesh.visible = any;
  }
  return { update };
}
