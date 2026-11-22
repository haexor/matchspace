# Contract: Spieler-Entitäten in `meta.json` (Viewer)

Gilt für Szenen ohne Veo (`veo_scene.py` mit `-`). Szenen mit Veo bleiben unverändert.

```json
{ "id": "own-15",   "kind": "player", "team": "own",      "number": 15 }
{ "id": "own-1004", "kind": "player", "team": "own",      "label": "S4" }
{ "id": "own-1001", "kind": "player", "team": "own",      "label": "TW" }
{ "id": "referee-1001", "kind": "player", "team": "referee", "label": "S1" }
```

- **Nummer bekannt**: `number` (1–99), kein `label`. ID `{team}-{number}`.
- **Nummer unbekannt**: kein `number`, `label` ist der Spurname (`S…`, Torwart `TW`). ID `{team}-{1000+k}`.
  Die Bereiche überschneiden sich nicht.
- **Keine Bilddaten**: Es gibt keine Felder mit Bilddaten oder Ausschnitten (FR-009, SC-006).

## Anzeige im Viewer (FR-007)

| Stelle | Nummer bekannt | Nummer unbekannt |
|--------|----------------|------------------|
| Trikot (Rücken) | Nummer | keine Nummer |
| Schild über dem Kopf | Nummer | `?` |
| Spielerauswahl | `Wir 15` | `Wir ? (S4)` |

Das Feld `poses`, die Sidecars und `looks` verwenden dieselben IDs. `looks.png` wird nach der Auswertung neu
erzeugt (tools/veo_looks.py), damit die IDs passen.
