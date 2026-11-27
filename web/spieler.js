// Ein Spieler einzeln als 3D-Modell: Avatar mit seiner Videotextur (looks.png), Haltung aus einem wählbaren Bild der Szene, Drehteller und freie Kamera.
// Aufruf: spieler.html?match=SZENE&player=own-6&frame=22  (optional: &tpose=1 Grundhaltung ohne Pose, &layer=skin|cloth nur Körper oder nur Kleidung, &kit=1 Kleidung als eigene Hüllen mit dem Kit-Blatt der Bild-KI)
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { loadAvatars } from './avatar.js?v=14';
import { query, base, meta, N, ENTITIES, PLAYER_SLOTS, J, JOINT_INDEX, samplePose } from './track.js';
import { createLooks } from './looks.js';

const $ = (id) => document.getElementById(id);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.shadowMap.enabled = true;
document.body.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#161c22');
scene.add(new THREE.HemisphereLight('#dfe9f5', '#27402a', 1.4));
const sun = new THREE.DirectionalLight('#fff3dd', 2.2);
sun.position.set(2.5, 4, 3);
sun.castShadow = true;
scene.add(sun);
const floor = new THREE.Mesh(new THREE.CircleGeometry(1.4, 64), new THREE.MeshStandardMaterial({ color: '#2d5a34', roughness: 1 }));
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);
const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 50);
camera.position.set(0, 1.25, 3.6);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.9, 0);
controls.enableDamping = true;
function resize() { renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }
addEventListener('resize', resize);
resize();

const { loadLooks, lookOf, hairOf, kitOf } = createLooks(meta, base);
const [factory] = await Promise.all([loadAvatars('models/player/player.glb'), loadLooks()]);

const players = ENTITIES.map((e, i) => ({ e, i })).filter(({ e }) => e.kind === 'player' && PLAYER_SLOTS.has(ENTITIES.indexOf(e)));
const who = $('who');
for (const { e, i } of players) who.add(new Option(`${e.id}${e.number ? ' · ' + e.number : ''} (${meta.teams[e.team].name})`, String(i)));
const frame = $('frame');
frame.max = String(N - 1);
const start = ENTITIES.findIndex((e) => e.id === query.get('player'));
who.value = String(start >= 0 ? start : players[0].i);
frame.value = String(Number(query.get('frame') ?? Math.floor(N / 2)));

const joints = Array.from({ length: J }, () => new THREE.Vector3());
$('tpose').checked = query.get('tpose') === '1';
$('layer').value = query.get('layer') ?? 'both';
$('kit').checked = query.get('kit') === '1';
// Die Schicht (ohne Kleidung, nur Kleidung) wird beim Laden von web/avatar.js gelesen: Wechsel lädt die Seite mit demselben Spieler neu.
function reload() {
  const q = new URLSearchParams(location.search);
  q.set('player', ENTITIES[Number(who.value)].id); q.set('frame', frame.value); q.set('layer', $('layer').value);
  if ($('tpose').checked) q.set('tpose', '1'); else q.delete('tpose');
  if ($('kit').checked) q.set('kit', '1'); else q.delete('kit');
  location.search = q.toString();
}
$('layer').addEventListener('change', reload);
$('kit').addEventListener('change', reload);      // wie die Schicht: wird beim Laden von web/avatar.js gelesen
let avatar = null, current = -1, lookStatus = '';

function build() {
  const i = Number(who.value);
  if (avatar) scene.remove(avatar.root);
  const e = ENTITIES[i];
  const kit = kitOf(e), look = lookOf(e);
  if (look) kit.hair = hairOf(look);
  avatar = factory.create(kit, e.label ? null : e.number, e.id, look);
  scene.add(avatar.root);
  current = i;
  lookStatus = look ? `${e.id}: Textur aus ${look.printKept ? 'Video und Foto' : 'dem Video'}` : `${e.id}: keine Videotextur, Mannschaftsfarben`;
}

function pose() {
  if ($('tpose').checked) { $('status').textContent = `${lookStatus} · Grundhaltung (T)`; return; }
  const slot = PLAYER_SLOTS.get(current), f = Number(frame.value);
  const ok = samplePose(slot, f, { x: 0, z: 0 }, joints);
  if (!ok) { $('status').textContent = 'Haltung wird geladen … (oder in diesem Bild nicht erkannt)'; return; }
  // um die Mitte der Hüfte stellen (Drehteller), Höhe bleibt wie in den Daten
  const mid = new THREE.Vector3().addVectors(joints[JOINT_INDEX.lHip], joints[JOINT_INDEX.rHip]).multiplyScalar(0.5);
  for (const p of joints) { p.x -= mid.x; p.z -= mid.z; }
  avatar.setPose(joints, JOINT_INDEX);
  $('status').textContent = lookStatus;
}

who.addEventListener('change', () => { build(); });
$('tpose').addEventListener('change', () => { build(); });      // zurücksetzen: neue Figur in Grundhaltung
$('wire').addEventListener('change', (e) => {
  avatar.root.traverse((o) => { if (o.isSkinnedMesh && o.material && 'wireframe' in o.material) o.material.wireframe = e.target.checked; });
});
build();

let last = performance.now();
function loop(now) {
  const dt = (now - last) / 1000;
  last = now;
  if ($('turn').checked) avatar.root.rotation.y += dt * 0.5;
  pose();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
