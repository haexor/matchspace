# Contract: Messbericht (Erweiterung von Feature 001)

Neue Felder neben denen aus `specs/001-rueckennummern/contracts/eval-report.md`:

```json
{
  "wrongTimeShare": 0.024,
  "switches": 2
}
```

- `wrongTimeShare`: Anteil der zugeordneten Spieler-Bilder, deren Referenz nicht die Hauptperson des
  Spielers ist, über alle Spieler der Szene (SC-002).
- `switches`: Wechsel der Referenzperson innerhalb eines Spielers, die mindestens 1 s anhalten.
