import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { loadAvatars } from './avatar.js?v=14';
import { query, base, meta, N, ENTITIES, L, W, POSES, PLAYER_SLOTS, JOINTS, BONES, J, JOINT_INDEX, poseChunk, samplePose, sample } from './track.js';
import { buildStadium } from './stadium.js';
import { numberSprite, ballTexture } from './props.js';
import { createLooks } from './looks.js';
import { createReference } from './reference.js';
import { createContactShadows } from './contact-shadows.js';

const $ = (id) => document.getElementById(id);

// ---------- Szene ----------
const UI = query.get('ui') !== '0';          // ui=0: keine Bedienelemente und Texte (für Videos)
const MARKS = query.get('labels') !== '0';   // labels=0: keine Nummernschilder und Ringe
document.body.classList.toggle('bare', !UI);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.prepend(renderer.domElement);
const scene = new THREE.Scene();
const reference = createReference(meta, base, query);

// Himmel als Verlauf, Dunst in der Ferne. Mit Kulisse aus dem Video kommt die Horizontfarbe von dort.
const BACKDROP = meta.pitch.backdrop ?? null;
const HORIZON = new THREE.Color(BACKDROP?.sky ?? '#d5e2ee');
const ZENITH = new THREE.Color(BACKDROP ? '#8fa9c4' : '#5b93d0');
scene.background = HORIZON;
scene.fog = new THREE.Fog(HORIZON, 70, 420);
const skyDome = new THREE.Mesh(new THREE.SphereGeometry(1500, 32, 16), new THREE.ShaderMaterial({
  side: THREE.BackSide, depthWrite: false, fog: false, toneMapped: false,
  uniforms: { top: { value: ZENITH }, horizon: { value: HORIZON } },
  vertexShader: 'varying vec3 dir; void main() { dir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `uniform vec3 top; uniform vec3 horizon; varying vec3 dir;
    void main() {
      float h = max(normalize(dir).y, 0.0);
      gl_FragColor = vec4(mix(horizon, top, pow(h, 0.55)), 1.0);
      #include <colorspace_fragment>
    }`,
}));
skyDome.renderOrder = -10;
skyDome.frustumCulled = false;
scene.add(skyDome);

// Mit Bildern aus dem Video (Kulisse, Luftbild, Spieler): Licht wie am Aufnahmetag, bedeckt, also viel weiches
// Himmelslicht und nur wenig gerichtete Sonne. Die Farben aus dem Video enthalten ihr Licht schon.
const OVERCAST = !!BACKDROP;
const HEMI = OVERCAST ? 3.6 : 2.5, SUN = OVERCAST ? 0.8 : 2.7;
const SUN_DIR = new THREE.Vector3(-0.42, 0.8, 0.43).normalize(); // vom Boden zur Lichtquelle
const hemi = new THREE.HemisphereLight(0xeaf2ff, 0x6f7f58, HEMI);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff3e0, SUN);
sun.castShadow = true;
const SHADOW_SIZE = Math.min(renderer.capabilities.maxTextureSize, innerWidth < 800 ? 2048 : 4096);
sun.shadow.mapSize.set(SHADOW_SIZE, SHADOW_SIZE);
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 400;
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.03;
scene.add(sun, sun.target);
// Helligkeit einer waagerechten Fläche unter diesem Licht: damit unbeleuchtete Fotos (Kulisse) dazu passen.
const GROUND_LIGHT = new THREE.Color(0xeaf2ff).multiplyScalar(HEMI / Math.PI)
  .add(new THREE.Color(0xfff3e0).multiplyScalar(SUN * SUN_DIR.y / Math.PI));

// Die Schattenkarte deckt nur die Umgebung des Blickziels ab: so bleibt sie aus der Nähe scharf.
const shadowU = new THREE.Vector3().crossVectors(SUN_DIR, new THREE.Vector3(0, 0, 1)).normalize();
const shadowV = new THREE.Vector3().crossVectors(SUN_DIR, shadowU).normalize();
let shadowHalf = 0;
function updateShadow(focus, distance) {
  const want = THREE.MathUtils.clamp(distance * 0.85, 9, 75);
  if (Math.abs(Math.log(want / (shadowHalf || 1e-3))) > 0.18) {
    shadowHalf = want;
    const c = sun.shadow.camera;
    c.left = c.bottom = -shadowHalf;
    c.right = c.top = shadowHalf;
    c.updateProjectionMatrix();
  }
  // auf ganze Texel einrasten, sonst flimmern die Schattenkanten bei bewegter Kamera
  const texel = 2 * shadowHalf / SHADOW_SIZE;
  const a = focus.dot(shadowU), b = focus.dot(shadowV);
  sun.target.position.set(focus.x, 0, focus.z)
    .addScaledVector(shadowU, Math.round(a / texel) * texel - a)
    .addScaledVector(shadowV, Math.round(b / texel) * texel - b);
  sun.position.copy(sun.target.position).addScaledVector(SUN_DIR, 200);
}

const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 4000);
camera.position.set(0, 38, 62);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);
controls.maxPolarAngle = Math.PI / 2 - 0.02;
controls.minDistance = 2;
controls.maxDistance = 250;

// Platz, Kulisse und Tore (web/stadium.js)
const { backdropWalls } = buildStadium({ renderer, scene, meta, base, groundLight: GROUND_LIGHT });

const bodyGeo = new THREE.CapsuleGeometry(0.24, 1.28, 4, 12);
const actors = ENTITIES.map((e, index) => {
  const group = new THREE.Group();
  let body, label, halo;
  if (e.kind === 'ball') {
    body = new THREE.Mesh(new THREE.SphereGeometry(0.11, 24, 16),
      new THREE.MeshStandardMaterial({ map: ballTexture(), roughness: 0.45 }));
    body.position.y = 0.11;
    halo = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.4, 40),
      new THREE.MeshBasicMaterial({ color: 0xffe600, transparent: true, opacity: 0.55, depthWrite: false }));
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.02;
    halo.visible = MARKS;
    group.add(halo);
  } else {
    const color = meta.teams[e.team].color;
    body = new THREE.Mesh(bodyGeo, new THREE.MeshStandardMaterial({ color, roughness: 0.8 }));
    body.position.y = 0.88;
    body.userData.entity = index;
    label = numberSprite(e.number == null ? '?' : e.label ?? String(e.number), color);   // ohne gelesene Rückennummer: ?
    label.visible = MARKS;
    group.add(label);
  }
  body.castShadow = true;
  group.add(body);
  scene.add(group);
  return { group, body, label, halo, kind: e.kind };
});
const ballIndex = ENTITIES.findIndex((e) => e.kind === 'ball');
const pickable = actors.filter((a) => a.kind === 'player').map((a) => a.body);

// Skelette: je Knochen ein Zylinder, je Gelenk eine Kugel, alle Spieler in zwei Instanz-Meshes.
const P = PLAYER_SLOTS.size;
let boneMesh = null, jointMesh = null;
let look = ['body', 'sticks', 'simple'].includes(query.get('look')) ? query.get('look') : 'body';
const jointPos = Array.from({ length: J }, () => new THREE.Vector3());
const contactShadows = createContactShadows(scene, PLAYER_SLOTS.size, JOINT_INDEX);
const headPos = new THREE.Vector3(), nosePos = new THREE.Vector3();
let selectedHasPose = false;
if (POSES) {
  const lambert = () => new THREE.MeshStandardMaterial({ roughness: 0.8 });
  boneMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(1, 1, 1, 10, 1), lambert(), P * BONES.length);
  jointMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 12, 8), lambert(), P * J);
  const partColor = (team, part) => {
    const shirt = new THREE.Color(meta.teams[team].color);
    if (part === 'shirt' || part === 'sock') return shirt;
    if (part === 'shorts') return shirt.multiplyScalar(0.4);
    if (part === 'boot') return new THREE.Color(0x151515);
    return new THREE.Color(0xd9a37e); // Haut
  };
  for (const [entity, slot] of PLAYER_SLOTS) {
    const team = ENTITIES[entity].team;
    BONES.forEach((b, i) => boneMesh.setColorAt(slot * BONES.length + i, partColor(team, b.part)));
    JOINTS.forEach((j, i) => jointMesh.setColorAt(slot * J + i, partColor(team, j.part)));
  }
  for (const mesh of [boneMesh, jointMesh]) {
    mesh.frustumCulled = false;
    mesh.castShadow = true;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    scene.add(mesh);
  }
}
const ZERO = new THREE.Matrix4().makeScale(0, 0, 0);
const UP = new THREE.Vector3(0, 1, 0);
const mtx = new THREE.Matrix4(), quat = new THREE.Quaternion(), scl = new THREE.Vector3();
const mid = new THREE.Vector3(), dir = new THREE.Vector3();

function drawSkeleton(slot, visible) {
  for (let i = 0; i < BONES.length; i++) {
    const index = slot * BONES.length + i;
    if (!visible) { boneMesh.setMatrixAt(index, ZERO); continue; }
    const bone = BONES[i], a = jointPos[bone.from], b = jointPos[bone.to];
    const len = dir.subVectors(b, a).length();
    if (len < 1e-4) { boneMesh.setMatrixAt(index, ZERO); continue; }
    quat.setFromUnitVectors(UP, dir.divideScalar(len));
    mid.addVectors(a, b).multiplyScalar(0.5);
    boneMesh.setMatrixAt(index, mtx.compose(mid, quat, scl.set(bone.radius, len, bone.radius)));
  }
  for (let j = 0; j < J; j++) {
    if (!visible) { jointMesh.setMatrixAt(slot * J + j, ZERO); continue; }
    const r = JOINTS[j].radius;
    jointMesh.setMatrixAt(slot * J + j, mtx.compose(jointPos[j], quat.identity(), scl.set(r, r, r)));
  }
}

// Körpermodelle: je Spieler eines, angelegt beim ersten Auftritt. Bis das Modell geladen ist
// (oder falls es fehlt), erscheinen die Spieler als Stab-Skelett.
let avatarFactory = null;
const avatars = new Map();
// Aussehen je Spieler aus dem Video (web/looks.js)
const { loadLooks, lookOf, hairOf, kitOf } = createLooks(meta, base);
if (POSES) {
  Promise.all([loadAvatars('models/player/player.glb'), loadLooks()]).then(([factory]) => { avatarFactory = factory; })
    .catch((err) => console.warn('Körpermodell nicht geladen, zeige Skelette:', err));
}

const marker = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.58, 48),
  new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.8, depthWrite: false }));
marker.rotation.x = -Math.PI / 2;
marker.visible = false;
scene.add(marker);

// ---------- Zustand ----------
let t = 0, playing = false, speed = 1, mode = 'free', selected = -1;
let heading = 0, headingSnap = true, lookYaw = 0, lookPitch = 0, followPrev = null;
const tmp = new THREE.Vector3(), tmp2 = new THREE.Vector3(), tmp3 = new THREE.Vector3();

function clockText(frame) {
  const p = meta.periods.findLast((q) => frame >= q.startFrame) || meta.periods[0];
  const sec = Math.floor((frame - p.startFrame) / meta.fps) + (p.clockStartS ?? (p.id - 1) * 45 * 60);
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  return `${p.id}. Hz  ${mm}:${String(sec % 60).padStart(2, '0')}`;
}

function setTime(frame) {
  t = Math.min(N - 1, Math.max(0, frame));
  if (t >= N - 1) setPlaying(false);
}
function setPlaying(on) {
  playing = on;
  $('play').textContent = on ? '⏸' : '▶';
}
function select(index) {
  selected = index;
  $('player').value = String(index);
  followPrev = null;
  headingSnap = true;
  lookYaw = lookPitch = 0;
}
function setMode(next) {
  mode = next;
  $('mode').value = next;
  if (mode !== 'free' && selected < 0) {
    select(actors.findIndex((a, i) => a.kind === 'player' && sample(i, t, tmp)));
  }
  controls.enabled = mode !== 'fp';
  followPrev = null;
  if (mode === 'free') camera.fov = 55; else if (mode === 'fp') camera.fov = 75;
  camera.updateProjectionMatrix();
}

// ---------- Bedienung ----------
const seek = $('seek');
seek.max = String(N - 1);
seek.addEventListener('input', () => setTime(Number(seek.value)));
$('play').addEventListener('click', () => { if (t >= N - 1) t = 0; setPlaying(!playing); });
$('speed').addEventListener('change', (e) => { speed = Number(e.target.value); });
$('mode').addEventListener('change', (e) => setMode(e.target.value));
for (const [i, e] of ENTITIES.entries()) {
  if (e.kind !== 'player') continue;
  const name = e.number == null ? `? (${e.label})` : e.label ?? e.number;   // ohne gelesene Rückennummer: ? und Name der Spur
  $('player').add(new Option(`${meta.teams[e.team].name} ${name}`, String(i)));
}
$('player').addEventListener('change', (e) => {
  select(Number(e.target.value));
  if (selected >= 0 && mode === 'free') setMode('follow');
  if (selected < 0) setMode('free');
});
$('topview').addEventListener('click', () => {
  setMode('free');
  controls.target.set(0, 0, 0);
  camera.position.set(0, 95, 0.01);
});
addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLSelectElement) return;
  if (e.code === 'Space') { e.preventDefault(); $('play').click(); }
  else if (e.code === 'ArrowLeft') setTime(t - 5 * meta.fps);
  else if (e.code === 'ArrowRight') setTime(t + 5 * meta.fps);
  else if (e.key === ',') { setPlaying(false); setTime(Math.round(t) - 1); }
  else if (e.key === '.') { setPlaying(false); setTime(Math.round(t) + 1); }
});

// Klick wählt einen Spieler, Ziehen dreht (in der Ich-Perspektive: umsehen).
const raycaster = new THREE.Raycaster();
let down = null;
renderer.domElement.addEventListener('pointerdown', (e) => {
  down = { x: e.clientX, y: e.clientY, moved: false };
});
addEventListener('pointermove', (e) => {
  if (!down) return;
  const dx = e.clientX - down.x, dy = e.clientY - down.y;
  if (Math.abs(dx) + Math.abs(dy) > 4) down.moved = true;
  if (mode === 'fp' && e.buttons) {
    lookYaw -= e.movementX * 0.004;
    lookPitch = Math.max(-1.2, Math.min(1.2, lookPitch - e.movementY * 0.004));
  }
});
addEventListener('pointerup', (e) => {
  if (down && !down.moved && e.target === renderer.domElement) {
    const r = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const hit = raycaster.intersectObjects(pickable.filter((m) => m.parent.visible))[0]; // auch unsichtbare Figuren treffen
    if (hit) {
      select(hit.object.userData.entity);
      if (mode === 'free') setMode('follow');
    }
  }
  down = null;
});

function resize() {
  // Mit Originalvideo bekommt die Szene nur den oberen Teil; das Video sitzt über der Leiste unten
  const bar = UI ? $('bar').offsetHeight : 0;
  const refH = UI ? reference.height() : 0;
  const height = Math.max(120, innerHeight - (refH ? refH + bar : 0));
  reference.resized();
  $('ref').style.bottom = `${bar}px`;
  renderer.setSize(innerWidth, height);
  camera.aspect = innerWidth / height;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

// ---------- Bildschleife ----------
function updateHeading(dt) {
  // Blickrichtung: Laufrichtung, im Stand zum Ball.
  const span = Math.max(0.5, meta.fps * 0.2);
  const has = sample(selected, t - span, tmp2) && sample(selected, t + span, tmp3);
  let want = null;
  if (selectedHasPose) {
    tmp3.subVectors(nosePos, headPos); // Blickrichtung aus der Kopfhaltung
    want = Math.atan2(tmp3.x, tmp3.z);
  } else if (has) {
    tmp3.sub(tmp2);
    if (tmp3.length() / (2 * span / meta.fps) > 1.0) want = Math.atan2(tmp3.x, tmp3.z);
  }
  if (want === null && sample(ballIndex, t, tmp3) && sample(selected, t, tmp2)) {
    tmp3.sub(tmp2);
    if (tmp3.length() > 0.5) want = Math.atan2(tmp3.x, tmp3.z);
  }
  if (want === null) return;
  let d = want - heading;
  d = Math.atan2(Math.sin(d), Math.cos(d));
  heading += headingSnap ? d : d * (1 - Math.exp(-dt * 4));
  headingSnap = false;
}

// Der Ball dreht sich mit dem zurückgelegten Weg (die Daten kennen keinen Drall).
const ballPrev = new THREE.Vector3(), ballAxis = new THREE.Vector3(), ballTurn = new THREE.Quaternion();
let ballSeen = false;
function rollBall() {
  const ball = actors[ballIndex];
  if (!ball || !ball.group.visible) { ballSeen = false; return; }
  const p = ball.group.position;
  if (ballSeen) {
    tmp.subVectors(p, ballPrev);
    const way = Math.hypot(tmp.x, tmp.z);
    if (way > 1e-4 && way < 3) {
      ballAxis.set(tmp.z, 0, -tmp.x).normalize();
      ball.body.quaternion.premultiply(ballTurn.setFromAxisAngle(ballAxis, way / 0.11));
    }
  }
  ballPrev.copy(p);
  ballSeen = true;
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (playing) setTime(t + dt * meta.fps * speed);
  reference.sync(t, playing, speed);

  for (const [i, actor] of actors.entries()) {
    actor.group.visible = sample(i, t, actor.group.position);
    if (actor.kind !== 'player') continue;
    const slot = PLAYER_SLOTS.get(i);
    const posed = look !== 'simple' && actor.group.visible && samplePose(slot, t, actor.group.position, jointPos);
    contactShadows.update(slot, posed ? jointPos : null, actor.group.position, actor.group.visible);
    if (i === selected) {
      selectedHasPose = posed;
      if (posed) { headPos.copy(jointPos[JOINT_INDEX.head]); nosePos.copy(jointPos[JOINT_INDEX.nose]); }
    }
    const shown = posed && !(mode === 'fp' && i === selected);
    const asBody = shown && look === 'body' && avatarFactory;
    if (POSES) drawSkeleton(slot, shown && !asBody);
    let avatar = avatars.get(i);
    if (asBody) {
      if (!avatar) {
        const e = ENTITIES[i];
        const kit = kitOf(e), look = lookOf(e);
        if (look) kit.hair = hairOf(look);
        avatar = avatarFactory.create(kit, e.label ? null : e.number, e.id, look);
        scene.add(avatar.root);
        avatars.set(i, avatar);
      }
      avatar.setPose(jointPos, JOINT_INDEX);
    }
    if (avatar) avatar.root.visible = !!asBody;
    actor.body.visible = !posed; // ohne Pose: einfache Figur
    if (actor.group.visible && MARKS) {
      // Schilder über den Köpfen: aus der Totalen lesbar, aus der Nähe ausgeblendet (dort steht die Nummer am Trikot).
      const dist = camera.position.distanceTo(actor.group.position);
      const near = look === 'body' && posed ? 9 : 3;
      const fade = THREE.MathUtils.clamp((dist - near) / (near * 0.7), 0, 1);
      const size = Math.max(0.3, dist * 0.016);
      actor.label.visible = fade > 0.01;
      actor.label.material.opacity = 0.92 * fade;
      actor.label.scale.setScalar(size);
      actor.label.position.y = (posed ? Math.max(jointPos[JOINT_INDEX.head].y + 0.18, 0.6) : 1.95) + size * 0.6;
    }
  }
  if (POSES) {
    boneMesh.instanceMatrix.needsUpdate = true;
    jointMesh.instanceMatrix.needsUpdate = true;
    poseChunk(t + POSES.chunkFrames); // nächsten Block vorladen
  }
  rollBall();
  const target = selected >= 0 && actors[selected].group.visible ? actors[selected].group.position : null;
  marker.visible = !!target && mode !== 'fp' && MARKS;
  if (target) marker.position.set(target.x, 0.03, target.z);

  if (mode === 'follow' && target) {
    tmp.set(target.x, 1, target.z);
    if (followPrev) camera.position.add(tmp2.copy(tmp).sub(followPrev));
    else { // zoom < 1: näher heran; orbit: Grad um den Spieler gedreht; tilt: Kamerahöhe als Vielfaches
      const orbit = THREE.MathUtils.degToRad(Number(query.get('orbit')) || 0);
      tmp2.set(12 * Math.sin(orbit), 6 * (Number(query.get('tilt')) || 1), 12 * Math.cos(orbit));
      camera.position.copy(tmp).add(tmp2.multiplyScalar(Number(query.get('zoom')) || 1));
    }
    (followPrev ??= new THREE.Vector3()).copy(tmp);
    controls.target.copy(tmp);
  }
  if (mode === 'fp' && target) {
    updateHeading(dt);
    actors[selected].group.visible = false;
    if (selectedHasPose) camera.position.copy(headPos); else camera.position.set(target.x, 1.7, target.z);
    const yaw = heading + lookYaw;
    tmp.set(Math.sin(yaw) * Math.cos(lookPitch), Math.sin(lookPitch), Math.cos(yaw) * Math.cos(lookPitch));
    camera.lookAt(tmp.add(camera.position));
  } else {
    controls.update();
  }

  if (mode === 'fp' && target) updateShadow(target, 45);
  else updateShadow(controls.target, camera.position.distanceTo(controls.target));
  skyDome.position.copy(camera.position);
  // Dunst soll nur den Horizont weich machen, nicht den Platz aus großer Höhe verschleiern
  scene.fog.near = 70 + camera.position.y * 3;
  scene.fog.far = 420 + camera.position.y * 8;
  // Die Kulisse stimmt nur für Blicke aus mäßiger Höhe. Von weit oben wäre sie eine schräg gesehene Fototafel: ausblenden.
  const wallOpacity = 1 - THREE.MathUtils.smoothstep(camera.position.y, 30, 60);
  for (const wall of backdropWalls) {
    wall.visible = wallOpacity > 0.01;
    wall.material.opacity = wallOpacity;
  }

  if (document.activeElement !== seek || playing) seek.value = String(Math.round(t));
  $('clock').textContent = clockText(Math.round(t));
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

$('status').textContent = `${meta.source.name} · ${meta.fps} Hz · ${Math.round(L * 10) / 10} × ${Math.round(W * 10) / 10} m`
  + (!POSES ? '' : POSES.synthetic ? ' · Körperhaltung: aus den Laufwegen erzeugt (Platzhalter)'
    : POSES.estimatedShare === undefined ? ' · Körperhaltung: aus dem Video geschätzt'
      : ` · Körperhaltung: ${Math.round(POSES.estimatedShare * 100)} % der Bilder mit im Video erkannten Gelenken, sonst natürliche Bewegung im Takt`);
$('skeletonLabel').hidden = !POSES;
$('look').value = look;
$('look').addEventListener('change', (e) => { look = e.target.value; });
if (query.has('t')) setTime(Number(query.get('t')) * meta.fps);
if (query.has('player')) select(ENTITIES.findIndex((e) => e.id === query.get('player')));
if (query.has('mode')) setMode(query.get('mode'));
if (query.get('view') === 'top') $('topview').click();
requestAnimationFrame(frame);
