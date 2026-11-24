// Kleine Bausteine der Szene: Nummernschild über einem Spieler und die Textur des Balls.
import * as THREE from 'three';

/** Rundes Schild mit Rückennummer, immer zur Kamera gedreht. */
export function numberSprite(text, color) {
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
export function ballTexture() {
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
