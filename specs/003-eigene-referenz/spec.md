# Feature Specification: Eigene Referenz statt Veo

**Feature Branch**: `003-eigene-referenz`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Eigene Referenz statt Veo: Messungen (Identität je Spieler, falsch zugeordnete Zeit, Spurwechsel, Rückennummern, Lage am Boden) sollen gegen eine selbst erstellte Referenz laufen, Veo nur noch als zweite Meinung daneben. Dazu ein lokales Markierwerkzeug im Browser: zeigt Videobilder einer Szene in Stichproben (etwa alle 2 s) mit den erkannten Boxen, schlägt unsere Zuordnung (Spieler, Mannschaft, Nummer) vor, der Nutzer korrigiert nur; rund 10–15 Minuten je Szene. Die Lage am Boden wird ohne Veo über die Platzgeometrie geprüft (Fußpunkte an Platzlinien), um zu klären, ob der Tiefenversatz von rund 0,9 m zwischen Szene und Veo ein Fehler der Szene ist. Bilder Minderjähriger bleiben lokal, Markierungen enthalten keine Namen. Außerdem die letzten Veo-Abhängigkeiten im Betrieb ohne Veo entfernen: Startwerte der Kamerakalibrierung (Ecken aus Veo) und Spieluhr aus dem Veo-Basisspiel."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Eine Szene selbst markieren (Priority: P1)

Der Trainer öffnet eine ausgewertete Szene im Markierwerkzeug auf seinem eigenen Rechner. Das Werkzeug zeigt
Stichprobenbilder aus dem Video, etwa alle 2 Sekunden, mit allen erkannten Personen auf dem Platz. Zu jeder
Person schlägt es vor, wer sie ist: Mannschaft, Spieler der Szene und Rückennummer, soweit bekannt. Der
Trainer bestätigt richtige Vorschläge mit einem Klick und korrigiert falsche. Zwischen zwei Stichproben kann
er das Video abspielen, um einem Spieler mit den Augen zu folgen. Am Ende liegt eine eigene Referenz der
Szene vor: Wer war wann wo.

**Why this priority**: Ohne eigene Referenz lässt sich nicht sagen, ob eine Änderung an Tracking, Nummern
oder Identität wirklich besser ist oder nur besser zu Veo passt. Veo ist nicht immer zuverlässig und kennt
nur Spieler, denen es selbst eine Nummer gegeben hat. Alle weiteren Verbesserungen hängen an dieser
Grundlage.

**Independent Test**: Eine der beiden Referenzszenen vollständig markieren und dabei die Zeit stoppen.
Danach prüfen, dass jede Person auf dem Platz in jeder Stichprobe eine Angabe hat (Person oder „unklar“)
und dass die Referenz ohne Bilder und ohne Namen gespeichert ist.

**Acceptance Scenarios**:

1. **Given** eine ausgewertete Szene, **When** der Trainer das Markierwerkzeug öffnet, **Then** sieht er die
   erste Stichprobe mit allen erkannten Personen auf dem Platz und je einem Vorschlag.
2. **Given** ein Vorschlag ist richtig, **When** der Trainer ihn bestätigt, **Then** ist die Person markiert,
   ohne dass er etwas eintippen muss.
3. **Given** das Tracking hat zwei Spieler vertauscht, **When** der Trainer in der nächsten Stichprobe die
   Person umbenennt, **Then** gilt die Korrektur nur für diese Person ab dieser Stichprobe; spätere Vorschläge
   übernehmen die Korrektur.
4. **Given** eine Person ist auf dem Bild nicht sicher zu erkennen, **When** der Trainer „unklar“ wählt,
   **Then** zählt diese Stelle bei der Messung nicht.
5. **Given** der Trainer unterbricht die Arbeit, **When** er das Werkzeug später wieder öffnet, **Then** sind
   alle bisherigen Markierungen erhalten, und er macht dort weiter.

---

### User Story 2 - Gegen die eigene Referenz messen (Priority: P2)

Nach dem Markieren misst die Auswertung eine Szene gegen die eigene Referenz:
- in wie viele Spieler der Szene eine echte Person zerfällt;
- wie viel Zeit eines Spielers zu einer anderen Person gehört;
- wie oft ein Spieler die Person wechselt;
- wie viele Spieler die richtige, falsche oder keine Nummer tragen.

Veo steht nur als zweite Meinung daneben. Wo Veo und die eigene Referenz sich widersprechen, listet der
Bericht die Stellen zum Nachsehen.

**Why this priority**: Das ist der eigentliche Nutzen der Referenz. Die Kennzahlen aus Feature 001 und 002
werden damit ohne Veo überprüfbar.

**Independent Test**: Für eine markierte Szene den Bericht erzeugen. Er enthält alle Kennzahlen aus eigener
Referenz. Fehlen die Veo-Daten ganz, entsteht derselbe Bericht ohne die Veo-Spalte.

**Acceptance Scenarios**:

1. **Given** eine markierte Szene, **When** die Messung läuft, **Then** stammen alle Kennzahlen aus der eigenen
   Referenz.
2. **Given** Veo-Daten liegen vor, **When** die Messung läuft, **Then** stehen die Veo-Werte als zweite Spalte
   daneben, und Stellen, an denen Veo und die eigene Referenz verschiedene Personen sehen, werden aufgelistet.
3. **Given** Veo-Daten fehlen, **When** die Messung läuft, **Then** entsteht der Bericht trotzdem, nur ohne
   Veo-Spalte.
4. **Given** eine Person, die Veo nicht kennt (ohne Veo-Nummer), **When** sie markiert ist, **Then** zählt sie
   in der Messung mit.
5. **Given** eine Szene ist nur teilweise markiert, **When** die Messung läuft, **Then** werden nur markierte
   Stichproben gezählt, und der Bericht nennt den Anteil.

---

### User Story 3 - Lage am Boden ohne Veo prüfen (Priority: P3)

Die Lage der Spieler am Boden wird an der Platzgeometrie geprüft. Steht ein Spieler mit dem Fuß auf einer
Platzlinie, ist seine wahre Lage auf dieser Linie bekannt. Der Abstand der gerechneten Lage zur Linie zeigt,
wie genau sie ist, vor allem in der Tiefe, also in Blickrichtung der Kamera. Damit wird geklärt, ob der
Versatz von rund 0,9 m zwischen fertiger Szene und Veo ein Fehler der Szene ist, ein Fehler von Veo oder ein
Unterschied in der Bezugsstelle am Körper.

**Why this priority**: Die Messung aus Feature 002 musste diesen Versatz herausrechnen, ohne zu wissen, wer
recht hat. Liegt die Szene falsch, wirkt das auf Laufwege, Ballkontakte und das Erkennen von Spurwechseln.

**Independent Test**: Für beide Referenzszenen die Stellen sammeln, an denen ein Fuß sichtbar auf einer
Linie steht. Für die fertige Szene, die rohen Spuren und, falls vorhanden, Veo jeweils den Tiefenfehler
angeben.

**Acceptance Scenarios**:

1. **Given** ein Spieler steht mit einem Fuß auf einer Seiten-, Tor- oder Strafraumlinie, **When** die
   Prüfung läuft, **Then** wird der Abstand seiner gerechneten Lage zur Linie in Tiefe und quer dazu
   ausgewiesen.
2. **Given** genug solche Stellen je Szene, **When** die Prüfung läuft, **Then** nennt der Bericht für jede
   Lagequelle den mittleren Tiefenfehler mit seiner Streuung und sagt, welche Quelle am genauesten liegt.
3. **Given** die Prüfung zeigt einen festen Tiefenfehler der fertigen Szene, **When** er behoben oder
   begründet ist, **Then** misst die Auswertung ohne herausgerechneten Versatz.

---

### User Story 4 - Betrieb ganz ohne Veo (Priority: P4)

Eine Szene lässt sich auswerten, ohne dass irgendeine Veo-Datei vorliegt. Die Kamerakalibrierung startet von
eigenen Platzpunkten statt von den in Veo angeklickten Ecken. Spielabschnitte, Anstoßzeit und Uhr, Platzmaße
und Mannschaftsnamen kommen aus einer eigenen kleinen Spielbeschreibung statt aus dem Veo-Basisspiel.

**Why this priority**: Mit eigenen Kameras gibt es keine Veo-Daten. Heute hängt der Betrieb ohne Veo noch am
Veo-Basisspiel und an Veos Ecken. Der Umfang ist klein, aber er schließt die letzte Lücke.

**Independent Test**: Die Veo-Daten einer Aufnahme unzugänglich machen und eine Referenzszene vollständig
auswerten. Das Ergebnis entspricht dem bisherigen, und die Uhr im Viewer zeigt die richtige Spielzeit.

**Acceptance Scenarios**:

1. **Given** keine Veo-Datei ist vorhanden, **When** eine Szene ausgewertet wird, **Then** läuft die
   Auswertung durch, und die Szene im Viewer gleicht der bisherigen.
2. **Given** eine eigene Spielbeschreibung mit Anstoßzeiten im Video, **When** eine Szene ausgewertet wird,
   **Then** zeigt der Viewer die richtige Spielzeit und den richtigen Spielabschnitt.
3. **Given** eine neue Aufnahme ohne Veo, **When** die Kamera kalibriert wird, **Then** genügen eigene
   Platzpunkte als Start.

### Edge Cases

- **Person ohne Box:** Ein Spieler ist auf dem Bild zu sehen, aber nicht erkannt (verdeckt, liegend). Er kann
  als „fehlt“ markiert werden; das zählt als verpasste Erkennung, nicht als falsche Identität.
- **Box mit zwei Personen:** Eine Box umfasst zwei Spieler im Zweikampf. Sie wird als „zwei Personen“
  markiert und zählt nicht für die Identität.
- **Unbekannte Personen:** Ohne lesbare Nummer bekommt eine Person eine neutrale Kennung (etwa „Wir A“,
  „Gegner C“). Dieselbe Person behält ihre Kennung über alle Stichproben der Szene.
- **Torhüter und Schiedsrichter:** werden als eigene Rollen markiert.
- **Auswechslung in der Szene:** Ein Spieler geht, ein anderer kommt. Das sind zwei Personen, auch bei
  ähnlichem Aussehen.
- **Widerspruch in der eigenen Referenz:** Dieselbe Kennung steht in einer Stichprobe an zwei Stellen, oder
  zwei Personen derselben Mannschaft tragen dieselbe Nummer. Das Werkzeug weist darauf hin, bevor gespeichert
  wird.
- **Neue Auswertung nach dem Markieren:** Nach einer Änderung an Tracking oder Identität passen die
  Vorschläge nicht mehr zur alten Referenz. Die Referenz bleibt gültig, weil sie an Bild und Box hängt, nicht
  an Spielernamen der Auswertung.
- **Andere Erkennung:** Werden die Personen neu erkannt und die Boxen ändern sich, bleibt die Referenz über
  die Lage im Bild zuordenbar. Was nicht mehr zuordenbar ist, wird gemeldet.
- **Fuß knapp neben der Linie:** Nur Stellen, an denen der Fuß sichtbar auf der Linie steht, zählen für die
  Lageprüfung. Im Zweifel wird die Stelle nicht verwendet.
- **Linienbreite:** Platzlinien sind rund 10–12 cm breit. Das bestimmt die erreichbare Genauigkeit der
  Lageprüfung quer zur Linie.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Das System MUST ein Markierwerkzeug bereitstellen, das lokal auf dem Rechner des Nutzers läuft
  und Stichprobenbilder einer Szene mit den erkannten Personen auf dem Platz zeigt. Der Abstand der
  Stichproben ist einstellbar, voreingestellt sind 2 Sekunden.
- **FR-002**: Das Werkzeug MUST zu jeder Person einen Vorschlag aus der Auswertung zeigen (Mannschaft oder
  Rolle, Kennung, Nummer). Ein richtiger Vorschlag MUST sich mit einer Handlung bestätigen lassen.
- **FR-003**: Das Werkzeug MUST erlauben, eine Person umzubenennen, als „unklar“, „zwei Personen“ oder „fehlt“
  zu markieren und ihr eine Nummer zu geben. Eine Korrektur MUST in den folgenden Stichproben als Vorschlag
  übernommen werden.
- **FR-004**: Das Werkzeug MUST das Video zwischen zwei Stichproben abspielen können, damit der Nutzer einer
  Person mit den Augen folgen kann.
- **FR-005**: Markierungen MUST laufend gespeichert werden und nach einer Unterbrechung erhalten bleiben.
- **FR-006**: Die Referenz MUST an Bild und Lage im Bild hängen, nicht an Namen der Auswertung, damit sie nach
  einer neuen Auswertung gültig bleibt.
- **FR-007**: Die Referenz MUST NOT Bilder, Bildausschnitte, Namen oder andere Angaben enthalten, die eine
  Person außerhalb der Szene erkennbar machen. Sie enthält nur Bild, Lage, Rolle, neutrale Kennung und
  Nummer. Sie bleibt lokal bei den Rohdaten.
- **FR-008**: Bilder und Video MUST den Rechner nicht verlassen. Das Werkzeug lädt nichts aus dem Netz nach,
  das Bilder sehen könnte, und sendet nichts.
- **FR-009**: Die Messung MUST Identitäten je Person, falsch zugeordnete Zeit, Personenwechsel innerhalb eines
  Spielers und richtige, falsche und fehlende Nummern gegen die eigene Referenz bestimmen. Sie zählt auch
  Personen, die Veo nicht kennt.
- **FR-010**: Die Messung MUST ohne Veo-Daten laufen. Liegen Veo-Daten vor, MUST sie die Veo-Werte als zweite
  Spalte zeigen und Stellen auflisten, an denen Veo und die eigene Referenz verschiedene Personen sehen.
- **FR-011**: Das System MUST die Lage am Boden an Stellen prüfen, an denen ein Fuß sichtbar auf einer bekannten
  Platzlinie steht. Es gibt den Fehler in Tiefe und quer zur Blickrichtung je Lagequelle an (fertige Szene,
  rohe Spuren, Veo falls vorhanden).
- **FR-012**: Ist der Tiefenfehler der fertigen Szene geklärt, MUST die Messung ohne pauschal herausgerechneten
  Versatz auskommen. Bleibt ein Versatz nötig, MUST er aus der eigenen Lageprüfung stammen, nicht aus Veo.
- **FR-013**: Die Auswertung einer Szene MUST ohne jede Veo-Datei laufen. Spielabschnitte, Anstoßzeiten, Uhr,
  Platzmaße, Mannschaftsnamen und -farben für den Viewer kommen aus einer eigenen Spielbeschreibung.
- **FR-014**: Die Kamerakalibrierung MUST ohne Veos angeklickte Ecken starten können, allein aus eigenen
  Platzpunkten im Bild.
- **FR-015**: Das Werkzeug MUST auf Widersprüche hinweisen: dieselbe Kennung zweimal in einer Stichprobe,
  dieselbe Nummer bei zwei Personen einer Mannschaft, eine Kennung in zwei Mannschaften.

### Key Entities *(include if feature involves data)*

- **Stichprobe**: ein Bild der Szene, in dem alle Personen auf dem Platz markiert werden.
- **Markierung**: eine Person in einer Stichprobe. Sie hat Lage im Bild, Rolle (Feldspieler, Torhüter,
  Schiedsrichter), Mannschaft, neutrale Kennung, Nummer (oder unbekannt) und einen Zustand (bestätigt,
  korrigiert, unklar, zwei Personen, fehlt).
- **Referenz einer Szene**: alle Markierungen einer Szene, mit Stand der Bearbeitung. Gehört zu Video und
  Erkennungen dieser Szene.
- **Linienstelle**: ein Fuß, der sichtbar auf einer bekannten Platzlinie steht, mit der gerechneten Lage aus
  jeder Quelle.
- **Spielbeschreibung**: Spielabschnitte mit Anstoßzeit im Video, Platzmaße, Mannschaften mit Namen und Farbe
  für den Viewer. Keine Personennamen.
- **Messbericht**: Kennzahlen aus eigener Referenz, Veo als zweite Spalte, Liste der Widersprüche, Ergebnis der
  Lageprüfung.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Eine 25-Sekunden-Szene ist in höchstens 15 Minuten vollständig markiert.
- **SC-002**: In einer vollständig markierten Szene hat jede erkannte Person auf dem Platz in jeder Stichprobe
  eine Angabe; höchstens 10 % der Markierungen sind „unklar“.
- **SC-003**: Beide Referenzszenen (705 und 722) sind markiert, und für beide liegt ein Messbericht mit allen
  Kennzahlen aus eigener Referenz vor, mit und ohne Veo-Daten.
- **SC-004**: Ein zweites Markieren von 3 Stichproben je Szene durch dieselbe Person stimmt in mindestens 95 %
  der Markierungen mit dem ersten überein. Die Referenz ist also wiederholbar.
- **SC-005**: Die Lageprüfung findet je Szene mindestens 20 Linienstellen und nennt für jede Lagequelle den
  mittleren Tiefenfehler. Die Frage, ob der Versatz von rund 0,9 m ein Fehler der Szene ist, ist beantwortet.
- **SC-006**: Mit unzugänglichen Veo-Daten läuft die Auswertung beider Szenen durch. Lage, Spieler und Nummern
  gleichen dem Lauf mit Veo-Daten, und die Uhr zeigt dieselbe Spielzeit.
- **SC-007**: Kein Bild und keine Markierung verlässt den Rechner. Die Referenzdateien enthalten keine Bilddaten
  und keine Namen.

## Assumptions

- **Grundlage:** Es gilt der Stand aus Feature 002: eigenes Tracking, Trennen an Spurwechseln, vorsichtiges
  Verbinden, gelesene Nummern.
- **Wer markiert:** Der Trainer oder ein Helfer aus dem Verein, der die Mannschaften kennt. Er markiert am
  eigenen Rechner. Mehrere Bearbeiter gleichzeitig sind nicht nötig.
- **Stichproben statt jedes Bild:** Alle 2 Sekunden genügen, weil Identitätsfehler mehrere Sekunden dauern. Was
  zwischen zwei Stichproben passiert, zeigt die Messung nicht; das Abspielen hilft nur beim Markieren.
- **Neutrale Kennungen:** Personen ohne lesbare Nummer heißen nur innerhalb der Szene „Wir A“, „Gegner B“ usw.
  Es werden keine Namen erfasst.
- **Linsendaten der Veo-Kamera:** Brennweite, Verzeichnung und Lage der beiden Linsen sind Eigenschaften der
  Kamera und kommen mit der Aufnahme. Sie bleiben für Veo-Aufnahmen eine Eingabe. Eigene Kameras brauchen eine
  eigene Linsenkalibrierung; das ist ein eigenes Feature. Ersetzt werden hier nur Veos angeklickte Ecken und
  das Veo-Basisspiel.
- **Kulisse und Luftbild:** Sie werden schon heute aus dem Video gerechnet und bleiben, wie sie sind.
- **Linien als Maßstab:** Die Platzlinien liegen dort, wo die Kalibrierung sie sieht. Wie genau die
  Kalibrierung selbst ist, prüft diese Lageprüfung mit; reicht sie nicht, ist das ein Befund, kein Fehler der
  Prüfung.
- **Referenzszenen:** die Szenen ab Videosekunde 705 und 722 des Heimspiels vom 2026-11-01. Weitere Szenen
  können später mit demselben Werkzeug dazukommen.
