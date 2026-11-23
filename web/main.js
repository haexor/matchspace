import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { loadAvatars } from './avatar.js?v=13';

const $ = (id) => document.getElementById(id);
const query = new URLSearchParams(location.search);
const base = `data/${query.get('match') || 'game1'}/`;

// ---------- Daten laden (Format: matchspace-track v0) ----------
let meta, data;
try {
  meta = await (await fetch(base + 'meta.json')).json();
  data = new Int16Array(await (await fetch(base + meta.tracks.file)).arrayBuffer());
} catch (err) {
  $('status').textContent = `Spieldaten unter ${base} nicht gefunden. Siehe README.`;
  throw err;
}
const N = meta.frames;
const ENTITIES = meta.entities;
const STRIDE = ENTITIES.length * 3;
const { scale: SCALE, missing: MISSING } = meta.tracks;
const L = meta.pitch.length, W = meta.pitch.width;

// ---------- Körperposen (optional, in Blöcken nachgeladen) ----------
const POSES = meta.poses ?? null;
const PLAYER_SLOTS = ENTITIES.map((e) => e.kind === 'player').reduce((acc, isPlayer, i) => {
  if (isPlayer) acc.set(i, acc.size);
  return acc;
}, new Map());
const JOINTS = POSES ? POSES.skeleton.joints : [];
const BONES = POSES ? POSES.skeleton.bones : [];
const J = JOINTS.length;
const JOINT_INDEX = Object.fromEntries(JOINTS.map((j, i) => [j.name, i]));
const chunkCache = new Map(); // Blocknummer -> Int16Array | null (lädt) | false (fehlt)

function poseChunk(frame) {
  const c = Math.floor(frame / POSES.chunkFrames);
  if (c < 0 || c >= POSES.chunks) return null;
  const cached = chunkCache.get(c);
  if (cached !== undefined) return cached || null;
  chunkCache.set(c, null);
  fetch(base + POSES.path.replace('{chunk}', String(c).padStart(3, '0')))
    .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.statusText))))
    .then((buf) => {
      chunkCache.set(c, new Int16Array(buf));
      for (const key of chunkCache.keys()) if (Math.abs(key - c) > 4) chunkCache.delete(key);
    })
    .catch(() => chunkCache.set(c, false));
  return null;
}

/** Gelenkpositionen eines Spielers zum Frame t in Three-Koordinaten; root = Position am Boden. */
function samplePose(slot, t, root, out) {
  const f0 = Math.min(N - 1, Math.max(0, Math.floor(t)));
  const f1 = Math.min(N - 1, f0 + 1);
  const c0 = poseChunk(f0);
  if (!c0) return false;
  const perFrame = PLAYER_SLOTS.size * J * 3;
  const o0 = (f0 % POSES.chunkFrames) * perFrame + slot * J * 3;
  if (c0[o0] === POSES.missing) return false;
  let c1 = poseChunk(f1);
  let o1 = (f1 % POSES.chunkFrames) * perFrame + slot * J * 3;
  if (!c1 || c1[o1] === POSES.missing) { c1 = c0; o1 = o0; }
  const a = t - f0, k = POSES.scale;
  for (let j = 0; j < J; j++) {
    const i0 = o0 + j * 3, i1 = o1 + j * 3;
    const x = c0[i0] + (c1[i1] - c0[i0]) * a;
    const y = c0[i0 + 1] + (c1[i1 + 1] - c0[i0 + 1]) * a;
    const z = c0[i0 + 2] + (c1[i1 + 2] - c0[i0 + 2]) * a;
    out[j].set(root.x + x * k, z * k, root.z - y * k);
  }
  return true;
}

/** Position eines Objekts zum (gebrochenen) Frame t, in Three-Koordinaten. */
function sample(entity, t, out) {
  const f0 = Math.min(N - 1, Math.max(0, Math.floor(t)));
  const f1 = Math.min(N - 1, f0 + 1);
  const i0 = f0 * STRIDE + entity * 3, i1 = f1 * STRIDE + entity * 3;
  if (data[i0] === MISSING) return false;
  const a = data[i1] === MISSING ? 0 : t - f0;
  const x = data[i0] + (data[i1] - data[i0]) * a;
  const y = data[i0 + 1] + (data[i1 + 1] - data[i0 + 1]) * a;
  const z = data[i0 + 2] + (data[i1 + 2] - data[i0 + 2]) * a;
  out.set(x * SCALE, z * SCALE, -y * SCALE); // Feld: x Länge, y Breite, z hoch
  return true;
}

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

// Feine Rasenstruktur: Rauschen, das aus der Nähe die Unschärfe des Luftbilds überdeckt.
function grassDetail() {
  // mehrere Größenstufen übereinander, damit die Struktur auch aus einigen Metern Abstand erhalten bleibt
  const n = 256, cv = document.createElement('canvas');
  cv.width = cv.height = n;
  const g = cv.getContext('2d');
  let seed = 12345;
  const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  const sum = new Float32Array(n * n);
  for (const [cell, weight] of [[1, 0.3], [3, 0.3], [9, 0.25], [32, 0.15]]) {
    const m = n / cell | 0, grid = Float32Array.from({ length: m * m }, rnd);
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        const fx = x / cell, fy = y / cell, x0 = Math.floor(fx) % m, y0 = Math.floor(fy) % m, x1 = (x0 + 1) % m, y1 = (y0 + 1) % m;
        const ax = fx - Math.floor(fx), ay = fy - Math.floor(fy);
        sum[y * n + x] += weight * ((grid[y0 * m + x0] * (1 - ax) + grid[y0 * m + x1] * ax) * (1 - ay)
          + (grid[y1 * m + x0] * (1 - ax) + grid[y1 * m + x1] * ax) * ay);
      }
    }
  }
  const img = g.createImageData(n, n);
  for (let i = 0; i < n * n; i++) {
    const v = Math.max(0, Math.min(255, 204 + (sum[i] - 0.5) * 300)); // Mittel 0,8
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(cv);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return tex;
}
const DETAIL = grassDetail();
const SURROUND = new THREE.Color(0x35602c);

/** Rasenmaterial: Bild (Luftbild oder gezeichneter Platz) mal Rasenstruktur; an den Rändern Übergang in die Umgebung.
 *  size: Kantenlängen in Metern, fade: Breite des Übergangs je Seite in Metern [links, rechts, fern, nah]. */
function groundMaterial(map, size, fade) {
  const material = new THREE.MeshLambertMaterial({ map });
  const uniforms = { detailMap: { value: DETAIL }, metres: { value: new THREE.Vector2(size[0], size[1]) },
    surround: { value: SURROUND }, fade: { value: new THREE.Vector4(...fade) } };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform sampler2D detailMap; uniform vec2 metres; uniform vec3 surround; uniform vec4 fade;`)
      .replace('#include <map_fragment>', `#include <map_fragment>
        vec2 gm = vMapUv * metres;
        vec4 edge = vec4(gm.x, metres.x - gm.x, metres.y - gm.y, gm.y) / max(fade, vec4(1e-4));
        float inside = min(min(clamp(edge.x, 0.0, 1.0), clamp(edge.y, 0.0, 1.0)), min(clamp(edge.z, 0.0, 1.0), clamp(edge.w, 0.0, 1.0)));
        diffuseColor.rgb = mix(surround, diffuseColor.rgb, smoothstep(0.0, 1.0, inside));
        float fine = texture2D(detailMap, gm / 1.9).r, coarse = texture2D(detailMap, gm / 23.0 + 0.37).r;
        diffuseColor.rgb *= (0.3 + 0.7 * fine / 0.8) * (0.7 + 0.3 * coarse / 0.8);`);
  };
  return material;
}

function buildPitch() {
  buildGoals();
  // Umgebung: eine große Fläche in gedämpfter Rasenfarbe, knapp unter dem Platz
  const far = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000),
    new THREE.MeshLambertMaterial({ color: SURROUND, polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2 }));
  const setSurround = () => far.material.color.copy(SURROUND);
  far.rotation.x = -Math.PI / 2;
  far.position.y = -0.03;
  far.receiveShadow = true;
  scene.add(far);
  const place = (mesh, cx, cz) => {
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(cx, 0, cz);
    mesh.receiveShadow = true;
    scene.add(mesh);
  };
  const photo = meta.pitch.texture;
  if (photo) {
    // Luftbild des echten Platzes: Zeile 0 ist die Gegenseite, Spalte 0 das linke Tor.
    const m = typeof photo.margin === 'number'
      ? { left: photo.margin, right: photo.margin, near: photo.margin, far: photo.margin } : photo.margin;
    const f = photo.fade ?? { left: m.left * 0.6, right: m.right * 0.6, near: m.near * 0.6, far: m.far * 0.6 };
    const size = [L + m.left + m.right, W + m.near + m.far];
    const tex = new THREE.TextureLoader().load(base + photo.file, (t) => {
      // Umgebung in der mittleren Rasenfarbe des Fotos, etwas gedämpft
      const cv = document.createElement('canvas');
      cv.width = cv.height = 8;
      const g = cv.getContext('2d', { willReadFrequently: true });
      g.drawImage(t.image, t.image.width * 0.3, t.image.height * 0.3, t.image.width * 0.4, t.image.height * 0.4, 0, 0, 8, 8);
      const d = g.getImageData(0, 0, 8, 8).data;
      let r = 0, gg = 0, b = 0;
      for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
      SURROUND.setRGB(r / 64 / 255, gg / 64 / 255, b / 64 / 255, THREE.SRGBColorSpace);
      const hsl = SURROUND.getHSL({});
      SURROUND.setHSL(hsl.h, hsl.s * 0.55, hsl.l * 0.85);
      setSurround();
    });
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    place(new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), groundMaterial(tex, size, [f.left, f.right, f.far, f.near])),
      (m.right - m.left) / 2, (m.near - m.far) / 2);
    buildBackdrop();
    return;
  }
  const margin = 6, s = 16; // Pixel pro Meter
  const cv = document.createElement('canvas');
  cv.width = (L + 2 * margin) * s;
  cv.height = (W + 2 * margin) * s;
  const g = cv.getContext('2d');
  g.fillStyle = '#2f7a34';
  g.fillRect(0, 0, cv.width, cv.height);
  g.translate(cv.width / 2, cv.height / 2);
  g.scale(s, s);
  const stripe = L / 14;
  for (let i = 0; i < 14; i += 2) {
    g.fillStyle = '#35873a';
    g.fillRect(-L / 2 + i * stripe, -W / 2, stripe, W);
  }
  g.strokeStyle = '#fff';
  g.fillStyle = '#fff';
  g.lineWidth = 0.12;
  g.strokeRect(-L / 2, -W / 2, L, W);
  g.beginPath(); g.moveTo(0, -W / 2); g.lineTo(0, W / 2); g.stroke();
  g.beginPath(); g.arc(0, 0, 9.15, 0, 2 * Math.PI); g.stroke();
  g.beginPath(); g.arc(0, 0, 0.2, 0, 2 * Math.PI); g.fill();
  for (const dir of [-1, 1]) {
    const gx = dir * L / 2;
    g.strokeRect(Math.min(gx, gx - dir * 16.5), -20.16, 16.5, 40.32);
    g.strokeRect(Math.min(gx, gx - dir * 5.5), -9.16, 5.5, 18.32);
    const px = gx - dir * 11;
    g.beginPath(); g.arc(px, 0, 0.2, 0, 2 * Math.PI); g.fill();
    const half = Math.acos(5.5 / 9.15); // Teilkreis außerhalb des Strafraums
    const mid = dir === 1 ? Math.PI : 0;
    g.beginPath(); g.arc(px, 0, 9.15, mid - half, mid + half); g.stroke();
    for (const side of [-1, 1]) {
      const a0 = Math.atan2(0, -dir), a1 = Math.atan2(-side, 0); // Viertelkreis ins Feld
      const sweep = Math.atan2(Math.sin(a1 - a0), Math.cos(a1 - a0));
      g.beginPath();
      g.arc(gx, side * W / 2, 1, a0, a1, sweep < 0);
      g.stroke();
    }
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  SURROUND.set(0x2c6a30);
  setSurround();
  const size = [L + 2 * margin, W + 2 * margin];
  place(new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), groundMaterial(tex, size, [3, 3, 3, 3])), 0, 0);
}

// Kulisse: Fotos der echten Umgebung auf senkrechten Flächen hinter den Linien (tools/veo_backdrop.py).
// Nur von innen sichtbar, damit sie den Blick von außen auf den Platz nicht verstellen.
const backdropWalls = [];
function buildBackdrop() {
  if (!BACKDROP) return;
  // Ausblenden nach oben (dort endet, was die Kamera sah) und an offenen Enden zur Kameraseite hin
  const fadeMap = (open) => {
    const cv = document.createElement('canvas');
    cv.width = 128; cv.height = 64;
    const g = cv.getContext('2d'), up = g.createLinearGradient(0, 0, 0, 64);
    up.addColorStop(0, '#000'); up.addColorStop(0.22, '#fff'); up.addColorStop(1, '#fff');
    g.fillStyle = up; g.fillRect(0, 0, 128, 64);
    if (open) {
      const side = g.createLinearGradient(open === 'from' ? 0 : 128, 0, open === 'from' ? 30 : 98, 0);
      side.addColorStop(0, 'rgba(0,0,0,1)'); side.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = side; g.fillRect(0, 0, 128, 64);
    }
    return new THREE.CanvasTexture(cv);
  };
  for (const wall of BACKDROP.walls) {
    const tex = new THREE.TextureLoader().load(base + wall.file);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    const [ax, ay] = wall.from, [bx, by] = wall.to;
    const dx = bx - ax, dz = -(by - ay), len = Math.hypot(dx, dz);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(len, wall.height),
      new THREE.MeshBasicMaterial({ map: tex, alphaMap: fadeMap(wall.open), transparent: true, depthWrite: false, fog: false, color: GROUND_LIGHT }));
    mesh.position.set((ax + bx) / 2, (wall.base ?? 0) + wall.height / 2, -(ay + by) / 2);
    mesh.rotation.y = Math.atan2(-dz, dx);
    mesh.renderOrder = -5;
    backdropWalls.push(mesh);
    scene.add(mesh);
  }
}

// Tore mit Netz: 7,32 × 2,44 m, Netz oben 0,8 m und unten 2 m tief.
function buildGoals() {
  const white = new THREE.MeshStandardMaterial({ color: 0xf4f4f4, roughness: 0.5 });
  const cv = document.createElement('canvas');
  cv.width = cv.height = 64;
  const g = cv.getContext('2d');
  g.strokeStyle = '#fff';
  g.lineWidth = 3;
  for (let i = 0; i <= 64; i += 16) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 64); g.moveTo(0, i); g.lineTo(64, i); g.stroke(); }
  const netTex = new THREE.CanvasTexture(cv);
  netTex.wrapS = netTex.wrapT = THREE.RepeatWrapping;
  netTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const net = new THREE.MeshBasicMaterial({ map: netTex, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false });
  const H = 2.44, HW = 3.66, TOP = 0.8, BOTTOM = 2.0, CELL = 0.48; // eine Kachel = 4 × 4 Maschen von 12 cm
  for (const dir of [-1, 1]) {
    const goal = new THREE.Group();
    goal.position.x = dir * L / 2;
    goal.scale.x = dir; // +x zeigt hinter das Tor
    const bar = (a, b, r = 0.06) => {
      const v = new THREE.Vector3().subVectors(b, a);
      const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, v.length(), 12), white);
      m.position.copy(a).addScaledVector(v, 0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.normalize());
      m.castShadow = true;
      goal.add(m);
    };
    const P = (x, y, z) => new THREE.Vector3(x, y, z);
    for (const s of [-1, 1]) {
      bar(P(0, 0, s * HW), P(0, H, s * HW));
      bar(P(0, H, s * HW), P(TOP, H, s * HW), 0.025);
      bar(P(TOP, H, s * HW), P(BOTTOM, 0, s * HW), 0.025);
      bar(P(0, 0, s * HW), P(BOTTOM, 0, s * HW), 0.025);
    }
    bar(P(0, H, -HW - 0.06), P(0, H, HW + 0.06));
    bar(P(BOTTOM, 0, -HW), P(BOTTOM, 0, HW), 0.025);
    bar(P(TOP, H, -HW), P(TOP, H, HW), 0.025);
    const quads = [], uvs = [];
    const quad = (a, b, c, d) => { // a-b-c-d umlaufend; Maschen in Metern entlang der Kanten
      quads.push(a, b, c, a, c, d);
      const w = a.distanceTo(b), h = b.distanceTo(c), skew = d.distanceTo(a) < 1e-6 ? 0 : new THREE.Vector3().subVectors(d, a).dot(new THREE.Vector3().subVectors(b, a).normalize());
      const uv = [[0, 0], [w, 0], [w + (c.distanceTo(d) - w + skew), h], [skew, h]].map(([u, v]) => [u / CELL, v / CELL]);
      uvs.push(uv[0], uv[1], uv[2], uv[0], uv[2], uv[3]);
    };
    quad(P(BOTTOM, 0, -HW), P(BOTTOM, 0, HW), P(TOP, H, HW), P(TOP, H, -HW));          // Rückwand
    quad(P(0, H, -HW), P(TOP, H, -HW), P(TOP, H, HW), P(0, H, HW));                   // Dach
    for (const s of [-1, 1]) quad(P(0, 0, s * HW), P(BOTTOM, 0, s * HW), P(TOP, H, s * HW), P(0, H, s * HW)); // Seiten
    const geo = new THREE.BufferGeometry().setFromPoints(quads);
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs.flat(), 2));
    const mesh = new THREE.Mesh(geo, net);
    mesh.renderOrder = 1;
    goal.add(mesh);
    scene.add(goal);
  }
}
buildPitch();

function numberSprite(text, color) {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 96;
  const g = cv.getContext('2d');
  g.fillStyle = color;
  g.beginPath(); g.arc(48, 48, 40, 0, 2 * Math.PI); g.fill();
  g.strokeStyle = 'rgba(255,255,255,0.9)';
  g.lineWidth = 4;
  g.stroke();
  g.fillStyle = '#fff';
  g.font = `bold ${text.length > 2 ? 34 : 46}px system-ui, sans-serif`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(text, 48, 51);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false, fog: false }));
  sprite.renderOrder = 5;
  return sprite;
}

// Ball: weiß mit dunklen Feldern an den zwölf Ecken eines Ikosaeders
function ballTexture() {
  const w = 256, h = 128, cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  const g = cv.getContext('2d'), img = g.createImageData(w, h);
  const t = (1 + Math.sqrt(5)) / 2, n = Math.hypot(1, t), spots = [];
  for (const a of [-1, 1]) for (const b of [-t, t]) spots.push([0, a / n, b / n], [a / n, b / n, 0], [b / n, 0, a / n]);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const lat = (0.5 - (y + 0.5) / h) * Math.PI, lon = (x + 0.5) / w * 2 * Math.PI;
      const d = [Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon)];
      let best = -1;
      for (const sp of spots) best = Math.max(best, d[0] * sp[0] + d[1] * sp[1] + d[2] * sp[2]);
      const v = best > 0.935 ? 28 : best > 0.925 ? 130 : 245;
      const i = (y * w + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

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
// Aussehen je Spieler aus dem Video (looks.png, tools/veo_looks.py): eine Kachel je Spieler. Fehlt sie, gelten die Mannschaftsfarben.
const LOOKS = meta.looks ?? null;
let lookAtlas = null, lookPixels = null;
function loadLooks() {
  if (!LOOKS) return Promise.resolve();
  return new THREE.TextureLoader().loadAsync(base + LOOKS.file).then((tex) => {
    tex.flipY = false;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    lookAtlas = tex;
    const cv = document.createElement('canvas');
    cv.width = tex.image.width; cv.height = tex.image.height;
    const g = cv.getContext('2d');
    g.drawImage(tex.image, 0, 0);
    lookPixels = g.getImageData(0, 0, cv.width, cv.height);
  }).catch((err) => console.warn('Videotextur nicht geladen, zeige Mannschaftsfarben:', err));
}
function lookOf(entity) {
  const k = LOOKS?.players?.[entity.id] ?? (entity.role === 'goalkeeper' ? undefined : LOOKS?.teams?.[entity.team]);
  if (k === undefined || !lookAtlas) return null;
  const tile = [(k % LOOKS.columns) * LOOKS.tile, Math.floor(k / LOOKS.columns) * LOOKS.tile];
  return { map: lookAtlas, tile, size: [lookAtlas.image.width, lookAtlas.image.height],
    rects: LOOKS.segments.map((s) => new THREE.Vector4(...s.rect)), ranges: LOOKS.segments.map((s) => new THREE.Vector2(...s.t)) };
}
/** Mittlere Farbe des Oberkopfs (oberstes Zehntel des Kopfbereichs) in der Kachel: Haarfarbe für die Augenbrauen. */
function hairOf(look) {
  const head = LOOKS.segments.find((s) => s.name === 'head').rect;
  let r = 0, g = 0, b = 0, n = 0;
  for (let y = head[1] + Math.floor(head[3] * 0.9); y < head[1] + head[3]; y++) {
    for (let x = head[0]; x < head[0] + head[2]; x++) {
      const o = ((look.tile[1] + y) * lookPixels.width + look.tile[0] + x) * 4;
      r += lookPixels.data[o]; g += lookPixels.data[o + 1]; b += lookPixels.data[o + 2]; n++;
    }
  }
  return new THREE.Color().setRGB(r / n / 255, g / n / 255, b / n / 255, THREE.SRGBColorSpace);
}
if (POSES) {
  Promise.all([loadAvatars('models/player/player.glb'), loadLooks()]).then(([factory]) => { avatarFactory = factory; })
    .catch((err) => console.warn('Körpermodell nicht geladen, zeige Skelette:', err));
}
function kitOf(entity) {
  const team = meta.teams[entity.team];
  const shirt = new THREE.Color(team.kit?.shirt ?? team.color);
  return { shirt, shorts: new THREE.Color(team.kit?.shorts ?? shirt.clone().multiplyScalar(0.4)), socks: new THREE.Color(team.kit?.socks ?? team.color) };
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
    const ndc = new THREE.Vector2(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
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
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight;
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

  for (const [i, actor] of actors.entries()) {
    actor.group.visible = sample(i, t, actor.group.position);
    if (actor.kind !== 'player') continue;
    const slot = PLAYER_SLOTS.get(i);
    const posed = look !== 'simple' && actor.group.visible && samplePose(slot, t, actor.group.position, jointPos);
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
