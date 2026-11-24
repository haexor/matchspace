"""Referenz für Ballkontakte einer Szene: vom Menschen bestätigte Kontakte, gegen die die automatische Erkennung gemessen wird.

Die Referenz hängt an der Videozeit (Bild im Szenenvideo), nicht an Spuren der Auswertung: Eine neue Auswertung ändert daran nichts, ein
Wiederfinden wie bei der Personenreferenz (tools/reference.py) ist nicht nötig. Der Spieler ist nur über die Box im Bild gemerkt, nie
über einen Namen. Die Datei enthält keine Bilder und bleibt wie alle Videodaten lokal.

Format (JSON):
  {"version": 1, "scene": "4928_45s", "fps": 29.97,
   "contacts": [{"frame": 790, "kind": "pass", "part": "right-foot", "box": [lens, x1, y1, x2, y2]}],
   "unseen": [[from_frame, to_frame]],         # Ball nicht erkennbar (zählt nicht gegen die Erkennung)
   "flights": [{"from": 93, "to": 117, "apex": 3.2}]}   # nur wo bestätigt; Höhe in Metern
kind: touch (Berührung beim Dribbling), pass, shot, header, loss, win; part: right-foot, left-foot, head, body, other.
"""
import json
from pathlib import Path

VERSION = 1
KINDS = ("touch", "pass", "shot", "header", "loss", "win")
PARTS = ("right-foot", "left-foot", "head", "body", "other")


def new(scene: str, fps: float) -> dict:
    return {"version": VERSION, "scene": scene, "fps": fps, "contacts": [], "unseen": [], "flights": []}


def add_contact(ref: dict, frame: int, kind: str, part: str | None = None, box: list | None = None) -> dict:
    """Kontakt eintragen oder, bei gleichem Bild, ersetzen (der Nutzer korrigiert)."""
    if kind not in KINDS:
        raise ValueError(f"unbekannte Art: {kind}")
    if part is not None and part not in PARTS:
        raise ValueError(f"unbekannter Körperteil: {part}")
    ref["contacts"] = [c for c in ref["contacts"] if c["frame"] != frame]
    ref["contacts"].append({"frame": int(frame), "kind": kind, "part": part, "box": box})
    ref["contacts"].sort(key=lambda c: c["frame"])
    return ref


def remove_contact(ref: dict, frame: int) -> dict:
    ref["contacts"] = [c for c in ref["contacts"] if c["frame"] != frame]
    return ref


def validate(ref: dict) -> list:
    """Probleme der Datei als Liste von Texten (leer = in Ordnung). Keine Namen und Bilder: nur bekannte Schlüssel."""
    bad = []
    if ref.get("version") != VERSION:
        bad.append(f"Version {ref.get('version')} unbekannt")
    allowed = {"version", "scene", "fps", "contacts", "unseen", "flights"}
    bad += [f"unerwarteter Schlüssel: {k}" for k in ref if k not in allowed]
    for c in ref.get("contacts", []):
        extra = set(c) - {"frame", "kind", "part", "box"}
        if extra:
            bad.append(f"Kontakt {c.get('frame')}: unerwartete Schlüssel {sorted(extra)}")
        if c.get("kind") not in KINDS:
            bad.append(f"Kontakt {c.get('frame')}: Art {c.get('kind')}")
        if c.get("part") is not None and c["part"] not in PARTS:
            bad.append(f"Kontakt {c.get('frame')}: Körperteil {c.get('part')}")
    return bad


def save(ref: dict, path) -> None:
    problems = validate(ref)
    if problems:
        raise ValueError("; ".join(problems))
    Path(path).write_text(json.dumps(ref, indent=1, ensure_ascii=False) + "\n")


def load(path) -> dict:
    ref = json.loads(Path(path).read_text())
    problems = validate(ref)
    if problems:
        raise ValueError("; ".join(problems))
    return ref
