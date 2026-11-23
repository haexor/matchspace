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
  | 705 | 77 | 56 / 24 / 6 / 10 / 4 / 5 | 1: 16, 2: 30, 3: 31 | 257 s |
  | 722 | 103 | 73 / 59 / 7 / 8 / – / 5 | 1: 13, 2: 25, 3: 65 | 367 s |

  Mehrere Gründe können auf eine Stelle fallen. Nachgeschärft gegenüber dem ersten Entwurf:
  - Zusammengefasst wird nur bis 6 s Länge und 3 Beteiligte; sonst wuchsen Gedränge zu Stellen mit über 20
    Spielern. Erste Fassung: 6 Beteiligte (57 und 62 Stellen). Nach der Rückmeldung beim Markieren („mehr als 3
    Spieler sind ungünstig“) sind es höchstens 3; größere Gedränge werden mehrere Fragen, an Spurenden je Paar.
    Das macht mehr, dafür überschaubarere Stellen (77 und 103).
  - An Spurenden zählen nur Spuren, die nahebei selbst beginnen oder enden. Wer weiterläuft, hätte bei einem Tausch
    eine Verdeckung.
  - Stellen ohne Beteiligte vorher oder nachher entfallen, weil es dort nichts zuzuordnen gibt.

  Mit 77 und 103 Stellen ist SC-001 (10 Minuten) verfehlt, solange eine Frage länger als 8 s dauert. Die Schwelle der Verdeckung ist einstellbar (`OCCLUDE`), bei
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

### Ergebnis der Lageprüfung (T019)

`line_check.py` mit 218 (705) und 176 (722) Linienstellen. Fehler gegenüber dem Fuß auf der Linie, Tiefe positiv =
weiter weg von der Kamera, Median (Streuung 25.–75. Perzentil):

| Quelle | 705 | 722 |
|---|---|---|
| fertige Szene | +0,78 m (0,65) | +0,21 m (1,20) |
| Fußpunkt aus Gelenkpunkten | +0,54 m (0,57) | +0,13 m (0,71) |
| Boxunterkante (rohe Spuren) | −0,81 m (0,66) | −0,91 m (0,94) |
| Veo | −1,01 m (0,67) | −1,33 m (1,82) |

Je Linie (die fernen Linien haben gröbere Pixel in der Tiefe):

| Linie | Entfernung | Boxunterkante | fertige Szene |
|---|---|---|---|
| Mittelkreis | 43–45 m | −0,83 bis −1,04 m (4,6–5,0 px unter dem Fuß) | +0,15 m (1,5–1,8 px) |
| Strafraum, Mittellinie, Bogen | 42–51 m | −0,62 bis −1,18 m | −0,06 bis +0,41 m |
| ferne Seitenlinie | 66 m | −0,59 bis −0,68 m | +0,87 bis +0,95 m (1,8 px; 1 px ≈ 0,5 m) |
| Torraum rechts (722, meist Torwart) | 55 m | −1,76 m | −1,85 m |

- **Befund**: Die fertige Szene liegt an den mittleren Linien auf 0,1–0,4 m genau. Boxunterkante und Veo setzen die
  Spieler rund 1 m zu nah an die Kamera; die Box reicht 4–5 Pixel unter den Fuß. Der Versatz von rund 0,9 m zwischen
  Szene und Veo aus Feature 002 ist damit überwiegend ein Fehler von Veo, nicht der Szene.
- **Kontrollbild**: 16 zufällige Linienstellen aus 705 angesehen. Die Schuhe stehen auf der Linie, das Fußgelenk
  liegt 2–3 Pixel über der Sohle, die Boxunterkante 2–5 Pixel darunter.
- **Grenzen**:
  - Die Stellen werden über das Fußgelenk gefunden. Liegt es selbst ein bis zwei Pixel daneben, verschiebt das
    die Wahrheit um rund 0,3–0,5 m. Das Kontrollbild spricht dagegen, ein Rest bleibt.
  - Auf der fernen Seitenlinie stehen auch viele Betreuer und Auswechselspieler.
  - Der Torraum rechts in 722 hängt fast nur am Torwart.
- **Folge**: Keine Korrektur der Szene (T020 entfällt). Die Messung gegen Veo braucht keinen pauschalen Versatz,
  weil sie über die rohen Bodenpunkte abgleicht, die wie Veo auf der Boxunterkante beruhen (R4).

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

### Ergebnis (T026, T027)

- **Kalibrierung ohne Veo-Start**: Der Start aus dem Raster (48 Lagen) ergibt für das Heimspiel vom 2026-11-01
  dieselbe Kamera wie bisher: 0,000 m Lage, 0,000° Drehung, Linienfehler gleich (Median 0,30 px, 90 % unter
  0,97 px), 17 s Rechenzeit.
- **Eigener Spielordner** `web/data/spiel-2026-11-01`: angelegt aus `spiel.json` und der Kamera. Luftbild und Kulisse
  wurden im Prüflauf gerechnet; freigegeben war nur das Panoramavideo. Dauer 13 s.
- **Szenen ohne Veo** (Prüflauf mit gesperrtem Veo-Basisspiel und `data/raw/veo/`): Beide Szenen laufen durch, ohne
  eine Veo-Datei zu öffnen.
  - Mit derselben Kamera ist `tracks.bin` bitgleich zum Lauf mit dem Veo-Basisspiel (705 `ea41a118…`,
    722 `640d9142…`). Uhr, Mannschaften, Spieler und Nummern sind gleich.
  - Mit der neu kalibrierten Kamera (Unterschiede um 1e-10) weichen die Lagen höchstens 3 cm ab, nur 0,2 % der
    Spieler-Bilder um mehr als 1 cm. Spieler und Nummern sind gleich.
- **Offen**: Die Anstoßzeiten in `spiel.json` (126 s und 3434 s) stammen noch aus Veo und müssen am Video bestätigt
  werden. Das Panorama in den Rohdaten beginnt erst bei Sekunde 600.

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

## R11 Gelerntes Spielmerkmal und Verbindungskosten

- **Frage**: Lässt sich das Aussehen so verbessern, dass Mitspieler im gleichen Trikot besser auseinandergehalten werden?
- **Messung** (je 8 Erkennungen als Stück, Paare derselben Person gegen Paare verschiedener Mitspieler, Trennschärfe
  AUC; 0,5 Zufall, 1,0 perfekt):

  | Szene | Bildmerkmale wie bisher | Mannschaftsanteil abgezogen | im Spiel gelernt (Hälfte 1 → Hälfte 2) |
  |---|---|---|---|
  | 705 | 0,78–0,86 | 0,81 | 0,96 |
  | 722 | 0,78–0,82 | 0,81 | 0,94 |

  Gelernt wird mit einer linearen Diskriminanzanalyse (`appearance.learn_fingerprint`) auf den Ketten des ersten
  Verbindungsdurchgangs mit mindestens 40 Erkennungen. Der Kosinus derselben Person bleibt bei etwa 0,88, der
  eines anderen Mitspielers fällt von 0,74–0,78 auf 0,22–0,38. Das Gewicht `LOOK_WEIGHT` bleibt deshalb unverändert.
- **Grenzen der Messung**: Die Beschriftung kommt aus unseren eigenen Spuren, und die Stücke liegen zeitlich nah
  beieinander. Das passt zum Verbinden über kurze Lücken, überschätzt aber die Trennschärfe etwas.
- **Wirkung auf die Verbindungen** (zweiter Durchgang in `own_scene.split_and_link`): Es entstehen in beiden Szenen
  dieselben Verbindungen wie ohne das gelernte Merkmal (705: 4, 722: 2; 38 und 49 Spieler). Falsche Kandidaten werden
  teurer: In 722 sinken die offenen Enden mit einem Kandidaten unter dem Höchstpreis von 13 auf 10. Mehr Spuren
  werden dadurch nicht verbunden. Was an den Szenen übrig bleibt, sind Spuren, die zwischen den Mannschaften wechseln
  (Verbindungen über Mannschaften sind verboten), und echte Mehrdeutigkeiten.
- **Entscheidung**: Das gelernte Merkmal bleibt als Schutz gegen falsche Verbindungen. Ob es Fehler verhindert,
  zeigt erst die Messung an der eigenen Referenz.

## R12 Bekannte Grenze: Wechsel zwischen den Mannschaften (nicht weiter nachgestellt)

- An einem Kontakt zweier Gegner (722, Bild 151 bis 547) tauscht die Spur der Auswertung zweimal die Person. Die
  richtigen Verbindungen (Ende bei Bild 151 zum Anfang bei Bild 159, Lücke 0,27 s, 1,2 m) kosten 3,4 bis 4,4 statt
  höchstens 2,5: Weg 1,2 bis 1,5, dazu 1,4 bis 2,7 für Aussehen und Größe. Am Kontakt überlappen sich beide Boxen, die
  Bildausschnitte enthalten dann beide Personen, und das Aussehen ist dort unzuverlässig.
- Naheliegende Abhilfen: Aussehen nur aus unverdeckten Erkennungen mitteln, oder an Kontakten Aussehen und Größe
  weglassen und nur nach Weg und Trikotfarbe verbinden.
- **Entscheidung**: Das wird nicht weiter nachgestellt. Der Platz und die Perspektive sind eine einzige; mit Kameras aus
  anderen Blickwinkeln fallen Verdeckungen und Kontakte weg oder lassen sich über die zweite Sicht auflösen. Was
  übrig bleibt, entscheidet die eigene Referenz (Markieren).

## R13 Aussehen gegen die Antworten von Hand; automatischer Tausch-Schritt verworfen

- **Messung**: An 57 Zuordnungen aus den ersten 29 Antworten (Szene 705, Verdeckungen mit mindestens zwei Beteiligten
  vorher) wurde geprüft, welche Box von vorher dem Aussehen einer Box nachher am ähnlichsten ist. Das Spielmerkmal
  (R11) traf die Antwort in 51 Fällen (89 %), bei Lernen und Prüfen auf getrennten Szenenhälften in 52 (91 %), bei
  einem Abstand zwischen bestem und zweitbestem Kandidaten ab 0,3 in 32 von 32. Die Bildmerkmale wie bisher trafen in 47
  (82 %).
- **Versuch**: `split_by_look`, ein Schritt, der zwei Mitspieler an einem Kontakt oder einer Bildverdeckung trennt, wenn
  beide nachher der anderen vorher ähnlicher sehen. Er fand in 705 bei 39 Begegnungen keinen einzigen Tausch und
  änderte die Übereinstimmung mit den Antworten nicht (55 stimmen, 14 nicht). Verworfen, der Code ist nicht
  übernommen.
- **Was bleibt unklar**: Ein Teil der 14 Abweichungen liegt dort, wo ein Spieler für über eine Sekunde gar keine Box
  hat; andere stammen aus der Zeit der missverständlichen Fragestellung (Boxen statt Personen).
- **Vorsicht**: Das Spielmerkmal liefert zugleich die Verbindungen und könnte die Referenz vorbelegen. Dann prüft die
  Referenz nicht mehr unabhängig, was das Merkmal leistet.

## R14 Klare Stellen selbst beantworten (Entscheidung des Nutzers)

- **Entscheidung** (2026-11-23): Der Nutzer will nur Unklares entscheiden müssen, am liebsten gar nichts von Hand. Die
  Auswertung beantwortet deshalb Stellen mit mindestens zwei Beteiligten vorher selbst, wenn jede Box nachher einer Box
  von vorher um mindestens 0,3 (Kosinus der gelernten Bildmerkmale) ähnlicher sieht als allen anderen
  (`tools/auto_answer.py`). Die Antwort trägt die Herkunft `auto`; Antworten von Hand haben immer Vorrang und werden nie
  überschrieben. Automatische Antworten werden bei jeder neuen Auswertung neu bestimmt.
- **Nie automatisch**: Kontrollstellen (sie sollen unabhängig prüfen), Nummernstellen, Stellen mit nur einem Beteiligten
  vorher und alle mit zu kleinem Abstand. Sie bleiben offen und werden bei der Messung ausgenommen. Der Bericht nennt
  Zahl und Anteil (`reference.auto`, `byHand`, `open`).
- **Preis**: Dasselbe Merkmal entscheidet beim Verbinden mit. An diesen Stellen prüft die Referenz das Aussehen nicht mehr
  unabhängig, alles andere schon. Ohne Handantworten ist die Schätzung aus den Kontrollstellen nicht möglich.

## R15 Messung gegen die eigene Referenz (T016)

Abdeckung der Referenz (Szene 705: nach den Änderungen an Verbindung und Farbtrennung neu erzeugt):

| Szene | Stellen | automatisch | von Hand | offen |
|---|---|---|---|---|
| 705 | 71 | 17 | 27 | 27 |
| 722 | 99 | 26 | 0 | 73 |

Kennzahlen (`jersey_eval.py`, gleiche Werte unter `own` mit und ohne `--veo`):

| Szene | Identitäten je Person | falsch zugeordnete Zeit | Wechsel | Spieler mit Nummer, davon falsch |
|---|---|---|---|---|
| 705, laut eigener Referenz | 1,14 | 5,2 % | 6 | 6, davon 0 |
| 705, laut Veo (zweite Meinung) | 2,0 | 5,4 % | 5 | (13 Widersprüche zur Referenz) |
| 722, laut eigener Referenz | 1,0 | 11,2 % | 11 | 7, davon 0 |
| 722, laut Veo (zweite Meinung) | 2,0 | 3,9 % | 3 | (13 Widersprüche zur Referenz) |

**Einordnung, ehrlich:**
- Die Zahlen sind nur schwach belastbar. In 722 sind erst 26 von 99 Stellen entschieden, keine von Hand. Die 11,2 %
  gehen auf eine einzige automatische Antwort zurück (18,5 s, Ende und Beginn). In 705 stammen alle 9 Antworten, die den
  Vorschlag der Auswertung ändern, aus der Zeit der missverständlichen Fragestellung (Boxen statt Personen).
- „Identitäten je Person“ ist gegen die eigene Referenz nicht mit den 2,2 aus Feature 002 vergleichbar: Die frühere
  Zahl galt gegen Veo, das selbst jede Person unter zwei Nummern führt (hier 2,0).
- Die Vergleichswerte aus Feature 002 gegen Veo (705: 5,8 %, 722: 2,9 % falsche Zeit) und die jetzigen gegen Veo (5,4 %
  und 3,9 %) liegen nahe beieinander. Die eigene Referenz bestätigt die Größenordnung in 705 und liefert für 722 noch
  keine belastbare Zahl.
- Offen: Kontrollstellen (5 je Szene) und Nummernstellen sind nie automatisch; ohne Handantworten gibt es daher keine
  Schätzung für Fehler außerhalb der Stellen und keine Wiederholungsprobe (SC-004).

## R16 Quickstart durchgegangen (T031)

| Schritt | Ergebnis |
|---|---|
| 0 Tests | 176 grün |
| 1 Kamera und Spielordner ohne Veo | erreicht: Kamera 0,000 m und 0,000° neben `camera.json` (17 s), Spielordner ohne Bewegungsdaten |
| 2 Szenen ohne Veo | erreicht: Prüflauf ohne Veo-Zugriff, Ergebnis mit derselben Kamera bitgleich |
| 3 Stellen entscheiden | **anders gelöst**: klare Stellen beantwortet die Auswertung (R14); Handarbeit freiwillig |
| 4 Messen | erreicht (R15); `reference.open` ist **nicht** 0: 27 (705) und 73 (722) |
| 5 Lage an Platzlinien | erreicht: 218 und 176 Linienstellen, die Szene liegt an den mittleren Linien auf 0,1–0,4 m genau (R5) |
| 6 Datenschutz | erreicht: nichts unter `data/` eingecheckt; die Referenz enthält nur `scene`, `identityStamp`, `spots`, `answers`, `seed` |

**Verfehlte Ziele:**
- SC-001 (höchstens 10 Minuten Markieren je Szene): nicht gemessen. 77 und 103 Stellen waren zu viel, deshalb der Wechsel
  zu automatischen Antworten; der Nutzer wollte nicht zuordnen.
- SC-004 (Wiederholbarkeit der Antworten von Hand): nicht gemessen, es gibt keine Wiederholungen.
- Schätzung der Fehler außerhalb der Stellen aus den Kontrollstellen: nicht möglich, die 5 Kontrollstellen je Szene sind
  offen.
- Anstoßzeiten (T023): die Werte in `spiel.json` sind noch die von Veo (126 s und 3434 s), vom Nutzer nicht bestätigt; das
  Panoramavideo beginnt in den Rohdaten erst bei Sekunde 600.
