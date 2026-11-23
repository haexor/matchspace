# Data Model: Eigene Referenz statt Veo

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Alle Dateien liegen lokal unter `data/work/<aufnahme>/` neben den Erkennungen und sind nicht eingecheckt. Keine
enthält Bilder oder Namen.

## Zuordnung der Auswertung (`{det}.identity.json`)

Von `own_scene.with_numbers` bei jedem Szenenlauf geschrieben. Sie hält fest, welche Erkennung zu welchem Spieler
der Szene gehört.

| Feld | Typ | Regel |
|------|-----|-------|
| `fps` | float | Bildrate der Erkennungen |
| `players` | {Name: Spieler} | Name wie im Viewer (`own-7`, `opponent-1003`) |
| Spieler.`team`, `keeper`, `number` | str, bool, int\|null | wie in der Szene |
| Spieler.`detections` | [[Bild, Linse, Box]] | zeitlich geordnet |
| `events` | [Ereignis] | Trennungen und Verbindungen aus Feature 002: `{kind: "split"\|"link", frame, players, reason}` |
| `numbers` | {Name: [[Nummer, Sicherheit]]} | beste Nummern je Spieler aus der Abstimmung, auch unsichere |
| `stamp` | str | Prüfsumme über Erkennungen und Spieler, zum Erkennen einer neuen Auswertung |

## Strittige Stelle und Kontrollstelle (`Spot`)

| Feld | Typ | Regel |
|------|-----|-------|
| `id` | str | stabil aus Bild und beteiligten Erkennungen (bleibt bei unveränderter Auswertung gleich) |
| `kind` | str | `occlusion`, `end`, `start`, `split`, `link`, `number`, `number-unsure`, `veo`, `control` |
| `frame` | int | Mitte der Stelle |
| `from`, `to` | int | Ausschnitt, 1,5 s vor bis 1,5 s nach der Stelle |
| `lens`, `crop` | int, [x, y, w, h] | Bildbereich der Linse für die Anzeige |
| `before`, `after` | [Beteiligter] | Spieler der Auswertung kurz vor und nach der Stelle |
| Beteiligter.`player`, `letter` | str, str | Name der Auswertung, Buchstabe in der Anzeige |
| Beteiligter.`anchor` | [Bild, Linse, Box] | erste bzw. letzte Erkennung am Rand der Stelle |
| Beteiligter.`boxes` | {Bild: [x1, y1, x2, y2]} | Boxen im Ausschnitt, zum Zeichnen |
| `proposal` | {Buchstabe nachher: Buchstabe vorher\|null} | Vorschlag der Auswertung |
| `priority` | float | Risiko; höhere zuerst |

## Antwort (`Answer`)

| Feld | Typ | Regel |
|------|-----|-------|
| `spot` | str | `id` der Stelle |
| `choice` | str | `proposed`, `swapped`, `mapped` (eigene Zuordnung), `unclear` |
| `mapping` | {Buchstabe nachher: Buchstabe vorher \| `other` \| `unclear`} | bei `mapped`; bei `proposed` und `swapped` abgeleitet |
| `numbers` | {Buchstabe: Nummer} | optional, lesbare Nummern |
| `anchors` | {Buchstabe: [Bild, Linse, Box, u, v]} | Kopie der Anker mit Bildlage, für das Wiederfinden |
| `at` | str | Zeitpunkt der Antwort (ISO), für die Wiederholungsprüfung |
| `repeat` | bool | zweite Antwort zur Wiederholungsprüfung (SC-004), zählt nicht für die Referenz |

## Referenz einer Szene (`{det}.reference.json`)

| Feld | Typ | Regel |
|------|-----|-------|
| `scene` | str | Szene |
| `identityStamp` | str | Stand der Zuordnung, zu dem die Stellen erzeugt wurden |
| `spots` | [Spot] | alle Stellen, auch entschiedene |
| `answers` | [Answer] | in Antwortreihenfolge; die letzte Antwort zu einer Stelle gilt |
| `seed` | int | Startwert der Kontrollstellen |

**Zustände einer Stelle**: offen → entschieden (`proposed`, `swapped`, `mapped`) oder unklar. Nach einer neuen
Auswertung: wiedergefunden (Antwort gilt weiter) oder verwaist (gemeldet, zählt als offen).

## Person (im Speicher, Messung)

Zusammenhängende Gruppe von Abschnitten der Spieler, verknüpft durch Antworten (Union-Find). Eine Person hat
Mannschaft und Nummer (vom Nutzer, sonst unbekannt) und je Erkennung eine Zugehörigkeit. Abschnitte nach „unklar“
gehören keiner Person und zählen nicht.

## Linienstelle (`LineSpot`, im Bericht)

| Feld | Typ | Regel |
|------|-----|-------|
| `frame`, `lens`, `box` | int | Erkennung |
| `line` | str | Linie des Normplatzes (`touch+`, `goalL`, `circle`, …) |
| `truth` | [x, y] | Punkt der Linie unter dem Fuß (m) |
| `errors` | {Quelle: [Tiefe, quer]} | m; Quellen `scene`, `box`, `feet`, `veo` |

## Spielbeschreibung (`spiel.json`)

| Feld | Typ | Regel |
|------|-----|-------|
| `name` | str | Anzeige, ohne Personennamen |
| `teams` | {own, opponent, referee: {name, color}} | Farben als `#rrggbb` |
| `periods` | [{id, videoStartS, clockStartS}] | Anstoß je Halbzeit in Sekunden des Videos |
