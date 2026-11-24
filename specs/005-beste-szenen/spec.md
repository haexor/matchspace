# Feature Specification: Beste Szenen vor der Kamera

**Feature Branch**: `005-beste-szenen`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Beste Szenen vor der Veo-Kamera mit maximaler Genauigkeit: aus den Szenen, die sich
direkt vor der Kamera abspielen (Spieler rund 100–125 Pixel, Ball rund 8 Pixel hoch aufgelöst), das Maximum
herausholen, statt das ganze Spiel mittelmäßig darzustellen. Dribbling, Schusstechnik, Fouls und Zweikämpfe
sollen möglichst genau gemessen und auf die Figuren übertragen werden, Bild für Bild, offline. Texturen der
Spieler aus den Bildern, in denen sie der Kamera am nächsten sind. Gemessen wird gegen eine selbst erstellte
Referenz, Veo höchstens als zweite Meinung."

**Ziel und Umfang (Rückmeldung des Nutzers)**: Nicht das ganze Spiel soll perfekt dargestellt werden, sondern
aus einzelnen kurzen Szenen soll das Maximum herausgeholt werden, das mit diesem Video möglich ist. Die Szenen
sind eine Vorschau darauf, wie gut die Darstellung mit mehreren Videostreams werden könnte. Rechenzeit und
Handarbeit gehen deshalb in wenige Szenen (etwa drei bis fünf), nicht in die Breite. Der Szenenfinder dient
nur dazu, diese Szenen zu finden.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Die besten Szenen eines Spiels finden (Priority: P1)

Der Trainer gibt ein ganzes Spiel an und bekommt eine Rangliste der Szenen, an denen sich die Arbeit lohnt.
Eine Szene ist ein Zeitfenster von etwa 10 bis 30 Sekunden. Sie ist gut, wenn der Spieler am Ball nah an der
Kamera ist (die Figuren sind dort im Bild am größten), der Ball in den meisten Bildern zu sehen ist, ein
Ballführer, Pässe, Schüsse oder Zweikämpfe vorkommen und mehrere Spieler beteiligt sind. Zu jeder Szene zeigt
die Liste Zeit, Gesamtpunkte, die Einzelwerte, aus denen sie sich ergeben, und ein Standbild.

**Why this priority**: Ohne Auswahl wird Rechenzeit und Markierarbeit auf Szenen verbraucht, in denen das Bild
für die gewünschte Genauigkeit gar nicht reicht. Die Szenen nah an der Kamera sind der einzige Ort, an dem
Fußkontakt, Schusstechnik und Zweikampf überhaupt zu lesen sind.

**Independent Test**: Für ein ganzes Spiel die Rangliste erzeugen, die zehn bestbewerteten Szenen ansehen und
prüfen, dass in jeder ein Ballführer in der nahen Zone vorkommt und der Ball überwiegend sichtbar ist.
Dagegen stichprobenartig eine schlecht bewertete Szene ansehen, in der das nicht so ist.

**Acceptance Scenarios**:

1. **Given** ein ganzes Spiel liegt lokal als Video vor, **When** der Szenenfinder läuft, **Then** entsteht eine
   Rangliste mit mindestens 20 Szenen, jede mit Zeit, Punkten, Einzelwerten und Standbild.
2. **Given** die Rangliste, **When** der Trainer eine Szene wählt, **Then** kann er sie abspielen und zur
   weiteren Verarbeitung (Referenz, Auswertung) freigeben.
3. **Given** zwei Szenen mit gleichem Geschehen, **When** eine näher an der Kamera spielt, **Then** steht sie
   in der Rangliste weiter oben.
4. **Given** der Szenenfinder bewertet eine Szene, **When** der Ball im Fenster überwiegend nicht gefunden
   wurde, **Then** ist das als eigener Einzelwert ausgewiesen und zieht die Punkte merklich herunter.
5. **Given** mehrere benachbarte Zeitfenster zeigen dasselbe Geschehen, **When** die Rangliste entsteht,
   **Then** erscheint dieses Geschehen nur einmal, mit dem besten Zuschnitt.

---

### User Story 2 - Referenz für Ballkontakte selbst erstellen (Priority: P2)

Der Trainer öffnet eine freigegebene Szene im lokalen Markierwerkzeug (Feature 003) und markiert Bild für Bild
das Wichtigste am Ball: Ballkontakte (Zeitpunkt, welcher Spieler, welcher Fuß oder Körperteil), Pässe,
Schüsse, Ballverlust und Ballgewinn. Das Werkzeug erlaubt schrittweises Vor und Zurück um einzelne Bilder und
zeigt die Ballspur und die vorgeschlagenen Berührungen. Er korrigiert nur, was nicht stimmt. Die Markierungen
enthalten keine Namen und keine Bilder.

**Why this priority**: „Maximale Genauigkeit“ ist nur ein Wort, solange man sie nicht gegen etwas Eigenes
messen kann. Veo kennt keine Ballkontakte und ist an dieser Stelle auch keine zweite Meinung.

**Independent Test**: Eine Szene vollständig markieren, das Werkzeug schließen und wieder öffnen; alle
Markierungen sind erhalten, die Datei enthält keine Bilder und keine Namen.

**Acceptance Scenarios**:

1. **Given** eine freigegebene Szene, **When** der Trainer das Markierwerkzeug öffnet, **Then** kann er die
   Szene Bild für Bild durchgehen und einen Ballkontakt am genauen Bild setzen.
2. **Given** das Werkzeug schlägt Berührungen aus der Ballspur vor, **When** der Trainer einen Vorschlag
   bestätigt, verschiebt oder löscht, **Then** ist die Entscheidung gespeichert.
3. **Given** der Trainer markiert einen Kontakt, **When** er den Spieler wählt, **Then** reicht ein Klick auf
   die Box im Bild, und der Fuß (links, rechts, Kopf, Körper) kommt als Auswahl dazu.
4. **Given** der Ball ist im Bild nicht zu sehen, **When** der Trainer einen Kontakt setzt, **Then** kann er
   „Ball nicht erkennbar“ angeben, und der Kontakt zählt nur für das, was erkennbar ist.
5. **Given** die Szene wurde neu ausgewertet, **When** der Trainer das Werkzeug öffnet, **Then** bleiben seine
   Markierungen gültig.

---

### User Story 3 - Ball und Ballführung genau darstellen (Priority: P3)

Der Ball bewegt sich wie ein echter Ball: Er rollt und bremst auf dem Rasen, fliegt als Parabel mit Höhe,
springt auf. Ballkontakte, Pässe und Schüsse werden aus der Ballspur und den Fußbewegungen als Ereignisse
erkannt. Der Fuß trifft den Ball genau dann und dort, wo der Kontakt war, mit einer zum Ereignis passenden
Bewegung (Pass, Schuss, Annahme). Beim Dribbling läuft der Ball vor dem Spieler und wird nur alle paar
Schritte berührt, statt dauernd am Fuß zu kleben. Wo der Ball nicht zu sehen war, ist der Verlauf erschlossen
und als erschlossen gekennzeichnet.

**Why this priority**: Der Ball und der Umgang des Spielers mit ihm ist laut Nutzer das Wichtigste an der
ganzen Darstellung. Heute wird der Ball nur an den nächsten Fuß gezogen.

**Independent Test**: Für mindestens drei markierte Szenen die erkannten Kontakte mit der Referenz vergleichen:
Zeitfehler, verpasste und erfundene Kontakte, richtiger Spieler. Dazu die Flughöhe bei einem Flugball prüfen.

**Acceptance Scenarios**:

1. **Given** ein Pass, **When** die Szene dargestellt wird, **Then** verlässt der Ball den Fuß im Moment des
   Kontakts, rollt oder fliegt danach nach den Gesetzen der Physik und endet beim Empfänger oder am Boden.
2. **Given** ein hoher Ball, **When** die Szene dargestellt wird, **Then** hat er eine Flughöhe, die zur
   sichtbaren Spur passt, und landet dort, wo er im Bild landet.
3. **Given** ein Dribbling über mehrere Schritte, **When** die Szene dargestellt wird, **Then** hat der Ball
   zwischen den Berührungen sichtbaren Abstand zum Fuß und wird in den Berührungen vom Fuß getroffen.
4. **Given** der Ball ist über mehrere Bilder nicht gefunden, **When** die Szene dargestellt wird, **Then**
   zeigt der Viewer diesen Abschnitt erkennbar als erschlossen an.
5. **Given** eine markierte Szene, **When** die Messung läuft, **Then** nennt der Bericht Zeitfehler der
   Kontakte (Mittel und Streuung), Anteil gefundener Kontakte, Anteil erfundener Kontakte und Anteil mit
   richtigem Spieler und Fuß.

---

### User Story 4 - Aussehen der Spieler aus den besten Bildern (Priority: P4)

Jeder Spieler bekommt eine Textur, die über das ganze Spiel aus den Bildern gebaut wird, in denen er der
Kamera am nächsten war. Die Wiedererkennung über Szenen hinweg läuft über Rückennummer und das gelernte
Aussehen aus Feature 002 und 003. Die Rückennummer und der Trikotaufdruck sind, wo sie lesbar sind, in der
Textur enthalten. Die Figuren sehen dadurch deutlich weniger gleich aus.

**Why this priority**: Heute stammt die Textur je Szene aus Bildern mit 50 bis 120 Pixeln Spielerhöhe. Ein
Spieler läuft im Lauf eines Spiels mindestens einmal nah an der Kamera vorbei.

**Independent Test**: Für zwei Spieler die Textur aus dem ganzen Spiel mit der aus nur einer Szene vergleichen
(Auflösung, Schärfe, Rückennummer lesbar) und eine Szene mit beiden Texturen ansehen.

**Acceptance Scenarios**:

1. **Given** ein ganzes Spiel mit erkannter Identität je Spieler, **When** die Texturen gebaut werden,
   **Then** entsteht je Spieler eine Textur, die aus dessen nächsten Bildern stammt.
2. **Given** ein Spieler kommt nie nah an die Kamera, **When** die Texturen gebaut werden, **Then** erhält er
   eine Textur aus seinen besten vorhandenen Bildern, und der Bericht nennt das.
3. **Given** die Rückennummer eines Spielers ist lesbar, **When** die Textur entsteht, **Then** steht die
   Nummer an der richtigen Stelle auf dem Rücken.
4. **Given** eine Szene wird dargestellt, **When** der Spieler eine Textur aus dem ganzen Spiel hat, **Then**
   nutzt der Viewer diese statt der Textur aus der Szene.

---

### User Story 5 - Schuss, Dribbling und Zweikampf als echte Bewegung (Priority: P5)

Für die besten Szenen werden Schusstechnik, Passschwung, Dribbling, Körpertäuschung und Zweikampf Bild für
Bild aus den Nahaufnahmen gelesen und auf die Figuren übertragen. Fouls und Zweikämpfe werden aus den Bahnen
als Ereignisse erkannt (zwei Spieler sehr nah, Ball in der Nähe, Tempoänderung, ein Spieler geht zu Boden).
Die Beinbewegung am Kontakt kommt aus den Bildern, nicht aus einer festen Vorlage. Wo das Bild nicht reicht,
ist die Bewegung als erschlossen gekennzeichnet. Bewegungsvorlagen aus Fremdquellen dürfen nur genutzt werden,
wenn ihre Lizenz geprüft ist.

**Why this priority**: Das ist der anspruchsvollste Teil und baut auf Ball und Referenz auf. Er macht aus
„Figuren laufen herum“ eine erkennbare Spielhandlung.

**Independent Test**: Eine Szene mit Schuss und eine mit Zweikampf ansehen und mit dem Video vergleichen:
Schwungrichtung, Standbein, Treffpunkt am Ball, Kontaktzeit.

**Acceptance Scenarios**:

1. **Given** ein Schuss in einer Nahszene, **When** die Szene dargestellt wird, **Then** stimmen Schwungbein,
   Standbein und Treffpunkt am Ball mit den Gelenkpunkten im Video überein, nicht mit einer festen Vorlage.
2. **Given** ein Zweikampf, **When** die Szene dargestellt wird, **Then** sind beide Spieler an den Stellen
   des Kontakts in möglichen Haltungen, und kein Körper durchdringt den anderen.
3. **Given** ein Foul, **When** das Ereignis erkannt wurde, **Then** erscheint es in der Ereignisliste der
   Szene mit Zeit und beteiligten Spielern.
4. **Given** eine Bewegungsvorlage aus fremder Quelle, **When** sie benutzt werden soll, **Then** ist ihre
   Lizenz in der Dokumentation geprüft und eingetragen, sonst wird sie nicht verwendet.

---

### Edge Cases

- Der Ball ist über lange Zeit nicht zu sehen (verdeckt, weit weg): Es wird nicht erfunden, was der Ball
  gemacht hat, sondern ein kurzer, möglicher Verlauf eingezeichnet und als erschlossen markiert; über eine
  Mindestdauer hinaus wird nichts ergänzt.
- Mehrere Bälle im Bild (Reservebälle, Hütchen): Nur der Spielball zählt, wie in Feature 001.
- Der Spieler am Ball steht im Gedränge: Die Kontaktzuordnung kann unklar sein; solche Kontakte sind als
  unsicher markiert und zählen in der Messung nur mit, wo die Referenz sicher ist.
- Der Ball geht aus dem Bild (hoher Flug über den Bildrand): Der Flug endet im Bildrand und wird nicht
  geraten.
- Die Spieler erscheinen im Video am Rand einer Bildhälfte sehr klein: Szenen dort bekommen schlechte Punkte.
- Rückennummer nirgends lesbar: Die Textur bleibt ohne Nummer, die Nummer wird nicht erfunden.
- Das ganze Spielvideo ist sehr groß: Das Holen und Auswerten läuft in Abschnitten und kann unterbrochen und
  fortgesetzt werden.
- Eine Szene wird neu ausgewertet, nachdem Referenzmarkierungen existieren: Markierungen bleiben gültig, soweit
  sich die Zuordnung wiederfinden lässt.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Das System MUST ein ganzes Spiel in Zeitfenstern bewerten und eine Rangliste der besten Szenen
  liefern, mit Punkten, Einzelwerten und Standbild je Szene.
- **FR-002**: Die Bewertung MUST mindestens umfassen: Auflösung des Ballführers im Bild (Nähe zur Kamera),
  Anteil der Bilder mit gefundenem Ball, Dauer, Anzahl Ballkontakte und Zweikämpfe, Anzahl beteiligter
  Spieler.
- **FR-003**: Benachbarte Fenster mit demselben Geschehen MUST in der Rangliste zu einer Szene
  zusammengefasst werden.
- **FR-004**: Von einem Spielvideo MUST nur geholt werden, was gebraucht wird (Abschnitte der gewählten
  Szenen und, falls für Texturen nötig, weitere Abschnitte), nur lesend vom Anbieter, unterbrech- und
  fortsetzbar, und es MUST ausschließlich lokal liegen bleiben.
- **FR-005**: Der Szenenfinder MUST ohne Veo-Positionsdaten arbeiten; Veo-Daten dürfen höchstens als zweite
  Meinung dazugestellt werden.
- **FR-006**: Das Markierwerkzeug MUST Ballkontakte, Pässe, Schüsse, Ballverlust und -gewinn je Bild
  markierbar machen, mit Spieler (Box im Bild) und Körperteil (links, rechts, Kopf, Körper).
- **FR-007**: Das Markierwerkzeug MUST schrittweises Vor und Zurück um einzelne Bilder erlauben und
  Berührungen aus der Ballspur vorschlagen.
- **FR-008**: Markierungen MUST ohne Namen und ohne Bilder gespeichert werden und bei erneuter Auswertung einer
  Szene gültig bleiben, soweit sie sich wiederfinden lassen.
- **FR-009**: Der Ball MUST sich nach Ballphysik bewegen: Rollen mit Reibung, Flug als Parabel mit Höhe,
  Aufspringen mit Verlust.
- **FR-010**: Die Flughöhe MUST aus der sichtbaren Ballspur bestimmt werden und darf nicht erfunden werden;
  wo sie nicht bestimmbar ist, MUST sie als unbekannt behandelt und so dargestellt werden.
- **FR-011**: Ballkontakte, Pässe und Schüsse MUST als Ereignisse aus Ballspur und Fußbewegung erkannt und mit
  Zeit, Spieler und Körperteil ausgewiesen werden.
- **FR-012**: Beim Kontakt MUST der Fuß den Ball zur Kontaktzeit am Kontaktpunkt treffen; bei Pass, Schuss und
  Annahme MUST die Bewegung zum Ereignis passen.
- **FR-013**: Beim Dribbling MUST der Ball zwischen den Berührungen Abstand zum Fuß haben.
- **FR-014**: Abschnitte ohne gefundenen Ball MUST im Viewer als erschlossen erkennbar sein.
- **FR-015**: Die Genauigkeit der Ballereignisse MUST gegen die eigene Referenz gemessen werden (Zeitfehler,
  gefundene und erfundene Kontakte, richtiger Spieler und Körperteil).
- **FR-016**: Das System MUST je Spieler eine Textur über das ganze Spiel aus den Bildern mit der besten
  Auflösung bauen und die Rückennummer an die richtige Stelle setzen, wo sie lesbar ist.
- **FR-017**: Die Wiedererkennung der Spieler über Szenen MUST über Rückennummer und gelerntes Aussehen laufen,
  nicht über Veo.
- **FR-018**: Zweikämpfe und Fouls MUST als Ereignisse aus den Bahnen erkannt und in einer Ereignisliste je
  Szene geführt werden.
- **FR-019**: Die Haltung der Beine bei Schuss, Pass, Dribbling und Zweikampf MUST in den besten Szenen aus
  den Bildern gelesen werden; Körper dürfen sich nicht durchdringen, jede Haltung MUST möglich sein.
- **FR-020**: Fremde Bewegungsvorlagen MUST nur verwendet werden, wenn ihre Lizenz geprüft und dokumentiert
  ist.
- **FR-021**: Bilder und Bewegungsdaten Minderjähriger MUST ausschließlich lokal bleiben; nichts davon darf in
  das Repository, in Berichte außerhalb des Rechners oder an externe Dienste gelangen.
- **FR-022**: Was erschlossen und nicht gemessen ist, MUST in Daten, Bericht und Viewer erkennbar sein.

### Key Entities *(include if feature involves data)*

- **Szene (Kandidat)**: Zeitfenster eines Spiels mit Punkten und Einzelwerten (Nähe, Ballsichtbarkeit, Dauer,
  Kontakte, Zweikämpfe, Beteiligte) und Standbild.
- **Ballereignis**: Kontakt, Pass, Schuss, Ballverlust oder -gewinn mit Zeit (Bild), Spieler (Spur), Körperteil
  und Sicherheit; entweder erkannt oder aus der Referenz.
- **Ballspur**: Lage und Höhe des Balls über die Zeit, je Abschnitt als gemessen oder erschlossen gekennzeichnet.
- **Spielertextur**: Textur je Spieler über das ganze Spiel mit Herkunft (aus welchen Bildern, wie nah) und
  Nummer.
- **Spielereignis**: Zweikampf oder Foul mit Zeit, beteiligten Spielern und Art.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Für ein ganzes Spiel entsteht die Rangliste der besten Szenen ohne manuelle Zwischenschritte;
  in den besten zehn Szenen kommt in mindestens 9 ein Ballführer in der nahen Zone vor und der Ball ist in
  mindestens 80 % der Bilder gefunden.
- **SC-002**: Der Trainer markiert die Ballereignisse einer Szene von 25 Sekunden in höchstens 15 Minuten.
- **SC-003**: Bei mindestens drei markierten Szenen weicht die erkannte Kontaktzeit im Mittel um höchstens
  3 Bilder (0,1 s) von der Referenz ab; mindestens 80 % der Referenzkontakte werden gefunden, höchstens 15 %
  der erkannten Kontakte sind erfunden. Werden diese Grenzen nicht erreicht, nennt der Bericht den erreichten
  Wert und was fehlt.
- **SC-004**: Bei Flugbällen in den Nahszenen liegt die dargestellte Flughöhe im Maximum höchstens 1,0 m neben
  der Höhe, die sich aus dem Bild ergibt (Messung an markierten Beispielen).
- **SC-005**: Kein dargestellter Abschnitt ohne gefundenen Ball ist als gemessen gekennzeichnet; alle
  erschlossenen Abschnitte sind im Viewer erkennbar.
- **SC-006**: Für mindestens 80 % der Spieler eines Spiels, die im Bild zu sehen waren, entsteht eine Textur
  aus Bildern mit mindestens 90 Pixel Spielerhöhe, wo ein solches Bild vorkommt.
- **SC-007**: Der Trainer bewertet in einer Sichtprüfung von fünf Nahszenen mindestens vier als „sieht nach
  dem Video aus“ bei Ballführung und Schusstechnik.
- **SC-008**: Ohne Ausnahme liegen alle Videos, Bilder, Markierungen mit Bildbezug und Bewegungsdaten nur
  lokal.

## Assumptions

- Das erste Spiel ist das Spiel vom 2026-11-01 (Heimspiel, Panorama 2048×2048, zwei Bildhälften von 2048×1024);
  weitere Heimspiele folgen mit denselben Werkzeugen.
- Das Spielvideo wird über den bestehenden, nur lesenden Zugang zu den Veo-Aufnahmen geholt (siehe
  Projektnotizen); es werden keine Zugangsdaten gespeichert oder ausgegeben.
- Die Nähe zur Kamera wird aus dem kalibrierten Kameramodell abgeleitet. Die beste Zone liegt nach heutiger
  Rechnung rund 10 bis 25 m von der Kamera entfernt, in der Platzmitte.
- Der Szenenfinder darf zur Vorauswahl der Fenster grobe Veo-Daten (Ballposition, Pässe, Schüsse) als zweite
  Meinung benutzen, damit nicht das ganze Video geholt und ausgewertet werden muss; die endgültige Bewertung
  und alles Weitere läuft mit eigenen Messungen am geholten Videoabschnitt.
- Es werden wenige Szenen (etwa drei bis fünf) bis zur Spitzenqualität gebracht; Qualität geht vor Anzahl.
  Texturen entstehen nur für die Spieler dieser Szenen.
- Mit einer Kamera und rund 8 Pixeln Ballgröße sind nicht alle Details messbar; das System sagt, was gemessen
  und was erschlossen ist, und erreicht die Zielwerte aus Erfolgskriterium SC-003 nicht zwingend.
- Weitere Kameraperspektiven folgen später; die Ereignisse, Markierungen und Messungen sind so geschnitten, dass
  sie mit mehr Perspektiven weiter gelten.
- Die Beschränkung auf Heimspiele gilt weiter.
- Live-Betrieb ist nicht Ziel; alles läuft nachträglich und darf Stunden rechnen.
- Wenn für Bewegungen keine Fremdquelle mit passender Lizenz gefunden wird, bleibt es bei den Bewegungen aus
  den Nahaufnahmen und der vorhandenen Vorlage.
