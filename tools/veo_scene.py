#!/usr/bin/env python3
"""Macht aus einer kurzen Veo-Szene Positionen und Körperhaltungen für den Viewer.

Ablauf (Erkennung aus tools/veo_detect.py + veo_colors.py, Gelenkpunkte aus tools/veo_keypoints.py), je Stufe ein Modul:
  1. Boxen über die Zeit zu Folgen verketten und den Veo-Spuren zuordnen, also Rückennummern
     vergeben. Verglichen wird am Boden in Metern (Kameramodell aus tools/veo_camera.py).
     Körpergröße aus der Boxhöhe, Ausreißer entfernen, glätten (tools/scene_boxes.py).
  2. Position je Spieler selbst messen: Fußpunkt der Box am Boden, geglättet. Veo liefert nur
     noch die Rückennummer und füllt Lücken (tools/scene_positions.py).
  3. Je Spieler die 2D-Gelenkpunkte seiner Boxen einsammeln (ViTPose).
     Spieler am Boden (gefoult, gestürzt) erkennt die Box: sehr niedrig oder breiter als hoch.
     Der Personendetektor übersieht flach liegende Spieler oft ganz. Deshalb wird dort, wo ein
     Spieler keine Box hat, Veo aber seine Position weiterführt, in einem vergrößerten
     Ausschnitt trotzdem nach Gelenkpunkten gesucht. Die Haltung am Boden (fallen, liegen,
     aufsetzen, aufstehen) wird direkt aus den 2D-Gelenkpunkten als Seitenansicht gelesen
     (tools/scene_keypoints.py).
  4. Haltung: Je Spieler wird die Bewegung gesucht, die im Kamerabild auf den Gelenkpunkten
     liegt und in allem, was das Bild offen lässt (Tiefe, verdeckte Gelenke, Lücken), einer
     natürlichen Bewegung im Takt der sichtbaren Schritte folgt (tools/pose_fit.py).
  5. Grenzen des Körpers (tools/pose_limits.py), Glättung, Boden: Jede Figur hat in jedem
     Bild ein vollständiges, mögliches Skelett. Stehende Füße bleiben an ihrer Stelle
     (tools/scene_poses.py). Schreiben der Szene: tools/scene_output.py.

Grenzen: ein Blickwinkel, Spieler nur rund 55 Pixel hoch. Was quer zur Blickrichtung
geschieht, ist gemessen; die Tiefe der Haltung ist erschlossen. Füße stehen immer auf dem
Boden, Sprünge gehen verloren.

Aufruf:
    .venv/bin/python tools/veo_scene.py VEO_ORDNER KAMERA.json VEO_ALIGN.json VIDEO START_S DETEKTIONEN.json BASIS_SPIEL AUSGABE_SPIEL
Ohne Veo (eigenes Spielertracking aus tools/track_players.py, Rückennummern selbst aus dem Video gelesen): VEO_ORDNER und
VEO_ALIGN.json als "-", optional am Ende --kader KADER.json (erlaubte Nummern je Mannschaft). Vom BASIS_SPIEL werden dann nur Platz, Kulisse, Mannschaften und Uhr übernommen.
Die Teile ohne Veo (Spuren, Ball) stehen in tools/own_scene.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jersey_identity  # noqa: E402
from scene_boxes import observe, smooth_boxes  # noqa: E402
import body_contact  # noqa: E402
from scene_context import load_run  # noqa: E402
from scene_keypoints import fill_gaps, floor_poses, gather_joints  # noqa: E402
from scene_output import write_scene  # noqa: E402
from scene_poses import fit_poses  # noqa: E402
from scene_positions import load_game, measure_positions  # noqa: E402


def main(veo_dir, camera_path, align_path, video, start, det_path, base_dir, out_dir, squad=None):
    run = load_run(veo_dir, camera_path, align_path, video, start, det_path, squad)
    observed = observe(run)
    smooth, heights = smooth_boxes(run, observed)
    run.clock("Boxen zugeordnet")
    joints = gather_joints(run, observed, smooth)
    fill_gaps(run, observed, smooth, heights, joints)
    floor = floor_poses(run, observed, smooth, heights, joints)
    game = load_game(run, observed, base_dir, out_dir)
    measure_positions(run, observed, joints, floor, game)
    result = fit_poses(run, observed, smooth, joints, floor, game)
    touched, biggest = body_contact.keep_apart(game.xy, game.slots)
    if touched:
        print(f"Mindestabstand {body_contact.MIN_DISTANCE} m zwischen Spielern: in {touched} Bildern auseinandergeschoben (höchstens {biggest:.2f} m)", flush=True)
    write_scene(run, game, result)


if __name__ == "__main__":
    args = sys.argv[1:]
    squad = None
    if "--kader" in args:   # optional: Nummern, die die Mannschaften tragen (nur ohne Veo)
        i = args.index("--kader")
        try:
            squad = jersey_identity.load_squad(args[i + 1])
        except (IndexError, jersey_identity.SquadError) as err:
            sys.exit(f"Kader: {err}")
        del args[i:i + 2]
    if len(args) != 8:
        sys.exit(__doc__)
    main(*args, squad=squad)
