# Contract: Messbericht (Erweiterung von Feature 001)

Neue Felder neben denen aus `specs/001-rueckennummern/contracts/eval-report.md`:

```json
{
  "wrongTimeShare": 0.024,
  "switches": 2,
  "depthOffsetM": 0.88
}
```

- `wrongTimeShare`: Anteil der zugeordneten Spieler-Bilder, deren Referenz nicht die Hauptperson des
  Spielers ist, über alle Spieler der Szene (SC-002).
- `switches`: Wechsel der Referenzperson innerhalb eines Spielers, die mindestens 1 s anhalten.
- `depthOffsetM`: fester Versatz der Szene gegenüber der Referenz in Blickrichtung der Kamera (Median, positiv:
  weiter weg). Er wird vor dem Abgleich herausgerechnet, weil gemessen wird, ob ein Spieler derselben Person
  folgt, nicht wie genau seine Lage ist. Ohne diese Korrektur zählten Nachbarn im Gedränge als Vertauschung
  (705: 10,3 % statt 6,9 % falsche Zeit). Ob die Szene oder die Referenz näher an der echten Lage ist, bleibt
  offen; das ist eine eigene Frage der Positionsgenauigkeit.
