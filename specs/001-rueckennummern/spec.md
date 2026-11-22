# Feature Specification: Rückennummern aus dem Video

**Feature Branch**: `001-rueckennummern`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Rückennummern und Spieleridentität selbst aus dem Videostream bestimmen, ohne Veo-Daten. Für jede eigene Spielerspur die Rückennummer aus den Videobildern lesen, mit einem eigenen, lokal laufenden Ziffernerkenner (keine externen Dienste, keine Bilder der Jugendspieler verlassen den Rechner). Spuren mit gleicher Mannschaft und gleicher Nummer zu einem Spieler zusammenführen, damit ein Spieler über die Szene eine Identität behält. Im Viewer erscheinen die gelesenen Nummern auf dem Trikot und in der Spielerauswahl. Ziel: Das Verfahren funktioniert später mit eigenen Kameras, die keine Veo-Daten liefern; Veo-Nummern dienen höchstens zum Nachmessen der Trefferquote."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rückennummer je Spieler aus dem Video (Priority: P1)

Ein Trainer öffnet eine ausgewertete Szene eines Heimspiels. Jeder Spieler, dessen Rücken in der Szene
irgendwann lesbar zu sehen ist, trägt die Nummer, die er im Video trägt. Die Nummer stammt allein aus
den Videobildern; Positionsdaten oder Nummern eines Fremdanbieters (Veo) fließen nicht ein.

**Why this priority**: Ohne Nummer ist ein Spieler nur „roter Spieler S3“. Trainer und Spieler wollen
sich und andere wiederfinden. Mit eigenen Kameras gibt es später keine fremde Quelle für Nummern mehr;
die Nummer aus dem Bild ist die einzige.

**Independent Test**: Eine der beiden Referenzszenen ohne Fremddaten auswerten und die vergebenen
Nummern mit einer Referenzliste (welcher Spieler trägt welche Nummer) vergleichen.

**Acceptance Scenarios**:

1. **Given** eine Szene, in der ein Spieler mehrfach mit dem Rücken zur Kamera läuft, **When** die Szene
   ausgewertet wird, **Then** trägt seine Figur seine echte Rückennummer.
2. **Given** ein Spieler, dessen Rücken nie lesbar zu sehen ist, **When** die Szene ausgewertet wird,
   **Then** bleibt er ohne Nummer und ist als „Nummer unbekannt“ erkennbar, statt eine geratene Nummer zu
   bekommen.
3. **Given** widersprüchliche Lesungen für einen Spieler (zum Beispiel 6 und 9), **When** keine Lesart
   deutlich überwiegt, **Then** bleibt die Nummer unbekannt.

---

### User Story 2 - Ein Spieler, eine Identität über die ganze Szene (Priority: P2)

Ein Spieler, der im Gedränge kurz verdeckt war, behält danach seine Identität. Wer im Viewer einem
Spieler folgt, bleibt bei ihm, statt dass die Figur verschwindet und als neuer, namenloser Spieler
wieder auftaucht.

**Why this priority**: Heute zerfällt ein Spieler über 25 Sekunden im Mittel in gut zwei Spuren. Das
stört beim Folgen eines Spielers und bei jeder späteren Auswertung (Laufwege, Statistiken).

**Independent Test**: In einer Referenzszene zählen, in wie viele getrennte Identitäten jeder echte
Spieler zerfällt, vorher und nachher.

**Acceptance Scenarios**:

1. **Given** zwei zeitlich getrennte Spurstücke derselben Mannschaft mit derselben gelesenen Nummer,
   **When** die Szene ausgewertet wird, **Then** erscheinen sie als ein Spieler.
2. **Given** zwei Spurstücke derselben Mannschaft mit derselben Nummer, die gleichzeitig auf dem Platz
   sind, **When** die Szene ausgewertet wird, **Then** werden sie nicht zusammengelegt, und höchstens eines
   behält die Nummer.

---

### User Story 3 - Nummern im Viewer (Priority: P3)

Im Viewer steht die gelesene Nummer auf dem Rücken der Figur, im Schild über dem Kopf und in der
Spielerauswahl („Wir 15“). Spieler ohne gelesene Nummer sind in der Auswahl ebenfalls wählbar und
deutlich als „unbekannt“ gekennzeichnet.

**Why this priority**: Macht P1 und P2 für Trainer und Spieler sichtbar; ohne P1 hat es nichts anzuzeigen.

**Independent Test**: Eine ausgewertete Szene im Viewer öffnen und prüfen, dass Rücken, Schild und
Auswahl dieselbe Nummer zeigen und unbekannte Spieler erkennbar sind.

**Acceptance Scenarios**:

1. **Given** ein Spieler mit gelesener Nummer 15, **When** er im Viewer ausgewählt wird, **Then** zeigen
   Trikot, Schild und Auswahl die 15.
2. **Given** ein Spieler ohne gelesene Nummer, **When** die Auswahl geöffnet wird, **Then** ist er dort
   wählbar und als unbekannt gekennzeichnet; auf seinem Trikot steht keine erfundene Nummer.

---

### User Story 4 - Trefferquote nachmessen (Priority: P4)

Wer das Verfahren verbessert, kann für eine Szene messen, wie viele Nummern stimmen, wie viele falsch
sind und wie viele unbekannt bleiben. Als Vergleich dient eine Referenzliste; für die vorhandenen
Veo-Aufnahmen darf das Veos Nummernzuordnung sein. Die Referenz beeinflusst das Ergebnis nicht.

**Why this priority**: Ohne Messung lässt sich nicht beurteilen, ob eine Änderung besser oder schlechter
liest. Nützlich, aber für Trainer nicht sichtbar.

**Independent Test**: Messung für eine Referenzszene ausführen; sie nennt richtige, falsche und
unbekannte Nummern. Eine Auswertung mit und ohne Referenz ergibt dieselben Nummern.

**Acceptance Scenarios**:

1. **Given** eine ausgewertete Szene und eine Referenzliste, **When** die Messung läuft, **Then** nennt sie
   je Mannschaft richtige, falsche und unbekannte Nummern.
2. **Given** dieselbe Szene ohne Referenzliste, **When** sie ausgewertet wird, **Then** sind die vergebenen
   Nummern dieselben wie mit Referenzliste.

### Edge Cases

- Ein Spieler zeigt nur die Vorderseite oder ist zu weit weg, sodass die Nummer nie lesbar ist.
- Ähnliche Ziffern: 6 und 9, 1 und 7, 3 und 8; zweistellige Nummern, bei denen eine Ziffer verdeckt ist
  (66 wird als 6 gelesen).
- Torhüter tragen andere Trikots und Nummernfarben als die Feldspieler.
- Schiedsrichter und Linienrichter haben keine Rückennummer und bekommen keine.
- Beide Mannschaften dürfen dieselbe Nummer haben; innerhalb einer Mannschaft trägt jede Nummer zur selben
  Zeit nur ein Spieler.
- Auswechslungen: Ein Spieler verlässt das Feld, ein anderer kommt; die Nummer gehört dann zu dem, der sie
  trägt.
- Auswechselspieler in Leibchen am Rand werden schon heute nicht als Spieler geführt und bekommen keine
  Nummer.
- Andere Trikot- und Nummernfarben (Gegner wechseln, Heimtrikot ändert sich); das Lesen darf nicht an den
  heutigen Farben hängen.
- Unscharfe Bilder bei schnellen Bewegungen und Bilder, in denen ein Arm oder ein anderer Spieler die
  Nummer verdeckt.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Das System MUST Rückennummern allein aus den Videobildern und der vorhandenen
  Kamerakalibrierung bestimmen; Fremddaten (Veo-Positionen, Veo-Nummern) dürfen das Ergebnis nicht
  beeinflussen.
- **FR-002**: Das Lesen MUST vollständig auf dem eigenen Rechner laufen; kein Bild und kein Bildausschnitt
  eines Spielers darf an einen externen Dienst gehen.
- **FR-003**: Das System MUST für jede Spielerspur eine Nummer mit einer Sicherheit angeben oder die Spur als
  „Nummer unbekannt“ führen; eine Nummer wird nur vergeben, wenn die Lesungen sie deutlich stützen.
- **FR-004**: Das System MUST verhindern, dass zwei Spieler derselben Mannschaft zur selben Zeit dieselbe
  Nummer tragen.
- **FR-005**: Das System MUST Spurstücke derselben Mannschaft mit derselben Nummer, die nicht gleichzeitig
  auf dem Platz sind, zu einem Spieler zusammenführen.
- **FR-006**: Schiedsrichter und Linienrichter MUST ohne Nummer bleiben.
- **FR-007**: Der Viewer MUST die gelesene Nummer auf dem Trikot, im Schild über dem Kopf und in der
  Spielerauswahl zeigen; Spieler ohne Nummer MUST wählbar und als unbekannt gekennzeichnet sein, ohne
  erfundene Nummer auf dem Trikot.
- **FR-008**: Das System MUST eine Messung bereitstellen, die vergebene Nummern mit einer Referenzliste
  vergleicht (richtig, falsch, unbekannt je Mannschaft); die Referenzliste darf die Vergabe nicht verändern.
- **FR-009**: Bildausschnitte und Zwischenergebnisse MUST lokal bei den Rohdaten bleiben und nicht in die
  für den Viewer veröffentlichten Daten gelangen; der Viewer erhält nur Nummern.
- **FR-010**: Das Lesen MUST unabhängig von bestimmten Trikot- und Nummernfarben funktionieren.
- **FR-011**: Eine Referenzszene von 25 Sekunden MUST mit dem Lesen der Nummern höchstens 5 Minuten länger
  ausgewertet werden als heute, auf der vorhandenen Hardware.
- **FR-012**: Vor der Auswertung MUST optional eine Liste der Nummern angegeben werden können, die eine
  Mannschaft im Spiel trägt (Kader); ist sie angegeben, vergibt das System nur Nummern aus der Liste. Ohne
  Liste sind alle Nummern von 1 bis 99 möglich. Namen werden nicht erfasst.

### Key Entities *(include if feature involves data)*

- **Spielerspur**: zusammenhängendes Stück, in dem eine Person auf dem Platz verfolgt wurde; hat Mannschaft,
  Zeitraum und Lage je Bild (gibt es schon).
- **Nummernlesung**: eine einzelne Lesung aus einem Videobild; gehört zu einer Spur, hat gelesene Nummer,
  Sicherheit und Zeitpunkt.
- **Spieler**: eine oder mehrere Spurstücke derselben Person; hat Mannschaft, Nummer (oder unbekannt) und
  die Sicherheit der Nummer.
- **Kader** (optional): Nummern, die eine Mannschaft im Spiel trägt.
- **Referenzliste** (nur für die Messung): welche Nummer zu welchem Spieler gehört, zum Beispiel aus Veo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In beiden Referenzszenen bekommen mindestens 80 % der Feldspieler, deren Rücken in der Szene
  mindestens einmal gut sichtbar ist, ihre richtige Nummer.
- **SC-002**: Höchstens 5 % der Spieler in den Referenzszenen tragen eine falsche Nummer (lieber unbekannt
  als falsch).
- **SC-003**: Ein echter Spieler zerfällt über eine 25-Sekunden-Szene im Mittel in höchstens 1,3 Identitäten
  (heute rund 2,1).
- **SC-004**: In keinem Bild tragen zwei Spieler derselben Mannschaft dieselbe Nummer.
- **SC-005**: Die Auswertung einer 25-Sekunden-Szene dauert mit dem Lesen der Nummern höchstens 5 Minuten
  länger als heute.
- **SC-006**: Die für den Viewer veröffentlichten Daten enthalten keine Bildausschnitte von Spielern; beim
  Auswerten geht keine Verbindung mit Bilddaten nach außen.

## Assumptions

- Bearbeitet werden vorerst nur Heimspiele auf dem eigenen Platz; die beiden Referenzszenen sind die
  Szenen ab Videosekunde 705 und 722 des Spiels vom 2026-11-01.
- Die Rückennummer steht groß auf dem Rücken; Nummern auf Brust oder Hose werden nicht gelesen.
- Lesbar ist eine Nummer erst ab einer gewissen Größe im Bild (bei den Veo-Aufnahmen etwa ab 28 Pixel
  Rückenhöhe); weiter entfernte Spieler bleiben oft unbekannt. Eigene Kameras mit höherer Auflösung sollen
  das später verbessern.
- Für die Messung an den vorhandenen Aufnahmen gilt Veos Nummernzuordnung als Referenz, obwohl Veo selbst
  Fehler macht; Abweichungen werden stichprobenartig am Video geprüft.
- Fertige, allgemeine Texterkennung reicht für so kleine Ziffern nicht (Test: etwa 4 von 16 Rücken
  richtig); es braucht einen auf Rückennummern zugeschnittenen Erkenner.
- Das eigene Spielertracking aus der vorigen Arbeit (ohne Veo) ist die Grundlage; seine Spuren werden
  weiterverwendet.
- Spielernamen gehören nicht zu diesem Feature (Daten von Minderjährigen); es bleibt bei Nummern.
