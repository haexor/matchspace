// Aussehen der Spieler aus dem Video (looks.png, tools/veo_looks.py): eine Kachel je Spieler; fehlt sie, gelten die
// Mannschaftsfarben. Dazu die Trikotfarben aus den Angaben der Mannschaft.
import * as THREE from 'three';

/** Zustand für ein Spiel: lädt looks.png und liefert Aussehen, Haarfarbe und Trikot je Figur. */
export function createLooks(meta, base) {
  const LOOKS = meta.looks ?? null;
  let lookAtlas = null, lookPixels = null, backAtlas = null;
  const kitSheets = new Map();        // Kit-Blätter je Mannschaft (Bilder), kitCache: fertige Kleidung je Spieler
  const kitCache = new Map();
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
    // Mannschaftsblätter der Bild-KI (looks.kit.teams, tools/kit_sheet.py): ein Bild je Mannschaft; die Rückennummer wird je Spieler aufgedruckt (kitFor)
    const kits = Object.entries(LOOKS.kit?.teams ?? {}).map(([team, k]) => new THREE.TextureLoader().loadAsync(`${base}${k.file}`).then((tex) => {
      kitSheets.set(team, tex.image);
    }).catch((err) => console.warn('Kit-Blatt nicht geladen:', err)));
    if (!LOOKS.file) return Promise.all(kits);      // Szene ohne Videotexturen: nur Kit-Blätter
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
  /** Kleidung eines Spielers aus dem Blatt seiner Mannschaft: Textur mit seiner Rückennummer, dazu was er laut Textur zusätzlich trägt (Unterhemd, Handschuhe, Schuhe); null ohne Blatt. */
  function kitFor(entity) {
    if (entity.role === 'goalkeeper') return null;      // der Torwart trägt ein anderes Trikot als sein Blatt (kein Blatt: einfarbig, siehe outfitOf)
    const sheet = kitSheets.get(entity.team), meta = LOOKS?.kit?.teams?.[entity.team];
    if (!sheet || !meta) return null;
    if (!kitCache.has(entity.id)) {
      const cv = document.createElement('canvas');
      cv.width = sheet.width; cv.height = sheet.height;
      const g = cv.getContext('2d');
      g.drawImage(sheet, 0, 0);
      const number = entity.number != null && !entity.label ? String(entity.number) : null;
      if (number) {
        const [x, y, w, h] = meta.boxes.shirtBack, size = Math.round(0.34 * h);
        const sample = g.getImageData(x + Math.round(0.4 * w), y + Math.round(0.4 * h), Math.round(0.2 * w), Math.round(0.1 * h)).data;
        let lum = 0;
        for (let i = 0; i < sample.length; i += 4) lum += 0.2126 * sample[i] + 0.7152 * sample[i + 1] + 0.0722 * sample[i + 2];
        lum /= sample.length / 4;
        g.fillStyle = lum > 150 ? '#1a1a1a' : '#f4f4f4';      // Aufdruck gegen den Stoff: hell auf dunklem, dunkel auf hellem Trikot
        g.font = `700 ${size}px "Arial Narrow", "Helvetica Neue", Arial, sans-serif`;
        g.textAlign = 'center';
        g.textBaseline = 'middle';
        g.fillText(number, x + w / 2, y + 0.46 * h, 0.5 * w);
      }
      const texture = new THREE.CanvasTexture(cv);
      texture.flipY = false;      // Texturkoordinaten zählen von oben (Pixel des Blatts)
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 4;
      kitCache.set(entity.id, { texture, boxes: meta.boxes, shape: meta.shape, size: meta.size, variant: LOOKS.kit?.players?.[entity.id] ?? {} });
    }
    return kitCache.get(entity.id);
  }
  function lookOf(entity) {
    const k = LOOKS?.players?.[entity.id] ?? (entity.role === 'goalkeeper' ? undefined : LOOKS?.teams?.[entity.team]);
    if (k === undefined || !lookAtlas) return null;
    const tile = [(k % LOOKS.columns) * LOOKS.tile, Math.floor(k / LOOKS.columns) * LOOKS.tile];
    const bp = LOOKS.backPatch, cell = bp?.players?.[entity.id];
    const back = backAtlas && cell !== undefined ? { map: backAtlas, cell: new THREE.Vector4((cell % bp.columns) * bp.cell, Math.floor(cell / bp.columns) * bp.cell, bp.cell, bp.half), y: bp.y, size: new THREE.Vector2(backAtlas.image.width, backAtlas.image.height) } : null;
    return { back, printKept: Boolean(LOOKS.cleaned?.printKept), photo: Boolean(LOOKS.fromPhoto?.[entity.id]?.vorn) && !LOOKS.faceFromModel, map: lookAtlas, tile, size: [lookAtlas.image.width, lookAtlas.image.height],
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

  /** Kleidung einer Figur als Hüllen: aus dem Blatt der Mannschaft, sonst (Torwart, Schiedsrichter, Mannschaft ohne Blatt) einfarbig in den Mannschaftsfarben. Jede Figur trägt Hüllen, auch ohne Videotextur. */
  function outfitOf(entity) {
    return kitFor(entity) ?? { flat: kitOf(entity), variant: LOOKS?.kit?.players?.[entity.id] ?? {} };
  }

  function kitOf(entity) {
    const team = meta.teams[entity.team];
    const shirt = new THREE.Color(team.kit?.shirt ?? team.color);
    return { shirt, shorts: new THREE.Color(team.kit?.shorts ?? shirt.clone().multiplyScalar(0.4)), socks: new THREE.Color(team.kit?.socks ?? team.color) };
  }

  return { loadLooks, lookOf, hairOf, kitOf, outfitOf };
}
