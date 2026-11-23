# Quickstart: Rückennummern prüfen

**Feature**: [spec.md](spec.md) | **Schnittstellen**: [contracts/](contracts/)

Prüft das Feature Ende zu Ende an den beiden Referenzszenen. Voraussetzung sind die Zwischenstände aus dem
README (Schritt 5): Szenenvideo, Detektionen mit Farben, Gelenkpunkte, Kamera. Alles liegt lokal unter
`data/work/` und `data/raw/` und ist nicht eingecheckt.

```sh
V=data/raw/veo/2026-11-01   # Veo-Rohdaten, nur für die Messung
W=data/work/veo-2026-11-01
```

## 0. Einheitstests

```sh
.venv/bin/python -m unittest discover -s tests
```

**Erwartet**: Alle Tests grün. Geprüft werden:
- Abstimmung und Vergabe ohne doppelte Nummer, Zusammenführen, Kaderfilter;
- Schiedsrichter ohne Nummer;
- Rücken-Erkennung aus Gelenkpunkten;
- synthetische Ausschnitte;
- Zählen in der Messung.

## 1. Erkenner trainieren (einmalig)

```sh
.venv/bin/python tools/jersey_reader.py train --negatives $W/scene_705.det.json $W/scene_722.det.json
```

**Erwartet**:
- `models/jersey-digits.pt` entsteht.
- Die Trefferquote auf dem zurückgehaltenen synthetischen Satz wird ausgegeben (zum Vergleich zwischen
  Läufen; der Satz enthält absichtlich viele kaum lesbare Beispiele).
- Während des Trainings geht keine Verbindung nach außen. Dafür optional ohne Netz laufen lassen, etwa mit
  `unshare -n`.

## 2. Szenen ohne Veo auswerten

```sh
for S in 705 722; do
  time .venv/bin/python tools/veo_scene.py - $W/camera.json - $W/scene_$S.mp4 $S $W/scene_$S.det.json \
       web/data/veo-2026-11-01 web/data/veo-szene-$S-eigen
  .venv/bin/python tools/veo_looks.py $W/scene_$S.mp4 $W/scene_$S.det.json $W/camera.json $W/background.png \
       web/data/veo-szene-$S-eigen
done
```

**Erwartet**:
- **Rechenzeit**: Je Szene höchstens 5 Minuten mehr als vor dem Feature. Vergleichswert ist die
  `real`-Zeit von `git stash`/main; die Konsole nennt die Zeit für das Lesen gesondert (SC-005).
- **Zwischenspeicher**: `$W/scene_$S.det.json.numbers.npz` entsteht.
- **Keine Bilder in den Viewer-Daten** (SC-006, FR-009):
  - `grep -c '"number"' web/data/veo-szene-$S-eigen/meta.json` zeigt Spieler mit Nummer.
  - In `web/data/veo-szene-$S-eigen/` liegen keine neuen Bilddateien außer den bekannten (`looks.png`,
    Kulisse, Boden).

## 3. Messen gegen Veo (Referenz, ändert nichts)

```sh
for S in 705 722; do
  .venv/bin/python tools/jersey_eval.py web/data/veo-szene-$S-eigen $W/scene_$S.det.json $W/camera.json $V $W/veo_align.json $S \
       --bericht $W/scene_$S.numbers-report.json
done
```

**Erwartet** je Szene (siehe [contracts/eval-report.md](contracts/eval-report.md)):

| Ziel | Wert |
|------|------|
| SC-001 richtig | `correct / visible` ≥ 0,80 je Szene, beide Mannschaften zusammen |
| SC-002 falsch | `wrong / Spieler` ≤ 0,05 |
| SC-003 | `identitiesPerPlayer` ≤ 1,3 |
| SC-004 | `duplicateFrames` = 0 |

Abweichungen aus `mismatches` am Video nachsehen. Ist Veo falsch, wird das im Bericht vermerkt, nicht
weggerechnet.

## 4. Referenz beeinflusst nichts (FR-008)

```sh
sha256sum web/data/veo-szene-705-eigen/meta.json   # vor und nach Schritt 3 gleich
```

## 5. Viewer

```sh
cd web && python3 -m http.server 8765
# http://localhost:8765/?match=veo-szene-705-eigen
```

**Erwartet** (siehe [contracts/viewer-entities.md](contracts/viewer-entities.md)):
- **Spieler mit Nummer**: Ein Spieler mit Nummer, zum Beispiel `Wir 15`, zeigt die 15 auf dem Rücken, im
  Schild und in der Auswahl.
- **Spieler ohne Nummer**: Er steht als `Wir ? (S4)` in der Auswahl, mit `?` im Schild und ohne Nummer auf
  dem Trikot.
- **Folgen**: Einem Spieler mit Nummer über die ganze Szene folgen. Die Figur bleibt dieselbe, auch nach
  Verdeckung.

## 6. Kader (optional)

```sh
echo '{"own": [1, 4, 5, 7, 11, 15, 66]}' > $W/kader.json
.venv/bin/python tools/veo_scene.py - $W/camera.json - $W/scene_705.mp4 705 $W/scene_705.det.json \
     web/data/veo-2026-11-01 web/data/veo-szene-705-eigen --kader $W/kader.json
```

**Erwartet**:
- Keine eigene Nummer außerhalb der Liste.
- Eine fehlerhafte Datei, etwa `{"own": [100]}` oder mit einem Namen, bricht vor der Auswertung mit Meldung
  ab.
