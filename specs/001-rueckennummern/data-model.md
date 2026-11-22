# Data Model: Rückennummern aus dem Video

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Datenformen in Python sind kleine `dataclass`-Typen; über Dateigrenzen gehen sie als `.npz` oder JSON
(siehe [contracts/](contracts/)).

## Spielerspur (vorhanden)

Eine Spur kommt aus `tools/track_players.py` und wird in `own_identities` gefiltert (Stand heute).

| Feld | Typ | Bedeutung |
|------|-----|-----------|
| `id` | str | `own-1003`, `opponent-1012`, `referee-1001` |
| `team` | `own` \| `opponent` \| `referee` | aus der Trikotfarbe |
| `frames` | int-Bereich | erstes und letztes Bild der Szene |
| `pos` | float[T, 2] | Lage am Boden in Metern je Bild, NaN wenn nicht gesehen |
| `kp`, `lens` | float[T, 17, 3], float[T] | Gelenkpunkte und Linse je Bild (Sidecar `players_own.npz`) |

## Ausschnitt (`BackCrop`, nur im Speicher)

| Feld | Typ | Regel |
|------|-----|-------|
| `track` | str | Spur-ID |
| `frame` | int | Bild der Szene |
| `height_px` | float | Abstand Schulter- zu Hüftmitte; ≥ 24 px, sonst kein Ausschnitt |
| `pixels` | uint8[32, 40] | entzerrter Graustufenausschnitt |

Ausschnitte werden nie gespeichert. Ausnahme ist ein ausdrücklicher Prüfschalter: Dann gehen sie nach
`data/work/…/crops_numbers/`, also nicht eingecheckt und nicht in `web/data` (FR-009, SC-006).

## Nummernlesung (`Reading`)

| Feld | Typ | Regel |
|------|-----|-------|
| `track` | str | Spur-ID |
| `frame` | int | Bild der Szene |
| `probs` | float[100] | Index 0 = keine Nummer, Index n = Nummer n; Summe 1 |
| `weight` | float | 0,3 bis 1, aus `height_px` (R4) |

Gespeichert als `{det}.numbers.npz` (siehe [contracts/numbers-cache.md](contracts/numbers-cache.md)).

## Spurnummer (`TrackNumber`, Zwischenergebnis der Abstimmung)

| Feld | Typ | Regel |
|------|-----|-------|
| `track` | str | Spur-ID |
| `ranked` | list[(int, float)] | Nummern mit normierter Sicherheit, absteigend, nach Kaderfilter |
| `windows` | int | Zeitfenster (0,4 s) mit zählender Lesung |
| `span_s` | float | Abstand des ersten zum letzten zählenden Fenster |

Eine Nummer gilt als **gestützt**, wenn alle drei Bedingungen gelten:
- Sicherheit ≥ 0,9;
- `windows` ≥ 3;
- `span_s` ≥ 1.

## Spieler (`Player`)

| Feld | Typ | Regel |
|------|-----|-------|
| `id` | str | ID der ersten Spur des Spielers (stabil, wenn sich nur Nummern ändern) |
| `team` | str | wie die Spuren |
| `tracks` | list[str] | Spurstücke, zeitlich ohne Überlappung |
| `number` | int \| None | 1–99 oder unbekannt |
| `confidence` | float | Sicherheit der Nummer, 0 bei unbekannt |

**Invarianten** (geprüft in Tests):
- Innerhalb einer Mannschaft tragen zwei Spieler, die gleichzeitig zu sehen sind, nie dieselbe Nummer
  (FR-004, SC-004).
- Ein Spieler mit mehreren Spurstücken hat eine Nummer. Ohne Nummer wird nichts zusammengeführt (FR-005).
- `referee` hat immer `number = None` (FR-006).
- Steht eine Nummer nicht im angegebenen Kader, wird sie nie vergeben (FR-012).

**Übergänge**:

```text
Spur ──Lesungen──▶ TrackNumber ──gestützt?──▶ Kandidat ──Vergabe ohne Doppel──▶ Spieler(number)
                                   └─nein──▶ Spieler(number=None)
Spieler gleicher Mannschaft + Nummer, ohne Überlappung, Lücke ≤ 8 m/s ──▶ ein Spieler
```

## Kader (optional)

`{"own": [int], "opponent": [int]}`, Nummern 1–99, siehe [contracts/squad-list.md](contracts/squad-list.md).

## Referenzliste und Messbericht (nur Messung)

Die Referenz wird zur Laufzeit aus Veo-Daten gebildet und nie gespeichert: Veo-Spieler mit Nummer und
Positionen. Der Bericht steht in [contracts/eval-report.md](contracts/eval-report.md).
