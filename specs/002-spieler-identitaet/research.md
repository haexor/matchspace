# Research: Eine Identität je Spieler über die ganze Szene

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Stand**: 2026-11-23

Messungen an den Szenen 705 und 722 (lokal, Veo nur als Referenz), Grundlage ist der Stand nach Feature 001.

## R0 Befund: Woran die Identität heute zerbricht

| Szene | Identitäten je Spieler | falsch zugeordnete Zeit | Spurwechsel ≥ 1 s | Spuren | ohne Referenz |
|---|---|---|---|---|---|
| 705 | 2,24 | 6,5 % | 7 | 38 | 7 |
| 722 | 2,17 | 5,7 % | 7 | 44 | 11 |

Die meisten Bruchstellen sind **keine Lücken, sondern Spurwechsel**: Eine Spur folgt im Gedränge erst
Spieler A, dann Spieler B. Die Stücke eines echten Spielers überlappen sich deshalb oft lange; ein Beispiel
ist die eigene 15 in Szene 705 mit 5 Stücken und bis zu 495 gemeinsamen Bildern. Echte Lücken (das Stück
endet, ein anderes beginnt) gibt es je Szene nur rund 5–8 Mal: 0–13 s lang, 1,5–25 m weit, mit 0–8
Kandidaten derselben Mannschaft in der Nähe. Daraus folgt die Spec-Ergänzung FR-011: Spurwechsel erst
trennen, dann alle Stücke verbinden.

**Ausgangsstand an der fertigen Szene** (T003, `jersey_eval.py`, Bericht `scene_S.identity-before.json`):

| Szene | Identitäten je Spieler | falsch zugeordnete Zeit | Wechsel ≥ 1 s | Tiefenversatz zu Veo |
|---|---|---|---|---|
| 705 | 2,22 | 6,9 % | 9 | +0,89 m |
| 722 | 2,11 | 5,7 % | 5 | +0,96 m |

Die fertige Szene setzt die Spieler über die Fußpunkte der Gelenkpunkte im Median rund 0,9 m weiter von der
Kamera weg als Veo (die rohen Spuren liegen 0,3 m neben Veo). Ohne Korrektur zählten dadurch Nachbarn im
Gedränge als Vertauschung: 10,3 % und 11,2 % falsche Zeit. Die Messung rechnet diesen festen Versatz deshalb
heraus. Welche Lage näher an der Wirklichkeit ist, ist eine eigene Frage der Positionsgenauigkeit und nicht
Teil dieses Features.

## R1 Aussehen: schwaches Merkmal bei 55 Pixeln

**Messung** (AUC: 0,5 = Zufall, 1 = perfekte Trennung zwischen „gleiche Person“ und „anderer Mitspieler“,
Stücke derselben Mannschaft):

| Merkmal | 705 | 722 |
|---|---|---|
| Farbe Trikot (Median Lab) | 0,45 | 0,55 |
| Farbe Hose | 0,50 | 0,67 |
| Farbe Stutzen | 0,45 | 0,55 |
| Farbe Haut (Unterarm) | 0,51 | 0,59 |
| Farbe Haare | 0,64 | 0,62 |
| Körpergröße (Schulter bis Knöchel, relativ) | 0,64 | 0,68 |
| Bildmerkmale DINOv2-small (ganze Box, gemittelt) | 0,60 | 0,70 |

- **Decision**: Das Aussehen ist kein Hauptmerkmal für Lücken über Sekunden. Es geht als schwaches,
  vorsichtig gewichtetes Merkmal in die Verbindung ein:
  - Bildmerkmale aus DINOv2-small, lokal, Apache-2.0, Gewichte unter `models/hf`, nicht eingecheckt;
  - Körpergröße.

  Bei der Erkennung von Spurwechseln vergleicht es dagegen Bilder aus derselben Sekunde (gleiches Licht,
  ähnliche Größe im Bild). Ob es dort trägt, entscheidet der erste Umsetzungsschritt mit festem Kriterium
  (R3).
- **Rationale**: Die Messung zeigt, dass Farben bei einheitlichen Trikots und 55 Pixeln Spielerhöhe kaum
  unterscheiden. Ein starkes Gewicht hätte falsche Verbindungen zur Folge (gegen SC-002).
- **Alternatives considered**:
  - Feste Farbklassen: verstößt gegen FR-010 und trennt Mitspieler nicht.
  - Spezielles Personen-Wiedererkennungsmodell (OSNet o. ä.): auf Fußgängern mit 128–256 Pixeln
    trainiert, Gewichte nur über Drittquellen; erst wenn DINOv2 bei Wechseln nicht reicht.
  - Eigenes Training eines Erkennungsmodells mit Paaren aus sicheren Spurstücken: denkbar als späteres
    Selbsttraining wie in Feature 001, aber erst nach Messung.

## R2 Laufweg und Nummer als Hauptmerkmale

- **Decision**: Für Lücken entscheiden vor allem Weg und Nummer.
  - **Erreichbarkeit**: Abstand höchstens 8 m/s × Lücke + 1,5 m Messrauschen; schon in Feature 001 so.
  - **Erwartete Lage**: Vom Ende des einen Stücks wird mit dem letzten Tempo weitergerechnet, mit einer
    Unsicherheit, die mit der Lücke wächst. Kosten ergeben sich aus dem Abstand des neuen Anfangs zur
    erwarteten Lage in Unsicherheiten.
  - **Nummer**: Verschiedene sichere Nummern verbieten eine Verbindung (FR-003). Dieselbe sichere Nummer
    senkt die Kosten stark; schon heute über `merge_by_number`.
  - **Eindeutigkeit (FR-004)**: Ein Ende wird nur mit einem Anfang verbunden, wenn dessen Kosten deutlich
    unter denen des zweitbesten Kandidaten liegen (Verhältnistest), und umgekehrt. Sonst bleiben beide
    getrennt.
- **Rationale**: Die Bruchstellen mit Lücke haben oft null oder einen Kandidaten. Dort entscheidet der
  Weg sicher, bei mehreren Kandidaten verhindert der Verhältnistest Raten.
- **Alternatives considered**: Globale Zuordnung über alle Stücke (Netzfluss mit minimalen Kosten):
  besser bei vielen gleichzeitigen Lücken, aber ohne eingebaute Vorsicht. Gierig mit Verhältnistest
  reicht für 5–8 Lücken je Szene. Ceiling als `ponytail:`-Kommentar.

## R3 Spurwechsel erkennen (FR-011)

- **Decision**: Kandidaten sind Kontaktstellen. Das sind Bilder, in denen eine Spur einer anderen Spur
  oder Erkennung derselben Mannschaft näher als 1,5 m kommt. Um jede Kontaktstelle wird verglichen, ob die
  Spur danach eher der eigenen Vergangenheit oder der des Gegenübers gleicht. Drei Belege:
  1. **Bewegung**: Verlängert man die Laufrichtung vor dem Kontakt, passt sie zum Weg danach besser als
     die vertauschte Zuordnung?
  2. **Nummer**: Vorher und nachher verschiedene sichere Lesungen (aus den Rückenlesungen von 001, je
     Teil abgestimmt).
  3. **Aussehen**: Bildmerkmale je 1 s vor und nach dem Kontakt, verglichen mit den Merkmalen des
     Gegenübers in derselben Zeit.

  Getrennt wird nur, wenn die Belege zusammen klar für einen Wechsel sprechen; im Zweifel nicht.
- **Erstes Umsetzungsziel**:
  - Zuerst die 7 bekannten Wechsel je Szene und rund 100 Kontakte ohne Wechsel auswerten, mit der
    Veo-Referenz nur zum Messen.
  - **Kriterium**: mindestens 5 von 7 Wechseln erkannt bei höchstens 1 falschen Trennung je Szene.
  - Wird das nicht erreicht, bleibt die Trennung auf Fälle mit Nummernbeleg beschränkt, und SC-002 wird
    offen als verfehlt berichtet.
- **Rationale**: Wechsel passieren fast nur bei engem Kontakt. So bleibt die Zahl der Prüfstellen klein,
  und lange ruhige Abschnitte werden nie getrennt. Bilder aus derselben Sekunde vergleichen besser als
  über eine lange Lücke (R1).
- **Alternatives considered**:
  - Bruchstellenerkennung über die ganze Merkmalsfolge (change point): bei schwachem Aussehen zu viele
    Fehlalarme.
  - Neues Tracking mit Aussehen schon bei der Zuordnung: der grundsätzlichere Weg, aber ein Umbau von
    `track_players.py`. Für später, wenn eigene Kameras höhere Auflösung liefern.

### Ergebnis des Messpunkts (T011)

Gemessen an allen Kontaktstellen (unter 1,5 m) der rohen Spuren, gegen die Wechsel laut Referenz. Ein Tausch
zweier Spuren zählt als ein Ereignis.

| Beleg | 705 (rund 7 Wechsel, 101 Kontakte) | 722 (3 Wechsel, 115 Kontakte) |
|---|---|---|
| Nummer vorher/nachher | 0 erkannt: kein Teil um einen Kontakt hat beidseits eine sichere Nummer | 0 |
| Aussehen (DINOv2, je 1 s vorher/nachher, mit Gegenüber) | Tauschwert meist um 0, nur 2 von 7 positiv | nicht trennscharf |
| Bewegung (Laufrichtung gerade gegen vertauscht) | Vorzeichen meist falsch: Die Spieler laufen beim Wechsel gemeinsam | uneinheitlich |
| **Farbe je Erkennung** (neu) | 3 erkannt, 1 Fehlalarm | 2 erkannt, 4 Fehlalarme laut Referenz |

Viele Wechsel gehen über Mannschaftsgrenzen: Eine Spur „wir“ folgt im Gedränge einem Gegner (Beispiel 705:
`own-1002` trägt ab Bild 510 gegnerische Trikots). Die Farbklasse jeder Erkennung zeigt das, obwohl die Spur
als Ganzes eine Mannschaft hat. Die „Fehlalarme“ in 722 tragen ebenfalls eindeutig das andere Trikot; die
Referenz sieht sie nicht, weil sie nur Spieler mit Veo-Nummer kennt.

- **Decision**: Kein Beleg erfüllt das Kriterium (5 von 7, höchstens 1 falsche Trennung).
  - Getrennt wird an Abschnitten fremder Trikotfarbe (ab 1 s, Farbe über 0,4 s geglättet). Eine Spur in
    fremdem Trikot folgt sicher nicht mehr ihrer Person; das ist kein schwacher Hinweis, sondern ein
    Widerspruch. Der fremde Abschnitt wird zu einem Stück der anderen Mannschaft, außer dort läuft schon eine
    Spur dieser Mannschaft (dann ist er doppelt und entfällt).
  - Dazu bleibt die Nummer: verschiedene sichere Nummern vor und nach einem Kontakt derselben Mannschaft.
  - Aussehen und Bewegung prüfen keine Wechsel. Das Aussehen bleibt beim Verbinden, wo es eine falsche
    Verbindung verhindert (722) und eine richtige ermöglicht (705).
- **Wirkung an den rohen Spuren** (vor dem Verbinden):

  | Szene | falsche Zeit | Wechsel | Identitäten |
  |---|---|---|---|
  | 705 | 6,4 % → 5,4 % | 7 → 5 | 2,17 → 2,28 |
  | 722 | 5,9 % → 2,8 % | 7 → 2 | 2,06 → 2,00 |

- **Grenze**: Wechsel zwischen zwei Spielern derselben Mannschaft ohne lesbare Nummer bleiben unerkannt. Das
  ist der größte Rest in 705. Abhilfe bringen erst schärfere Bilder (eigene Kameras, mehrere Blickwinkel),
  siehe ADR 0002.

## R4 Nummern über zusammengeführte Spieler

- **Decision**:
  - Die Rückenlesungen aller Stücke eines Spielers werden gemeinsam abgestimmt: `jersey_identity.vote` je
    Spieler statt je Spur.
  - Danach gelten `assign` (keine Nummer doppelt) und `merge_by_number` (Anker) wie bisher, nun auf
    Spielerebene.
  - Spurwechsel trennen auch die Lesungen: Jeder Teil hat nur seine eigenen Lesungen.
- **Rationale**: Heute bleiben Spieler unbekannt, weil jedes Stück für sich zu wenige Fenster hat (zum
  Beispiel die gegnerische 15 mit 46 % Einigkeit, weil die Spur zwei Personen enthält).

## R5 Ablauf, Zwischenspeicher und Module

- **Decision**:
  1. `tools/appearance.py` (neu): Bildmerkmale und Größe je Erkennung, einmaliger Videodurchlauf.
     Zwischenspeicher `{det}.appearance.npz` je Erkennung (Bild, Linse, Box), wie `{det}.numbers.npz`:
     unabhängig von der Spurbildung. Keine Bilder, nur Merkmalsvektoren (384 + 384 Zahlen). Sie
     beschreiben eine Person nur innerhalb dieser Szene und werden nicht in die Viewer-Daten übernommen.
  2. `tools/identity_link.py` (neu, reine Logik): Kontaktstellen, Wechselprüfung, Trennen, Verbinden mit
     Verhältnistest.
  3. `tools/own_scene.py`: Ablauf `own_identities` → Merkmale und Lesungen laden → Trennen → Verbinden →
     Nummern je Spieler. Die Rückgabeform bleibt `{(Mannschaft, Nummer|1000+k): (Farbe, Torwart, {Bild:
     Zeile})}`, `veo_scene.py` merkt davon nichts.
  4. `tools/jersey_eval.py`: Der Bericht zählt zusätzlich den Anteil falsch zugeordneter Spielerzeit
     (SC-002) und Spurwechsel.
- **Rationale**: Die Trennung in Videozugriff, reine Logik und Einbindung macht die Logik ohne Video
  testbar. Der Zwischenspeicher je Erkennung hat sich bei 001 bewährt.

## R6 Viewer

- **Decision**: keine Änderung nötig.
  - Ein Spieler mit mehreren Stücken ist eine Entität. Lücken bis 1 s werden überbrückt (`OWN_GAP`),
    längere blenden die Figur aus, danach kehrt sie als dieselbe zurück (FR-007).
  - Die Stichproben für SC-004 laufen über `?player=…&mode=follow` an früheren Bruchstellen.

## R7 Tests

- **Decision**: `unittest` wie in 001. Reine Logik in `identity_link.py` mit künstlichen Spuren:
  - Lücke erreichbar oder nicht; Verhältnistest bei zwei Kandidaten;
  - verschiedene Nummern verbieten; Mannschaften getrennt; Torwart getrennt;
  - Tausch zweier Spuren an einem Kontakt wird erkannt; Vorbeilaufen ohne Wechsel bleibt.

  Für `appearance.py` gibt es einen Test der Form und des Zwischenspeichers mit einem winzigen künstlichen
  Video.

## R8 Messgrößen

Gemessen mit `tools/jersey_eval.py`, Veo nur als Referenz:
- Identitäten je Referenzspieler (SC-001);
- falsch zugeordnete Zeit über alle Spieler (SC-002);
- richtige und falsche Nummern (SC-003);
- Lesezeit (SC-005).

SC-004 wird am Viewer stichprobenartig geprüft (10 frühere Bruchstellen je Szene).

## R9 Ergebnis (T015–T018)

An der fertigen Szene, `jersey_eval.py`, Tiefenversatz herausgerechnet:

| Szene | falsch zugeordnete Zeit | Wechsel ≥ 1 s | Identitäten je Spieler | Nummern |
|---|---|---|---|---|
| 705 | 6,9 % → 5,8 % | 9 → 7 | 2,22 → 2,22 | 7, keine falsch |
| 722 | 5,7 % → 2,9 % | 5 → 1 | 2,11 → 2,22 | 7, keine falsch |

| Ziel | Stand |
|---|---|
| SC-001 Identitäten ≤ 1,5 | verfehlt: 2,22 in beiden Szenen |
| SC-002 falsche Zeit ≤ 3 % | 722 erreicht (2,9 %), 705 verfehlt (5,8 %) |
| SC-003 ≥ 7 richtige Nummern, ≤ 5 % falsch | erreicht: je 7, keine falsch |
| SC-004 8 von 10 Stichproben | verfehlt: 705 rund 5–6, 722 4 von 10 |
| SC-005 ≤ 5 min mehr | erreicht: rund 30 s, beim ersten Lauf dazu 55 s Bildmerkmale |
| SC-006 keine neuen Bilddaten | erreicht |

- **Stichproben (SC-004)**: Je Szene 10 frühere Bruchstellen der rohen Spuren, Bildausschnitte des Spielers 1 s
  vorher und nachher, am Video angesehen. In 705 sicher gleich bei 4, plausibel bei 2, verloren bei 2, fraglich
  bei 2. In 722 gleich bei 4, bei 6 endet die Figur. Ein Sprung auf eine falsche Person war nicht dabei.
- **Warum die Identitäten nicht sinken**: Das Trennen an fremden Trikots macht aus 38 und 44 Spuren 40 und 51
  Spieler. Verbunden werden nur 2 und 0 Lücken, weil der zweitbeste Kandidat fast immer nah dran ist. Das ist
  die gewollte Vorsicht (SC-002 vor SC-001), bei 55 Pixeln Spielerhöhe aber zu wenig Unterscheidung.
- **Nächste Hebel**:
  - eigene Kameras (Auflösung, mehrere Blickwinkel), siehe ADR 0002;
  - das Aussehen schon beim Tracking nutzen;
  - Selbsttraining eines Wiedererkennungsmerkmals an sicheren Stücken (wie beim Nummernleser).
