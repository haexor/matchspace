#!/usr/bin/env python3
"""Liest aus dem Viewer das echte Körpernetz der Figuren aus: das Netz in der Grundhaltung (einmal) und je Bild die Knochenmatrizen jeder Figur.

Warum: tools/veo_looks.py legt die Videobilder bisher auf einen vereinfachten Körper (elliptische Zylinder) und der Viewer zeigt die Textur auf einem
anderen (dem Avatar-Netz). Jede Abweichung der beiden Körper verzerrt den Aufdruck. Mit den Knochenmatrizen aus dem Viewer rechnet tools/avatar_mesh.py
das Netz in jedem Bild genau so, wie der Viewer es zeichnet, und veo_looks.py nimmt die Farben von dieser Oberfläche.

Aufruf:
    .venv/bin/python tools/avatar_bake.py SZENE AUSGABE.pkl [--von 0] [--bis N]
SZENE ist der Ordner unter web/data/ (zum Beispiel veo-szene-nah-eigen).
"""
import argparse
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import viewer_shot  # noqa: E402

STATIC = """() => {
  const { avatars } = window.__bake;
  const [first] = [...avatars.values()];
  let body = null;
  first.root.traverse((o) => { if (o.isSkinnedMesh && !o.name.startsWith('Hair_') && !o.name.startsWith('Eyebrows') && !o.name.startsWith('Eyes') && o.geometry.attributes.position.count > 4000) body = o; });
  const g = body.geometry, a = g.attributes;
  return { position: Array.from(a.position.array), normal: Array.from(a.normal.array), skinIndex: Array.from(a.skinIndex.array), skinWeight: Array.from(a.skinWeight.array),
           look: Array.from(a.look.array), wear: a.wear ? Array.from(a.wear.array) : null, index: Array.from(g.index.array), bones: body.skeleton.bones.map((b) => b.name),
           boneInverses: body.skeleton.boneInverses.flatMap((m) => Array.from(m.elements)), bind: Array.from(body.bindMatrix.elements) };
}"""

FRAME = """async (f) => {
  const { avatars, ENTITIES, setTime } = window.__bake;
  setTime(f);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const out = {};
  for (const [i, av] of avatars) {
    if (!av.root.visible) continue;
    let body = null;
    av.root.traverse((o) => { if (o.isSkinnedMesh && !o.name.startsWith('Hair_') && !o.name.startsWith('Eyebrows') && !o.name.startsWith('Eyes') && o.geometry.attributes.position.count > 4000) body = o; });
    av.root.updateMatrixWorld(true);
    body.skeleton.update();
    out[ENTITIES[i].id] = { mw: Array.from(body.matrixWorld.elements), bind: Array.from(body.bindMatrix.elements), bindInv: Array.from(body.bindMatrixInverse.elements),
                            bones: Array.from(body.skeleton.boneMatrices) };
  }
  return out;
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szene")
    ap.add_argument("ausgabe")
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--bis", type=int, default=None)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    server = viewer_shot.serve(viewer_shot.WEB)
    args, env = viewer_shot.browser_options(os.environ)
    began = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=args, env=env)
        page = browser.new_page(viewport={"width": 640, "height": 400})
        page.on("pageerror", lambda e: print("Seitenfehler:", str(e)[:200]))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/?match={a.szene}&ui=0&ref=0&bake=1&mode=free&t={a.von / 25}")
        page.wait_for_function(viewer_shot.LOADING, timeout=120000)
        page.wait_for_function("window.__bake && window.__bake.avatars.size > 0", timeout=120000)
        page.wait_for_timeout(2000)
        static = page.evaluate(STATIC)
        fps = page.evaluate("document.getElementById('seek').max")
        last = int(fps) if a.bis is None else a.bis
        frames = {}
        for f in range(a.von, last + 1):
            frames[f] = page.evaluate(FRAME, f)
            if f % 50 == 0:
                print(f"  Bild {f}: {len(frames[f])} Figuren [{time.time() - began:.0f} s]", flush=True)
        browser.close()
    server.shutdown()
    pickle.dump({"static": {k: np.array(v) if k != "bones" else v for k, v in static.items()},
                 "frames": {f: {k: {m: np.array(x, np.float64) for m, x in d.items()} for k, d in fr.items()} for f, fr in frames.items()}},
                open(a.ausgabe, "wb"), protocol=4)
    print(f"-> {a.ausgabe} ({len(frames)} Bilder), {time.time() - began:.0f} s")


if __name__ == "__main__":
    main()
