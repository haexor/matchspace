# Research: Rückennummern aus dem Video

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Stand**: 2026-11-22

Alle offenen Punkte des Technical Context sind hier entschieden. Grundlage sind die Vorversuche an den
Szenen 705 und 722 (lokal, nicht eingecheckt) und der vorhandene Code.

## R1 Erkenner: eigenes kleines Netz statt fertiger Texterkennung

- **Decision**: Ein kleines Faltungsnetz (rund 0,6 Mio. Gewichte) klassifiziert einen entzerrten
  Rückenausschnitt in 100 Klassen: die Nummern 1–99 und „keine Nummer lesbar“. Es läuft mit Torch auf der
  vorhandenen GPU (RTX A2000), notfalls auf der CPU.
- **Rationale**: Die Ziffern sind im Veo-Video nur rund 12–20 Pixel hoch. Fertige Texterkennung ist auf
  Dokumente und Schilder trainiert: TrOCR-base las im Vorversuch etwa 4 von 16 Rücken richtig, TrOCR-small
  lädt wegen seines Tokenizers nicht. Eine Klasse je Nummer statt einer Ziffernfolge macht die Abstimmung über
  die Spur (R4) und die Einschränkung auf den Kader (FR-012) zu einfachem Rechnen mit Wahrscheinlichkeiten.
  Die Klasse „keine Nummer“ fängt Vorderansichten, Verdeckungen und Unschärfe ab, statt sie in eine Nummer zu
  zwingen (FR-003).
- **Alternatives considered**:
  - TrOCR/allgemeine OCR: zu schwach bei der Größe, groß und langsam.
  - Zwei Ziffernköpfe (Zehner, Einer, Länge): erkennt Teilverdeckungen feiner, macht Abstimmung und
    Kaderfilter aber komplizierter; erst nötig, wenn R1 die Ziele verfehlt.
  - Externe Dienste: ausgeschlossen (FR-002, Daten Minderjähriger).

## R2 Trainingsdaten: synthetisch, ohne Veo-Nummern

- **Decision**: Trainiert wird auf künstlich erzeugten Rückenausschnitten. Nummern werden in fetten
  serifenlosen Schriften gezeichnet, die das System schon mitbringt (DejaVu Sans Bold, Liberation Sans Bold,
  Noto Sans Bold, Condensed-Varianten von DejaVu und Open Sans; gefunden zur Laufzeit über `fc-match`, kein
  Pfad im Code). Die Ziffern werden einzeln gesetzt, oft schmal und hoch (Breite 0,45–1,1), wie auf
  Trikots. Dazu kommen:
  - zufällige Trikot- und Nummernfarben mit Mindestkontrast, auch dunkle Nummern auf hellem Stoff (FR-010);
  - Stofffalten als Helligkeitswellen, Schräglage und Perspektive (±25°), Drehung, Lage und Größe auf dem
    Rücken;
  - Verkleinern auf 20–44 Pixel Ausschnitthöhe (so groß sind echte gelesene Rücken), wieder Vergrößern,
    Bewegungsunschärfe, Rauschen und JPEG-Kompression (Qualität 25–80) wie im Videostrom;
  - Verdeckung durch Arm- oder Körperstreifen und abgeschnittene Ziffern. Ist weniger als 80 % der Nummer zu
    sehen (aus 66 wird nur noch eine 6), heißt das Beispiel „keine Nummer“: Das Netz soll nicht raten;
  - Beispiele für „keine Nummer“: leere Trikotflächen, Vorderseiten und Rasenränder. Sie kommen auch aus den
    eigenen Videos: Ausschnitte von Spielern, die der Kamera zugewandt sind. Das erkennen die Gelenkpunkte,
    Veo wird dafür nicht gebraucht.
  - Ausschnitte stehen beim Training nur im Speicher. Das Modell kommt nach `models/jersey-digits.pt`
    (nicht eingecheckt). Zufallsstartwert fest, Training wiederholbar.
- **Rationale**: FR-001 verlangt, dass Veo das Ergebnis nicht beeinflusst. Würde auf Veo-Nummern
  trainiert, steckte Veo im Erkenner. Synthetische Daten gibt es in beliebiger Menge und mit allen Farben, die
  später bei eigenen Kameras und anderen Gegnern vorkommen.
- **Alternatives considered**:
  - Training auf Veo-Nummern: verletzt FR-001, und die Messung (FR-008) wäre nicht mehr unabhängig.
  - Hand-beschriftete Rücken: unabhängig von Veo und zulässig, kostet aber Zeit. Rückfallebene, falls die
    synthetischen Daten nicht reichen (siehe R9).
  - Öffentliche Rückennummern-Datensätze (z. B. aus Profiligen): Lizenz unklar, Download nötig, andere
    Bildqualität; nicht nötig, solange R2 reicht.

## R3 Ausschnitte: Rücken aus den Gelenkpunkten

- **Decision**: Die Ausschnitte kommen aus den Gelenkpunkten, die es je Erkennung schon gibt
  (`{det}.keypoints.npz`, ViTPose, COCO-17).
  - **Rücken zur Kamera**, wenn beide Bedingungen gelten:
    - die linke Schulter liegt im Bild links der rechten (`lShoulder.x < rShoulder.x − 2 px`);
    - Schultern und Hüften sind sicher (≥ 0,3).

    Die zunächst geplante Bedingung „Nase unsicher“ entfällt: ViTPose meldet die Nase auch von hinten mit
    hoher Sicherheit (Median 0,78). Die Schulterlage allein trennt sicher, wie Ausschnittbögen beider Szenen
    zeigen: Rücken mit Nummer auf der einen, Vorderseiten ohne auf der anderen Seite.
  - **Ausschnitt**: entlang der Rumpfachse von 15 % der Rumpfhöhe über der Schulterlinie bis 5 % unter der
    Hüftlinie. Die halbe Breite ist der größere Wert aus 0,7 × Schulterabstand und 0,45 × Rumpfhöhe. Die
    Nummer sitzt im unteren Teil des Rückens, deshalb reicht der Ausschnitt bis zur Hüfte. Er wird hochkant
    auf 40×32 Pixel (Höhe × Breite) entzerrt, als Graustufe, und der Kontrast je Ausschnitt normiert.
  - **Mindestgröße**: Schulter–Hüfte ≥ 18 Pixel. Darunter wird nicht gelesen; zwischen 18 und 28 Pixel zählt
    die Lesung weniger (R4). Gemessen an den Gelenkpunkten liegt die Rumpfhöhe der Rücken meist bei 10–23
    Pixeln. Ab 18 Pixeln gibt es je Szene rund 3500–4000 Rücken, ab 24 Pixeln nur noch rund 1300–1700.
  - **Bilder**: Jedes zweite Bild der Szene wird gelesen. Das Video wird dabei nur einmal geöffnet.
    Linsengeometrie und Bildzugriff kommen aus `tools/veo_looks.py` und `track_players.track_hues`.
- **Rationale**: Im Vorversuch waren Nummern ab etwa 28 Pixel Rückenhöhe mit dem Auge lesbar. Die
  Gelenkpunkte legen den Rücken genauer fest als die Box und erlauben, Vorderansichten gleich auszusortieren.
  Graustufen mit normiertem Kontrast machen das Netz farbunabhängig (FR-010).
- **Alternatives considered**:
  - Ganze Box ans Netz: mehr Hintergrund, schlechter bei 55 Pixel hohen Spielern.
  - Eigener Nummerndetektor: unnötig, weil die Gelenkpunkte den Rücken schon liefern.

## R4 Abstimmung je Spur

- **Decision**:
  - **Einzelne Lesung**: liefert Wahrscheinlichkeiten p über 1–99 und „keine“. Sie zählt nur, wenn
    p(keine) < 0,5.
  - **Abhängige Lesungen**: Nachbarbilder sind kaum unabhängig. Deshalb zählt je Zeitfenster von 0,4 s nur
    die beste Lesung.
  - **Spurwert je Nummer**: k = Σ w · log(p_k + 0,01). Das Gewicht w steigt mit der Rückenhöhe
    (18 px → 0,3; ≥ 28 px → 1).
  - **Kader**: Ist er angegeben, entfallen Nummern außerhalb des Kaders vor dem Normieren (FR-012).
  - **Vergabe**: Eine Nummer wird nur vergeben, wenn alle vier Bedingungen gelten:
    - die normierte Sicherheit der besten Nummer ist ≥ 0,9;
    - in mindestens 3 Fenstern ist sie die beste Lesung;
    - zwischen dem ersten und letzten dieser Fenster liegt ≥ 1 s;
    - sie ist in mindestens 60 % der zählenden Fenster die beste Lesung (Einigkeit). Die Summe der
      Logarithmen allein wird bei vielen Lesungen sehr sicher, auch wenn jede dritte Lesung etwas anderes
      sagt (66 gegen 6, 15 gegen 5).

    Sonst bleibt die Nummer unbekannt (FR-003, SC-002).
  - **Einstellen und Prüfen**: Die Schwellen werden an Szene 705 eingestellt und an Szene 722 geprüft, damit
    sie nicht auf eine Szene zugeschnitten sind.
- **Rationale**: Lieber unbekannt als falsch (SC-002 ≤ 5 %). Ähnliche Ziffern (6/9, 1/7, 3/8) verteilen
  ihre Wahrscheinlichkeit auf zwei Nummern und fallen so von selbst unter die Schwelle.
- **Alternatives considered**:
  - Mehrheitsentscheid über die Einzellesungen: wirft die Sicherheit weg und ist anfällig für Serien aus
    Nachbarbildern.
  - Glättung über ein verstecktes Markov-Modell: unnötig, denn eine Spur trägt in der Szene nur eine
    Nummer.

## R5 Keine doppelte Nummer, Zusammenführen

- **Decision**:
  - **Zusammenführen** (FR-005): Spuren einer Mannschaft mit derselben Nummer, die sich zeitlich nicht
    überlappen, werden zu einem Spieler. Die Lücke muss körperlich machbar sein:
    Abstand ÷ Lücke ≤ 8 m/s, gemessen von Ende zu Anfang. Ist sie es nicht, bleibt die Nummer bei der
    sichereren Spur.
  - **Doppelte Nummern** (FR-004): Je Mannschaft werden die Spuren gierig nach Sicherheit absteigend
    vergeben. Eine Spur bekommt ihre beste Nummer, wenn keine zeitlich überlappende Spur sie schon hat.
    Sonst bekommt sie die zweitbeste, falls auch die die Schwelle aus R4 erfüllt, und sonst keine Nummer
    (SC-004).
  - **Lücken**: Zwischen den Stücken eines Spielers wird nur so weit überbrückt wie heute (`OWN_GAP`, 1 s).
    Längere Lücken zeigen den Spieler nicht, er behält aber seine Identität.
  - **Ohne Nummer**: Schiedsrichter (Mannschaft `referee`) werden gar nicht gelesen (FR-006).
- **Rationale**: Nummern sind in einer Szene persönlich, auch bei Auswechslungen. Eine zweite Nummer
  bekommt eine Spur nur, wenn auch die die Schwelle aus R4 erfüllt; so macht der Konflikt keine falsche
  Nummer, nur eine unbekannte. Gierig nach Sicherheit ist deterministisch und reicht bei rund 20 Spuren je
  Mannschaft.
- **Alternatives considered**:
  - Optimale Zuordnung über alle Spuren (ganzzahlige Optimierung): bei der Größe kein messbarer Gewinn, mehr
    Code. Ceiling als `ponytail:`-Kommentar.
  - Zusammenführen auch über das Aussehen (Videotextur): könnte unbekannte Stücke verbinden, ist aber ein
    eigenes Thema; erst wenn SC-003 verfehlt wird (siehe R9).

## R6 Messung gegen Veo, getrennt vom Ergebnis

- **Decision**: Ein eigenes Werkzeug `tools/jersey_eval.py` misst. Es liest nur fertige Ausgaben (Szenen-Meta
  und Spurpositionen) und Veos Daten unter `data/raw/veo/`. Es schreibt einen Bericht nach `data/work/…`,
  nie in die Szene.
  - **Zuordnung**: Eigene Spieler werden Veo-Spielern über den mittleren Abstand am Boden in gemeinsamen
    Bildern zugeordnet. Das macht `track_players.compare_veo` schon (wiederverwenden, nicht neu schreiben).
  - **Zahlen je Mannschaft**:
    - richtig, falsch, unbekannt, bezogen auf Spieler mit mindestens einem gut sichtbaren Rücken
      (≥ 28 px, Rücken zur Kamera);
    - Identitäten je Veo-Spieler (SC-003);
    - Bilder mit doppelter Nummer (SC-004);
    - Laufzeit (SC-005).
- **Rationale**: FR-008 verlangt, dass die Referenz die Vergabe nicht ändert. Das ist am sichersten, wenn die
  Auswertung Veo gar nicht importiert und die Messung erst danach läuft.
- **Alternatives considered**:
  - Messung in `veo_scene.py` mit einbauen: Veo-Code im Produktionspfad, Risiko für FR-001.

## R7 Einbindung in die Szenenauswertung und Aufteilung von `veo_scene.py`

- **Decision**:
  - **Erst auslagern** (Commit `refactor:`): Die Teile für den Betrieb ohne Veo ziehen aus `veo_scene.py`
    in ein neues Modul `tools/own_scene.py`. Das sind `own_identities`, `own_ball`, `attach_ball` und ihre
    Konstanten, rund 100 Zeilen.
  - **Dann einbauen**: `own_identities` ruft nach dem Tracking den Leser (`tools/jersey_reader.py`) und die
    Vergabe (`tools/jersey_identity.py`) auf.
  - **Zwischenspeicher**: Die Lesungen landen als `{det}.numbers.npz` neben den anderen Zwischenständen in
    `data/work/` (nur Wahrscheinlichkeiten und Zeiten, keine Bilder).
  - **Ohne Modell**: Fehlt `models/jersey-digits.pt`, läuft die Auswertung wie heute weiter, alle Nummern
    unbekannt, mit einem Hinweis.
  - **Was danach bleibt**: `veo_scene.py` hat dann noch rund 900 Zeilen. Begründung und Aufteilungsplan
    stehen in [plan.md](plan.md) unter Complexity Tracking.
- **Rationale**: Die Verfassung verlangt, Dateien über 500 Zeilen aufzuteilen oder einen Plan zu nennen.
  Sie verlangt auch, Umbauten von Verhaltensänderungen zu trennen. Das Auslagern schafft den Platz, ohne
  dass die Nummern die Datei weiter wachsen lassen.
- **Alternatives considered**:
  - Ganz `veo_scene.main` (600 Zeilen) jetzt in Stufen zerlegen: großer Umbau ohne Bezug zum Feature,
    gehört in ein eigenes Feature.

## R8 Tests

- **Decision**: Tests mit `unittest` aus der Standardbibliothek unter `tests/` (`test_*.py`), Aufruf
  `.venv/bin/python -m unittest discover -s tests`. Die reine Logik bekommt Einheitstests:
  - Abstimmung, Vergabe, Zusammenführen;
  - Rücken-Erkennung und Viereck aus Gelenkpunkten;
  - Erzeugen synthetischer Ausschnitte (Form, Wertebereich, Wiederholbarkeit);
  - Zählen in der Messung.

  Die Ende-zu-Ende-Prüfung an echten Szenen steht in [quickstart.md](quickstart.md), weil die Daten nicht
  eingecheckt sind.
- **Rationale**: Das Projekt hat noch kein Testwerkzeug, und pytest ist nicht installiert. Die Verfassung
  verlangt Tests in eigenen Dateien und keine neue Abhängigkeit ohne Not.

## R9 Rückfallebenen, falls Ziele verfehlt werden

Reihenfolge, nur bei gemessener Lücke:

1. **SC-001 verfehlt**:
   - Selbsttraining: sehr sichere Spur-Nummern (≥ 0,98) als Beschriftung echter Ausschnitte nachtrainieren.
     Das ist weiter ohne Veo.
   - Danach eine kleine Menge Rücken von Hand beschriften, lokal.
2. **SC-002 verfehlt**: Schwellen aus R4 anheben.
3. **SC-003 verfehlt**: Spuren an widersprüchlichen Lesungen trennen (unreine Spuren); Zusammenführen über
   das Aussehen als eigenes Folgefeature.
4. **SC-005 verfehlt**: nur jedes dritte Bild lesen, Ausschnitte stapelweise auf der GPU.

Die Ergebnisse jedes Schritts kommen in den Bericht der Messung.

## Stand nach der Umsetzung (2026-11-23)

Gemessen mit `tools/jersey_eval.py` gegen Veo, nur als Referenz.

**Vorgehen:**
- **Training**: zuerst nur künstlich. Mit drei Anpassungen an die echten Rücken stieg die Zahl richtiger
  Nummern deutlich, und es blieben keine falschen:
  - schmale Ziffern;
  - Trikot-1 mit Anstrich;
  - Ausschnitte so groß wie im Video.
- **Nachtrainieren (R9 Stufe 1)**: an den eigenen sicheren Lesungen aus Szene 705. Szene 722 blieb dabei
  ungesehen.
- **Schwellen (an 705 eingestellt)**:
  - Einigkeit 70 %;
  - mindestens 5 Fenster.
- **Überlappung und Erreichbarkeit**:
  - Zwei Stücke gelten erst als gleichzeitig, wenn sie länger als 0,5 s zusammen zu sehen sind (Übergabe im
    Tracking).
  - Erreichbarkeit wird an jedem Wechsel geprüft (8 m/s plus 1,5 m Messrauschen).
  - Schwächere Stücke schließen sich einem schon sicher erkannten Spieler an.

**Ergebnis (je Szene):**

| Ziel | 705 | 722 |
|---|---|---|
| SC-001 richtig bei gut sichtbarem Rücken | 4/6 (67 %) | 4/6 (67 %) |
| SC-002 falsche Nummern | 0 | 0 |
| SC-003 Identitäten je Spieler | 2,24 | 2,17 |
| SC-004 Bilder mit doppelter Nummer | 0 | 0 |
| SC-005 Zeit fürs Lesen | 5 s | 6 s |

**Verfehlt:**
- **SC-001**: Die gegnerische 15 und 11 schwanken zwischen ähnlichen Lesarten (75, 71, 37) und bleiben unbekannt.
- **SC-003**: Die meisten Spurstücke zeigen nie lesbar den Rücken; Nummern allein können sie nicht
  verbinden.

**Nächste Schritte:**
- R9 Stufe 1 mit beiden Szenen und einer weiteren Runde;
- R9 Stufe 2 (einige Rücken von Hand beschriften);
- für SC-003 Stufe 3 (Zusammenführen über Aussehen und Weg) als eigenes Feature.
