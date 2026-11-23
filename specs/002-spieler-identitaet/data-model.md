# Data Model: Eine Identität je Spieler

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Spurstück (`Piece`)

Ein Teil einer Spur zwischen zwei Trennstellen. Ohne Trennung ist es die ganze Spur.

| Feld | Typ | Regel |
|------|-----|-------|
| `id` | str | `{Spur}` oder `{Spur}/{k}` nach Trennung |
| `team` | str | `own`, `opponent`, `referee` |
| `keeper` | bool | Torwart (eigene Gruppe, FR-006) |
| `frames` | {Bild: Zeile} | Zeile wie aus `track_players` (Lage x, y; Linse; Box) |

## Merkmale je Erkennung (Zwischenspeicher, `{det}.appearance.npz`)

| Feld | Typ | Regel |
|------|-----|-------|
| `frame`, `lens`, `box` | int | Schlüssel wie im Nummern-Zwischenspeicher |
| `embedding` | float16[R, 768] | Bildmerkmale der Box, Länge 1; keine Bilder |
| `height` | float32[R] | Schulter bis Knöchel in Pixeln, NaN wenn unsicher |
| `stamp` | float64[4] | mtime Video, Detektionen, Modell; Format-Version |

## Aussehen je Stück (`Look`, im Speicher)

| Feld | Typ | Regel |
|------|-----|-------|
| `mean` | float[768] | gemittelte Merkmale, Länge 1 |
| `count` | int | Zahl der Erkennungen; unter 8 gilt das Aussehen als unsicher und zählt nicht |
| `height_m` | float | Körpergröße am Boden (Median) |

## Kontakt und Wechsel (`Contact`)

| Feld | Typ | Regel |
|------|-----|-------|
| `a`, `b` | str | zwei Stücke derselben Mannschaft |
| `frame` | int | Bild des geringsten Abstands (< 1,5 m) |
| `motion`, `number`, `look` | float | Belege für einen Tausch (> 0) oder dagegen (< 0) |
| `swap` | bool | nur wahr, wenn die Belege zusammen klar sind |

Bei `swap` werden beide Stücke an `frame` getrennt. Läuft nur eine Spur in eine fremde Person (die andere
endet), wird nur sie getrennt.

## Verbindung (`Link`)

| Feld | Typ | Regel |
|------|-----|-------|
| `end`, `start` | str | Ende des einen und Anfang des anderen Stücks |
| `cost` | float | Weg (Abstand zur erwarteten Lage in Unsicherheiten) + Aussehen + Größe − Nummernbonus |
| `margin` | float | Kosten des zweitbesten Kandidaten ÷ eigene Kosten; verbunden wird nur ab 2 |

**Verbote** (FR-003, FR-006):
- gleichzeitig länger als 0,5 s zu sehen;
- andere Mannschaft;
- Torwart mit Feldspieler;
- verschiedene sichere Nummern;
- unerreichbar.

## Spieler (`Player`, wie in Feature 001)

Ein oder mehrere verbundene Stücke. Die Nummer wird über die Lesungen aller Stücke abgestimmt. Die
Invarianten aus 001 bleiben: keine Nummer doppelt zur selben Zeit, und Schiedsrichter ohne Nummer.
