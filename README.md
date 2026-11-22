# MatchSpace

Rekonstruktion von Fußballspielen als frei navigierbares 3D-Replay.
Aktueller Stand: Web-Viewer, der Trackingdaten im eigenen Format abspielt.

## Viewer starten

```sh
python3 -m http.server 8765 --directory web
# dann http://localhost:8765 öffnen
```

URL-Parameter: `?match=game1` (Ordner unter `web/data/`), `&t=600` (Startzeit in
Sekunden), `&mode=free|follow|fp`, `&player=own-9`, `&look=body|sticks|simple` (Körpermodell,
Stab-Skelett oder einfache Figur), `&zoom=0.5` (Kameraabstand beim Folgen), `&orbit=90` und
`&tilt=0.5` (Richtung und Höhe der Folge-Kamera), `&view=top`, `&ui=0` (ohne Bedienelemente, für
Videos), `&labels=0` (ohne Nummernschilder und Ringe).

Das Körpermodell liegt unter `web/models/player/player.glb` (Quelle und Lizenz in `LIZENZ.txt` daneben); fehlt es, zeigt der Viewer Stab-Skelette.
Es liefert nur die Form. Das Aussehen kommt aus dem Video: Hat ein Spiel eine `looks.png` (siehe
`veo_looks.py` unten), trägt jede Figur die Farben, die ihr Spieler im Video hat (Trikot, Hose, Stutzen,
Schuhe, Haut, Haare). Ohne sie ist die Ausrüstung eine Farbe je Körperregion, Standard ist die
Teamfarbe aus `meta.json` (`teams.<team>.kit` mit `shirt`, `shorts`, `socks` überschreibt sie).
Spiele mit Bildern aus dem Video werden bei bedecktem Himmel beleuchtet wie am Aufnahmetag.

## Beispieldaten erzeugen

Die Daten liegen nicht im Repository. Quelle: Metrica Sports Sample Data
(https://github.com/metrica-sports/sample-data, bei öffentlicher Nutzung Quelle nennen).

```sh
B=https://raw.githubusercontent.com/metrica-sports/sample-data/master/data/Sample_Game_1
mkdir -p data/raw/metrica
curl -L $B/Sample_Game_1_RawTrackingData_Home_Team.csv -o data/raw/metrica/game1_Home.csv
curl -L $B/Sample_Game_1_RawTrackingData_Away_Team.csv -o data/raw/metrica/game1_Away.csv
python3 tools/convert_metrica.py data/raw/metrica/game1_Home.csv data/raw/metrica/game1_Away.csv web/data/game1
.venv/bin/python tools/synth_poses.py web/data/game1   # Körperhaltung aus den Laufwegen, ca. 490 MB
```

Die Metrica-Daten enthalten keine Körperposen. `synth_poses.py` erzeugt deshalb aus den
Laufwegen eine natürliche Bewegung (Stehen, Gehen, Laufen aus aufgezeichneten Bewegungen eines
Menschen, `tools/motion_clips.py`). Das ist ein Platzhalter, keine Messung.

## Eigene Spiele aus Veo

Braucht die Python-Umgebung `.venv` (numpy, opencv, scipy, ultralytics, torch, transformers) und die
Gewichte von ViTPose unter `models/vitpose-plus-base` (Hugging Face `usyd-community/vitpose-plus-base`). Zwischenergebnisse
liegen unter `data/work/`. Die Rohdaten unter `data/raw/veo/` (Veo-Export und Panorama-Video,
abgerufen über die Veo-Verbindung von vereinsfunk) sind Bewegungsprofile von Minderjährigen
und bleiben lokal.

```sh
V=data/raw/veo/2026-11-01; W=data/work/veo-2026-11-01
# 1. Kamera an den Platzlinien kalibrieren, Platz ausmessen (je Aufzeichnung: anderer Platz, anderer Standort)
#    Statt $W/landmarks.json geht auch "-": Start aus den vier in Veo angeklickten Ecken, ohne Handarbeit
.venv/bin/python tools/veo_camera.py $V/panorama_600_900.mp4 $W/landmarks.json $V/camera_alignment.json $W/camera.json $W/camera_check.jpg
# 2. Personen und Trikotfarben erkennen (1 Bild/s reicht für Schritt 3)
.venv/bin/python tools/veo_detect.py $V/panorama_600_900.mp4 $W/detections.json 1
.venv/bin/python tools/veo_colors.py $V/panorama_600_900.mp4 $W/detections.json
# 3. Veos Positionsangaben auf den echten Platz abbilden
.venv/bin/python tools/veo_align.py $V $W/camera.json $W/veo_align.json 600:$W/detections.json 4110:$W/detections_4110.json
# 4. Ganzes Spiel für den Viewer: Positionen, Haltung aus den Laufwegen, Luftbild und Kulisse des Platzes
python3 tools/convert_veo.py $V/export.json web/data/veo-2026-11-01 $W/veo_align.json $W/camera.json
.venv/bin/python tools/track_limits.py web/data/veo-2026-11-01   # Veos Sprünge trennen, Tempo und Beschleunigung begrenzen
.venv/bin/python tools/synth_poses.py web/data/veo-2026-11-01
.venv/bin/python tools/veo_ground.py $W/camera.json $V/panorama_600_900.mp4 web/data/veo-2026-11-01
.venv/bin/python tools/veo_backdrop.py $W/camera.json $W/background.png web/data/veo-2026-11-01   # nach veo_ground.py
# 5. Eine kurze Szene dicht auswerten: alle Bilder erkennen (veo_detect.py + veo_colors.py auf dem Szenenvideo),
#    Gelenkpunkte je Person auf dem Platz (rund 2 Minuten je 25 Sekunden Video), dann Positionen und Haltung
.venv/bin/python tools/veo_keypoints.py $W/scene_705.mp4 $W/scene_705.det.json --kamera $W/camera.json
.venv/bin/python tools/veo_scene.py $V $W/camera.json $W/veo_align.json $W/scene_705.mp4 705 $W/scene_705.det.json web/data/veo-2026-11-01 web/data/veo-szene-705
#    vorher den Ball selbst im Video suchen (rund 3 Minuten; ohne Veo, die letzten beiden Angaben nur zum Vergleich)
#    .venv/bin/python tools/veo_ball.py $W/scene_705.mp4 $W/scene_705.det.json $W/camera.json web/data/veo-2026-11-01 705
#    ohne Veo (eigenes Spielertracking, Spieler ohne Rückennummer): VEO_ORDNER und VEO_ALIGN.json als "-"
#    .venv/bin/python tools/veo_scene.py - $W/camera.json - $W/scene_705.mp4 705 $W/scene_705.det.json web/data/veo-2026-11-01 web/data/veo-szene-705-eigen
# 6. Aussehen je Spieler aus dem Video (rund 4 Minuten je Szene); nach jeder neuen Haltung wiederholen
.venv/bin/python tools/veo_looks.py $W/scene_705.mp4 $W/scene_705.det.json $W/camera.json $W/background.png web/data/veo-szene-705
# dann http://localhost:8765/?match=veo-2026-11-01 oder ?match=veo-szene-705
```

- `veo_camera.py` bestimmt je Aufzeichnung Standort und Blickrichtung der Kamera sowie Länge und Breite des
  Platzes. Nichts davon wird von einem anderen Spiel übernommen: Auswärts ist der Platz anders groß und die
  Kamera steht anders. Jede Linie des Normplatzes wird im Bild verfolgt und bleibt ihrer Normlinie fest
  zugeordnet. Den Maßstab liefern Tor (7,32 × 2,44 m), Mittelkreis, Strafraum und Torraum; ohne diese
  genormten Markierungen funktioniert es so nicht. Das Kontrollbild zeigt die Normlinien über dem Video.
  Als Start reichen die vier Ecken, die in Veo angeklickt wurden (Handpunkte `-`); das Werkzeug probiert dann
  Platzlängen von 80 bis 120 m durch. Sicherer ist eine `landmarks.json` mit etwa 19 von Hand abgelesenen
  Punkten je Bildhälfte. Am Ende meldet das Werkzeug, ob es alle Linien gefunden hat. Geprüft ist der Weg
  ohne Handpunkte bisher nur an der einen Aufzeichnung vom 2026-11-01.
- Annahmen der Liniensuche: weiße Linien auf grünem Rasen (gelbe Kleinfeldlinien werden übergangen), Maße von
  Strafraum, Torraum und Mittelkreis nach Norm für Großfeld. Hinter den Außenlinien darf ein heller Randstein
  liegen: Gezählt wird die erste Linie von innen.
- Was über Veo bekannt ist: Die Linsendaten in `camera_alignment.json` (Brennweite, Verzeichnung, Ausrichtung
  der beiden Linsen) stimmen. Die Bildhälften des Panoramas sind aber nicht das Sensorbild: Sie sind anders
  skaliert, und unterhalb von Zeile 608 (von 1024) ist das Bild senkrecht auf die Hälfte gestaucht. Gerade
  Linien haben dort einen Knick. `veo_camera.py` bestimmt diese Abbildung mit; danach liegen die Linien im
  Mittel 0,2 Pixel (3 bis 4 cm am Boden) neben dem Modell. Veo gibt Positionen als Anteil eines Vierecks aus
  vier angeklickten Ecken an (y = 0 an der Kameraseite) und nimmt 105 m Länge an. Beim Spiel vom 2026-11-01
  lag eine dieser Ecken 7 m neben der echten; der Platz ist 90,0 × 55,0 m groß. Nach der Umrechnung liegen
  Veos Positionen im Mittel 0,2 m neben unseren Fußpunkten.
- `veo_scene.py` misst die Positionen selbst (Fußpunkt am Boden). Veo liefert dort nur noch Rückennummern
  und füllt Lücken.
- `track_limits.py` hält Laufwege im Bereich des Möglichen: Wo eine Bahn schneller als 12 m/s wäre (Veo
  vertauscht Spieler), wird sie unterbrochen, statt die Figur über den Platz fliegen zu lassen. Sonst wird
  gerade so weit geglättet, dass niemand schneller als 8,7 m/s läuft oder mit mehr als 8 m/s² beschleunigt.
  Beim Spiel vom 2026-11-01 kam Veos Bahn vorher auf bis zu 166 m/s.
- `check_motion.py SPIELORDNER` zählt Bilder mit unmöglichen Bewegungen (Tempo, Beschleunigung, Sprünge,
  Knochenlängen, Gelenkgrenzen, Drehtempo, Schweben, Gleichgewicht) und nennt die schlimmsten Stellen mit
  Spieler und Sekunde. `veo_scene.py` ruft es am Ende auf. Stand: Szenen 0,5 % und 0,9 % der Spieler-Bilder
  mit mindestens einer Verletzung (fast nur Gleichgewicht am Szenenanfang), ganzes Spiel 1,2 %.
- Haltung (`pose_fit.py`): Eine Kamera misst, wo die Gelenke im Bild liegen, nicht die Tiefe. Je Spieler wird
  deshalb die Bewegung gesucht, die im Kamerabild auf den erkannten Gelenkpunkten liegt (ViTPose,
  `veo_keypoints.py`) und in allem, was das Bild offen lässt, einer natürlichen Bewegung folgt: Stehen,
  Gehen, Laufen passend zu Tempo und Richtung (`motion_clips.py`, aufgezeichnete Bewegungen aus dem
  Körpermodell), im Takt der im Video sichtbaren Schritte. Wo ein Spieler verdeckt ist oder Gelenke
  fehlen, läuft diese Bewegung im Takt weiter; Lücken werden so von beiden Seiten überbrückt.
  Links und rechts verwechselt die Erkennung bei so kleinen Spielern oft; für Arme und Beine wird je
  Bild die Lesart genommen, die zur Bewegung passt.
- Körpermaße: Die Größe je Spieler kommt aus den Gelenkpunkten (Bein plus Rumpf), die Proportionen sind
  an allen Spielern gemessen (`pose_limits.SHARE`). Ein zu großes Skelett würde sich „klein machen“ und
  dazu in die Knie gehen oder sich zur Kamera neigen.
- Der Abstand eines Spielers zur Kamera ist viel ungenauer als seine seitliche Lage (ein Pixel sind
  seitlich wenige Zentimeter, in die Tiefe rund 0,3 m). Er wird aus dem stehenden Fuß bestimmt und
  stärker geglättet.
- `pose_limits.py` hält Haltungen in dem Bereich, den ein Körper hergibt (Gelenkgrenzen, feste
  Knochenlängen, höchste Drehgeschwindigkeit je Knochen, nichts unter dem Boden) und hält stehende
  Füße an ihrer Stelle auf dem Rasen fest. Die Gelenkgrenzen gelten als letzter Schritt, nach dem Glätten
  und nach dem Festhalten der Füße. Jede Figur hat in jedem Bild ein Skelett.
- Gleichgewicht: Wie weit sich ein Spieler zur Kamera hin oder von ihr weg neigt, sieht eine Kamera nicht.
  Diese Neigung wird so gewählt, dass er nicht umfällt: Schwerpunkt über den stehenden Füßen, verschoben um
  das, was Beschleunigung und Kurvenlauf verlangen (`pose_limits.balance_depth`). Der Abstand zur Kamera
  wird dafür sehr ruhig geschätzt (Schwankungen schneller als rund 0,3 Hz gelten als Messrauschen); ein
  Antritt genau auf die Kamera zu oder von ihr weg erscheint dadurch über gut eine Sekunde verteilt.
- Spieler am Boden (gefoult, gestürzt, sitzend): `veo_scene.py` erkennt sie an der Box (sehr niedrig
  oder breiter als hoch). Flach liegende Spieler übersieht der Personendetektor oft; dort wird an
  der von Veo weitergeführten Position trotzdem nach Gelenkpunkten gesucht, geprüft über die
  Trikotfarbe. Die Haltung am Boden wird nicht mehr Gelenk für Gelenk abgelesen (das ergab verdrehte,
  unmögliche Haltungen), sondern aus festen, möglichen Haltungen gebildet (`ground_motion.py`): vorgebeugt,
  auf Händen und Knien, bäuchlings, auf der Seite, sitzend, kniend. Welche gilt, bestimmt die gemessene
  Höhe des Körpers; der Sturz geht in Laufrichtung. Das ist eine plausible Darstellung, keine Messung der
  einzelnen Gelenke. Beispiel: Foul in `web/data/veo-szene-722` ab Sekunde 9.
- Aufstehen: Die Liegephase endet, sobald die gemessene Körperhöhe einige Bilder lang Sitzhöhe hat; dann
  geht es über Sitzen mit aufgestützten Händen, Sitzen, Hocken und Vorbeugen nach oben, höchstens so schnell,
  wie sich ein Mensch aufrichtet.
- Langsames Gehen und Stehen: Unter 0,5 m/s zeigt die Vorlage keinen Gang. Entfernt sich der Körper dort
  mehr als 22 cm von einem stehenden Fuß, macht die Figur einen einzelnen Schritt (Fuß heben, neu setzen,
  immer nur ein Fuß), statt zu gleiten oder das Bein zu überdehnen. Langsames Gehen verkürzt nur die
  Schritte; das Knie des Schwungbeins beugt wie beim normalen Gehen.
- Ball: `veo_ball.py` sucht ihn in jedem Bild selbst (YOLO „sports ball“, auch unsichere Treffer), ohne Veo:
  Treffer, die über mehr als 2 s immer wieder am selben Pixel liegen (Reservebälle), zählen nicht; aus den
  übrigen wird die zeitliche Kette gewählt, in der der Ball jeden Weg mit höchstens 35 m/s schafft. Gefunden
  in 29 % (Szene 722) und 60 % (Szene 705) der Bilder, im Median 0,24–0,35 m von Veos Ballspur entfernt.
  `veo_scene.py` überbrückt Lücken bis 2 s gerade und zieht den Ball an die Fußspitze, wenn er näher als
  0,9 m liegt. Flughöhe fehlt noch (der Ball liegt immer am Boden, ein hoher Ball erscheint zu weit hinten),
  und die Figuren treten nicht nach dem Ball.
- Eigenes Spielertracking (`track_players.py`, in `veo_scene.py` mit "-" statt Veo-Angaben): Personen werden
  am Boden in Metern verfolgt, beide Linsen zusammen (Kalman-Filter, in Blickrichtung ungenauer als quer,
  Zuordnung je Bild mit Trikotfarbe, doppelte Spuren derselben Person zusammengelegt, Stücke über Lücken bis
  3 s verbunden). Es zählen nur Spuren, die meist innerhalb der Linien liegen; Spuren ohne Trikotfarbe nur,
  wenn sie mindestens 1,5 m innerhalb liegen und lange auf dem Platz sind (Torwart). Leibchen der
  Auswechselspieler erkennt `split_bibs` am Farbton (zum Beispiel orange gegen rot), ohne festen Schwellwert.
  Gegen Veos Identitäten geprüft: Veo-Spieler zu 91–95 % ihrer Bilder abgedeckt, Spuren zu rund 90 % rein.
  Grenzen: Rückennummern fehlen (Spieler heißen S1, S2 ...; TW für den Torwart), ein Spieler zerfällt im
  Mittel in rund zwei Spuren (die Figur verschwindet dann kurz und erscheint als andere Spur), die
  Trikotfarben-Klassen in `veo_colors.py` sind noch fest auf Rot, Grün und Gelb eingestellt.
- Abhängigkeit von Veo: Das eigene Kamerasystem wird keine Veo-Daten liefern. Im Modus ohne Veo bleiben
  davon nur die Startwerte der Kalibrierung (Ecken aus Veo, `veo_camera.py`; mit Handpunkten entbehrlich)
  und die Uhr aus dem Basisspiel.
- `veo_looks.py` holt das Aussehen jedes Spielers aus dem Video: Jede Stelle der Körperoberfläche wird
  mit der gerechneten Haltung ins Kamerabild gelegt (jedes Körperteil an seinen erkannten Gelenkpunkten
  nachgerichtet, Verdeckung über einen Tiefenpuffer aller Spieler) und ihre Farbe über alle Bilder der Szene
  gemittelt. Rasen zählt nicht (auch nicht im Schatten), Bildpunkte, die sich deutlich vom leeren Platz
  abheben, zählen mehr. Nie gesehene Stellen kommen von der Gegenseite oder aus der Mannschaft; Spieler,
  die im Video nicht zu sehen sind, tragen das Mittel ihrer Mannschaft. Ergebnis: `looks.png` (eine Kachel
  mit 128 × 128 Texeln je Spieler) und `looks` in `meta.json`. Grob, weil die Spieler im Video nur 50 bis 120
  Pixel hoch sind: Gesichter und Rückennummern sind nicht zu erkennen (die Nummer druckt der Viewer auf),
  das Licht des Spieltags steckt in den Farben.
- Zwischenergebnisse liegen neben den Erkennungen: `*.det.json.keypoints.npz` (Gelenkpunkte je Box),
  `*.det.json.virtual.npz` (Suche nach Spielern ohne Box) und `*.det.json.players.npz` (Gelenkpunkte,
  Körperhöhe und Liegen je Spieler, für `veo_looks.py`). Sie bleiben lokal bei den Rohdaten.
- Kulisse und Luftbild: `veo_ground.py` rechnet den Rasen samt Linien aus dem Video in die Draufsicht,
  `veo_backdrop.py` legt das Hintergrundbild auf senkrechte Flächen hinter Gegengerade und Toren. Die
  Kulisse stimmt nur vom Kamerastandort aus genau, die Kameraseite fehlt. Die Linien stammen aus dem
  Foto, nicht aus Normmaßen.
- Grenzen: ein Blickwinkel, Spieler rund 55 Pixel hoch. Was quer zur Blickrichtung geschieht, ist
  gemessen; die Tiefe der Haltung ist erschlossen. Sprünge gehen verloren (Füße stehen immer auf dem
  Rasen). Die Kennung der Mannschaften (Rot, Grün, Gelb für Schiedsrichter) ist für die Erkennung fest
  eingestellt; das Aussehen der Figuren kommt aus dem Video.
- Rechenzeit je 25 Sekunden Video (RTX A2000): Gelenkpunkte rund 2 Minuten, `veo_scene.py` rund 80 Sekunden,
  dazu die Personenerkennung. `veo_keypoints.py` rechnet mit `--kamera` nur Personen auf dem Platz (bis 2 m
  daneben) und nimmt das kleine ViTPose-Modell. Mit `--modell models/vitpose-plus-huge` rechnet es rund
  fünfmal länger; die Punkte beider Modelle liegen im Mittel 0,5 Pixel auseinander, die fertigen Haltungen
  im Mittel 2 cm (jedes zehnte Gelenk mehr als 10 cm). `veo_scene.py` ist für kurze Szenen gebaut; eine ganze
  Halbzeit müsste in Abschnitten gerechnet und zusammengesetzt werden, das gibt es noch nicht.
- Lizenzen vor einer Weitergabe prüfen: Ultralytics YOLO steht unter AGPL-3.0. ViTPose steht unter
  Apache-2.0. Das Körpermodell der Figuren (`web/models/player/player.glb`, Quaternius „Universal Base
  Characters“) ist CC0. Die Bewegungsvorlagen (Stehen, Gehen, Laufen) liest `motion_clips.py` weiter aus
  `web/models/Xbot.glb`; sie stammen aus den Beispielen von three.js und ursprünglich von Mixamo (Adobe),
  die Bedingungen für eine Weitergabe sind nicht geprüft.

## Datenformat `matchspace-track` (Version 1)

Schnittstelle zwischen Rekonstruktion und Viewer. Ein Spiel ist ein Ordner.

**`meta.json`**

| Feld | Bedeutung |
|---|---|
| `fps`, `frames` | Abtastrate und Anzahl Frames |
| `pitch` | `length` und `width` in Metern; optional `texture` (`file`: Luftbild des Platzes, Zeile 0 = Gegenseite; `margin`: Rand um das Feld in Metern, eine Zahl oder `{left, right, far, near}`; `fade`: Breite des Übergangs in die Umgebung je Seite) und `backdrop` (`sky`: Farbe, `walls`: Bilder auf senkrechten Flächen mit `file`, `from` und `to` in Feldkoordinaten, `base`, `height`, optional `open` für das frei endende Ende) |
| `teams` | Name und Farbe je Team |
| `periods` | Halbzeiten mit `startFrame` und `endFrame` |
| `entities` | Spieler und Ball in der Reihenfolge, in der sie in `tracks.bin` stehen |
| `tracks` | Dateiname, Datentyp, `scale` (Meter pro Einheit), `missing` (Wert für "nicht erfasst") |
| `poses` | optional: Skelettdefinition und Lage der Pose-Dateien |

**`tracks.bin`**: Position je Objekt am Boden. `int16` little-endian, Reihenfolge
Frame → Objekt → `x, y, z`, Einheit Zentimeter.

Koordinaten: Ursprung im Anstoßpunkt, `x` entlang der Länge, `y` entlang der Breite, `z` nach oben.

**`poses/000.bin`, `poses/001.bin`, …**: 3D-Gelenkpositionen in Blöcken von
`chunkFrames` Frames, die der Viewer nach Bedarf nachlädt. `int16` little-endian,
Reihenfolge Frame → Spieler → Gelenk → `x, y, z`, Einheit Millimeter, relativ zur
Bodenposition des Spielers aus `tracks.bin`, Achsen wie das Feld. Spieler in der
Reihenfolge von `entities` (ohne Ball).

`poses.skeleton` legt Gelenke und Knochen fest, der Viewer zeichnet, was dort steht.
Aktuell 20 Gelenke: Becken, Nacken, Kopf, Nase, Schultern, Ellbogen, Handgelenke,
Hüften, Knie, Knöchel, Fersen, Fußspitzen. Fehlt ein Block oder ein Spieler darin,
zeigt der Viewer die einfache Figur.

Noch nicht enthalten: Unsicherheit je Messung, Ballhöhe aus echten Daten, frei
definierte Feldmarkierungen, Gelenkrotationen für texturierte Avatare.
