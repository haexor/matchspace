// Einen Spieler selbst steuern: W, A, S, D laufen (relativ zur Kamera), Umschalt sprinten, Leertaste springen, E schießen. Aufruf: spielen.html?match=SZENE&player=own-6
// Bewegung: web/movement.js, Laufanimation: web/runner.js, Werte je Spieler (heute für alle gleich): web/profile.js. Kleidung: Kit der Mannschaft (web/garments.js), wenn die Szene eines hat.
import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { loadAvatars } from './avatar.js?v=14';
import { query, base, meta, ENTITIES, PLAYER_SLOTS, J, JOINT_INDEX } from './track.js';
import { buildStadium } from './stadium.js';
import { ballTexture } from './props.js';
import { createLooks } from './looks.js';
import { ATTRIBUTES, ratingsOf, physicsOf } from './profile.js';
import { createMover, stepMover, createBall, stepBall } from './movement.js';
import { runnerPose } from './runner.js';

const $ = (id) => document.getElementById(id);
const L = meta.pitch.length, W = meta.pitch.width;
const BOUNDS = { x: L / 2 + 4, z: W / 2 + 4 };

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.prepend(renderer.domElement);
const scene = new THREE.Scene();
const HORIZON = new THREE.Color(meta.pitch.backdrop?.sky ?? '#d5e2ee');
scene.background = HORIZON;
scene.fog = new THREE.Fog(HORIZON, 90, 420);
// Licht wie in der Szenenansicht (bedeckter Aufnahmetag mit Bildern aus dem Video)
const OVERCAST = !!meta.pitch.backdrop, HEMI = OVERCAST ? 3.6 : 2.5, SUN = OVERCAST ? 0.8 : 2.7;
const SUN_DIR = new THREE.Vector3(-0.42, 0.8, 0.43).normalize();
scene.add(new THREE.HemisphereLight(0xeaf2ff, 0x6f7f58, HEMI));
const sun = new THREE.DirectionalLight(0xfff3e0, SUN);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { near: 1, far: 120, left: -14, right: 14, top: 14, bottom: -14 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.03;
scene.add(sun, sun.target);
const GROUND_LIGHT = new THREE.Color(0xeaf2ff).multiplyScalar(HEMI / Math.PI).add(new THREE.Color(0xfff3e0).multiplyScalar(SUN * SUN_DIR.y / Math.PI));
buildStadium({ renderer, scene, meta, base, groundLight: GROUND_LIGHT });

const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 2.5;
controls.maxDistance = 30;
controls.maxPolarAngle = Math.PI / 2 - 0.05;
function resize() { renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }
addEventListener('resize', resize);
resize();

const { loadLooks, lookOf, hairOf, kitOf, outfitOf } = createLooks(meta, base);
const [factory] = await Promise.all([loadAvatars('models/player/player.glb'), loadLooks()]);

const players = ENTITIES.map((e, i) => ({ e, i })).filter(({ e, i }) => e.kind === 'player' && PLAYER_SLOTS.has(i));
const who = $('who');
for (const { e, i } of players) who.add(new Option(`${e.id}${e.number ? ' · ' + e.number : ''} (${meta.teams[e.team].name})`, String(i)));
const start = ENTITIES.findIndex((e) => e.id === query.get('player'));
who.value = String(start >= 0 ? start : players[0].i);

const ball = createBall(2, 0);
const ballMesh = new THREE.Mesh(new THREE.SphereGeometry(0.11, 24, 16), new THREE.MeshStandardMaterial({ map: ballTexture(), roughness: 0.45 }));
ballMesh.castShadow = true;
scene.add(ballMesh);

const joints = Array.from({ length: J }, () => new THREE.Vector3());
let avatar = null, entity = null, ratings = null, physics = null, mover = createMover(0, 0, Math.PI / 2);

function build() {
  if (avatar) scene.remove(avatar.root);
  entity = ENTITIES[Number(who.value)];
  const kit = kitOf(entity), look = lookOf(entity);
  if (look) kit.hair = hairOf(look);
  avatar = factory.create(kit, entity.label ? null : entity.number, entity.id, look, outfitOf(entity));
  scene.add(avatar.root);
  ratings = ratingsOf(entity);
  physics = physicsOf(ratings);
  $('name').textContent = `${entity.id}${entity.number ? ' · ' + entity.number : ''}`;
  $('ratings').innerHTML = ATTRIBUTES.map(([key, label]) => `<tr><td>${label}</td><td>${ratings[key]}</td></tr>`).join('');
  $('status').textContent = look ? 'Gesicht und Haut aus dem Video, Kleidung vom Kit' : 'Standardkörper mit Kit';
  $('tp').href = `spieler.html?match=${query.get('match') ?? ''}&player=${entity.id}&tpose=1`;
  mover = createMover(0, 0, Math.PI / 2);
  Object.assign(ball, createBall(2, 0));
  camera.position.set(-6, 3.2, 0);
  controls.target.set(0, 1.0, 0);
}
who.addEventListener('change', build);
build();

const keys = new Set();
addEventListener('keydown', (e) => { if (e.target instanceof HTMLSelectElement) return; keys.add(e.code); if (e.code === 'Space') e.preventDefault(); });
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());
const fwd = new THREE.Vector3(), right = new THREE.Vector3(), UP = new THREE.Vector3(0, 1, 0);
let jumpHeld = false, shotHeld = false;

let last = performance.now();
function loop(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  // Wunschrichtung relativ zur Kamera: W läuft vom Betrachter weg
  fwd.subVectors(controls.target, camera.position).setY(0).normalize();
  right.crossVectors(fwd, UP);
  const f = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0) - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0);
  const r = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0);
  const jump = keys.has('Space') && !jumpHeld, shoot = keys.has('KeyE') && !shotHeld;
  jumpHeld = keys.has('Space'); shotHeld = keys.has('KeyE');
  stepMover(mover, { dx: fwd.x * f + right.x * r, dz: fwd.z * f + right.z * r, sprint: keys.has('ShiftLeft') || keys.has('ShiftRight'), jump }, physics, dt, BOUNDS);
  stepBall(ball, mover, physics, dt, shoot, BOUNDS);
  runnerPose(mover, physics.sprintSpeed, joints, JOINT_INDEX);
  avatar.setPose(joints, JOINT_INDEX);
  ballMesh.position.set(ball.x, ball.y, ball.z);
  ballMesh.rotation.x += ball.vz * dt / 0.11; ballMesh.rotation.z -= ball.vx * dt / 0.11;
  // Kamera folgt: Ziel und Kamera um dieselbe Strecke verschieben
  const tx = mover.x, ty = 1.0 + mover.y * 0.5, tz = mover.z;
  camera.position.add(new THREE.Vector3(tx - controls.target.x, ty - controls.target.y, tz - controls.target.z));
  controls.target.set(tx, ty, tz);
  controls.update();
  sun.target.position.set(mover.x, 0, mover.z);
  sun.position.set(mover.x, 0, mover.z).addScaledVector(SUN_DIR, 60);
  $('speed').textContent = (Math.hypot(mover.vx, mover.vz) * 3.6).toFixed(1);
  $('stamina').style.width = `${Math.round(mover.stamina * 100)}%`;
  $('stamina').style.background = mover.stamina < 0.25 ? '#d29922' : '#3fb950';
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
