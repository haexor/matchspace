# Research: Eigene Referenz statt Veo

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Stand**: 2026-11-23

Grundlage ist der Stand nach Feature 002 (Szenen 705 und 722 des Heimspiels vom 2026-11-01).

## R0 Was heute noch an Veo hängt

| Stelle | Veo-Anteil | Folge |
|---|---|---|
| `jersey_eval.py` | Veo-Spuren sind die Wahrheit, nur Spieler mit Veo-Nummer zählen; Tiefenversatz zu Veo wird herausgerechnet | wird zur zweiten Meinung (R4) |
| `veo_scene.py` ohne Veo | liest das Basisspiel `web/data/veo-2026-11-01`: Spielabschnitte und Anstoß im Video, Uhr, Mannschaftsnamen und -farben, Quelle, dazu die Bewegungsdaten aller Veo-Spieler (im Betrieb ohne Veo gleich wieder verworfen) | eigene Spielbeschreibung (R7) |
| `veo_camera.py` | ohne Handpunkte: Veos angeklickte Ecken; **auch mit Handpunkten** startet die Anpassung bei Veos geschätzter Kameralage | eigener Start (R6) |
| `veo_camera.read_veo` | Linsendaten der Kamera (Brennweite, Verzeichnung, Lage der Linsen) | bleibt: Eigenschaft der Kamera (Spec, Annahmen) |
| Luftbild und Kulisse | aus dem Video gerechnet, aber im Ordner des Veo-Basisspiels abgelegt | wandern in den eigenen Spielordner (R7) |

## R1 Strittige Stellen finden

**Messung** an den rohen Spuren (Boxen derselben Linse überlappen, Stellen mit gemeinsamen Spielern
zusammengefasst):

| Szene | Verdeckungsstellen (Überlappung > 0,1 / 0,3 / 0,5) | Spuren beginnen/enden mitten auf dem Platz |
|---|---|---|
| 705 | 23 / 31 / 20 | 33 von 76 Enden |
| 722 | 12 / 15 / 30 | 44 von 88 Enden |

- **Decision**: Gründe für eine strittige Stelle:
  1. **Verdeckung**: Boxen zweier Spieler derselben Linse überlappen um mehr als 30 % der kleineren Box;
  2. **Spurende oder -beginn** mitten auf dem Platz (mehr als 1 m innerhalb der Linien, nicht am Anfang oder
     Ende der Szene);
  3. **Trennung oder Verbindung** aus Feature 002;
  4. **Nummer prüfen**: jeder Spieler mit vergebener Nummer, einmal, an der Stelle mit der besten Rückenlesung;
  5. **Nummer unsicher**: beste Nummer mit Sicherheit zwischen 0,5 und 0,9 aus mindestens 2 Fenstern;
  6. **Veo sieht anders** (nur wenn Veo-Daten vorliegen): Laut Veo wechselt ein Spieler die Person für
     mindestens 1 s.

  Stellen mit gemeinsamen Spielern, die weniger als 1 s auseinanderliegen, werden eine Stelle. Ein Ausschnitt
  reicht von 1,5 s vor bis 1,5 s nach der Stelle.
- **Erwartung**: 30–50 Stellen je Szene. Bei 10 Minuten bleiben 12–20 s je Stelle. Das reicht, wenn eine
  Bestätigung ein Tastendruck ist. Wird SC-001 verfehlt, kommen die Stellen nach Risiko sortiert, und die
  Messung nennt, was offen bleibt.
- **Gemessen (T008)** nach dem Bau von `review_spots.py`:

  | Szene | Stellen | davon Verdeckung / Spurende oder -beginn / Trennung oder Verbindung / Nummer / Veo / Kontrolle | Beteiligte je Stelle | Ausschnitte zusammen |
  |---|---|---|---|---|
  | 705 | 57 | 37 / 17 / 6 / 10 / 4 / 5 | 1–2: 41, 3–6: 16 | 200 s |
  | 722 | 62 | 44 / 32 / 5 / 8 / – / 5 | 1–2: 38, 3–6: 24 | 232 s |

  Mehrere Gründe können auf eine Stelle fallen. Nachgeschärft gegenüber dem ersten Entwurf:
  - Zusammengefasst wird nur bis 6 s Länge und 6 Beteiligte; sonst wuchsen Gedränge zu Stellen mit über 20
    Spielern.
  - An Spurenden zählen nur Spuren, die nahebei selbst beginnen oder enden. Wer weiterläuft, hätte bei einem Tausch
    eine Verdeckung.
  - Stellen ohne Beteiligte vorher oder nachher entfallen, weil es dort nichts zuzuordnen gibt.

  Mit rund 60 Stellen ist SC-001 (10 Minuten) knapp. Die Schwelle der Verdeckung ist einstellbar (`OCCLUDE`), bei
  0,5 wären es rund ein Drittel weniger Verdeckungsstellen.
- **Kontrollstellen**: 5 je Szene, zufällig über Zeit und Spieler aus Abschnitten ohne Grund, mit festem
  Startwert (wiederholbar). Die Frage lautet: Ist das dieselbe Person wie 1,5 s vorher?
- **Alternatives considered**:
  - Jede Stichprobe markieren: vom Nutzer abgelehnt (zu viel Handarbeit).
  - Nur Kontakte unter 1,5 m (wie in 002): rund 100 je Szene, zu viele.

## R2 Referenz aus Antworten

- **Decision**: Die Referenz ist die Zuordnung der Auswertung, korrigiert an den entschiedenen Stellen.
  - Jede Stelle schneidet die beteiligten Spieler in **Abschnitte** (vorher, nachher).
  - Eine Antwort verknüpft Abschnitte: „wie vorgeschlagen“ heißt, jeder Spieler bleibt dieselbe Person.
    „Vertauscht“ heißt, die Abschnitte nach der Stelle gehören über Kreuz zu den Personen davor. „Andere Person“
    heißt, der Abschnitt danach ist niemand von vorher. Bei einem Spurbeginn kann der Nutzer den Abschnitt einer
    endenden Spur derselben Stelle zuordnen.
  - **Personen** sind zusammenhängende Gruppen verknüpfter Abschnitte (Union-Find). Abschnitte ohne Antwort
    bleiben ihre eigene Person, das ist die Annahme „unauffällig heißt richtig“.
  - „Unklar“ nimmt die Abschnitte nach der Stelle aus der Messung, bis eine spätere Antwort sie wieder anbindet.
  - Nummern einer Person: vom Nutzer angegeben, sonst unbekannt.
- **Haltbarkeit (FR-006)**: Antworten speichern je Abschnitt Bild, Linse und Box der ersten und letzten
  Erkennung, dazu die Lage im Bild. Nach einer neuen Auswertung wird ein Abschnitt über die Boxen wiedergefunden
  (gleiches Bild, Überlappung > 50 %). Was nicht wiederzufinden ist, wird gemeldet und zählt als offen.
- **Rationale**: Die Messung braucht Personen je Erkennung. Aus wenigen Antworten an Bruchstellen lassen sie
  sich vollständig ableiten, ohne jede Erkennung zu markieren.

## R3 Markierwerkzeug

- **Decision**: Ein kleiner lokaler Webserver aus der Python-Standardbibliothek (`http.server`), nur an
  `127.0.0.1` gebunden, und eine schlichte Seite unter `web/review/` ohne fremde Skripte:
  - **Server** (`tools/review_server.py`): liefert die Seite, das Szenenvideo aus `data/work/` mit
    Range-Anfragen (nötig zum Springen im Video), die Stellen als JSON, nimmt Antworten an und schreibt sie
    sofort atomar in die Referenzdatei.
  - **Seite**: spielt je Stelle den Ausschnitt in Endlosschleife ab (Linse ausgeschnitten und vergrößert),
    zeichnet die Boxen der Beteiligten mit Buchstaben (A, B, …) vorher und nachher. Antwort per Taste: `Enter` wie
    vorgeschlagen, `V` vertauscht, `A`/`U` andere Person oder unklar je Spur, Ziffern für die Nummer; `←`/`→`
    blättern.
  - **Video**: Die Szenenvideos sind H.264, 2048 × 2048, 29,97 Bilder/s. Das spielen Chromium und Firefox
    selbst ab.
- **Rationale**: Keine neue Abhängigkeit (Ponytail-Leitlinie). Bilder bleiben auf dem Rechner, und die Seite
  lädt nichts aus dem Netz. Antworten müssen nicht von Hand exportiert werden.
- **Alternatives considered**:
  - **Reine Seite mit Dateiauswahl** (ohne Server): Antworten nur über Herunterladen, fehleranfällig.
  - **Desktop-Oberfläche** (OpenCV-Fenster): kein bequemes Abspielen und Zoomen.
  - **Fertige Markierwerkzeuge** (CVAT, Label Studio): groß, eigene Datenhaltung, Bildlast; für 30–50 Fragen
    je Szene überdimensioniert.

## R4 Messen gegen die eigene Referenz, Veo als zweite Meinung

- **Decision**:
  - Identitätskennzahlen werden **je Erkennung** gemessen (Spieler der Auswertung → Person der Referenz),
    nicht über die Lage der fertigen Szene. Damit spielt die Lagegenauigkeit für die Identität keine Rolle,
    und der pauschale Tiefenversatz entfällt (FR-012).
  - Kennzahlen wie in Feature 002: Identitäten je Person, falsch zugeordnete Zeit, Personenwechsel ≥ 1 s,
    Nummern (richtig, falsch, unbekannt).
  - Dazu kommen Abdeckung (Anteil entschiedener Stellen, „unklar“) und die Schätzung aus den Kontrollstellen.
  - **Veo als zweite Spalte**: Abgleich der Erkennungen über ihre Bodenlage (die rohen Bodenpunkte liegen im
    Median 0,3 m neben Veo, ohne Versatz). Daraus entstehen dieselben Kennzahlen „laut Veo“ und eine Liste der
    Stellen, an denen Veo eine andere Person sieht als die Referenz.
- **Rationale**: Die Identität hängt an Erkennungen, nicht an Metern. Der Versatz der fertigen Szene ist eine
  eigene Frage (R5).

## R5 Lageprüfung an Platzlinien

**Machbarkeit** (Fußgelenk im Bild unter 1,5 Pixel neben einer projizierten Platzlinie, Sicherheit ≥ 0,5):
705 mit 3454 Treffern in rund 1100 Ereignissen, 722 mit 2598 Treffern in rund 900 Ereignissen. Die meisten
liegen an Torlinie, Seitenlinie, Mittelkreis und Torraum.

- **Decision**:
  - **Linienstelle**: Das untere Fußgelenk (es steht) liegt im Bild unter 1,5 Pixel neben einer Platzlinie, ist
    über 3 Bilder ruhig (unter 2 Pixel Bewegung), und der Linienpunkt ist im Hintergrundbild hell (die Linie ist
    dort wirklich zu sehen).
  - **Wahre Lage**: der Punkt der Linie unter dem Fuß.
  - **Fehler je Quelle**: Abstand der Lage zu diesem Punkt, zerlegt in Tiefe (Blickrichtung der Kamera) und quer
    dazu. Quellen sind die fertige Szene, der rohe Bodenpunkt (Boxunterkante), der Fußpunkt aus den
    Gelenkpunkten und Veo (falls vorhanden).
  - **Ergebnis**: Median und Streuung je Quelle. Daraus folgt, ob der Versatz von 0,9 m ein Fehler der Szene ist.
    Je Szene werden höchstens 3 Stellen je Spieler und Sekunde verwendet, damit wenige Spieler das Ergebnis
    nicht beherrschen.
  - **Grenze**: Körpermitte und stehender Fuß liegen bis rund 0,3 m auseinander. Im Mittel über viele Stellen
    gleicht sich das aus, ein fester Versatz bleibt sichtbar.
- **Folge für die Szene**: Zeigt die Prüfung einen festen Tiefenfehler der fertigen Szene, wird er im selben
  Feature behoben (Ursache in `veo_scene.feet_on_ground`). Danach wird die Prüfung wiederholt.
- **Kontrollbild**: Ausschnitte einiger Linienstellen im Scratchpad zum Ansehen, nie eingecheckt.

## R6 Kamerakalibrierung ohne Veo-Start

- **Decision**: Die Anpassung an die Handpunkte startet ohne Veos Kameralage. Durchprobiert wird ein grobes
  Gitter möglicher Kameralagen: Höhe 4–15 m, Abstand hinter der Seitenlinie 2–20 m, Lage entlang der Linie, Blick
  zur Platzmitte. Je Startlage werden nur die Handpunkte angepasst; die beste Lage ist der Start für die
  bisherige Verfeinerung an den Linien. Veos angeklickte Ecken entfallen; ohne Handpunkte bricht das Werkzeug mit
  einer klaren Meldung ab.
- **Prüfkriterium**: Für das Heimspiel vom 2026-11-01 liegt die neue Kamera höchstens 0,1 m und 0,1° neben der
  heutigen, und der Linienfehler ist gleich.
- **Alternatives considered**: Lage aus der Linsengeometrie direkt berechnen (PnP je Linse). Das braucht ein
  Umrechnen des eigenen Verzeichnungsmodells; das Gitter ist einfacher und robust.

## R7 Eigene Spielbeschreibung

- **Decision**: `spiel.json` je Aufnahme, lokal unter `data/work/<aufnahme>/`:

  ```json
  {"name": "U15, 2026-11-01",
   "teams": {"own": {"name": "Wir", "color": "#d7263d"}, "opponent": {"name": "Gegner", "color": "#1f9d55"},
             "referee": {"name": "Schiedsrichter", "color": "#f2c200"}},
   "periods": [{"id": 1, "videoStartS": 126, "clockStartS": 0}, {"id": 2, "videoStartS": 3434, "clockStartS": 2400}]}
  ```

  - `tools/own_match.py` legt daraus und aus `camera.json` (Platzmaße) einen eigenen Spielordner an,
    `web/data/<spiel>/meta.json`, ohne Bewegungsdaten.
  - `veo_ground.py` und `veo_backdrop.py` schreiben Luftbild und Kulisse dorthin wie bisher.
  - `veo_scene.py` liest im Betrieb ohne Veo nur noch diese Beschreibung, keine Veo-Bewegungsdaten.
- **Anstoßzeiten**: Der Nutzer trägt die Videosekunde des Anstoßes je Halbzeit einmal ein. Für das Heimspiel vom
  2026-11-01 werden die Werte am Video bestätigt, nicht aus Veo übernommen.

## R8 Nachweis „ohne Veo“

- **Decision**: Ein Prüflauf startet die Auswertung mit einem Python-Audit-Hook (`sys.addaudithook`). Er bricht
  ab, sobald eine Datei unter `data/raw/veo/` oder im Veo-Basisspiel geöffnet wird. Der Ordner wird ausdrücklich
  angegeben, nicht über ein Namensmuster, weil auch Szenenordner mit `veo-` beginnen. So ist nachgewiesen, dass
  nichts von Veo gelesen wird, ohne Rohdaten zu verschieben. Für die Auswertung einer Szene braucht es aus
  `data/raw/veo/` nichts; Kalibrierung, Luftbild und Kulisse lesen die Aufnahme selbst (Panoramavideo,
  Linsendaten) mit ausdrücklicher Freigabe.
- **Vergleich**: Lage, Spieler und Nummern der Szene gleichen dem Lauf mit Veo-Basisspiel (Prüfsumme von
  `tracks.bin`); die Uhr in `meta.json` zeigt dieselbe Spielzeit.

## R9 Tests

- `unittest` wie bisher:
  - **Stellen finden**: mit künstlichen Spielern (Überlappung, Spurende mitten auf dem Platz, am Rand nicht,
    Zusammenfassen, Kontrollstellen wiederholbar).
  - **Referenz**: „wie vorgeschlagen“, „vertauscht“, „andere Person“, „unklar“, Spurbeginn einer endenden Spur
    zuordnen, Wiederfinden nach neuer Auswertung.
  - **Messung**: Kennzahlen aus der Referenz, ohne und mit künstlicher Veo-Spalte.
  - **Lageprüfung**: künstliche Kamera, Fuß auf einer Linie mit bekanntem Versatz.
  - **Spielbeschreibung**: Uhr und Abschnitte; kein Lesen von Veo-Dateien (Audit-Hook).
  - **Server**: Range-Anfrage, Speichern einer Antwort, nur `127.0.0.1`, keine Pfade außerhalb erlaubter Ordner.
- Die Seite wird von Hand und mit einem Bildschirmfoto im Scratchpad geprüft.

## R10 Datenschutz

- Die Referenzdatei enthält nur Bild, Linse, Box, Lage, Rolle, neutrale Kennung, Nummer und Antwort. Sie liegt
  unter `data/work/` (nicht eingecheckt).
- Der Server liefert Video nur aus `data/work/` und nur an `127.0.0.1`. Die Seite lädt keine fremden Skripte,
  Schriften oder Bilder.
- Bildschirmfotos zur Prüfung nur im Scratchpad.
