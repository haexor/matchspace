# Contract: Messbericht (ersetzt die Veo-Wahrheit aus Feature 001 und 002)

```json
{
  "scene": "scene_705",
  "reference": {
    "spots": 42, "decided": 40, "unclear": 3, "open": 2, "orphaned": 0,
    "control": {"spots": 5, "errorsFound": 0, "missedRateEstimate": 0.0}
  },
  "own": {
    "teams": {"own": {"persons": 12, "correct": 3, "wrong": 0, "unknown": 9},
              "opponent": {"persons": 13, "correct": 2, "wrong": 0, "unknown": 11}},
    "identitiesPerPerson": 2.1,
    "wrongTimeShare": 0.05,
    "switches": 6,
    "playersWithNumber": 7,
    "wrongPlayers": []
  },
  "veo": {
    "identitiesPerPerson": 2.2, "wrongTimeShare": 0.07, "switches": 9,
    "disagreements": [{"frame": 412, "player": "own-1002", "reference": "Wir C", "veo": ["opponent", 5]}]
  },
  "duplicateFrames": 0,
  "readSeconds": null,
  "lines": {
    "spots": 64,
    "sources": {"scene": {"depthMedian": 0.85, "depthIqr": 0.4, "acrossMedian": 0.05},
                "box": {"depthMedian": 0.02, "depthIqr": 0.3, "acrossMedian": 0.03},
                "feet": {"depthMedian": 0.01, "depthIqr": 0.25, "acrossMedian": 0.02},
                "veo": {"depthMedian": -0.05, "depthIqr": 0.5, "acrossMedian": 0.1}}
  }
}
```

Alle Werte oben sind Beispiele. Gezählt wird so:

- **`own`**: gegen die eigene Referenz, je Erkennung.
  - `persons`: Personen der Referenz je Mannschaft, die mindestens 1 s zu sehen sind.
  - `correct`, `wrong`, `unknown`: Nummernvergleich, nur für Personen mit vom Nutzer angegebener Nummer;
    `unknown` heißt, der Spieler trägt keine Nummer.
  - `identitiesPerPerson`, `wrongTimeShare`, `switches`: wie in Feature 002, aber gegen Personen der Referenz.
- **`veo`**: dieselben Kennzahlen gegen Veo (Abgleich über die rohen Bodenpunkte, ohne Versatz), dazu die
  Stellen, an denen Veo und die Referenz verschiedene Personen sehen. Fehlt, wenn ohne `--veo` gemessen wird.
- **`reference.control.missedRateEstimate`**: Anteil der Kontrollstellen mit Fehler, als Schätzung für Fehler
  außerhalb der strittigen Stellen.
- **`lines`**: nur von `line_check.py`.
  - Fehler in Metern: Tiefe positiv heißt weiter von der Kamera weg als die Linie.
  - `depthIqr`: Abstand zwischen 25. und 75. Perzentil.
- **Entfällt gegenüber Feature 002**: `depthOffsetM`. Es gibt keinen pauschal herausgerechneten Versatz mehr.
