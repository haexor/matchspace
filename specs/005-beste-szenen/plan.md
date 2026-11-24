# Plan: Beste Szenen vor der Kamera

Spec: [spec.md](spec.md). Ziel laut Nutzer: wenige kurze Szenen (drei bis fünf) bis zur Spitzenqualität bringen, als
Vorschau darauf, was mit mehreren Videostreams möglich wäre. Nicht das ganze Spiel.

## Technischer Rahmen

- Sprache und Umgebung wie bisher: Python in `.venv` (numpy, scipy, opencv, torch, ultralytics, transformers), Viewer in
  three.js ohne Build-Schritt, lokale Review-Werkzeuge. Tests mit pytest in eigenen Dateien unter `tests/`.
- Daten: Rohvideo und alles daraus Abgeleitete nur lokal (`data/raw/`, `data/work/`, `web/data/`), nichts davon im
  Repository (Bewegungs- und Bilddaten Minderjähriger).
- Verfassung: eigener Worktree (`../matchspace.worktrees/005-beste-szenen`), Dateien unter 500 Zeilen, Tests getrennt,
  Konventionelle Commits ohne Hinweise auf Werkzeuge, vor neuen Funktionen im Wissensgraphen nachsehen.

## Messungen, die den Zuschnitt bestimmt haben (2026-11-24)

| Zone (Spieler 1,70 m, Panorama 2048×2048) | Spielerhöhe | Ball |
|---|---|---|
| Mitte, 10 bis 20 m von der Kamera | 105 bis 125 px | rund 8,5 px |
| 50 m entfernt | 45 px | 4 bis 5 px |
| Seitlich außen (x ≈ ±30 m) | 70 bis 80 px | 2 bis 4 px |

- Die Kamera steht auf x ≈ 0, 9,5 m hinter der nahen Seitenlinie. Die **Nahzone** ist der Streifen von rund 10 bis 25 m
  Abstand (Platzkoordinate y von −27 bis −12) und 5 bis 24 m seitlich der Mitte. Bei |x| < 5 m liegt die Naht zwischen
  den beiden Linsenbildern; dort wird eine Figur geteilt, das gibt schlechte Punkte.
- Der eigene Ballfund hatte in den Szenen 705 und 722 nur 60 % und 29 % der Bilder. In der Nahzone muss er deutlich
  besser sein; das misst der Szenenfinder (SC-001).
- Veos Basisspiel (Ball und 94 Spurkennungen, 25 Hz aus 2,5 Hz) liegt für das ganze Spiel vor. Es taugt **nur für die
  Vorauswahl** der Zeitfenster; Veos Ball ist geglättet (keine Stöße) und kein Maß für Kontakte. Gemessen wird am Video.

## Vorgehen in Stufen

Die Stufen entsprechen den Geschichten der Spec; jede ist für sich lieferbar.

### Stufe 1 – Szenenfinder (US1)

1. **Vorauswahl** aus dem Basisspiel in 15-Sekunden-Fenstern (Schritt 5 s): Anteil der Zeit mit Ball in der Nahzone,
   Spieler in 3 m um den Ball (Zweikampf, Dribbling), Tempowechsel. Fenster, die sich überlappen, werden zusammengelegt.
2. **Videoabschnitte holen**: nur die besten Kandidaten, je rund 45 Sekunden, mit `ffmpeg -ss … -c copy` direkt aus dem
   Panorama des Anbieters (die Adresse stammt aus dem lesenden Zugang über vereinsfunk; Cookie und Token werden nie
   gespeichert oder ausgegeben, siehe Projektnotizen). Die Abschnitte liegen unter `data/raw/veo/DATUM/scenes/`.
3. **Eigene Bewertung** je Abschnitt: Personenerkennung in jedem Bild und eigene Ballsuche (`veo_detect.py`,
   `veo_ball.py`). Einzelwerte: Ballanteil, Spielerhöhe des Ballführers in Pixeln, Ballgröße, Beteiligte, Kontakte,
   Zweikämpfe. Gesamtpunkte sind eine einfache gewichtete Summe; die Einzelwerte stehen daneben.
4. **Ausgabe**: `data/work/DATUM/scenes/ranking.json` mit Rangliste und Standbildern, dazu eine kleine Textliste.

Neu: `tools/scene_finder.py` (Vorauswahl, Bewertung, Rangliste), Tests in `tests/test_scene_finder.py`.

### Stufe 2 – Referenz für Ballkontakte (US2)

- Erweiterung des Review-Werkzeugs (`tools/review_server.py`, `web/review/`) um einen **Ballmodus**: Bild für Bild vor und
  zurück, Ballspur und Boxen eingeblendet, Kontakt mit Klick auf Box und Körperteil setzen, Pass, Schuss, Verlust,
  Gewinn; „Ball nicht erkennbar“.
- Speicherung in `tools/ball_reference.py` (Dateiformat wie die Referenz aus Feature 003: ohne Bilder, ohne Namen; Spieler als
  Spuranker, damit die Markierungen eine neue Auswertung überstehen).
- Vorschläge aus der Ballspur: Knicke der Bahn und Tempowechsel (siehe Stufe 3, gleicher Code).

### Stufe 3 – Ball und Ballführung (US3)

- `tools/ball_physics.py`: Flug als Parabel (Lage, Geschwindigkeit, Höhe, Schwerkraft), angepasst an die Strahlen durch die
  Ballpixel; Rollen mit Reibung; Aufspringen mit Verlust. Aus der Wurfparabel entsteht die Höhe, die heute fehlt
  (Ball am Boden angenommen). Ein Flug braucht rund zehn Bilder, damit die Höhe bestimmt ist; sonst bleibt sie unbekannt.
- `tools/ball_events.py`: Kontakte, Pässe, Schüsse aus Knicken der Ballspur, Tempo- und Richtungswechsel und der Nähe der
  Füße (Fußgelenke aus den Gelenkpunkten). Ausgabe mit Zeit, Spieler, Körperteil und Sicherheit.
- `tools/ball_motion.py`: baut die Ballspur zwischen den Ereignissen aus Physik zusammen, beim Kontakt trifft der Fuß den
  Ball; Abschnitte ohne gefundenen Ball tragen die Kennung „erschlossen“. Die Szenenausgabe (`scene_output.py`) nimmt
  diese Spur und Kennung in `meta.json` auf, der Viewer färbt erschlossene Abschnitte.
- `tools/ball_eval.py`: misst gegen die Referenz: Zeitfehler, gefundene und erfundene Kontakte, richtiger Spieler und
  Körperteil, Höhenfehler bei Flugbällen.
- Die bisherige Heranziehung des Balls an den nächsten Fuß (`own_scene.attach_ball`) fällt weg, sobald Kontakte erkannt sind.

### Stufe 4 – Texturen aus den nächsten Bildern (US4)

- Für die Spieler der gewählten Szenen: Bilder aus den Abschnitten und, wo nötig, weiteren Abschnitten holen, in denen der
  Spieler nah an der Kamera ist (Vorauswahl aus dem Basisspiel, Zuordnung über Rückennummer und gelerntes Aussehen aus
  Feature 002/003). Textur aus diesen Bildern mit dem bestehenden Verfahren (`veo_looks.py`), aber mit Auswahl nach
  Spielerhöhe in Pixeln und über Szenen hinweg gemittelt. Die Rückennummer wird nur eingesetzt, wo der Leser sie sicher
  liest.
- Neu: `tools/match_looks.py` (Auswahl und Mittelung über Abschnitte), Änderung in `veo_looks.py` für die Bildauswahl.

### Stufe 5 – Bewegung am Kontakt (US5)

- Aus den Nahaufnahmen die Beinbewegung am Kontakt lesen: Gelenkpunkte in voller Auflösung (Ausschnitte mit der
  Spielerbox statt des ganzen Linsenbilds), Anpassung der Haltung Bild für Bild am Kontakt (`pose_fit.py`), Schwungfenster
  um Kontakte und Schüsse ohne Fußfesthalten (`foot_planting.py`).
- Zweikämpfe und Fouls als Ereignisse (`tools/duel_events.py`): zwei Spieler in unter 1 m, Ball in 2 m, Tempowechsel,
  Spieler am Boden. Körper dürfen sich nicht durchdringen; Haltungsprüfung wie bisher in `pose_limits.py`.
- Fremde Bewegungsvorlagen: Lizenz zuerst prüfen und in `specs/005-beste-szenen/research.md` eintragen; ohne geprüfte Lizenz
  wird nichts verwendet.

## Prüfen

- Rangliste: Sichtprüfung der besten zehn Szenen, Zahlen laut SC-001.
- Referenz und Messung: Zeitfehler, Anteile laut SC-003 für mindestens drei markierte Szenen; Werte werden auch dann
  ausgewiesen, wenn sie die Ziele verfehlen.
- Flughöhe: SC-004 an markierten Flugbällen.
- Umbau-Sicherheit: Szenen 705 und 722 und die neun Viewer-Ansichten aus Feature 004 bleiben bei Änderungen ohne
  Ballbezug bit- bzw. pixelgleich.
- Tests für jede neue Funktion in eigenen Dateien; JS-Änderungen am Viewer werden mit Ansichten verglichen.

## Constitution-Check

- Eigener Worktree und Branch: erfüllt.
- Größe: neue Module bleiben unter 500 Zeilen; `review_server.py` und `review_spots.py` werden nur um kleine Teile erweitert,
  der Ballmodus bekommt eigene Dateien.
- Tests getrennt vom Produktionscode: ja.
- Wiederverwendung: vor jeder neuen Funktion im Wissensgraphen prüfen (`graphify-out/`), besonders für Ballspur
  (`own_scene.py`, `veo_ball.py`), Referenzformat (`reference.py`) und Review (`review_spots.py`).
- Keine Zugangsdaten, keine absoluten Pfade und keine Bilder oder Bewegungsdaten im Repository.

## Bekannte Grenzen

- Eine Kamera, Ball rund 8 px: Kontaktzeiten sind nur so genau, wie die Ballspur im Bild trägt. Die Zielwerte aus SC-003
  sind nicht zugesichert; der Bericht nennt den erreichten Wert.
- Veos Daten sind nur Vorauswahl; sie können gute Szenen übersehen.
- Fremde Bewegungsdaten haben oft Lizenzen, die eine Weitergabe oder kommerzielle Nutzung einschränken; ohne Prüfung gibt es
  keine.
