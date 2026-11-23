# Quickstart: Identität je Spieler prüfen

**Feature**: [spec.md](spec.md) | **Schnittstellen**: [contracts/](contracts/)

Voraussetzungen wie in `specs/001-rueckennummern/quickstart.md`: Szenenvideo, Detektionen, Gelenkpunkte,
Kamera, Nummernleser. Dazu DINOv2-small lokal unter `models/hf`; das Modell wird einmal heruntergeladen,
Bilder werden dabei nicht übertragen.

```sh
V=data/raw/veo/2026-11-01   # nur für die Messung
W=data/work/veo-2026-11-01
```

## 0. Einheitstests

```sh
.venv/bin/python -m unittest discover -s tests
```

## 1. Wechsel und Verbindungen einer Szene ansehen

```sh
.venv/bin/python tools/identity_link.py $W/scene_705.mp4 $W/scene_705.det.json $W/camera.json
```

**Erwartet**: Die Ausgabe listet Kontakte mit Belegen (Bewegung, Nummer, Aussehen), Trennungen und
Verbindungen mit Kosten und Abstand zum Zweitbesten. Bei unklaren Fällen steht „getrennt gelassen“.

## 2. Szenen auswerten und messen

```sh
for S in 705 722; do
  time .venv/bin/python tools/veo_scene.py - $W/camera.json - $W/scene_$S.mp4 $S $W/scene_$S.det.json \
       web/data/veo-2026-11-01 web/data/veo-szene-$S-eigen
  .venv/bin/python tools/veo_looks.py $W/scene_$S.mp4 $W/scene_$S.det.json $W/camera.json $W/background.png \
       web/data/veo-szene-$S-eigen
  .venv/bin/python tools/jersey_eval.py web/data/veo-szene-$S-eigen $W/scene_$S.det.json $W/camera.json $V \
       $W/veo_align.json $S --bericht $W/scene_$S.identity-report.json
done
```

**Erwartet** je Szene:

| Ziel | Wert | vor dem Feature (705 / 722) | danach |
|------|------|-------|-------|
| SC-001 Identitäten je Spieler | ≤ 1,5 | 2,22 / 2,11 | 2,22 / 2,22 |
| SC-002 falsch zugeordnete Zeit | ≤ 3 % | 6,9 % / 5,7 % | 5,8 % / 2,9 % |
| SC-003 Spieler mit richtiger Nummer | ≥ 7, falsch ≤ 5 % | 7, 0 falsch | 7, 0 falsch |
| SC-005 Mehrzeit | ≤ 5 min | | rund 30 s, beim ersten Lauf dazu 55 s |

Die Messung rechnet einen festen Tiefenversatz der Szene zu Veo heraus (`depthOffsetM`, rund 0,9 m).

Dazu muss `meta.json` vor und nach der Messung dieselbe Prüfsumme haben.

## 3. Viewer-Stichproben (SC-004)

Je Szene 10 frühere Bruchstellen aus der Ausgabe von Schritt 1 wählen und dem Spieler folgen:

```sh
cd web && python3 -m http.server 8765
# http://localhost:8765/?match=veo-szene-705-eigen&player=own-15&mode=follow&t=…
```

**Erwartet**: In mindestens 8 von 10 Fällen bleibt die Kamera beim richtigen Spieler. Gegengeprüft wird am
Video, nicht an Veo allein.

## 4. Keine neuen Bilddaten (SC-006)

```sh
git status --short web/   # keine neuen Dateien
ls web/data/veo-szene-705-eigen/   # wie vorher: meta.json, tracks.bin, poses/, looks.png, Kulisse
```
