# Contract: Spielbeschreibung und eigener Spielordner

## `spiel.json` (Eingabe, lokal unter `data/work/<aufnahme>/`)

```json
{
  "name": "U15, 2026-11-01",
  "teams": {
    "own": {"name": "Wir", "color": "#d7263d"},
    "opponent": {"name": "Gegner", "color": "#1f9d55"},
    "referee": {"name": "Schiedsrichter", "color": "#f2c200"}
  },
  "periods": [
    {"id": 1, "videoStartS": 126, "clockStartS": 0},
    {"id": 2, "videoStartS": 3434, "clockStartS": 2400}
  ]
}
```

- **Regeln**:
  - keine Personennamen;
  - Farben `#rrggbb`;
  - `periods` aufsteigend, `videoStartS` ist die Videosekunde des Anstoßes;
  - `clockStartS` ist die Spielzeit beim Anstoß (2. Halbzeit: Länge der 1. Halbzeit).
- **Fehler**: Ungültige Angaben werden mit verständlicher Meldung abgelehnt.

## Eigener Spielordner (`web/data/<spiel>/meta.json`, Ausgabe von `own_match.py`)

- Gleiches Format `matchspace-track` Version 1 wie bisher, mit drei Unterschieden:
  - **Bewegungsdaten**: keine (`frames: 0`, keine `entities` außer dem Ball, kein `tracks`-Eintrag).
  - **Platz**: Maße aus `camera.json`.
  - **Quelle**: `source.name` aus `spiel.json`.
- `periods` erhält zusätzlich `videoStartS`, wie im Veo-Basisspiel.
- `veo_ground.py` und `veo_backdrop.py` ergänzen `pitch.texture` und `pitch.backdrop` wie bisher.
- Der Viewer lädt diesen Ordner nicht als Spiel. Er ist nur die Grundlage für Szenen.
