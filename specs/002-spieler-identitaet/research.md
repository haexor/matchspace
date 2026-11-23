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
