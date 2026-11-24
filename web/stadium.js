// Platz, Umgebung, Kulisse und Tore der Szene.
import * as THREE from 'three';

/** Baut Rasen, Umgebung, Kulisse und Tore in die Szene. Liefert die Kulissenwände: ihre Deckkraft hängt von der Kamerahöhe ab. */
export function buildStadium({ renderer, scene, meta, base, groundLight }) {
  const L = meta.pitch.length, W = meta.pitch.width;
  const BACKDROP = meta.pitch.backdrop ?? null;
  const GROUND_LIGHT = groundLight;

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
  return { backdropWalls };
}
