#!/usr/bin/env python3
"""Ein Befehl für eine Szene: beste Videobilder je Spieler heraussuchen, mit der Bild-KI scharfe Rück-/Vorderansichten erzeugen, auf die Avatare legen.

Schritte (jeder einzeln mit seinem Werkzeug aufrufbar):
  1. tools/photo_candidates.py   Ausschnitte je Spieler und Ansicht   -> ARBEIT/kandidaten
     tools/team_text.py + team_detect.py   Mannschaftsfarben und Rückenschrift selbst erkennen -> ARBEIT/teams.json
  2. tools/photo_ai.py           Bild-KI (bezahlt, mit Zwischenspeicher, Kostengrenze) -> ARBEIT/ki
  3. tools/looks_from_photo.py   Ansichten auf die Avatare legen      -> AUSGABESZENE

Aufruf:
    .venv/bin/python tools/looks_ki.py VIDEO DETEKTIONEN.json KAMERA.json HINTERGRUND.png SZENENORDNER NETZ.pkl --arbeit ORDNER --ausgabe AUSGABESZENE
        [--teams TEAMS.json] [--ansichten hinten,vorn] [--modell M] [--ersatz M] [--max-kosten 3.0] [--trocken]
--trocken: Ausschnitte wählen und die Kosten ausgeben, kein Aufruf der KI, keine Ausgabeszene.
SZENENORDNER: Szene mit bereinigter Videotextur (looks.png, 4-fach; tools/looks_clean.py --aufdruck-behalten).
Mannschaftsdaten (Farben, lange Ärmel, Rückenschrift) erkennt tools/team_detect.py selbst und legt sie in ARBEIT/teams.json ab; wer korrigieren will, ändert diese Datei
(sie wird nicht überschrieben, außer mit --neu) oder gibt mit --teams eine eigene an.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import looks_from_photo  # noqa: E402
import photo_ai  # noqa: E402
import photo_candidates  # noqa: E402
import team_detect  # noqa: E402
import team_text  # noqa: E402


def main(a):
    work = Path(a.arbeit)
    cands = work / "kandidaten"
    if a.neu or not (cands / "index.json").exists():
        photo_candidates.main(a.video, a.detektionen, a.kamera, a.hintergrund, a.szenenordner, str(cands), set(), a.min_hoehe, a.min_frontal)
    # Ein Trockenlauf darf keine Modellaufrufe auslösen und soll eine spätere
    # reguläre Erkennung nicht mit den unvollständigen Planungsdaten blockieren.
    teams = Path(a.teams) if a.teams else work / ("teams.plan.json" if a.trocken else "teams.json")
    if not a.teams and (a.neu or not teams.exists()):
        team_text.main([(a.video, a.detektionen, a.kamera, a.hintergrund, a.szenenordner)], str(work / "team-text"), 40)
        team_detect.main(a.szenenordner, str(teams), str(work / "team-text"), str(cands), not a.trocken, infer=not a.trocken)
    ai = argparse.Namespace(kandidaten=str(cands), teams=str(teams), ausgabe=str(work / "ki"), ansichten=a.ansichten, spieler=None,
                            modell=a.modell, ersatz=a.ersatz, max_kosten=a.max_kosten, trocken=a.trocken)
    photo_ai.cmd_lauf(ai)
    if a.trocken:
        return
    looks_from_photo.all_players(a.szenenordner, work / "ki", a.netz, a.ausgabe)
    print(f"Fertig: {a.ausgabe} (Viewer: spieler.html?match={Path(a.ausgabe).name}&player=SPIELER)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("video", "detektionen", "kamera", "hintergrund", "szenenordner", "netz"):
        ap.add_argument(name)
    ap.add_argument("--teams", help="eigene Mannschaftsdaten statt der erkannten")
    ap.add_argument("--arbeit", required=True)
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--ansichten", default=",".join(photo_ai.VIEWS))
    ap.add_argument("--modell", default=photo_ai.MODEL)
    ap.add_argument("--ersatz", default=photo_ai.FALLBACK)
    ap.add_argument("--max-kosten", type=float, default=photo_ai.MAX_COST, dest="max_kosten")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--min-hoehe", type=int, default=36, dest="min_hoehe", help="kleinste Spielerhöhe (Pixel) für einen Ausschnitt")
    ap.add_argument("--min-frontal", type=float, default=0.7, dest="min_frontal", help="kleinste Frontalität (cos) des Rumpfs zur gewünschten Seite")
    ap.add_argument("--neu", action="store_true", help="Ausschnitte neu wählen, auch wenn schon vorhanden")
    main(ap.parse_args())
