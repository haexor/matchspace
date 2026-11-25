#!/usr/bin/env python3
"""Bild vom Viewer (web/) mit WebGL, ohne Fenster: zum Prüfen von Szenen, Texturen und Haltung, wo kein Bildschirm da ist.

Startet einen kleinen Webserver für web/, öffnet den Viewer in einem Chromium über Playwright, wartet, bis die Szene geladen ist, und speichert ein Bild.

Browser und Grafik:
  - Im Nix-devShell (Atom com.github.haexmas.atoms.nix-playwright) setzt die Shell PLAYWRIGHT_BROWSERS_PATH auf die Browser des gepinnten nixpkgs und
    PLAYWRIGHT_GL_* auf Mesa (llvmpipe, Software-WebGL). Die Pfade gehen nur an den Browser-Prozess, nicht an die Shell.
  - Ohne diese Variablen (ohne devShell) nimmt Playwright seinen eigenen Browser und die Grafik des Rechners.
  - Der Playwright-Client muss zu den Browsern passen: pip install playwright==<playwright-driver.version> (siehe README des Atoms).

Aufruf:
    python tools/viewer_shot.py SZENE AUSGABE.png [--zeit 3.2] [--spieler own-6] [--modus follow|free|fp] [--zoom 0] [--ohne-ui]
                                [--breite 1200] [--hoehe 800] [--original]
SZENE ist der Ordner unter web/data/ (zum Beispiel veo-szene-nah-eigen). Das Original-Video unter der Szene bleibt aus, außer mit --original.
"""
import argparse
import functools
import http.server
import os
import threading
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
LOADING = "document.getElementById('status').textContent.indexOf('Lade') !== 0"
GL_ARGS = ["--use-angle=gl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox"]


def browser_options(environ):
    """(Startargumente, Umgebung) für den Browser-Prozess. Mit PLAYWRIGHT_GL_* (Nix-devShell) bekommt nur dieser Prozess Mesas Bibliotheken und den
    Software-Renderer; ohne sie bleibt die Umgebung unverändert und der Rechner stellt die Grafik."""
    env = dict(environ)
    if environ.get("PLAYWRIGHT_GL_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = environ["PLAYWRIGHT_GL_LIBRARY_PATH"]
        env["__EGL_VENDOR_LIBRARY_FILENAMES"] = environ.get("PLAYWRIGHT_GL_EGL_VENDOR", "")
        env["LIBGL_DRIVERS_PATH"] = environ.get("PLAYWRIGHT_GL_DRIVERS", "")
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return list(GL_ARGS), env


def viewer_url(port, scene, time, player, mode, ui, original):
    query = [f"match={scene}"]
    if time is not None:
        query.append(f"t={time}")
    if player:
        query.append(f"player={player}")
    if mode:
        query.append(f"mode={mode}")
    if not ui:
        query.append("ui=0")
    if not original:
        query.append("ref=0")
    return f"http://127.0.0.1:{port}/?" + "&".join(query)


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szene")
    ap.add_argument("ausgabe")
    ap.add_argument("--zeit", type=float)
    ap.add_argument("--spieler")
    ap.add_argument("--modus", choices=["free", "follow", "fp"])
    ap.add_argument("--zoom", type=int, default=0, help="Mausrad-Schritte nach vorn")
    ap.add_argument("--ohne-ui", action="store_true")
    ap.add_argument("--original", action="store_true")
    ap.add_argument("--breite", type=int, default=1200)
    ap.add_argument("--hoehe", type=int, default=800)
    ap.add_argument("--warten", type=float, default=3.0, help="Sekunden nach dem Laden bis zum Bild")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    server = serve(WEB)
    args, env = browser_options(os.environ)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=args, env=env)
        page = browser.new_page(viewport={"width": a.breite, "height": a.hoehe})
        page.on("console", lambda m: problems.append(f"{m.type}: {m.text[:200]}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"Seitenfehler: {str(e)[:300]}"))
        page.goto(viewer_url(server.server_address[1], a.szene, a.zeit, a.spieler, a.modus, not a.ohne_ui, a.original))
        try:
            page.wait_for_function(LOADING, timeout=120000)
        except Exception as err:   # noqa: BLE001 - Zeitüberschreitung ist hier eine Meldung, kein Abbruch
            problems.append(f"Szene nicht geladen: {str(err)[:120]}")
        page.wait_for_timeout(int(a.warten * 1000))
        if a.zoom:
            page.mouse.move(a.breite / 2, a.hoehe / 2)
            for _ in range(a.zoom):
                page.mouse.wheel(0, -300)
                page.wait_for_timeout(120)
            page.wait_for_timeout(1500)
        page.screenshot(path=a.ausgabe)
        browser.close()
    server.shutdown()
    print(f"-> {a.ausgabe}")
    for line in problems[:10]:
        print(line)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
