// Weiche Kontaktschatten unter Füßen und Körper. Bei bedecktem Himmel wirft die Sonne kaum einen Schatten: ohne dunkle Stelle am Boden schweben
// die Figuren. Je Spieler drei Flecken (linker und rechter Fuß, Körpermitte); ein Fuß-Fleck wird mit der Höhe des Fußes schwächer und kleiner,
// ein abgehobener Fuß wirft also keinen scharfen Schatten.
import * as THREE from 'three';

const FOOT_RADIUS = 0.2, BODY_RADIUS = 0.5;    // m Halbmesser eines Flecks
const FOOT_ALPHA = 0.5, BODY_ALPHA = 0.28;     // Dunkelheit direkt am Boden
const FADE_HEIGHT = 0.3;                       // m: in dieser Höhe über dem Boden ist der Fußschatten weg
const LIFT = 0.012;                            // m über dem Rasen (gegen Flackern mit dem Boden)

function blobTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const g = canvas.getContext('2d');
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, 'rgba(0,0,0,1)');
  grad.addColorStop(0.45, 'rgba(0,0,0,0.55)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** slots: Zahl der Spieler (Plätze in den Haltungsdaten); names: Gelenkindizes {lHeel, rHeel, lToe, rToe}. */
export function createContactShadows(scene, slots, index) {
  const tex = blobTexture();
  const geometry = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const make = () => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
      map: tex, transparent: true, depthWrite: false, opacity: 0, fog: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
    }));
    mesh.renderOrder = 1;
    mesh.visible = false;
    mesh.castShadow = mesh.receiveShadow = false;
    scene.add(mesh);
    return mesh;
  };
  const shadows = Array.from({ length: slots }, () => ({ left: make(), right: make(), body: make() }));
  const mid = new THREE.Vector3();

  function place(mesh, x, z, radius, alpha) {
    mesh.position.set(x, LIFT, z);
    mesh.scale.set(radius * 2, 1, radius * 2);
    mesh.material.opacity = alpha;
    mesh.visible = alpha > 0.01;
  }

  return {
    /** joints: Gelenkpositionen (Three-Koordinaten) oder null, wenn der Spieler ohne Haltung gezeigt wird; ground: Position am Boden. */
    update(slot, joints, ground, shown) {
      const s = shadows[slot];
      if (!s) return;
      if (!shown) { s.left.visible = s.right.visible = s.body.visible = false; return; }
      place(s.body, ground.x, ground.z, BODY_RADIUS, BODY_ALPHA);
      if (!joints) { s.left.visible = s.right.visible = false; return; }
      for (const [mesh, heel, toe] of [[s.left, index.lHeel, index.lToe], [s.right, index.rHeel, index.rToe]]) {
        mid.addVectors(joints[heel], joints[toe]).multiplyScalar(0.5);
        const lift = Math.max(0, Math.min(1, mid.y / FADE_HEIGHT));
        place(mesh, mid.x, mid.z, FOOT_RADIUS * (1 + 0.5 * lift), FOOT_ALPHA * (1 - lift));
      }
    },
  };
}
