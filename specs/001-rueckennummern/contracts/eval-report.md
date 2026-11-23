# Contract: Messbericht

Konsole und optional JSON unter `data/work/`. Nur Zahlen und IDs, keine Bilder, keine Namen.

```json
{
  "scene": "veo-szene-705-eigen",
  "teams": {
    "own":      { "visible": 9, "correct": 8, "wrong": 0, "unknown": 1 },
    "opponent": { "visible": 10, "correct": 8, "wrong": 1, "unknown": 1 }
  },
  "identitiesPerPlayer": 1.2,
  "duplicateFrames": 0,
  "readSeconds": 74.0,
  "mismatches": [ { "player": "own-15", "reference": 16, "confidence": 0.93 } ]
}
```

- `visible`: Referenzspieler mit mindestens einem gut sichtbaren Rücken (Schulter bis Hüfte ≥ 28 px, Rücken zur Kamera).
- `correct`: Der eigene Spieler mit der meisten gemeinsamen Zeit trägt die Referenznummer.
- `wrong`: trägt eine andere Nummer.
- `unknown`: trägt keine Nummer.
- `identitiesPerPlayer`: Mittel über Referenzspieler; gezählt werden eigene Spieler, die ihm mindestens 1 s
  zugeordnet sind (SC-003).
- `duplicateFrames`: Bilder, in denen zwei Spieler einer Mannschaft dieselbe Nummer tragen (SC-004).
- `mismatches`: zum Nachsehen am Video.
