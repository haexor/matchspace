#!/usr/bin/env python3
"""Prüflauf „ohne Veo“: führt ein Werkzeug aus und bricht ab, sobald es Veo-Daten öffnet.

Ein Python-Audit-Hook (sys.addaudithook) prüft jedes Öffnen von Dateien und Ordnern. Verboten sind data/raw/veo/
und die mit --verbiete angegebenen Ordner (etwa das Veo-Basisspiel). Einzelne Dateien der Aufnahme selbst lassen
sich mit --erlaube freigeben. Ordner, die nur im Namen „veo“ tragen (Szenenausgaben), sind nicht betroffen.
Grenze: Was Bibliotheken in C öffnen (etwa OpenCV ein Video), sieht der Hook nicht; deshalb werden auch die
Argumente des Werkzeugs geprüft.

Aufruf:
    .venv/bin/python tools/no_veo_check.py [--verbiete ORDNER …] [--erlaube DATEI …] WERKZEUG.py [ARGUMENTE …]
"""
import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT = [REPO / "data" / "raw" / "veo"]


class VeoAccess(PermissionError):
    """Ein Werkzeug hat im Betrieb ohne Veo Veo-Daten geöffnet."""


def parse(argv: list[str]) -> tuple[list[Path], set[Path], list[str]]:
    forbidden, allowed = list(DEFAULT), set()
    while argv and argv[0] in ("--verbiete", "--erlaube"):
        flag, value, argv = argv[0], argv[1], argv[2:]
        (forbidden.append if flag == "--verbiete" else allowed.add)(Path(value).resolve())
    if not argv:
        raise SystemExit(__doc__)
    return forbidden, allowed, argv


def blocked(path, forbidden: list[Path], allowed: set[Path]) -> bool:
    try:
        p = Path(os.fsdecode(path)).resolve()
    except (TypeError, ValueError):
        return False
    if p in allowed:
        return False
    return any(p == f or f in p.parents for f in forbidden)


def main() -> None:
    forbidden, allowed, argv = parse(sys.argv[1:])
    for arg in argv[1:]:
        if blocked(arg, forbidden, allowed):
            raise VeoAccess(f"Veo-Daten als Argument: {arg}")

    def hook(event, args):
        if event in ("open", "os.listdir", "os.scandir") and args and isinstance(args[0], (str, bytes, os.PathLike)):
            if blocked(args[0], forbidden, allowed):
                raise VeoAccess(f"Zugriff auf Veo-Daten im Betrieb ohne Veo: {os.fsdecode(args[0])}")
    sys.addaudithook(hook)
    sys.argv = argv
    sys.path.insert(0, str(Path(argv[0]).resolve().parent))
    runpy.run_path(argv[0], run_name="__main__")
    print("Prüflauf ohne Veo: keine Veo-Datei geöffnet", file=sys.stderr)


if __name__ == "__main__":
    main()
