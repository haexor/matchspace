// Aussehen der Spieler aus dem Video (looks.png, tools/veo_looks.py): eine Kachel je Spieler; fehlt sie, gelten die
// Mannschaftsfarben. Dazu die Trikotfarben aus den Angaben der Mannschaft.
import * as THREE from 'three';

/** Zustand für ein Spiel: lädt looks.png und liefert Aussehen, Haarfarbe und Trikot je Figur. */
export function createLooks(meta, base) {
  const LOOKS = meta.looks ?? null;
  let lookAtlas = null, lookPixels = null, backAtlas = null;
  const kitTextures = new Map();      // Kit-Blätter der Bild-KI (looks.kit.players, tools/kit_sheet.py)
  function loadLooks() {
    if (!LOOKS) return Promise.resolve();
    // Rückenpartie aus dem Foto (scharfe Nummer): eigene Bilddatei, ein Feld je Spieler (tools/looks_from_photo.py)
    const backs = LOOKS.backPatch ? new THREE.TextureLoader().loadAsync(`${base}${LOOKS.backPatch.file}?v=${LOOKS.backPatch.cell}`).then((tex) => {
      tex.flipY = false;
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.generateMipmaps = false;
      tex.minFilter = THREE.LinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.needsUpdate = true;
      backAtlas = tex;
    }).catch((err) => console.warn('Rückenpartie nicht geladen:', err)) : Promise.resolve();
    const kits = Object.entries(LOOKS.kit?.players ?? {}).map(([id, k]) => new THREE.TextureLoader().loadAsync(`${base}${k.file}`).then((tex) => {
      tex.flipY = false;      // Texturkoordinaten zählen von oben (Pixel des Blatts)
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      kitTextures.set(id, tex);
    }).catch((err) => console.warn('Kit-Blatt nicht geladen:', err)));
    return Promise.all([backs, ...kits]).then(() => new THREE.TextureLoader().loadAsync(`${base}${LOOKS.file}?tile=${LOOKS.tile}`).then((tex) => {
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
    })).catch((err) => console.warn('Videotextur nicht geladen, zeige Mannschaftsfarben:', err));
  }
  function lookOf(entity) {
    const k = LOOKS?.players?.[entity.id] ?? (entity.role === 'goalkeeper' ? undefined : LOOKS?.teams?.[entity.team]);
    if (k === undefined || !lookAtlas) return null;
    const tile = [(k % LOOKS.columns) * LOOKS.tile, Math.floor(k / LOOKS.columns) * LOOKS.tile];
    const bp = LOOKS.backPatch, cell = bp?.players?.[entity.id];
    const back = backAtlas && cell !== undefined ? { map: backAtlas, cell: new THREE.Vector4((cell % bp.columns) * bp.cell, Math.floor(cell / bp.columns) * bp.cell, bp.cell, bp.half), y: bp.y, size: new THREE.Vector2(backAtlas.image.width, backAtlas.image.height) } : null;
    const kitMeta = LOOKS.kit?.players?.[entity.id], kit = kitMeta && kitTextures.has(entity.id) ? { texture: kitTextures.get(entity.id), boxes: kitMeta.boxes, size: kitMeta.size } : null;
    return { kit, back, printKept: Boolean(LOOKS.cleaned?.printKept), photo: Boolean(LOOKS.fromPhoto?.[entity.id]?.vorn) && !LOOKS.faceFromModel, map: lookAtlas, tile, size: [lookAtlas.image.width, lookAtlas.image.height],
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

  function kitOf(entity) {
    const team = meta.teams[entity.team];
    const shirt = new THREE.Color(team.kit?.shirt ?? team.color);
    return { shirt, shorts: new THREE.Color(team.kit?.shorts ?? shirt.clone().multiplyScalar(0.4)), socks: new THREE.Color(team.kit?.socks ?? team.color) };
  }

  return { loadLooks, lookOf, hairOf, kitOf };
}
