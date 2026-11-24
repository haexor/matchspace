"""Ausgabe der Szene (Ende von tools/veo_scene.py): Bahnen, Haltungen, 2D-Gelenkpunkte, Bilder des Platzes, meta.json und Bericht."""
import json
import math
import shutil
import sys
from array import array
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import check_motion  # noqa: E402
from own_scene import BALL_REACH, attach_ball  # noqa: E402
from scene_poses import CHUNK_FRAMES, MISSING, POSE_SCALE, SEEN_SHARE  # noqa: E402
from scene_positions import OUT_FPS  # noqa: E402
from synth_poses import BONES, JOINTS, NAMES  # noqa: E402


CONTACT_PULL = 3   # Bilder vor und nach einem Kontakt, in denen der Ball an den Fuß gezogen wird


def write_scene(run, game, result) -> None:
    """Schreibt tracks.bin, poses/, meta.json und die Bilder des Platzes nach game.out_dir, die 2D-Gelenkpunkte je Spieler
    (für tools/veo_looks.py, bleiben lokal bei den Rohdaten) neben die Erkennungen, und gibt den Bericht aus."""
    base, base_dir, out_dir, xy, total, tscale = game.base, game.base_dir, game.out_dir, game.xy, game.total, game.tscale
    slots, ball, ball_source, det_path = game.slots, game.ball, game.ball_source, run.det_path
    E = len(base["entities"])
    J = len(JOINTS)
    run.clock("Haltungen")
    track = game.ball_track
    if ball is not None and result.toes:
        active = None
        if track is not None:   # mit erkannten Kontakten nur rund um diese an den Fuß ziehen, dazwischen gilt die Bahn der Physik
            active = np.zeros(total, bool)
            for c in track.contacts:
                active[max(0, c - CONTACT_PULL):c + CONTACT_PULL + 1] = True
        xy[:, ball] = attach_ball(xy[:, ball], np.stack(result.toes, axis=1), OUT_FPS, active)
    print(f"Ball aus {ball_source}; an den Fuß gezogen, wo er in {BALL_REACH} m Reichweite einer Fußspitze lag"
          + (f", nur rund um {len(track.contacts)} erkannte Kontakte; Höhe aus der Wurfparabel in {int(track.flight.sum())} Bildern" if track is not None else ""))
    # 2D-Gelenkpunkte je Spieler im Takt der Ausgabe, für tools/veo_looks.py (bleibt lokal bei den Rohdaten)
    np.savez_compressed(f"{det_path}.players{'_own' if run.no_veo else ''}.npz",
                        **{f"{k}.{part}": v for k, view in result.views.items() for part, v in view.items()})
    flat = np.array(game.data, np.int64).reshape(total, E, 3)
    flat[:, :, :2] = np.where(np.isnan(xy), base["tracks"]["missing"], np.round(xy / tscale))
    if ball_source == "Video":   # ohne Physik (kein .ball3d.npz): am Boden
        flat[:, ball, 2] = 0 if track is None else np.round(track.z / tscale)
    with open(out_dir / "tracks.bin", "wb") as f:
        array("h", flat.ravel().tolist()).tofile(f)

    pose_dir = out_dir / "poses"
    pose_dir.mkdir(exist_ok=True)
    per_chunk = CHUNK_FRAMES * len(slots) * J * 3
    chunks = math.ceil(total / CHUNK_FRAMES)
    for c in range(chunks):
        with open(pose_dir / f"{c:03d}.bin", "wb") as f:
            result.buf[c * per_chunk:(c + 1) * per_chunk].tofile(f)
    # Bilder des Platzes (Luftbild, Kulisse) aus dem Basisspiel mitnehmen
    pitch = base["pitch"]
    for name in [pitch.get("texture", {}).get("file")] + [w.get("file") for w in pitch.get("backdrop", {}).get("walls", [])]:
        if name and (base_dir / name).exists():
            shutil.copyfile(base_dir / name, out_dir / name)

    meta = dict(base)
    meta.update({
        "frames": total,
        "periods": [{"id": game.period["id"], "startFrame": 0, "endFrame": total - 1, "clockStartS": game.clock_start}],
        "source": {"name": f"{base['source']['name']}, Szene ab Videosekunde {run.start:.0f}",
                   "notes": ("Positionen und Spuren aus dem Panorama gemessen (eigenes Tracking, ohne Veo), Rückennummern selbst aus dem Video gelesen (tools/jersey_reader.py), unlesbare bleiben unbekannt. " if run.no_veo else
                             "Positionen aus dem Panorama gemessen (Fußpunkt am Boden), Rückennummern und Lücken aus Veo. ") +
                            "Körperhaltung im Kamerabild an die erkannten Gelenkpunkte angepasst (ein Blickwinkel); "
                            "Tiefe, verdeckte Gelenke und Lücken folgen einer natürlichen Bewegung im Takt der Schritte."},
        "poses": {
            "synthetic": False,
            "estimatedShare": round(result.estimated / max(1, result.present_total), 3),
            "source": "2D-Gelenkpunkte (ViTPose) je Spieler, daran angepasstes Skelett (tools/pose_fit.py) mit natürlicher "
                      "Bewegung als Vorlage (tools/motion_clips.py), begrenzt durch tools/pose_limits.py. "
                      "Tiefe erschlossen, Füße auf den Boden gesetzt.",
            "path": "poses/{chunk}.bin", "chunkFrames": CHUNK_FRAMES, "chunks": chunks, "dtype": "int16le",
            "layout": "frame, player, joint, [x, y, z]", "relativeTo": "track", "scale": POSE_SCALE, "missing": MISSING,
            "skeleton": {"joints": [{"name": a, "radius": r, "part": part} for a, r, part in JOINTS],
                         "bones": [{"from": NAMES.index(a), "to": NAMES.index(b), "radius": r, "part": part} for a, b, r, part in BONES]},
        },
    })
    old_meta = out_dir / "meta.json"
    if old_meta.exists() and (out_dir / "looks.png").exists():   # Videotexturen der Spieler (tools/veo_looks.py) behalten
        looks = json.loads(old_meta.read_text()).get("looks")
        if looks:
            meta["looks"] = looks
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    report(result, total, out_dir)


def report(result, total: int, out_dir: Path) -> None:
    """Zusammenfassung der Rechnung und Prüfung auf unmögliche Bewegungen (tools/check_motion.py)."""
    share = result.estimated / max(1, result.present_total)
    print(f"{total} Frames ({total / OUT_FPS:.0f} s). Jede Figur hat in jedem Bild ein Skelett; in {share:.0%} "
          f"aller Spieler-Bilder sind mindestens {SEEN_SHARE:.0%} der Gelenke im Video erkannt, der Rest folgt der natürlichen Bewegung.")
    print("Anteil je Spieler:", dict(sorted(result.summary.items(), key=lambda kv: -kv[1])))
    if result.errors:
        print(f"Abweichung Skelett zu Gelenkpunkten im Bild: im Mittel {np.mean(result.errors):.1f} Pixel (schlechtester Spieler {np.max(result.errors):.1f}); "
              f"rückwärts laufend erkannt: {result.backward_frames} Spieler-Bilder")
    print("Eingriffe der harten Gelenkgrenzen nach der Anpassung (Bilder, Summe über Spieler und Körperseiten):", dict(result.stats))
    print(f"Fallen, Liegen und Aufstehen aus Vorlagen dargestellt: {result.grounded} Spieler-Bilder")
    print(f"Fußstellung (Ferse, Zehe) aus dem Bild gesetzt: {result.feet_from_video} Fuß-Bilder")
    print(f"Stehende Füße rutschten im Mittel mit {result.slip_before / max(1, result.slip_frames):.2f} m/s über den Rasen, "
          f"nach dem Festhalten mit {result.slip_after / max(1, result.slip_frames):.2f} m/s ({result.slip_frames} Fuß-Bilder mit Bodenkontakt)")
    print(f"-> {out_dir}")
    print("Prüfung auf unmögliche Bewegungen (tools/check_motion.py):")
    check_motion.report(check_motion.check(out_dir))
