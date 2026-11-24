"""Eingaben und Uhr einer Szenenrechnung (tools/veo_scene.py), damit die Stufen nicht je zehn Einzelwerte tragen müssen."""
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
import veo_tracks  # noqa: E402


@dataclass
class Run:
    """Was jede Stufe der Szenenrechnung über die Szene wissen muss. tracks und align gibt es nur mit Veo (no_veo falsch)."""
    cam: dict
    no_veo: bool            # ohne Veo: eigenes Spielertracking
    tracks: dict | None
    align: dict | None
    det: dict
    video: str
    det_path: str
    camera_path: str
    align_path: str
    start: float            # Videosekunde, ab der die Szene beginnt
    squad: object           # erlaubte Nummern je Mannschaft (nur ohne Veo) oder None
    began: float

    @property
    def frames(self) -> list:
        return self.det["frames"]

    @property
    def fps(self) -> float:
        return self.det["fps"]

    @property
    def n(self) -> int:
        return len(self.det["frames"])

    @property
    def size(self) -> list:
        return self.cam["lensSize"]

    @property
    def length(self) -> float:
        return self.cam["pitch"]["length"]

    @property
    def width(self) -> float:
        return self.cam["pitch"]["width"]

    @property
    def cam_pos(self) -> list:
        return self.cam["position"]

    def clock(self, label: str) -> None:
        print(f"  [{time.time() - self.began:.0f} s] {label}", flush=True)


def load_run(veo_dir, camera_path, align_path, video, start, det_path, squad=None) -> Run:
    """Liest Kamera, Erkennungen und (mit Veo) die Veo-Spuren."""
    began = time.time()
    cam = veo_camera.load(camera_path)
    no_veo = align_path == "-"
    align = tracks = None
    if not no_veo:
        align = json.loads(Path(align_path).read_text())
        tracks = veo_tracks.build_tracks(veo_tracks.load_export(veo_dir), align["H"])
    det = json.loads(Path(det_path).read_text())
    return Run(cam, no_veo, tracks, align, det, video, det_path, camera_path, align_path, float(start), squad, began)
