# Quickstart: Eigene Referenz prüfen

**Feature**: [spec.md](spec.md) | **Schnittstellen**: [contracts/](contracts/)

Voraussetzungen wie in Feature 002 (Szenenvideo, Erkennungen, Gelenkpunkte, Kamera, Nummernleser, DINOv2). Aus
`$V` werden nur das Panoramavideo (die Aufnahme selbst) und die Linsendaten der Kamera gelesen, außer bei `--veo`.

```sh
W=data/work/veo-2026-11-01
V=data/raw/veo/2026-11-01        # nur für die zweite Meinung und den Vergleich
```

## 0. Einheitstests

```sh
.venv/bin/python -m unittest discover -s tests
```

## 1. Eigener Spielordner und Kamera ohne Veo

```sh
.venv/bin/python tools/veo_camera.py $V/panorama_600_900.mp4 $W/landmarks.json $V/camera_alignment.json $W/camera-eigen.json
.venv/bin/python tools/own_match.py $W/spiel.json $W/camera-eigen.json web/data/spiel-2026-11-01
.venv/bin/python tools/veo_ground.py $W/camera.json $V/panorama_600_900.mp4 web/data/spiel-2026-11-01
.venv/bin/python tools/veo_backdrop.py $W/camera.json $W/background.png web/data/spiel-2026-11-01
```

**Erwartet**: Die Kamera liegt höchstens 0,1 m und 0,1° neben `camera.json`, bei gleichem Linienfehler. Der
Spielordner enthält `meta.json`, `ground.jpg` und die Kulissenbilder, aber keine Bewegungsdaten.

## 2. Szenen ohne Veo auswerten, mit Nachweis

```sh
for S in 705 722; do
  .venv/bin/python tools/no_veo_check.py --verbiete web/data/veo-2026-11-01 tools/veo_scene.py - $W/camera.json - $W/scene_$S.mp4 $S \
       $W/scene_$S.det.json web/data/spiel-2026-11-01 web/data/veo-szene-$S-eigen
done
```

**Erwartet**:
- Kein Abbruch durch den Audit-Hook, also wurde nichts von Veo gelesen.
- `tracks.bin` hat dieselbe Prüfsumme wie beim Lauf mit dem Veo-Basisspiel.
- Die Uhr in `meta.json` stimmt überein.
- `$W/scene_$S.det.json.identity.json` ist geschrieben.

## 3. Strittige Stellen erzeugen und entscheiden

```sh
.venv/bin/python tools/review_spots.py $W/scene_705.det.json $W/camera.json --veo $V $W/veo_align.json 705
.venv/bin/python tools/review_server.py $W/scene_705.mp4 $W/scene_705.det.json
# Browser: http://127.0.0.1:8766/
```

**Erwartet**:
- 30–50 Stellen; jede spielt als Ausschnitt mit Buchstaben an den Beteiligten.
- `Enter` bestätigt.
- Nach einem Neustart des Servers sind alle Antworten da.
- Zeit stoppen (SC-001: höchstens 10 Minuten).
- Danach 5 Stellen ein zweites Mal entscheiden (Wiederholung, SC-004).

## 4. Messen

```sh
.venv/bin/python tools/jersey_eval.py $W/scene_705.det.json $W/camera.json --bericht $W/scene_705.reference-report.json
.venv/bin/python tools/jersey_eval.py $W/scene_705.det.json $W/camera.json --veo $V $W/veo_align.json 705 \
     --bericht $W/scene_705.reference-report-veo.json
```

**Erwartet**:
- Beide Berichte haben dieselben Werte unter `own`; nur der zweite hat `veo` mit Widerspruchsliste.
- `reference.open` ist 0, `unclear` höchstens 15 %.

## 5. Lage an Platzlinien

```sh
.venv/bin/python tools/line_check.py $W/scene_705.mp4 $W/scene_705.det.json $W/camera.json web/data/veo-szene-705-eigen \
     --veo $V $W/veo_align.json 705 --bericht $W/scene_705.lines.json
```

**Erwartet**:
- Mindestens 20 Linienstellen, Median und Streuung des Tiefenfehlers je Quelle.
- Die Aussage, ob die fertige Szene oder Veo den Versatz von 0,9 m trägt.

## 6. Datenschutz

```sh
git status --short                  # keine neuen Dateien unter data/ oder web/data/ eingecheckt
.venv/bin/python -c "import json; r=json.load(open('$W/scene_705.det.json.reference.json')); print(sorted(r))"
```

**Erwartet**: Die Referenz enthält nur `scene`, `identityStamp`, `spots`, `answers` und `seed`, keine Bilddaten.
