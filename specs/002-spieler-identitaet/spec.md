# Feature Specification: Eine Identität je Spieler über die ganze Szene

**Feature Branch**: `002-spieler-identitaet`

**Created**: 2026-11-23

**Status**: Draft

**Input**: User description: "Spieleridentität über die ganze Szene ohne Veo: Spurstücke derselben Person zusammenführen, auch wenn ihr Rücken nie lesbar war. Heute zerfällt ein echter Spieler über eine 25-Sekunden-Szene im Mittel in rund 2,2 Identitäten (Figur verschwindet und taucht als neuer Spieler wieder auf). Zusammenführen anhand von Aussehen aus dem Video (Trikot, Hose, Stutzen, Haut- und Haarfarbe, Körpergröße), Laufweg (wohin konnte der Spieler in der Lücke kommen) und vorhandenen sicheren Rückennummern als Ankern; Mannschaftszugehörigkeit bleibt. Lieber getrennt lassen als zwei verschiedene Spieler zu einem machen. Zusammengeführte Spieler sammeln die Rückenlesungen aller ihrer Stücke, damit mehr Spieler ihre Nummer bekommen. Alles lokal, keine Bilder nach außen, Veo nur zum Nachmessen. Im Viewer bleibt eine Figur über Lücken dieselbe."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Einem Spieler über die ganze Szene folgen (Priority: P1)

Ein Trainer wählt im Viewer einen Spieler und folgt ihm durch die Szene. Wird der Spieler kurz verdeckt
(Zweikampf, Gedränge) oder vom Tracking verloren, taucht er danach als derselbe Spieler wieder auf. Er
bleibt in der Auswahl derselbe Eintrag, und die Kamera bleibt bei ihm, statt dass die Figur verschwindet
und ein neuer, namenloser Spieler erscheint.

**Why this priority**: Heute zerfällt ein echter Spieler über 25 Sekunden im Mittel in rund 2,2
Identitäten. Wer einem Spieler folgt, verliert ihn dabei mehrfach. Jede spätere Auswertung je Spieler,
etwa Laufwege oder Ballkontakte, braucht eine stabile Identität.

**Independent Test**: Für eine Referenzszene zählen, in wie viele getrennte Identitäten jeder echte
Spieler zerfällt, vorher und nachher. Dazu stichprobenartig im Viewer einzelnen Spielern über ihre
früheren Bruchstellen folgen.

**Acceptance Scenarios**:

1. **Given** ein Spieler wird im Zweikampf verdeckt und danach wieder erkannt, **When** die Szene
   ausgewertet wird, **Then** sind Teil vor und nach der Verdeckung ein Spieler.
2. **Given** zwei Spurstücke derselben Mannschaft, deren Lücke der Spieler laufend nicht überbrücken
   konnte, etwa 40 m in einer Sekunde, **When** die Szene ausgewertet wird, **Then** werden sie nicht
   zusammengeführt.
3. **Given** zwei Spurstücke, die zur selben Zeit an verschiedenen Orten zu sehen sind, **When** die Szene
   ausgewertet wird, **Then** werden sie nie zu einem Spieler.

---

### User Story 2 - Lieber getrennt als vertauscht (Priority: P2)

Wenn nicht klar ist, ob zwei Stücke zur selben Person gehören, etwa zwei Mitspieler im selben Trikot,
die sich im Gedränge kreuzen, bleiben sie getrennt. Ein Spieler darf nicht unbemerkt zu einem anderen
werden, denn eine falsche Verbindung verfälscht Laufwege und Nummern schlimmer als eine Lücke.

**Why this priority**: Eine falsche Verbindung ist im Viewer schwer zu erkennen und vergiftet alles
Weitere: Die Figur springt an eine andere Stelle, und die Nummer wandert zu einem anderen Spieler.

**Independent Test**: In den Referenzszenen messen, wie viel Zeit jedes zusammengeführten Spielers zu
einer anderen echten Person gehört als zu seiner Hauptperson.

**Acceptance Scenarios**:

1. **Given** zwei Mitspieler im gleichen Trikot laufen dicht aneinander vorbei und das Tracking
   verliert beide, **When** Aussehen und Weg keine eindeutige Zuordnung erlauben, **Then** bleiben die
   Stücke danach eigene Spieler.
2. **Given** zwei Stücke mit gelesenen, verschiedenen Rückennummern, **When** die Szene ausgewertet wird,
   **Then** werden sie nie zusammengeführt.
3. **Given** zwei Stücke verschiedener Mannschaften, **When** die Szene ausgewertet wird, **Then** werden
   sie nie zusammengeführt.

---

### User Story 3 - Mehr Spieler mit Nummer (Priority: P3)

Ein zusammengeführter Spieler sammelt die Rückenlesungen aller seiner Stücke. Spieler, deren Rücken in
jedem einzelnen Stück zu selten zu sehen war, bekommen so ihre Nummer. Bekannte Nummern werden zu Ankern:
Ein Stück, das zu einem Spieler mit Nummer gehört, trägt danach diese Nummer.

**Why this priority**: Heute bleiben Spieler mit gut sichtbarem Rücken unbekannt, weil jedes ihrer
Stücke für sich zu wenige Lesungen hat. Das hängt an P1 und verbessert das Ergebnis aus Feature 001.

**Independent Test**: In den Referenzszenen die Zahl der Spieler mit richtiger Nummer vorher und nachher
vergleichen. Die Zahl falscher Nummern darf dabei nicht steigen.

**Acceptance Scenarios**:

1. **Given** ein Spieler mit drei Stücken, die jedes für sich zu wenige Rückenlesungen haben,
   **When** die Stücke zusammengeführt werden, **Then** bekommt der Spieler seine Nummer, sofern die
   Lesungen zusammen klar sind.
2. **Given** ein Spieler mit sicherer Nummer und ein Stück ohne lesbaren Rücken, das nach Aussehen und
   Weg zu ihm gehört, **When** die Szene ausgewertet wird, **Then** trägt das Stück im Viewer diese
   Nummer.

### Edge Cases

- **Gleiches Trikot, gleiche Größe:** Zwei Mitspieler sehen sich bei rund 55 Pixeln Spielerhöhe kaum
  unterschiedlich aus. Das Aussehen allein reicht dann nicht, entscheiden müssen Weg und Nummer, sonst
  bleiben die Stücke getrennt.
- **Auswechslung:** Ein Spieler verlässt das Feld, ein anderer kommt mit gleichem Trikot an ähnlicher
  Stelle. Das sind zwei Personen.
- **Torhüter:** Er trägt ein anderes Trikot als seine Mannschaft und bleibt lange im Strafraum. Er wird
  nicht mit Feldspielern verbunden.
- **Schiedsrichter:** Zwei Schiedsrichter in gleicher Kleidung werden nicht zu einer Person.
- **Lange Lücke:** Ein Spieler ist lange nicht zu sehen, weil er am Bildrand außerhalb der Kamera oder
  lange verdeckt ist. Je länger die Lücke, desto mehr Orte sind möglich und desto vorsichtiger wird
  verbunden.
- **Doppelte Spuren:** Zwei Spurstücke folgen kurz derselben Person. Das ist eine Person, keine zwei
  gleichzeitig.
- **Licht:** Schatten und Gegenlicht ändern die Farben eines Trikots zwischen zwei Stücken.
- **Liegende Spieler:** Ein gestürzter oder liegender Spieler sieht anders aus als ein stehender; das
  darf eine Verbindung nicht verhindern.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Das System MUST Spurstücke derselben Person innerhalb einer Szene zu einem Spieler
  zusammenführen und dafür nur Videobilder, Kamerakalibrierung und daraus gewonnene Daten nutzen.
  Fremddaten (Veo-Positionen, Veo-Identitäten, Veo-Nummern) dürfen das Ergebnis nicht beeinflussen.
- **FR-002**: Das System MUST für eine Verbindung Aussehen (Kleidung, Haut- und Haarfarbe,
  Körpergröße), Weg (ist die Lücke laufend zu schaffen) und gelesene Rückennummern berücksichtigen.
- **FR-003**: Das System MUST NOT Stücke verbinden, die gleichzeitig an verschiedenen Orten zu sehen
  sind, die zu verschiedenen Mannschaften gehören, die verschiedene sichere Rückennummern tragen oder
  deren Lücke laufend nicht zu überbrücken ist.
- **FR-004**: Das System MUST unsichere Verbindungen unterlassen. Lassen Aussehen, Weg und Nummer
  mehrere Zuordnungen ähnlich gut zu, bleiben die Stücke getrennt.
- **FR-005**: Das System MUST die Rückenlesungen aller Stücke eines zusammengeführten Spielers gemeinsam
  zur Nummernvergabe heranziehen. Die Regeln aus Feature 001 bleiben bestehen: keine Nummer doppelt zur
  selben Zeit je Mannschaft, und lieber unbekannt als falsch.
- **FR-006**: Torhüter, Feldspieler und Schiedsrichter MUST getrennte Gruppen bleiben; über diese
  Grenzen wird nicht verbunden.
- **FR-007**: Der Viewer MUST einen zusammengeführten Spieler als eine Figur mit einem Eintrag in der
  Spielerauswahl zeigen. Über kurze Lücken bewegt sich die Figur plausibel weiter; über lange Lücken
  darf sie ausgeblendet sein, kehrt aber als dieselbe Figur zurück.
- **FR-008**: Das System MUST eine Messung bereitstellen, die gegen eine Referenz ermittelt:
  - Identitäten je echtem Spieler;
  - den Anteil falsch verbundener Zeit;
  - die Zahl der Spieler mit richtiger und falscher Nummer.

  Die Referenz darf das Ergebnis nicht verändern.
- **FR-009**: Bilder und Bildausschnitte MUST lokal bleiben. In die Viewer-Daten gelangen keine neuen
  Bilddaten über die bestehenden Videotexturen hinaus.
- **FR-010**: Die Verbindung MUST unabhängig von bestimmten Trikotfarben funktionieren; sie vergleicht
  Stücke untereinander statt mit festen Farben.

### Key Entities *(include if feature involves data)*

- **Spurstück**: ein zusammenhängendes Stück, in dem das Tracking eine Person verfolgt hat. Es hat
  Mannschaft, Zeitraum, Lage je Bild und Rückenlesungen; das gibt es schon.
- **Aussehensbeschreibung**: je Spurstück zusammengefasst, wie die Person im Video aussieht:
  - Farben von Trikot, Hose, Stutzen, Haut und Haaren;
  - Körpergröße;
  - wie sicher die Beschreibung ist, also aus wie vielen und wie guten Bildern sie stammt.
- **Verbindung**: Entscheidung, dass zwei Stücke dieselbe Person sind, mit ihrer Begründung (Aussehen,
  Weg, Nummer) und Sicherheit.
- **Spieler**: ein oder mehrere verbundene Stücke, mit Mannschaft und Nummer (oder unbekannt); das gibt
  es schon aus Feature 001.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ein echter Spieler zerfällt in beiden Referenzszenen im Mittel in höchstens 1,5
  Identitäten (heute 2,24 und 2,17).
- **SC-002**: Höchstens 3 % der Spielerzeit gehören zu einer anderen echten Person als der Hauptperson
  des Spielers (falsch verbunden). Gemessen wird über alle Spieler einer Szene.
- **SC-003**: Mindestens so viele Spieler wie heute tragen ihre richtige Nummer (je Szene 7), möglichst
  mehr. Höchstens 5 % der Spieler tragen eine falsche Nummer.
- **SC-004**: Bei 10 Stichproben je Szene, in denen ein Spieler im Viewer über eine frühere Bruchstelle
  verfolgt wird, bleibt die Kamera in mindestens 8 Fällen beim richtigen Spieler.
- **SC-005**: Die Auswertung einer 25-Sekunden-Szene dauert höchstens 5 Minuten länger als heute.
- **SC-006**: Die Viewer-Daten enthalten keine neuen Bilddaten von Spielern, und beim Auswerten geht
  keine Verbindung mit Bilddaten nach außen.

## Assumptions

- **Grundlage:** Es gilt der Stand aus Feature 001: eigenes Tracking ohne Veo, gelesene Rückennummern
  mit Sicherheit, Videotexturen je Spieler. Daraus wird weitergebaut.
- **Umfang:** Verbunden wird nur innerhalb einer Szene von rund 25 Sekunden, nicht über mehrere Szenen
  oder ein ganzes Spiel. Das wäre ein eigenes Feature.
- **Referenzszenen:** die Szenen ab Videosekunde 705 und 722 des Heimspiels vom 2026-11-01. Veos Spuren
  dienen nur als Referenz und sind selbst nicht fehlerfrei. Abweichungen werden stichprobenartig am Video
  geprüft.
- **Ziel 1,5 statt 1,3:** Das ursprüngliche Ziel aus Feature 001 war 1,3. Hier gilt bewusst 1,5, weil
  einige Spieler den Bildbereich ganz verlassen oder sehr lange verdeckt sind und eine Verbindung dann
  geraten wäre. Wo die Wahl zwischen 1,3 und mehr falschen Verbindungen besteht, gilt SC-002 vor SC-001.
- **Sichtbarkeit:** Ist ein Spieler eine Weile gar nicht zu sehen, muss die Figur in der Lücke nicht
  sichtbar sein. Wichtig ist, dass sie danach als dieselbe zurückkehrt.
- **Kleine Spieler im Bild:** Die Spieler sind im Video nur rund 55 Pixel hoch. Gesichter werden weder
  erkannt noch verwendet, es geht nur um grobe Farben und Größe.
- **Keine Namen:** Es werden keine Namen und keine biometrischen Merkmale gespeichert, die eine Person
  außerhalb der Szene wiedererkennbar machen.
